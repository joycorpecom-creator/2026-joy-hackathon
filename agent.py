"""BurgerMockup Agent — LLM-driven tool-calling with session memory.

Replaces action_router + gemini_llm with a Hermes-style agent:
  - LLM reasons about user intent
  - LLM picks tools ↔ we execute ↔ LLM formats final response
  - Per-chat conversation history (last 20 turns)
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from config_store import load_settings
from burgerprints import BurgerPrintsClient
from mockup_engine import generate_mockup, generate_product_mockup, generate_uploaded_design_product_mockup

ROOT = Path(__file__).parent
MEMORY_DIR = ROOT / "memory"
MAX_HISTORY = 20  # turns per session

# ─── Tool definitions (Gemini function declarations) ────────────────────────

TOOL_DECLARATIONS = types.Tool(
    function_declarations=[
        # ── Account ──
        types.FunctionDeclaration(
            name="bp_authenticated",
            description="Kiểm tra kết nối BurgerPrints API. Trả về true nếu API key hợp lệ.",
            parameters={"type": "object", "properties": {}, "required": []},
        ),
        types.FunctionDeclaration(
            name="bp_balance",
            description="Xem số dư tài khoản BurgerPrints.",
            parameters={"type": "object", "properties": {}, "required": []},
        ),
        # ── Product / Catalog ──
        types.FunctionDeclaration(
            name="bp_get_product",
            description="Lấy chi tiết sản phẩm theo short_code. Short_code có dạng USG5000, USNL3900, EUAPHS...",
            parameters={
                "type": "object",
                "properties": {"short_code": {"type": "string", "description": "Mã sản phẩm BP, VD USG5000"}},
                "required": ["short_code"],
            },
        ),
        types.FunctionDeclaration(
            name="bp_search_products",
            description="Tìm sản phẩm trong catalog theo từ khóa (tên, mã số). Dùng khi user gõ tên như 'Gildan 5000', 'Next Level 3900', 'Lady T-Shirt'.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Từ khóa tìm kiếm"}},
                "required": ["query"],
            },
        ),
        types.FunctionDeclaration(
            name="bp_out_of_stock",
            description="Liệt kê sản phẩm đang hết hàng.",
            parameters={"type": "object", "properties": {}, "required": []},
        ),
        # ── Orders ──
        types.FunctionDeclaration(
            name="bp_get_order",
            description="Lấy thông tin đơn hàng theo ID. Hỗ trợ cả internal ID (Axxx-CT-xxx) và seller reference (BP-xxx, ORD-xxx).",
            parameters={
                "type": "object",
                "properties": {"order_id": {"type": "string", "description": "Mã đơn hàng"}},
                "required": ["order_id"],
            },
        ),
        types.FunctionDeclaration(
            name="bp_list_orders",
            description="Liệt kê danh sách đơn hàng gần đây.",
            parameters={"type": "object", "properties": {}, "required": []},
        ),
        types.FunctionDeclaration(
            name="bp_tracking",
            description="Theo dõi vận đơn của đơn hàng.",
            parameters={
                "type": "object",
                "properties": {"order_id": {"type": "string", "description": "Mã đơn hàng"}},
                "required": ["order_id"],
            },
        ),
        types.FunctionDeclaration(
            name="bp_cancel_order",
            description="Hủy đơn hàng. CẦN XÁC NHẬN từ user trước khi thực hiện.",
            parameters={
                "type": "object",
                "properties": {"order_id": {"type": "string", "description": "Mã đơn hàng cần hủy"}},
                "required": ["order_id"],
            },
        ),
        # ── Mockup ──
        types.FunctionDeclaration(
            name="create_mockup_from_order",
            description="Tạo lifestyle mockup từ đơn hàng có sẵn. Dùng khi user có order ID + mô tả scene.",
            parameters={
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Mã đơn hàng, VD DEMO-1001 hoặc BP-xxx"},
                    "scene": {"type": "string", "description": "Mô tả scene: cafe, streetwear, outdoor... Có thể tiếng Việt hoặc Anh."},
                },
                "required": ["order_id", "scene"],
            },
        ),
        types.FunctionDeclaration(
            name="create_mockup_from_product",
            description="Tạo lifestyle mockup từ sản phẩm trong catalog (không cần đơn hàng). Dùng khi user nói 'tạo mockup Gildan 5000 cafe'.",
            parameters={
                "type": "object",
                "properties": {
                    "short_code": {"type": "string", "description": "Mã sản phẩm BP, có được từ bp_get_product hoặc bp_search_products"},
                    "scene": {"type": "string", "description": "Mô tả scene: cafe, streetwear, outdoor..."},
                },
                "required": ["short_code", "scene"],
            },
        ),
        types.FunctionDeclaration(
            name="create_mockup_from_uploaded_design",
            description="Tạo lifestyle mockup từ file in user đã upload + sản phẩm BP catalog. Dùng khi session hiện tại đã có design file.",
            parameters={
                "type": "object",
                "properties": {
                    "short_code": {"type": "string", "description": "Mã sản phẩm BP, VD USG5000"},
                    "scene": {"type": "string", "description": "Bối cảnh/mood/style, VD đường phố New York"},
                },
                "required": ["short_code", "scene"],
            },
        ),
    ]
)

# ═══════════════════════════════════════════════════════════════════════════
# Agent
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """Bạn là J_agent, trợ lý BurgerMockup AI cho người bán BurgerPrints.
Nhiệm vụ: phân tích yêu cầu người dùng → chọn công cụ phù hợp → trả kết quả.

LUẬT:
- LUÔN xưng hô "Dạ" mở đầu mỗi câu trả lời, gọi user là "anh".
- Trả lời NGẮN GỌN, thân thiện, kiểu tin nhắn chat.
- Khi user hỏi về sản phẩm (tên như "Gildan 5000", "Next Level 3900", "Lady T-Shirt"):
  → GỌI bp_search_products TRƯỚC để tìm short_code chính xác.
- Khi user muốn tạo mockup + nói cả tên sản phẩm lẫn scene:
  → GỌI bp_search_products để lấy short_code → SAU ĐÓ gọi create_mockup_from_product.
- KHI SESSION CÓ DESIGN FILE (user đã upload): ưu tiên gọi create_mockup_from_uploaded_design thay vì create_mockup_from_product.
- Khi user chỉ đưa order ID + scene: gọi create_mockup_from_order luôn.
- Khi user hỏi "số dư", "balance": gọi bp_balance.
- Khi user hỏi "test api", "api ok": gọi bp_authenticated.
- Khi user hỏi "order X": gọi bp_get_order(X).
- Khi user hỏi "tracking X": gọi bp_tracking(X).
- Nếu không chắc chắn công cụ nào → hỏi lại user 1 câu.
- KHÔNG bịa kết quả. Chỉ dùng dữ liệu từ tool trả về.
- Trả lời bằng tiếng Việt.
- Khi trả kết quả sản phẩm, dùng format tự nhiên: "Dạ anh, đây là sản phẩm em tìm được:" rồi liệt kê thông số ngắn gọn.
- Khi trả kết quả mockup, dùng format: "Dạ anh, đây là mockup..." kèm scene, kích thước, thời gian, chi phí/provider nếu có.
"""


class BurgerMockupAgent:
    """LLM agent with BurgerPrints tools + session memory."""

    def __init__(self):
        self.settings = load_settings()
        self.bp = BurgerPrintsClient()
        self.llm_key = self.settings.get("llm_api_key", "").strip()
        self.model = self.settings.get("llm_model", "gemini-3-flash-preview")
        self._client: Optional[genai.Client] = None
        # Per-chat session memory: {chat_id: [Content, ...]}
        self.sessions: Dict[str, List[types.Content]] = {}
        self._current_chat_id = "web"
        self._load_sessions()

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            if not self.llm_key or "..." in self.llm_key:
                raise RuntimeError("Gemini API key chưa được cấu hình.")
            self._client = genai.Client(api_key=self.llm_key)
        return self._client

    # ── Session memory ──────────────────────────────────────────────────

    def _session_path(self, chat_id: str) -> Path:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        return MEMORY_DIR / f"session_{chat_id}.json"

    def _load_sessions(self):
        if MEMORY_DIR.exists():
            for f in sorted(MEMORY_DIR.glob("session_*.json")):
                try:
                    data = json.loads(f.read_text())
                    cid = f.stem.replace("session_", "")
                    self.sessions[cid] = [
                        types.Content.model_validate(c) for c in data
                    ]
                except Exception:
                    pass

    def _save_session(self, chat_id: str):
        path = self._session_path(chat_id)
        data = [c.model_dump() for c in self.sessions.get(chat_id, [])]
        path.write_text(json.dumps(data, ensure_ascii=False, default=str))

    def _get_history(self, chat_id: str) -> List[types.Content]:
        if chat_id not in self.sessions:
            self.sessions[chat_id] = [
                types.Content(role="user", parts=[types.Part.from_text(text=SYSTEM_PROMPT)]),
                types.Content(role="model", parts=[types.Part.from_text(text="Dạ, J_agent sẵn sàng!")]),
            ]
        hist = self.sessions[chat_id]
        # Keep within max history
        if len(hist) > MAX_HISTORY * 2 + 2:
            hist = hist[:2] + hist[-(MAX_HISTORY * 2):]
            self.sessions[chat_id] = hist
        return hist

    # ── Tool execution ──────────────────────────────────────────────────

    def _execute_tool(self, name: str, args: Dict[str, Any]) -> Any:
        """Execute a tool and return the result as a JSON-serializable dict."""
        try:
            if name == "bp_authenticated":
                r = self.bp.authenticated()
                ok = r.get("data", {}).get("is_success", False)
                return {"connected": ok, "message": "OK" if ok else "API key không hợp lệ"}

            if name == "bp_balance":
                r = self.bp.balance()
                return {"balance": r}

            if name == "bp_get_product":
                sc = args.get("short_code", "")
                try:
                    r = self.bp.product(sc)
                except Exception:
                    # Fuzzy fallback
                    from action_router import _fuzzy_find_product
                    resolved = _fuzzy_find_product(sc, self.bp)
                    if resolved:
                        r = self.bp.product(resolved)
                    else:
                        return {"error": f"Không tìm thấy sản phẩm '{sc}'"}
                d = r.get("data", r)
                return {
                    "short_code": d.get("short_code", sc),
                    "name": d.get("display_name") or d.get("name", "?"),
                    "image_url": d.get("url") or d.get("image") or "",
                }

            if name == "bp_search_products":
                q = args.get("query", "")
                from action_router import _fuzzy_find_product, _get_product_cache
                resolved = _fuzzy_find_product(q, self.bp)
                if resolved:
                    r = self.bp.product(resolved)
                    d = r.get("data", r)
                    return {
                        "found": True,
                        "short_code": resolved,
                        "name": d.get("display_name") or d.get("name", ""),
                        "image_url": d.get("url") or "",
                    }
                # Broader search via API
                r = self.bp.products(page_size=10, search=q)
                rows = (r.get("data", {}) or {}).get("result", [])
                matches = []
                for p in rows[:5]:
                    matches.append({
                        "short_code": p.get("short_code"),
                        "name": p.get("display_name") or p.get("name"),
                    })
                return {"found": len(matches) > 0, "products": matches, "total": len(rows)}

            if name == "bp_out_of_stock":
                r = self.bp.out_of_stock()
                rows = (r.get("data", {}) or {}).get("result", [])
                return {"count": len(rows), "items": rows[:10]}

            if name == "bp_get_order":
                oid = args.get("order_id", "")
                try:
                    r = self.bp.get_order(oid)
                except Exception as e:
                    return {"error": str(e)}
                state = r.get("state") or r.get("status", "?")
                items = r.get("items") or []
                item_names = [i.get("name") or i.get("catalog_sku", "item") for i in items[:5]]
                return {
                    "order_id": r.get("id", oid),
                    "state": state,
                    "amount": r.get("amount") or r.get("total", "?"),
                    "items": item_names,
                }

            if name == "bp_list_orders":
                r = self.bp.list_orders(page_size=5)
                rows = self.bp._rows(r)
                orders = []
                for o in rows[:5]:
                    orders.append({
                        "id": o.get("id"), "state": o.get("state") or o.get("status"),
                        "amount": o.get("amount") or o.get("total"),
                    })
                return {"orders": orders, "count": len(orders)}

            if name == "bp_tracking":
                oid = args.get("order_id", "")
                try:
                    r = self.bp.tracking(oid)
                except Exception as e:
                    return {"error": str(e)}
                return {"tracking": str(r)}

            if name == "bp_cancel_order":
                oid = args.get("order_id", "")
                return {"warning": f"Hủy đơn {oid} là hành động không thể hoàn tác. Cần xác nhận CONFIRM CANCEL {oid}."}

            if name == "create_mockup_from_order":
                oid = args.get("order_id", "")
                scene = args.get("scene", "")
                t0 = time.time()
                asset = self.bp.extract_first_asset(oid)
                result = generate_mockup(asset, scene)
                elapsed = round(time.time() - t0, 2)
                return {
                    "mockup_url": f"/outputs/{result['path'].split('/')[-1]}",
                    "provider": result["provider"],
                    "size": f"{result['width']}×{result['height']}",
                    "integrity": result["integrity_score"],
                    "time": f"{elapsed}s",
                    "cost": f"${result['cost_usd']}",
                    "product": asset.product_name,
                    "color": asset.color_name,
                }

            if name == "create_mockup_from_product":
                sc = args.get("short_code", "")
                scene = args.get("scene", "")
                try:
                    r = self.bp.product(sc)
                except Exception:
                    from action_router import _fuzzy_find_product
                    resolved = _fuzzy_find_product(sc, self.bp)
                    if resolved:
                        sc = resolved
                        r = self.bp.product(sc)
                    else:
                        return {"error": f"Không tìm thấy sản phẩm '{sc}'"}
                d = r.get("data", r)
                pname = d.get("display_name") or d.get("name", sc)
                pcolor = d.get("color_name") or d.get("color") or "as shown in the attached BP product image"
                base_url = d.get("url") or d.get("image") or ""
                t0 = time.time()
                result = generate_product_mockup(sc, pname, pcolor, base_url, scene)
                elapsed = round(time.time() - t0, 2)
                # ── imgbb → n8n sync ──
                # Gemini returns local bytes/path. Upload to imgbb first so n8n can download a public HTTPS URL.
                from imgbb_uploader import upload_image
                from sync_webhook import build_mockup_payload, post_mockup_created
                local_path = result.get("path", "")
                imgbb_result = upload_image(local_path) if local_path else {"ok": False, "error": "missing local path"}
                public_img_url = imgbb_result.get("url") or imgbb_result.get("display_url") or ""
                sync_payload = build_mockup_payload(
                    result=result,
                    product_id=sc,
                    product_name=pname,
                    color=pcolor,
                    scene=scene,
                    raw_user_input=scene,
                    public_base_url=self.settings.get("public_base_url", ""),
                )
                if public_img_url:
                    sync_payload["assets"]["image_url"] = public_img_url
                    sync_payload["assets"]["imgbb_url"] = public_img_url
                    sync_payload["assets"]["imgbb_delete_url"] = imgbb_result.get("delete_url", "")
                # Upload local file to Lark media here (Python requests works). n8n only creates record + appends token.
                try:
                    from lark_media_sync import _load_config, _get_tenant_token, _upload_to_base_media
                    lcfg = _load_config()
                    ltoken = _get_tenant_token(lcfg["app_id"], lcfg["app_secret"], lcfg["lark_base_url"])
                    media = _upload_to_base_media(local_path, lcfg["base_token"], ltoken, lcfg["lark_base_url"], result.get("filename") or Path(local_path).name)
                    if media.get("file_token"):
                        sync_payload["assets"]["lark_file_token"] = media["file_token"]
                except Exception as e:
                    sync_payload["assets"]["lark_media_error"] = str(e)
                sync_result = post_mockup_created(sync_payload, self.settings)
                sync_info = {
                    "sync_status": sync_result.get("status", "skipped"),
                    "sync_record_id": sync_result.get("record_id", ""),
                    "sync_image_url": public_img_url,
                }
                if imgbb_result.get("error"):
                    sync_info["imgbb_error"] = str(imgbb_result["error"])
                if sync_result.get("error"):
                    sync_info["sync_error"] = str(sync_result["error"])

                return {
                    "mockup_url": f"/outputs/{result['path'].split('/')[-1]}",
                    "provider": result["provider"],
                    "size": f"{result['width']}×{result['height']}",
                    "integrity": result["integrity_score"],
                    "time": f"{elapsed}s",
                    "cost": f"${result['cost_usd']}",
                    "product": f"{sc} — {pname}",
                    "color": pcolor,
                    **sync_info,
                }

            if name == "create_mockup_from_uploaded_design":
                sc = args.get("short_code", "")
                scene = args.get("scene", "")
                from design_store import get_current_design
                chat_id = self._current_chat_id
                design = get_current_design(chat_id)
                if not design:
                    return {"error": "Chưa có file in nào trong session. Anh upload file PNG/JPG/SVG trước nha."}
                design_path = design.get("normalized_path") or design.get("source_path")
                if not design_path or not Path(design_path).exists():
                    return {"error": "File in không tìm thấy trên server, upload lại giúp anh."}
                # Resolve product
                try:
                    r = self.bp.product(sc)
                except Exception:
                    from action_router import _fuzzy_find_product
                    resolved = _fuzzy_find_product(sc, self.bp)
                    if resolved:
                        sc = resolved
                        r = self.bp.product(sc)
                    else:
                        return {"error": f"Không tìm thấy sản phẩm '{sc}'"}
                d = r.get("data", r)
                pname = d.get("display_name") or d.get("name", sc)
                pcolor = d.get("color_name") or d.get("color") or ""
                t0 = time.time()
                result = generate_uploaded_design_product_mockup(
                    design_path=design_path,
                    product=d,
                    scene_prompt=scene,
                    short_code=sc,
                    product_name=pname,
                    color_name=pcolor,
                )
                elapsed = round(time.time() - t0, 2)
                return {
                    "mockup_url": f"/outputs/{result['path'].split('/')[-1]}",
                    "provider": result["provider"],
                    "size": f"{result['width']}×{result['height']}",
                    "integrity": result["integrity_score"],
                    "time": f"{elapsed}s",
                    "cost": f"${result['cost_usd']}",
                    "product": f"{sc} — {pname}",
                    "color": pcolor,
                    "design_id": design["design_id"],
                }

            return {"error": f"Unknown tool: {name}"}

        except Exception as e:
            return {"error": str(e)}

    # ── Agentic chat loop ────────────────────────────────────────────────

    def chat(self, chat_id: str, message: str) -> Dict[str, Any]:
        """Process one user message through the agentic loop.

        Returns: {"type": "text"|"mockup"|"product"|"error", "content": ..., ...}
        """
        if not self.llm_key or "..." in self.llm_key:
            return {"type": "text", "content": "Dạ, Gemini API key chưa được cấu hình anh ơi."}

        self._current_chat_id = str(chat_id)
        history = self._get_history(chat_id)

        # Create a copy for this turn's tool-calling loop
        turn_history = list(history)
        turn_history.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))

        max_rounds = 5
        for _round in range(max_rounds):
            try:
                resp = self.client.models.generate_content(
                    model=self.model,
                    contents=turn_history,
                    config=types.GenerateContentConfig(
                        tools=[TOOL_DECLARATIONS],
                        temperature=0.3,
                        max_output_tokens=2000,
                    ),
                )
            except Exception as e:
                return {"type": "error", "content": f"LLM error: {e}"}

            if not resp.candidates:
                return {"type": "text", "content": "Dạ, em chưa phản hồi được."}

            candidate = resp.candidates[0]
            if not candidate.content or not candidate.content.parts:
                return {"type": "text", "content": "Dạ, em không xử lý được."}

            text_parts = []
            func_calls = []

            for part in candidate.content.parts:
                if part.function_call:
                    func_calls.append(part.function_call)
                if part.text:
                    text_parts.append(part.text)

            if not func_calls:
                # Final text response — save to session, return
                final_text = "".join(text_parts).strip()
                if not final_text:
                    final_text = "Dạ, em đã xử lý xong."
                elif not final_text.lower().startswith("dạ"):
                    final_text = "Dạ, " + final_text

                # Save turn to session
                history.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
                history.append(types.Content(role="model", parts=[types.Part.from_text(text=final_text)]))
                self._save_session(chat_id)

                return {"type": "text", "content": final_text}

            # ── Execute tool calls ──
            # Preserve original function_call parts (they contain thought_signature)
            model_parts = []
            for p in candidate.content.parts:
                if p.function_call or p.text:
                    model_parts.append(p)
            turn_history.append(types.Content(role="model", parts=model_parts))

            # Execute each tool and feed results back
            tool_responses = []
            executed_results = []
            for fc in func_calls:
                result = self._execute_tool(fc.name, dict(fc.args))
                executed_results.append((fc, result))
                tool_responses.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response={"result": result},
                    )
                )

            turn_history.append(types.Content(role="user", parts=tool_responses))

            # Check if the last tool call was a mockup — if so, return it directly
            last_fc, result = executed_results[-1]
            if last_fc.name in ("create_mockup_from_order", "create_mockup_from_product", "create_mockup_from_uploaded_design"):
                print(">>> MOCKUP TOOL DETECTED, returning result", flush=True)
                mockup_url = result.get("mockup_url", "")
                provider = result.get("provider", "unknown")
                integrity = result.get("integrity", 0)
                size_val = result.get("size", "?")
                elapsed = result.get("time", "?")
                cost = result.get("cost", "$0")
                product = result.get("product", "")
                color = result.get("color", "")
                # scene from the tool args
                scene = dict(last_fc.args).get("scene", "")

                # Deterministic final reply: natural chat format with full details.
                size_val_clean = size_val.replace("×", "x") if size_val else "?"
                final_parts = [f"Dạ anh, đây là mockup cho {product} ({color}), em đã tạo xong rồi."]
                if scene:
                    final_parts.append(f"• Scene: {scene}")
                final_parts.append(f"• Kích thước: {size_val_clean}")
                final_parts.append(f"• Thời gian: {elapsed}")
                final_parts.append(f"• Chi phí: {cost}")
                final_parts.append(f"• Provider: {provider}")
                sync_status = result.get("sync_status", "disabled")
                sync_emoji = "✓" if sync_status == "sent" else "✗" if sync_status.startswith("fail") else "○"
                final_parts.append(f"• Sync: {sync_emoji} {sync_status}")
                final_text = "\n".join(final_parts)

                # Save session
                history.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
                history.append(types.Content(role="model", parts=[types.Part.from_text(text=final_text)]))
                self._save_session(chat_id)

                return {
                    "type": "mockup",
                    "content": final_text,
                    "image": mockup_url,
                    "meta": {
                        "provider": provider,
                        "integrity": integrity,
                        "size": size_val,
                        "time": elapsed,
                        "cost": cost,
                        "product": product,
                        "color": color,
                    },
                }

        # Exhausted rounds
        return {"type": "text", "content": "Dạ, em xử lý hơi lâu. Anh thử lại nhé."}

    def clear_session(self, chat_id: str):
        """Clear session memory for a chat."""
        self.sessions.pop(chat_id, None)
        path = self._session_path(chat_id)
        if path.exists():
            path.unlink()

    def test_connection(self) -> Dict[str, Any]:
        try:
            resp = self.client.models.generate_content(
                model=self.model,
                contents="Reply with OK",
                config=types.GenerateContentConfig(max_output_tokens=10),
            )
            return {"ok": True, "model": self.model}
        except Exception as e:
            return {"ok": False, "error": str(e)}
