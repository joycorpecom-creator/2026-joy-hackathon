"""
Planner — product-only V1 runtime. No order_id flows.
"""
import json
import re
import uuid
from typing import Any, Dict, Optional

from google import genai
from config_store import load_settings
from .plan_schema import (
    AgentPlan, SceneSchema, ToolPlanStep,
    INTENT_REFINE, INTENT_SYNC_LARK,
    INTENT_CONFIRM_PLAN, INTENT_EDIT_PLAN, INTENT_CANCEL,
    INTENT_GREETING, INTENT_HELP, INTENT_UNKNOWN,
    INTENT_LIST_SELLER_PRODUCTS, INTENT_GET_SELLER_PRODUCT, INTENT_CREATE_FROM_SELLER_PRODUCT,
)
from .scene_expander import extract_count, expand_scenes
from .registry import tool_inventory_for_prompt

CONFIRM_WORDS = ["ok", "oke", "okay", "đồng ý", "tạo đi", "tạo luôn", "chạy đi", "confirm", "yes"]
EXECUTE_NOW_WORDS = ["tạo luôn", "chạy luôn", "không cần hỏi", "khỏi hỏi", "execute now"]

PLANNER_SYSTEM = """
You are JOY Mockup Planner. Product-only runtime.
Only use seller product IDs like A53636-28 via BurgerShop v1 product API.
Do not plan order_id/order/list-order/order-info actions.
Output JSON only.
"""


def _is_confirm(text: str) -> bool:
    t = text.strip().lower()
    return any(t == w or t.startswith(w + " ") for w in CONFIRM_WORDS)


def _wants_execute_now(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in EXECUTE_NOW_WORDS)


def _has_mockup_intent(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in ["tạo", "mockup", "ảnh", "hình", "lifestyle", "phong cách", "scene", "bối cảnh"])


def extract_seller_product_ids(text: str) -> list:
    ids = []
    for m in re.finditer(r"\b(A\d{4,}-\d{1,6})(?!-)\b", text or "", re.I):
        ids.append(m.group(1).upper())
    return ids


def _has_list_product_intent(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in [
        "tất cả product", "toàn bộ product", "danh sách product", "list product", "lấy product",
        "tất cả sản phẩm", "toàn bộ sản phẩm", "danh sách sản phẩm", "lấy sản phẩm", "lấy toàn bộ sản phẩm",
        "sản phẩm đã add", "product đã add"
    ])


def _has_product_info_intent(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in [
        "thông tin product", "chi tiết product", "xem product", "product info", "seller product",
        "thông tin sản phẩm", "chi tiết sản phẩm", "xem sản phẩm", "toàn bộ thông tin sản phẩm"
    ])


def _has_refine_intent(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in ["sửa ảnh", "đổi ảnh", "đổi cảnh", "thay cảnh", "chỉnh ảnh", "refine", "làm lại ảnh", "giống ảnh", "ảnh 1", "ảnh 2", "ảnh 3", "ảnh 4", "ảnh 5", "ảnh vừa rồi"])


def _image_ref(text: str, context: Dict[str, Any]) -> Optional[str]:
    m = re.search(r"ảnh\s*(\d{1,2})", text, re.I)
    if not m:
        return None
    idx = int(m.group(1))
    imgs = (((context.get("last_mockup_job") or {}).get("images")) or [])
    for im in imgs:
        if int(im.get("index", -1)) == idx:
            return im.get("image_id") or im.get("id")
    return None


def deterministic_plan(message: str, context: Dict[str, Any]) -> AgentPlan:
    text = (message or "").strip()
    session_id = str(context.get("session", {}).get("id") or context.get("session_id") or "web")
    lower = text.lower()
    plan_id = f"plan_{uuid.uuid4().hex[:12]}"

    if _is_confirm(text):
        return AgentPlan(intent=INTENT_CONFIRM_PLAN, confidence=0.98, plan_id=plan_id, session_id=session_id, raw_message=text)
    if any(k in lower for k in ["huỷ", "hủy", "cancel", "dừng"]):
        return AgentPlan(intent=INTENT_CANCEL, confidence=0.9, plan_id=plan_id, session_id=session_id, raw_message=text)
    if lower in ["hi", "hello", "chào", "xin chào"]:
        return AgentPlan(intent=INTENT_GREETING, confidence=0.9, plan_id=plan_id, session_id=session_id, raw_message=text)
    if any(k in lower for k in ["bạn tên gì", "tên gì", "mày tên gì", "em tên gì", "who are you", "your name"]):
        return AgentPlan(intent=INTENT_HELP, confidence=0.9, reason="identity_question", plan_id=plan_id, session_id=session_id, raw_message=text)

    product_ids = extract_seller_product_ids(text)
    current_product = (context.get("session") or {}).get("current_order_id") or context.get("current_product_id")
    product_id = product_ids[0] if product_ids else current_product

    if _has_product_info_intent(text) and product_id:
        return AgentPlan(intent=INTENT_GET_SELLER_PRODUCT, confidence=0.93, order_id=product_id, tool_plan=[ToolPlanStep(1, "bs_get_seller_product", {"product_id": product_id})], plan_id=plan_id, session_id=session_id, raw_message=text)
    if _has_list_product_intent(text):
        return AgentPlan(intent=INTENT_LIST_SELLER_PRODUCTS, confidence=0.91, tool_plan=[ToolPlanStep(1, "bs_list_seller_products", {})], plan_id=plan_id, session_id=session_id, raw_message=text)

    if _has_refine_intent(text):
        image_id = _image_ref(text, context)
        last_job = context.get("last_mockup_job") or {}
        if image_id or last_job or product_id:
            step = ToolPlanStep(1, "refine_mockup", {"image_id": image_id or "last_image", "instruction": text})
            return AgentPlan(intent=INTENT_REFINE, confidence=0.88, order_id=product_id, tool_plan=[step], plan_id=plan_id, session_id=session_id, raw_message=text)

    if product_id and _has_mockup_intent(text):
        count = extract_count(text) or 1
        scenes = expand_scenes(text, count=count)
        requires_confirmation = (count >= 4 or any(s.source != "explicit" for s in scenes)) and not _wants_execute_now(text)
        tool_plan = [ToolPlanStep(1, "create_mockup_from_seller_product", {"product_id": product_id, "scenes": [s.to_dict() for s in scenes]})]
        return AgentPlan(intent=INTENT_CREATE_FROM_SELLER_PRODUCT, confidence=0.93, batch_count=count, scenes=scenes, order_id=product_id, tool_plan=tool_plan, plan_id=plan_id, session_id=session_id, raw_message=text, requires_confirmation=requires_confirmation, reason="seller product mockup" if not requires_confirmation else "batch lớn hoặc có scene suy luận")

    if _has_mockup_intent(text):
        return AgentPlan(
            intent=INTENT_CREATE_FROM_SELLER_PRODUCT,
            confidence=0.86,
            batch_count=extract_count(text) or 1,
            missing_fields=["product_id"],
            clarifying_question="Dạ anh gửi giúp em product_id dạng A53636-28 để tạo mockup.",
            plan_id=plan_id,
            session_id=session_id,
            raw_message=text,
        )

    return AgentPlan(intent=INTENT_UNKNOWN, confidence=0.3, plan_id=plan_id, session_id=session_id, raw_message=text)


class Planner:
    def __init__(self):
        self.settings = load_settings()
        self.llm_key = self.settings.get("llm_api_key", "").strip()
        self.model = self.settings.get("llm_model", "gemini-3-flash-preview")
        self._client = None

    def _client_obj(self):
        if self._client is None and self.llm_key:
            self._client = genai.Client(api_key=self.llm_key)
        return self._client

    def plan(self, message: str, context: Dict[str, Any], use_llm: bool = False) -> AgentPlan:
        return deterministic_plan(message, context)

    def plan_with_llm(self, message: str, context: Dict[str, Any]) -> AgentPlan:
        try:
            client = self._client_obj()
            if not client:
                return deterministic_plan(message, context)
            prompt = {"user_message": message, "context": context, "tool_inventory": tool_inventory_for_prompt()}
            resp = client.models.generate_content(model=self.model, contents=PLANNER_SYSTEM + "\n\nINPUT JSON:\n" + json.dumps(prompt, ensure_ascii=False, default=str))
            txt = (resp.text or "").strip()
            txt = re.sub(r"^```json|```$", "", txt, flags=re.I | re.M).strip()
            data = json.loads(txt)
            return plan_from_dict(data, message, context)
        except Exception:
            return deterministic_plan(message, context)


def plan_from_dict(data: Dict[str, Any], message: str, context: Dict[str, Any]) -> AgentPlan:
    session_id = str(context.get("session", {}).get("id") or context.get("session_id") or "web")
    scenes = [SceneSchema(index=int(s.get("index") or i + 1), prompt=str(s.get("prompt") or ""), source=str(s.get("source") or "explicit"), camera=str(s.get("camera") or ""), lighting=str(s.get("lighting") or ""), background=str(s.get("background") or ""), constraints=list(s.get("constraints") or []), reference_image_id=s.get("reference_image_id")) for i, s in enumerate(data.get("scenes") or [])]
    steps = [ToolPlanStep(int(st.get("step") or i + 1), st.get("tool"), st.get("args") or {}) for i, st in enumerate(data.get("tool_plan") or [])]
    product_id = data.get("product_id") or data.get("order_id")
    return AgentPlan(intent=data.get("intent") or INTENT_UNKNOWN, confidence=float(data.get("confidence") or 0), requires_confirmation=bool(data.get("requires_confirmation")), reason=data.get("reason") or "", order_id=product_id, batch_count=data.get("batch_count"), scenes=scenes, missing_fields=list(data.get("missing_fields") or []), clarifying_question=data.get("clarifying_question"), tool_plan=steps, plan_id=data.get("plan_id") or f"plan_{uuid.uuid4().hex[:12]}", session_id=session_id, raw_message=message)
