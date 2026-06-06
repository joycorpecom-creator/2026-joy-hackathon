"""
Planner — reason first, no tool execution.
Produces structured AgentPlan from natural language + context + tool inventory.
"""

import json
import re
import uuid
from typing import Any, Dict, Optional

from google import genai
from config_store import load_settings
from .plan_schema import (
    AgentPlan, SceneSchema, ToolPlanStep,
    INTENT_CREATE_BATCH, INTENT_CREATE_SINGLE, INTENT_REFINE,
    INTENT_LIST_ORDERS, INTENT_ORDER_INFO, INTENT_SYNC_LARK,
    INTENT_CONFIRM_PLAN, INTENT_EDIT_PLAN, INTENT_CANCEL,
    INTENT_GREETING, INTENT_HELP, INTENT_UNKNOWN,
)
from .scene_expander import extract_order_ids, extract_count, expand_scenes
from .registry import tool_inventory_for_prompt

CONFIRM_WORDS = ["ok", "oke", "okay", "đồng ý", "tạo đi", "tạo luôn", "chạy đi", "confirm", "yes"]
EXECUTE_NOW_WORDS = ["tạo luôn", "chạy luôn", "không cần hỏi", "khỏi hỏi", "execute now"]

PLANNER_SYSTEM = """
You are JOY Mockup Planner.
You DO NOT execute tools. You only analyze user request and output valid JSON plan.

Rules:
1. Always inspect session context and available tools.
2. Identify intent.
3. Resolve order_id from message or session.current_order_id.
4. Resolve image references like "ảnh 2" from last_mockup_job.images.
5. For batch_count >= 4, requires_confirmation=true unless user explicitly says execute now.
6. If scenes are vague/grouped, expand into concrete diverse scenes.
7. If required info missing, set missing_fields and clarifying_question.
8. Output JSON only, no markdown.

JSON shape:
{
  "intent": "create_mockup_batch|create_mockup_single|refine_mockup|list_orders|get_order_info|sync_lark|confirm_plan|edit_plan|cancel|greeting|help|unknown",
  "confidence": 0.0,
  "requires_confirmation": true,
  "reason": "short reason",
  "order_id": "... or null",
  "batch_count": 5,
  "scenes": [{"index":1,"prompt":"...","source":"explicit|grouped|inferred|reference","camera":"","lighting":"","background":"","constraints":[],"reference_image_id":null}],
  "missing_fields": [],
  "clarifying_question": null,
  "tool_plan": [{"step":1,"tool":"get_order_info","args":{"order_id":"..."}}]
}
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


def _has_order_info_intent(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in ["thông tin order", "xem order", "order info", "chi tiết order", "lấy order"])


def _has_list_order_intent(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in ["danh sách order", "toàn bộ order", "tất cả order", "order id", "order_id", "đơn hàng gần đây"])


def _has_refine_intent(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in ["sửa ảnh", "đổi ảnh", "chỉnh ảnh", "refine", "làm lại ảnh", "giống ảnh", "ảnh 1", "ảnh 2", "ảnh 3", "ảnh 4", "ảnh 5"])


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
    """Reliable local planner for known business intents."""
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

    order_ids = extract_order_ids(text)
    current_order = (context.get("session") or {}).get("current_order_id") or context.get("current_order_id")
    order_id = order_ids[0] if order_ids else current_order

    if _has_order_info_intent(text) and order_id:
        return AgentPlan(intent=INTENT_ORDER_INFO, confidence=0.92, order_id=order_id, tool_plan=[ToolPlanStep(1, "get_order_info", {"order_id": order_id})], plan_id=plan_id, session_id=session_id, raw_message=text)

    if _has_list_order_intent(text) and not _has_mockup_intent(text):
        return AgentPlan(intent=INTENT_LIST_ORDERS, confidence=0.9, tool_plan=[ToolPlanStep(1, "list_orders", {})], plan_id=plan_id, session_id=session_id, raw_message=text)

    if any(k in lower for k in ["sửa ảnh", "đổi ảnh", "chỉnh ảnh", "edit scene"]):
        pending = context.get("pending_plan") or {}
        if pending and pending.get("scenes"):
            return AgentPlan(intent=INTENT_EDIT_PLAN, confidence=0.92, plan_id=plan_id, session_id=session_id, raw_message=text)

    if _has_refine_intent(text) and not order_ids:
        image_id = _image_ref(text, context)
        if image_id:
            step = ToolPlanStep(1, "refine_mockup", {"image_id": image_id, "instruction": text})
            return AgentPlan(intent=INTENT_REFINE, confidence=0.88, tool_plan=[step], plan_id=plan_id, session_id=session_id, raw_message=text)

    if _has_order_info_intent(text) and order_id:
        return AgentPlan(intent=INTENT_ORDER_INFO, confidence=0.92, order_id=order_id, tool_plan=[ToolPlanStep(1, "get_order_info", {"order_id": order_id})], plan_id=plan_id, session_id=session_id, raw_message=text)

    if _has_mockup_intent(text):
        count = extract_count(text) or 1
        if not order_id:
            return AgentPlan(
                intent=INTENT_CREATE_BATCH if count > 1 else INTENT_CREATE_SINGLE,
                confidence=0.86,
                batch_count=count,
                missing_fields=["order_id"],
                clarifying_question="Dạ anh gửi giúp em order_id cần tạo mockup.",
                plan_id=plan_id,
                session_id=session_id,
                raw_message=text,
            )
        scenes = expand_scenes(text, count=count)
        intent = INTENT_CREATE_BATCH if count > 1 else INTENT_CREATE_SINGLE
        requires_confirmation = (count >= 4 or any(s.source != "explicit" for s in scenes)) and not _wants_execute_now(text)
        tool_plan = [
            ToolPlanStep(1, "get_order_info", {"order_id": order_id}),
            ToolPlanStep(2, "create_mockup_batch", {"order_id": order_id, "scenes": [s.to_dict() for s in scenes]}),
        ]
        return AgentPlan(
            intent=intent,
            confidence=0.93,
            requires_confirmation=requires_confirmation,
            reason="batch lớn hoặc có scene suy luận" if requires_confirmation else "request đủ rõ để execute",
            order_id=order_id,
            batch_count=count,
            scenes=scenes,
            tool_plan=tool_plan,
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
        # deterministic planner is primary; LLM planner can be enabled later.
        plan = deterministic_plan(message, context)
        return plan

    def plan_with_llm(self, message: str, context: Dict[str, Any]) -> AgentPlan:
        """Optional LLM planner. Kept isolated; deterministic fallback always available."""
        try:
            client = self._client_obj()
            if not client:
                return deterministic_plan(message, context)
            prompt = {
                "user_message": message,
                "context": context,
                "tool_inventory": tool_inventory_for_prompt(),
            }
            resp = client.models.generate_content(
                model=self.model,
                contents=PLANNER_SYSTEM + "\n\nINPUT JSON:\n" + json.dumps(prompt, ensure_ascii=False, default=str),
            )
            txt = (resp.text or "").strip()
            txt = re.sub(r"^```json|```$", "", txt, flags=re.I | re.M).strip()
            data = json.loads(txt)
            return plan_from_dict(data, message, context)
        except Exception:
            return deterministic_plan(message, context)


def plan_from_dict(data: Dict[str, Any], message: str, context: Dict[str, Any]) -> AgentPlan:
    session_id = str(context.get("session", {}).get("id") or context.get("session_id") or "web")
    scenes = [SceneSchema(
        index=int(s.get("index") or i + 1),
        prompt=str(s.get("prompt") or ""),
        source=str(s.get("source") or "explicit"),
        camera=str(s.get("camera") or ""),
        lighting=str(s.get("lighting") or ""),
        background=str(s.get("background") or ""),
        constraints=list(s.get("constraints") or []),
        reference_image_id=s.get("reference_image_id"),
    ) for i, s in enumerate(data.get("scenes") or [])]
    steps = [ToolPlanStep(int(st.get("step") or i + 1), st.get("tool"), st.get("args") or {}) for i, st in enumerate(data.get("tool_plan") or [])]
    return AgentPlan(
        intent=data.get("intent") or INTENT_UNKNOWN,
        confidence=float(data.get("confidence") or 0),
        requires_confirmation=bool(data.get("requires_confirmation")),
        reason=data.get("reason") or "",
        order_id=data.get("order_id"),
        batch_count=data.get("batch_count"),
        scenes=scenes,
        missing_fields=list(data.get("missing_fields") or []),
        clarifying_question=data.get("clarifying_question"),
        tool_plan=steps,
        plan_id=data.get("plan_id") or f"plan_{uuid.uuid4().hex[:12]}",
        session_id=session_id,
        raw_message=message,
    )
