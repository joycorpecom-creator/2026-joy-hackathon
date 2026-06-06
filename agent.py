"""BurgerMockup Agent — LLM-driven tool-calling with session memory.

Current runtime: BurgerShop v1 seller products only. No order_id flows.
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from config_store import load_settings
from burgerprints import BurgerPrintsClient
from mockup_engine import generate_mockup

ROOT = Path(__file__).parent
MEMORY_DIR = ROOT / "memory"
MAX_HISTORY = 20

TOOL_DECLARATIONS = types.Tool(
    function_declarations=[
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
        types.FunctionDeclaration(
            name="bs_list_seller_products",
            description="Liệt kê seller products từ BurgerShop v1. Seller product IDs dạng Axxxxx-xx.",
            parameters={
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "description": "Trang", "default": 1},
                    "page_size": {"type": "integer", "description": "Số sản phẩm/trang", "default": 10},
                },
                "required": [],
            },
        ),
        types.FunctionDeclaration(
            name="bs_get_seller_product",
            description="Lấy chi tiết seller product BurgerShop v1 theo product_id dạng Axxxxx-xx, gồm mockup/design/variant.",
            parameters={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Seller product ID, VD A53636-28"},
                },
                "required": ["product_id"],
            },
        ),
        types.FunctionDeclaration(
            name="create_mockup_from_seller_product",
            description="Tạo lifestyle mockup từ seller product BurgerShop v1 có design/mockup sẵn. Dùng product_id dạng Axxxxx-xx + scene.",
            parameters={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Seller product ID, VD A53636-28"},
                    "scene": {"type": "string", "description": "Mô tả scene/phong cách. Có thể dùng dấu phẩy cho nhiều scene."},
                },
                "required": ["product_id", "scene"],
            },
        ),
        types.FunctionDeclaration(
            name="refine_mockup",
            description="Điều chỉnh/thay đổi mockup seller product đã tạo trước đó. Chỉ dùng product memory/current_order_id dạng Axxxxx-xx.",
            parameters={
                "type": "object",
                "properties": {"new_scene": {"type": "string", "description": "Mô tả scene mới hoặc điều chỉnh"}},
                "required": ["new_scene"],
            },
        ),
        types.FunctionDeclaration(
            name="memory_save_profile",
            description="Lưu sở thích bền vững của seller: marketplace, style, brand tone, persona, sản phẩm ưa dùng.",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["key", "value"],
            },
        ),
        types.FunctionDeclaration(
            name="memory_search",
            description="Tìm lại mockup/prompt/product/style đã dùng trước đây trong chat này.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
    ]
)

SYSTEM_PROMPT = """Bạn là J_agent, trợ lý BurgerMockup AI cho người bán BurgerPrints.
Nhiệm vụ: phân tích ý định → chọn đúng công cụ → trả kết quả có ảnh khi có.

RUNTIME HIỆN TẠI: SELLER PRODUCTS ONLY (BurgerShop v1). Không có luồng order_id.

NHẬN DIỆN SELLER PRODUCT:
- Seller product ID có dạng Axxxxx-xx, ví dụ A53636-28.
- Đây là sản phẩm final của seller trong BurgerShop v1, có design/mockup thật.

LUẬT ROUTING:
- User muốn danh sách seller product → gọi bs_list_seller_products.
- User muốn xem chi tiết/ảnh seller product Axxxxx-xx → gọi bs_get_seller_product.
- User muốn tạo mockup/lifestyle/scene/phong cách từ Axxxxx-xx → gọi create_mockup_from_seller_product(product_id, scene).
- Nếu thiếu scene khi tạo mockup → hỏi lại scene/phong cách 1 câu, không tự bịa.
- Nếu user yêu cầu nhiều ảnh/nhiều phong cách → truyền nhiều scene bằng dấu phẩy.
- refine_mockup chỉ dùng khi đã có mockup seller product trước đó trong memory; không hỏi lại product_id nếu memory có current_order_id/current_product_id dạng Axxxxx-xx.
- Product mockup creation dùng BurgerShop v1 seller product API, không dùng catalog/order API.

CHAT STYLE:
- LUÔN xưng hô "Dạ" mở đầu mỗi câu trả lời, gọi user là "anh".
- Ngắn gọn, tự nhiên, không markdown ảnh trong text nếu hệ thống đã trả image field.
- KHÔNG bịa kết quả. Chỉ dùng dữ liệu từ tool.
- Trả lời tiếng Việt.
"""


class BurgerMockupAgent:
    """LLM agent with BurgerPrints seller-product tools + session memory."""

    def __init__(self):
        self.settings = load_settings()
        self.bp = BurgerPrintsClient()
        self.llm_key = self.settings.get("llm_api_key", "").strip()
        self.model = self.settings.get("llm_model", "gemini-3-flash-preview")
        self._client: Optional[genai.Client] = None
        self.sessions: Dict[str, List[types.Content]] = {}
        self._current_chat_id = "web"
        self._load_sessions()
        try:
            import burger_memory as mem
            mem.search_memory("_init", "", limit=1)
        except Exception:
            pass

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            if not self.llm_key or "..." in self.llm_key:
                raise RuntimeError("Gemini API key chưa được cấu hình.")
            self._client = genai.Client(api_key=self.llm_key)
        return self._client

    def _session_path(self, chat_id: str) -> Path:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        return MEMORY_DIR / f"session_{chat_id}.json"

    def _load_sessions(self):
        if MEMORY_DIR.exists():
            for f in sorted(MEMORY_DIR.glob("session_*.json")):
                try:
                    data = json.loads(f.read_text())
                    cid = f.stem.replace("session_", "")
                    self.sessions[cid] = [types.Content.model_validate(c) for c in data]
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
        self.sessions[chat_id][0] = types.Content(role="user", parts=[types.Part.from_text(text=SYSTEM_PROMPT)])
        self.sessions[chat_id][1] = types.Content(role="model", parts=[types.Part.from_text(text="Dạ, J_agent sẵn sàng!")])
        hist = self.sessions[chat_id]
        if len(hist) > MAX_HISTORY * 2 + 2:
            hist = hist[:2] + hist[-(MAX_HISTORY * 2):]
            self.sessions[chat_id] = hist
        return hist

    def _split_scenes(self, scene: str) -> List[str]:
        """Split comma/newline separated scene request into a capped batch."""
        import re
        raw = str(scene or "").strip()
        if not raw:
            return []
        parts = [x.strip(" -•\t") for x in re.split(r"[,;\n]+", raw) if x.strip()]
        return parts[:8] or [raw]

    def _create_seller_product_mockup_once(self, product_id: str, scene: str) -> Dict[str, Any]:
        t0 = time.time()
        asset = self.bp.extract_first_seller_product_asset(product_id)
        result = generate_mockup(asset, scene)
        elapsed = round(time.time() - t0, 2)
        out = self._finalize_generated_mockup(result, asset, scene, elapsed)
        out["product_id"] = product_id
        return out

    def _finalize_generated_mockup(self, result: Dict[str, Any], asset, scene: str, elapsed: float) -> Dict[str, Any]:
        from imgbb_uploader import upload_image
        from sync_webhook import build_mockup_payload, post_mockup_created
        local_path = result.get("path", "")
        imgbb_result = upload_image(local_path) if local_path else {"ok": False, "error": "missing local path"}
        public_img_url = imgbb_result.get("url") or imgbb_result.get("display_url") or ""
        product_id = asset.product_id or asset.order_id or ""
        sync_payload = build_mockup_payload(
            result=result,
            product_id=product_id,
            product_name=asset.product_name,
            color=asset.color_name,
            scene=scene,
            raw_user_input=scene,
            public_base_url=self.settings.get("public_base_url", ""),
        )
        if public_img_url:
            sync_payload["assets"]["image_url"] = public_img_url
            sync_payload["assets"]["imgbb_url"] = public_img_url
            sync_payload["assets"]["imgbb_delete_url"] = imgbb_result.get("delete_url", "")
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
            "product_id": product_id,
            "mockup_url": f"/outputs/{result['path'].split('/')[-1]}",
            "provider": result["provider"],
            "size": f"{result['width']}×{result['height']}",
            "integrity": result["integrity_score"],
            "time": f"{elapsed}s",
            "cost": f"${result['cost_usd']}",
            "product": asset.product_name,
            "color": asset.color_name,
            "scene": scene,
            "source_asset": result.get("source_asset", "?"),
            **sync_info,
        }

    def _execute_tool(self, name: str, args: Dict[str, Any]) -> Any:
        try:
            if name == "bp_authenticated":
                r = self.bp.authenticated()
                ok = r.get("data", {}).get("is_success", False)
                return {"connected": ok, "message": "OK" if ok else "API key không hợp lệ"}

            if name == "bp_balance":
                r = self.bp.balance()
                return {"balance": r}

            if name == "bs_list_seller_products":
                r = self.bp.bs_products(page=args.get("page", 1), page_size=args.get("page_size", 10))
                data = r.get("data", r) if isinstance(r, dict) else {}
                result = data.get("result", []) if isinstance(data, dict) else []
                items = []
                for p in result[:12]:
                    if isinstance(p, dict):
                        items.append({
                            "id": p.get("id"),
                            "title": p.get("title"),
                            "state": p.get("state"),
                            "mockup_url": p.get("mockup_url") or "",
                            "uri": p.get("uri"),
                            "product_type": p.get("product_type"),
                            "vendor": p.get("vendor"),
                            "description": p.get("description") or p.get("desc") or "",
                            "tags": p.get("tags"),
                            "collection_ids": p.get("collection_ids") or [],
                            "user_id": p.get("user_id"),
                            "created_at": p.get("created_at"),
                            "updated_at": p.get("updated_at"),
                            "bp_fields": sorted(list(p.keys())),
                        })
                return {
                    "products": items,
                    "count": len(items),
                    "total": data.get("total", 0) if isinstance(data, dict) else len(items),
                    "page": data.get("page") if isinstance(data, dict) else None,
                    "page_size": data.get("page_size") if isinstance(data, dict) else None,
                    "source": "BurgerShop v1 Product API",
                }

            if name == "bs_get_seller_product":
                pid = args.get("product_id") or args.get("seller_product_id") or ""
                try:
                    r = self.bp.bs_product(pid)
                except Exception as e:
                    return {"error": str(e)}
                data = r.get("data", r) if isinstance(r, dict) else {}
                if not isinstance(data, dict) or not data:
                    return {"error": f"Không tìm thấy seller product {pid}"}
                designs = data.get("designs") or []
                mockups = data.get("mockups") or []
                variants = data.get("variants") or []
                first_v = variants[0] if variants and isinstance(variants[0], dict) else {}
                design_src = designs[0].get("src") if designs and isinstance(designs[0], dict) else ""
                vm = first_v.get("mockup") if isinstance(first_v.get("mockup"), dict) else {}
                dm = data.get("mockup") if isinstance(data.get("mockup"), dict) else {}
                mockup_src = (mockups[0].get("src") if mockups and isinstance(mockups[0], dict) else "") or vm.get("src") or dm.get("src") or data.get("mockup_url") or ""
                product_types = data.get("product_types") or []
                return {
                    "product_id": data.get("id", pid),
                    "title": data.get("title", ""),
                    "status": data.get("status"),
                    "state": data.get("state"),
                    "price": data.get("price"),
                    "compare_price": data.get("compare_price"),
                    "vendor": data.get("vendor"),
                    "category": data.get("category"),
                    "product_type": data.get("product_type") or (product_types[0].get("name", "") if product_types and isinstance(product_types[0], dict) else ""),
                    "product_format": data.get("product_format"),
                    "is_custom": data.get("is_custom"),
                    "is_personalize": data.get("is_personalize"),
                    "download_limit": data.get("download_limit"),
                    "store_id": data.get("store_id"),
                    "uri": data.get("uri"),
                    "seo_title": data.get("seo_title"),
                    "seo_desc": data.get("seo_desc"),
                    "short_desc": data.get("short_desc"),
                    "desc": data.get("desc"),
                    "tags": data.get("tags"),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                    "short_codes": [pt.get("short_code", "") for pt in product_types if isinstance(pt, dict)],
                    "product_types": product_types,
                    "options": data.get("options") or [],
                    "layers": data.get("layers") or [],
                    "mockup_src": mockup_src,
                    "design_src": design_src,
                    "store_channels": data.get("store_channels") or [],
                    "product_url": next((c.get("url") for c in (data.get("store_channels") or []) if isinstance(c, dict) and c.get("url")), ""),
                    "designs": [{
                        "id": d.get("id"), "src": d.get("src"), "type": d.get("type"), "short_code": d.get("short_code"),
                        "width": d.get("width"), "height": d.get("height"),
                        "printable_width": d.get("printable_width"), "printable_height": d.get("printable_height"),
                        "printable_left": d.get("printable_left"), "printable_top": d.get("printable_top"),
                        "position": d.get("position"), "created_at": d.get("created_at"), "updated_at": d.get("updated_at"),
                    } for d in designs if isinstance(d, dict)],
                    "mockups": [{
                        "src": m.get("src"), "id": m.get("id"), "position": m.get("position"),
                        "media_type": m.get("media_type"), "source": m.get("source"), "thumbnail_url": m.get("thumbnail_url"),
                    } for m in mockups if isinstance(m, dict)],
                    "variants": [{
                        "id": v.get("id"), "sku": v.get("sku"), "name": v.get("name"),
                        "short_code": v.get("short_code"), "short_code_name": v.get("short_code_name"),
                        "color_name": v.get("color_name"), "color_value": v.get("color_value"), "color_id": v.get("color_id"),
                        "size_name": v.get("size_name"), "size_id": v.get("size_id"),
                        "price": v.get("price"), "compare_price": v.get("compare_price"), "cost": v.get("cost"),
                        "state": v.get("state"), "position": v.get("position"),
                        "mockup_src": (v.get("mockup") or {}).get("src") if isinstance(v.get("mockup"), dict) else "",
                    } for v in variants[:50] if isinstance(v, dict)],
                    "counts": {"designs": len(designs), "mockups": len(mockups), "variants": len(variants), "product_types": len(product_types), "store_channels": len(data.get("store_channels") or [])},
                    "bp_fields": sorted(list(data.keys())),
                    "source": "BurgerShop v1 Product API",
                    "image_markdown": f"![{pid}]({mockup_src or design_src})" if (mockup_src or design_src) else "",
                }

            if name == "create_mockup_from_seller_product":
                pid = args.get("product_id") or args.get("seller_product_id") or ""
                scene_raw = args.get("scene", "")
                no_split = args.get("no_split", False)
                if no_split:
                    results = [self._create_seller_product_mockup_once(pid, scene_raw)]
                else:
                    results = [self._create_seller_product_mockup_once(pid, scn) for scn in self._split_scenes(scene_raw)]
                if len(results) == 1:
                    return results[0]
                return {"type": "mockup_batch", "product_id": pid, "count": len(results), "mockups": results, "product": results[0].get("product", "") if results else "", "color": results[0].get("color", "") if results else ""}

            if name == "refine_mockup":
                import burger_memory as mem
                import re
                state = mem.get_state(self._current_chat_id)
                pid = state.get("current_product_id") or state.get("current_order_id")
                if not pid or not re.search(r"^A\d{4,}-\d{1,6}$", str(pid), re.I):
                    return {"error": "Chưa có seller product ID dạng Axxxxx-xx trong memory. Anh gửi lại product_id giúp em."}
                prev_scene = state.get("current_scene") or ""
                new_scene = str(args.get("new_scene", "")).strip()
                scene = f"Refine previous mockup. Previous scene: {prev_scene}. Change request: {new_scene}" if prev_scene else new_scene
                return self._create_seller_product_mockup_once(pid, scene)

            if name == "memory_save_profile":
                import burger_memory as mem
                key = str(args.get("key", "")).strip()
                value = str(args.get("value", "")).strip()
                if not key or not value:
                    return {"error": "missing key/value"}
                prof = mem.update_profile(self._current_chat_id, {key: value})
                return {"saved": True, "profile": prof}

            if name == "memory_search":
                import burger_memory as mem
                q = str(args.get("query", "")).strip()
                return {"results": mem.search_memory(self._current_chat_id, q, limit=5)}

            return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            return {"error": str(e)}

    def chat(self, chat_id: str, message: str) -> Dict[str, Any]:
        if not self.llm_key or "..." in self.llm_key:
            return {"type": "text", "content": "Dạ, Gemini API key chưa được cấu hình anh ơi."}

        self._current_chat_id = str(chat_id)
        history = self._get_history(chat_id)
        turn_history = list(history)

        try:
            import context_loader
            joy_ctx = context_loader.load_context(message, max_total=4500)
            turn_history.append(types.Content(role="user", parts=[types.Part.from_text(text=joy_ctx)]))
        except Exception:
            pass
        try:
            import burger_memory as mem
            mem_ctx = mem.build_memory_context(str(chat_id), message)
            turn_history.append(types.Content(role="user", parts=[types.Part.from_text(text=mem_ctx)]))
        except Exception:
            pass

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
                final_text = "".join(text_parts).strip() or "Dạ, em đã xử lý xong."
                if not final_text.lower().startswith("dạ"):
                    final_text = "Dạ, " + final_text
                history.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
                history.append(types.Content(role="model", parts=[types.Part.from_text(text=final_text)]))
                self._save_session(chat_id)
                try:
                    import burger_memory as mem
                    mem.record_turn(str(chat_id), message, final_text)
                except Exception:
                    pass
                return {"type": "text", "content": final_text}

            model_parts = [p for p in candidate.content.parts if p.function_call or p.text]
            turn_history.append(types.Content(role="model", parts=model_parts))

            tool_responses = []
            executed_results = []
            for fc in func_calls:
                result = self._execute_tool(fc.name, dict(fc.args))
                executed_results.append((fc, result))
                tool_responses.append(types.Part.from_function_response(name=fc.name, response={"result": result}))
            turn_history.append(types.Content(role="user", parts=tool_responses))

            last_fc, result = executed_results[-1]
            if last_fc.name in ("create_mockup_from_seller_product", "refine_mockup"):
                if result.get("error"):
                    final_text = f"Dạ, có lỗi khi tạo mockup: {result['error']}"
                    history.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
                    history.append(types.Content(role="model", parts=[types.Part.from_text(text=final_text)]))
                    self._save_session(chat_id)
                    return {"type": "text", "content": final_text}

                batch = result.get("type") == "mockup_batch"
                mockups = result.get("mockups", [result]) if batch else [result]
                try:
                    import burger_memory as mem
                    for m in mockups:
                        mem.record_mockup(str(chat_id), m, scene=m.get("scene", ""))
                except Exception:
                    pass

                if len(mockups) == 1:
                    m = mockups[0]
                    mockup_url = m.get("mockup_url", "")
                    provider = m.get("provider", "unknown")
                    size_val = m.get("size", "?")
                    elapsed = m.get("time", "?")
                    cost = m.get("cost", "$0")
                    product = m.get("product", "")
                    color = m.get("color", "")
                    scene = m.get("scene", "")
                    final_parts = [f"Dạ anh, đây là mockup cho {product} ({color}), em đã tạo xong rồi."]
                    if scene:
                        final_parts.append(f"• Scene: {scene}")
                    final_parts.append(f"• Kích thước: {size_val.replace('×', 'x') if size_val else '?'}")
                    final_parts.append(f"• Thời gian: {elapsed}")
                    final_parts.append(f"• Chi phí: {cost}")
                    final_parts.append(f"• Provider: {provider}")
                    sync_status = m.get("sync_status", "disabled")
                    sync_emoji = "✓" if sync_status == "sent" else "✗" if str(sync_status).startswith("fail") else "○"
                    final_parts.append(f"• Sync: {sync_emoji} {sync_status}")
                    final_text = "\n".join(final_parts)
                    history.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
                    history.append(types.Content(role="model", parts=[types.Part.from_text(text=final_text)]))
                    self._save_session(chat_id)
                    try:
                        import burger_memory as mem
                        mem.record_turn(str(chat_id), message, final_text)
                    except Exception:
                        pass
                    public_url = f"http://36.50.26.198:8000{mockup_url}" if str(mockup_url).startswith("/") else mockup_url
                    return {
                        "type": "mockup",
                        "content": final_text,
                        "image": mockup_url,
                        "images": [{"url": mockup_url, "public_url": public_url, "scene": scene, "index": 1, "product_id": m.get("product_id", ""), "image_id": m.get("image_id", "")}],
                        "meta": {
                            "provider": provider, "integrity": m.get("integrity", 0),
                            "size": size_val, "time": elapsed, "cost": cost,
                            "product": product, "product_id": m.get("product_id", ""), "color": color,
                            "warnings": m.get("warnings", []),
                        },
                    }

                images = []
                for idx, x in enumerate([m for m in mockups if m.get("mockup_url")], start=1):
                    u = x.get("mockup_url", "")
                    images.append({
                        "url": u,
                        "public_url": f"http://36.50.26.198:8000{u}" if str(u).startswith("/") else u,
                        "scene": x.get("scene", ""),
                        "index": idx,
                        "product_id": x.get("product_id", ""),
                        "product": x.get("product", ""),
                        "provider": x.get("provider", ""),
                        "integrity": x.get("integrity", 0),
                        "cost": x.get("cost", ""),
                    })
                final_text = f"Dạ anh, em đã tạo {len(images)} mockup cho {result.get('product', 'seller product')}:"
                for im in images:
                    final_text += f"\n• {im['scene']}"
                final_text += f"\n• Tổng thời gian: {sum(float(str(x.get('time', '0')).replace('s','') or 0) for x in mockups):.1f}s"
                history.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
                history.append(types.Content(role="model", parts=[types.Part.from_text(text=final_text)]))
                self._save_session(chat_id)
                try:
                    import burger_memory as mem
                    mem.record_turn(str(chat_id), message, final_text)
                except Exception:
                    pass
                return {"type": "mockup", "content": final_text, "images": images, "meta": {"product": result.get("product", ""), "color": result.get("color", ""), "count": len(images)}}

        return {"type": "text", "content": "Dạ, em xử lý hơi lâu. Anh thử lại nhé."}

    def clear_session(self, chat_id: str):
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
