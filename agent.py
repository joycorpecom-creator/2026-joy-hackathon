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
from mockup_engine import generate_mockup, generate_product_mockup

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
            description="Liệt kê danh sách đơn hàng gần đây. Khi user hỏi lấy toàn bộ/order_id, phải trả kèm ảnh mockup/design nếu order item có mockups[].src hoặc designs[].src.",
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
                    "scene": {"type": "string", "description": "Mô tả scene: cafe, streetwear, outdoor... Có thể tiếng Việt hoặc Anh. Có thể dùng dấu phẩy cho nhiều scene."},
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
                    "scene": {"type": "string", "description": "Mô tả scene: cafe, streetwear, outdoor... Có thể dùng dấu phẩy cho nhiều scene: 'cafe, outdoor, studio'."},
                },
                "required": ["short_code", "scene"],
            },
        ),
        # ── Refine / Reuse ──
        types.FunctionDeclaration(
            name="refine_mockup",
            description="Điều chỉnh/thay đổi mockup đã tạo trước đó mà KHÔNG cần nhắc lại order_id. Dùng khi user nói 'thay đổi người mẫu ốm hơn', 'đổi scene cafe', 'thêm background biển'. Agent tự động lấy order_id từ session_state.current_order_id.",
            parameters={
                "type": "object",
                "properties": {
                    "new_scene": {"type": "string", "description": "Mô tả scene mới hoặc điều chỉnh cần thay đổi"},
                },
                "required": ["new_scene"],
            },
        ),
        # ── Memory ──
        types.FunctionDeclaration(
            name="memory_save_profile",
            description="Lưu sở thích bền vững của seller: marketplace, style, brand tone, persona, sản phẩm ưa dùng. Chỉ dùng khi user nói rõ preference hoặc lặp lại thói quen.",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Tên field, VD marketplace, preferred_styles, brand_tone, favorite_products"},
                    "value": {"type": "string", "description": "Giá trị ngắn gọn cần lưu"},
                },
                "required": ["key", "value"],
            },
        ),
        types.FunctionDeclaration(
            name="memory_search",
            description="Tìm lại mockup/prompt/product/style đã dùng trước đây trong chat này.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Từ khóa cần tìm lại"},
                },
                "required": ["query"],
            },
        ),
    ]
)

# ═══════════════════════════════════════════════════════════════════════════
# Agent
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """Bạn là J_agent, trợ lý BurgerMockup AI cho người bán BurgerPrints.
Nhiệm vụ: phân tích ý định → chọn đúng công cụ → trả kết quả có ảnh khi có.

PHÂN BIỆT 3 NHÓM Ý ĐỊNH BẮT BUỘC:
1) LẤY THÔNG TIN / ẢNH SẢN PHẨM BP CATALOG
   - Ví dụ: "lấy thông tin sản phẩm XXX", "chỉ trả ảnh sản phẩm XXX", "cho xem product XXX".
   - Đây là sản phẩm phôi/catalog của BP, chưa phải thiết kế final của seller.
   - Hành động: gọi bp_search_products nếu user đưa tên; gọi bp_get_product nếu user đưa short_code rõ.
   - KHÔNG tạo mockup nếu user không có từ khóa tạo ảnh/mockup/lifestyle/scene/phong cách.
   - Nếu user yêu cầu NHIỀU ảnh / nhiều phong cách cùng lúc (VD "5 phong cách", "tạo 3 ảnh"), dùng dấu phẩy trong scene: "cafe, streetwear, outdoor, studio, flat-lay".

2) TẠO MOCKUP TỪ SẢN PHẨM PHÔI BP CATALOG
   - Ví dụ: "tạo hình ảnh mockup sản phẩm XXX với phong cách A,B,C".
   - User chưa đưa order_id. Nguồn là base mockup/catalog product BP.
   - Hành động: bp_search_products → create_mockup_from_product.

3) TẠO MOCKUP TỪ ORDER_ID CÓ SẴN
   - Ví dụ: "tạo mockup của sản phẩm với order_id XX với phong cách A".
   - Đây là sản phẩm FINAL user đã thiết kế trên BP; order chứa design/mockup_url thật.
   - Hành động: create_mockup_from_order(order_id, scene).
   - Không dùng create_mockup_from_product cho case có order_id.

LUẬT ROUTING:
- Từ khóa tạo ảnh: "tạo", "create", "mockup", "lifestyle", "phong cách", "scene", "bối cảnh", "ảnh mockup" → intent tạo mockup.
- Từ khóa xem/lấy: "lấy thông tin", "cho xem", "chỉ trả ảnh", "ảnh sản phẩm", "thông tin sản phẩm" mà KHÔNG có intent tạo → intent product_info.
- Nếu có order_id + intent tạo → luôn create_mockup_from_order.
- Nếu có product name/code + intent tạo + không có order_id → product mockup branch.
- Nếu chỉ có product name/code + intent xem/lấy → product info branch.
- Nếu thiếu scene khi tạo mockup → hỏi lại scene/phong cách 1 câu, không tự bịa.
- Khi user hỏi danh sách/toàn bộ order_id/đơn hàng gần đây: gọi bp_list_orders. Câu trả lời phải kèm ảnh nếu tool trả mockup_url hoặc design_url. Dùng markdown image `![order](url)` để web render ảnh.

4) REFINE / ĐIỀU CHỈNH MOCKUP CŨ
   - Ví dụ: "thay đổi người mẫu ốm hơn", "đổi scene cafe", "tạo lại với background biển".
   - User KHÔNG nhắc lại order_id, chỉ muốn thay đổi mockup vừa tạo.
   - Hành động: refine_mockup(new_scene="mô tả thay đổi"). Agent tự lấy current_order_id từ memory.
   - KHÔNG hỏi lại order_id khi user refine.

CHAT STYLE:
- LUÔN xưng hô "Dạ" mở đầu mỗi câu trả lời, gọi user là "anh".
- Ngắn gọn, tự nhiên, không markdown ảnh trong text nếu hệ thống đã trả image field.
- KHÔNG bịa kết quả. Chỉ dùng dữ liệu từ tool.
- Trả lời tiếng Việt.
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
        # Memory system (burger_memory)
        try:
            import burger_memory as mem
            # one-time schema init
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
        # Always refresh system prompt so routing rule updates apply immediately.
        self.sessions[chat_id][0] = types.Content(role="user", parts=[types.Part.from_text(text=SYSTEM_PROMPT)])
        self.sessions[chat_id][1] = types.Content(role="model", parts=[types.Part.from_text(text="Dạ, J_agent sẵn sàng!")])
        hist = self.sessions[chat_id]
        # Keep within max history
        if len(hist) > MAX_HISTORY * 2 + 2:
            hist = hist[:2] + hist[-(MAX_HISTORY * 2):]
            self.sessions[chat_id] = hist
        return hist

    # ── Tool execution ──────────────────────────────────────────────────


    def _split_scenes(self, scene: str) -> List[str]:
        """Split comma/newline separated scene request into a capped batch."""
        import re
        raw = str(scene or "").strip()
        if not raw:
            return []
        parts = [x.strip(" -•\t") for x in re.split(r"[,;\n]+", raw) if x.strip()]
        return parts[:8] or [raw]

    def _create_order_mockup_once(self, oid: str, scene: str) -> Dict[str, Any]:
        """Generate one order-based mockup + upload/sync."""
        t0 = time.time()
        asset = self.bp.extract_first_asset(oid)
        result = generate_mockup(asset, scene)
        elapsed = round(time.time() - t0, 2)

        return self._finalize_generated_mockup(result, asset, scene, elapsed)

    def _create_seller_product_mockup_once(self, product_id: str, scene: str) -> Dict[str, Any]:
        """Generate one mockup from BurgerShop seller product with attached design/mockup."""
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
        sync_payload = build_mockup_payload(
            result=result, product_id=asset.product_id or oid, product_name=asset.product_name,
            color=asset.color_name, scene=scene, raw_user_input=scene,
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
            "order_id": asset.order_id,
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
                # Extract first item's images
                item = items[0] if items else {}
                mockups = item.get("mockups") or []
                designs = item.get("designs") or []
                mockup_url = (
                    (mockups[0].get("src") if mockups else None)
                    or item.get("mockup_front_url")
                    or item.get("mockup_url_front")
                    or item.get("mockup_url")
                    or ""
                )
                design_url = (
                    (designs[0].get("src") if designs else None)
                    or item.get("design_front_url")
                    or item.get("design_url_front")
                    or item.get("design_url")
                    or ""
                )
                short_code = item.get("short_code") or item.get("catalog_sku") or ""
                product_meta = {}
                if short_code:
                    try:
                        pr = self.bp.product(short_code)
                        pd = pr.get("data", pr) if isinstance(pr, dict) else {}
                        if isinstance(pd, dict):
                            product_meta = {
                                "catalog_name": pd.get("display_name") or pd.get("name"),
                                "print_area": pd.get("print_area"),
                                "resolution": pd.get("resolution") or pd.get("resolution_default"),
                                "base_mockup_url": pd.get("url"),
                                "variations": pd.get("variations", [])[:20],
                            }
                    except Exception:
                        product_meta = {}
                line_items = []
                for it in items:
                    line_items.append({
                        "item_id": it.get("id"),
                        "product_id": it.get("product_id"),
                        "name": it.get("name") or it.get("product_name") or it.get("catalog_sku") or "",
                        "short_code": it.get("short_code") or it.get("catalog_sku") or "",
                        "sku": it.get("sku"),
                        "color": it.get("color_name"),
                        "color_hex": it.get("color_value"),
                        "size": it.get("size_name"),
                        "quantity": it.get("quantity"),
                        "price": it.get("price"),
                        "base_cost": it.get("base_cost"),
                        "amount": it.get("amount"),
                        "shipping_fee": it.get("shipping_fee"),
                        "currency": it.get("currency") or r.get("currency"),
                        "designs": it.get("designs") or [],
                        "mockups": it.get("mockups") or [],
                    })
                return {
                    "order_id": r.get("id", oid),
                    "state": state,
                    "fulfillment": r.get("fulfillment"),
                    "currency": r.get("currency"),
                    "amount": (r.get("seller") or {}).get("amount") or r.get("amount") or r.get("total", "?"),
                    "shipping_fee": (r.get("seller") or {}).get("shipping_fee") or r.get("shipping_fee"),
                    "tax_amount": (r.get("seller") or {}).get("tax_amount") or r.get("tax_amount"),
                    "shipping_method": r.get("shipping_method"),
                    "shipping": r.get("shipping"),
                    "items": item_names,
                    "line_items": line_items,
                    "mockup_url": mockup_url,
                    "design_url": design_url,
                    "product": item.get("name") or item.get("product_name") or item.get("catalog_sku") or "",
                    "short_code": short_code,
                    "product_meta": product_meta,
                    "image_markdown": f"![{oid}]({mockup_url or design_url})" if (mockup_url or design_url) else "",
                }

            if name == "bp_list_orders":
                r = self.bp.list_orders(page_size=10, sandbox=False)
                rows = self.bp._rows(r)
                orders = []
                for o in rows[:10]:
                    items = o.get("items") or o.get("line_items") or []
                    item = items[0] if items else {}
                    mockups = item.get("mockups") or []
                    designs = item.get("designs") or []
                    mockup_url = (
                        (mockups[0].get("src") if mockups else None)
                        or item.get("mockup_front_url")
                        or item.get("mockup_url_front")
                        or item.get("mockup_url")
                        or ""
                    )
                    design_url = (
                        (designs[0].get("src") if designs else None)
                        or item.get("design_front_url")
                        or item.get("design_url_front")
                        or item.get("design_url")
                        or ""
                    )
                    orders.append({
                        "id": o.get("id") or o.get("order_id") or o.get("reference_order"),
                        "state": o.get("state") or o.get("status"),
                        "amount": o.get("amount") or o.get("total"),
                        "product": item.get("name") or item.get("product_name") or item.get("catalog_sku") or "",
                        "short_code": item.get("short_code") or item.get("catalog_sku") or "",
                        "mockup_url": mockup_url,
                        "design_url": design_url,
                        "image_markdown": f"![{o.get('id') or 'order'}]({mockup_url or design_url})" if (mockup_url or design_url) else "",
                    })
                return {"orders": orders, "count": len(orders), "note": "Include image_markdown for each order that has an image."}

            if name == "bs_list_seller_products":
                r = self.bp.bs_products(page=args.get("page", 1), page_size=args.get("page_size", 10))
                data = r.get("data", r) if isinstance(r, dict) else {}
                result = data.get("result", []) if isinstance(data, dict) else []
                items = []
                for p in result[:12]:
                    if isinstance(p, dict):
                        items.append({
                            "id": p.get("id"), "title": p.get("title"), "state": p.get("state"),
                            "mockup_url": p.get("mockup_url") or "", "uri": p.get("uri"),
                            "product_type": p.get("product_type"), "vendor": p.get("vendor"),
                        })
                return {"products": items, "count": len(items), "total": data.get("total", 0) if isinstance(data, dict) else len(items)}

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
                    "product_id": data.get("id", pid), "title": data.get("title", ""),
                    "price": data.get("price"), "compare_price": data.get("compare_price"),
                    "vendor": data.get("vendor"),
                    "product_type": data.get("product_type") or (product_types[0].get("name", "") if product_types and isinstance(product_types[0], dict) else ""),
                    "short_codes": [pt.get("short_code", "") for pt in product_types if isinstance(pt, dict)],
                    "mockup_src": mockup_src, "design_src": design_src,
                    "designs": [{
                        "src": d.get("src"), "type": d.get("type"), "short_code": d.get("short_code"),
                        "printable_width": d.get("printable_width"), "printable_height": d.get("printable_height"),
                        "printable_left": d.get("printable_left"), "printable_top": d.get("printable_top"),
                        "position": d.get("position"),
                    } for d in designs if isinstance(d, dict)],
                    "mockups": [{"src": m.get("src"), "id": m.get("id"), "position": m.get("position")} for m in mockups if isinstance(m, dict)],
                    "variants": [{
                        "id": v.get("id"), "sku": v.get("sku"), "short_code": v.get("short_code"),
                        "short_code_name": v.get("short_code_name"), "color_name": v.get("color_name"),
                        "color_value": v.get("color_value"), "size_name": v.get("size_name"),
                        "price": v.get("price"), "compare_price": v.get("compare_price"), "cost": v.get("cost"),
                        "mockup_src": (v.get("mockup") or {}).get("src") if isinstance(v.get("mockup"), dict) else "",
                    } for v in variants[:20] if isinstance(v, dict)],
                    "store_channels": data.get("store_channels") or [],
                    "image_markdown": f"![{pid}]({mockup_src or design_src})" if (mockup_src or design_src) else "",
                }

            if name == "create_mockup_from_seller_product":
                pid = args.get("product_id") or args.get("seller_product_id") or ""
                scene = args.get("scene", "")
                results = [self._create_seller_product_mockup_once(pid, scn) for scn in self._split_scenes(scene)]
                if len(results) == 1:
                    return results[0]
                return {"type": "mockup_batch", "product_id": pid, "count": len(results), "mockups": results, "product": results[0].get("product", "") if results else "", "color": results[0].get("color", "") if results else ""}

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
                scenes = self._split_scenes(scene)
                results = []
                for scn in scenes:
                    one = self._create_order_mockup_once(oid, scn)
                    results.append(one)
                if len(results) == 1:
                    return results[0]
                return {
                    "type": "mockup_batch",
                    "order_id": oid,
                    "count": len(results),
                    "mockups": results,
                    "product": results[0].get("product", "") if results else "",
                    "color": results[0].get("color", "") if results else "",
                }

            if name == "refine_mockup":
                import burger_memory as mem
                state = mem.get_state(self._current_chat_id)
                oid = state.get("current_order_id")
                if not oid:
                    return {"error": "Chưa có order_id trong memory. Anh gửi lại order_id giúp em."}
                prev_scene = state.get("current_scene") or ""
                new_scene = str(args.get("new_scene", "")).strip()
                scene = f"Refine previous mockup. Previous scene: {prev_scene}. Change request: {new_scene}" if prev_scene else new_scene
                return self._create_order_mockup_once(oid, scene)

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

    # ── Agentic chat loop ────────────────────────────────────────────────

    def _format_product_response(self, result, message, history, chat_id):
        """Convert product tool result into structured type=product response."""
        code = result.get("short_code") or result.get("code") or ""
        name_val = result.get("name") or ""
        image_url = result.get("image_url") or result.get("url") or ""
        if result.get("found") is False and result.get("products"):
            first = result["products"][0]
            code = first.get("short_code") or code
            name_val = first.get("name") or name_val
        final_text = f"Dạ anh, đây là sản phẩm em tìm được: {name_val or code}"
        if code:
            final_text += f" ({code})"
        history.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
        history.append(types.Content(role="model", parts=[types.Part.from_text(text=final_text)]))
        self._save_session(chat_id)
        try:
            import burger_memory as mem
            mem.record_turn(str(chat_id), message, final_text)
            mem.update_state(str(chat_id), {"current_product": f"{code} — {name_val}" if code else name_val, "current_product_image": image_url})
        except Exception:
            pass
        return {
            "type": "product",
            "content": final_text,
            "image": image_url,
            "meta": {"code": code, "name": name_val, "url": image_url},
        }

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
        # ── PRE-ROUTER: deterministic product-info extraction ──
        # Only kicks in for unambiguous "view product info" intent.
        # Everything else (mockup, auth, balance, orders, chat) → LLM.
        t_lower = message.lower().strip()
        has_mockup_keywords = any(k in t_lower for k in [
            "tạo", "create", "mockup", "lifestyle", "phong cách", "scene",
            "bối cảnh", "ảnh mockup", "tạo hình", "làm mockup",
            "streetwear", "cafe", "outdoor", "studio", "flat-lay"
        ])
        has_view_keywords = any(k in t_lower for k in [
            "lấy thông tin", "cho xem", "chỉ trả ảnh", "chỉ muốn xem",
            "thông tin sản phẩm", "ảnh sản phẩm"
        ])
        has_order_id = bool(self.bp.find_order_id(message))
        if has_view_keywords and not has_mockup_keywords and not has_order_id:
            # Try to find product: check for short_code first
            import re
            m = re.search(r"\b([A-Z]{2,5}\d{3,5}[A-Z]?)\b", message, re.I)
            if m:
                code = m.group(1).upper()
                result = self._execute_tool("bp_get_product", {"short_code": code})
                if result.get("image_url") or result.get("short_code"):
                    return self._format_product_response(result, message, history, chat_id)
            # Try fuzzy product name extraction
            from action_router import _extract_product_search
            search_term = _extract_product_search(message)
            if search_term:
                result = self._execute_tool("bp_search_products", {"query": search_term})
                if result.get("image_url") or result.get("found"):
                    return self._format_product_response(result, message, history, chat_id)

        # ── END PRE-ROUTER ──
        # Hermes/Joy-style compact context: project manifest + durable memory + recall.
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
                try:
                    import burger_memory as mem
                    mem.record_turn(str(chat_id), message, final_text)
                except Exception:
                    pass

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

            # ── Accumulate mockup results (multiple rounds possible) ──
            last_fc, result = executed_results[-1]
            if last_fc.name in ("create_mockup_from_order", "create_mockup_from_product", "refine_mockup"):
                if result.get("error"):
                    final_text = f"Dạ, có lỗi khi tạo mockup: {result['error']}"
                    history.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
                    history.append(types.Content(role="model", parts=[types.Part.from_text(text=final_text)]))
                    self._save_session(chat_id)
                    return {"type": "text", "content": final_text}

                # Single or batch?
                batch = result.get("type") == "mockup_batch"
                mockups = result.get("mockups", [result]) if batch else [result]

                # Record each mockup in memory
                try:
                    import burger_memory as mem
                    for m in mockups:
                        scn = m.get("scene", "")
                        mem.record_mockup(str(chat_id), m, scene=scn)
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
                    size_val_clean = size_val.replace("×", "x") if size_val else "?"
                    final_parts = [f"Dạ anh, đây là mockup cho {product} ({color}), em đã tạo xong rồi."]
                    if scene:
                        final_parts.append(f"• Scene: {scene}")
                    final_parts.append(f"• Kích thước: {size_val_clean}")
                    final_parts.append(f"• Thời gian: {elapsed}")
                    final_parts.append(f"• Chi phí: {cost}")
                    final_parts.append(f"• Provider: {provider}")
                    sync_status = m.get("sync_status", "disabled")
                    sync_emoji = "✓" if sync_status == "sent" else "✗" if sync_status.startswith("fail") else "○"
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

                    return {
                        "type": "mockup",
                        "content": final_text,
                        "image": mockup_url,
                        "meta": {
                            "provider": provider, "integrity": m.get("integrity", 0),
                            "size": size_val, "time": elapsed, "cost": cost,
                            "product": product, "color": color,
                            "warnings": m.get("warnings", []),
                        },
                    }

                # Multi-mockup: return batch response
                images = [
                    {"url": x.get("mockup_url", ""), "scene": x.get("scene", ""),
                     "product": x.get("product", ""), "provider": x.get("provider", ""),
                     "integrity": x.get("integrity", 0), "cost": x.get("cost", "")}
                    for x in mockups if x.get("mockup_url")
                ]
                final_text = f"Dạ anh, em đã tạo {len(images)} mockup cho {result.get('product', 'order')}:"
                for im in images:
                    final_text += f"\n• {im['scene']}"
                final_text += f"\n• Tổng thời gian: {sum(float(x.get('time', '0').replace('s','') or 0) for x in mockups):.1f}s"

                history.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
                history.append(types.Content(role="model", parts=[types.Part.from_text(text=final_text)]))
                self._save_session(chat_id)
                try:
                    import burger_memory as mem
                    mem.record_turn(str(chat_id), message, final_text)
                except Exception:
                    pass

                return {
                    "type": "mockup",
                    "content": final_text,
                    "images": images,
                    "meta": {
                        "product": result.get("product", ""),
                        "color": result.get("color", ""),
                        "count": len(images),
                    },
                }
            # Product lookup/search: return structured image payload directly.
            # Web UI can render <img>; avoids markdown image text like ![...](url).
            if last_fc.name in ("bp_get_product", "bp_search_products") and not result.get("error"):
                # Only finalize product lookup when user intent is view/info.
                # If message asks mockup/create/style or uploaded design exists, let LLM continue
                # to create_mockup_from_* in the next tool round.
                tmsg = message.lower()
                wants_mockup_final = any(k in tmsg for k in ["mockup", "tạo", "hình ảnh", "phong cách", "style", "scene"])
                if wants_mockup_final:
                    continue
                code = result.get("short_code") or result.get("code") or ""
                name_val = result.get("name") or ""
                image_url = result.get("image_url") or result.get("url") or ""
                if result.get("found") is False and result.get("products"):
                    first = result["products"][0]
                    code = first.get("short_code") or code
                    name_val = first.get("name") or name_val
                if code or name_val or image_url:
                    final_text = f"Dạ anh, đây là sản phẩm em tìm được: {name_val or code}"
                    if code:
                        final_text += f" ({code})"
                    history.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
                    history.append(types.Content(role="model", parts=[types.Part.from_text(text=final_text)]))
                    self._save_session(chat_id)
                    try:
                        import burger_memory as mem
                        mem.record_turn(str(chat_id), message, final_text)
                        mem.update_state(str(chat_id), {"current_product": f"{code} — {name_val}" if code else name_val, "current_product_image": image_url})
                    except Exception:
                        pass
                    return {
                        "type": "product",
                        "content": final_text,
                        "image": image_url,
                        "meta": {"code": code, "name": name_val, "url": image_url},
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
