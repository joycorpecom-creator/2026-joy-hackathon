"""Agent Orchestrator V2 — Planner → Validator → Executor → Verifier → Memory."""

from typing import Any, Dict
import re

import burger_memory as mem
from .context_builder import build_context
from .planner import Planner
from .plan_schema import AgentPlan, INTENT_CONFIRM_PLAN, INTENT_EDIT_PLAN, INTENT_CANCEL, INTENT_HELP, INTENT_UNKNOWN, needs_confirmation, plan_display_text
from .plan_validator import validate_plan, auto_fix_plan
from .executor import Executor
from .verifier import verify_mockup_result


def resolve_image_reference(text: str, context: dict) -> str:
    """Resolve 'ảnh 2' from text to image_id/url in last_mockup_job."""
    m = re.search(r"ảnh\s*(\d{1,2})", text or "", re.I)
    if not m:
        return ""
    idx = int(m.group(1))
    imgs = ((context.get("last_mockup_job") or {}).get("images") or [])
    for im in imgs:
        if int(im.get("index") or -1) == idx:
            return im.get("image_id") or im.get("id") or im.get("url", "")
    return ""


class AgentOrchestrator:
    def __init__(self, agent):
        self._agent = agent
        self._planner = Planner()
        self._executor = Executor(agent)

    def process(self, message: str, session_id: str = "web") -> Dict[str, Any]:
        cid = str(session_id)
        ctx = build_context(cid, message)
        plan = self._planner.plan(message, ctx)

        if plan.intent == INTENT_CONFIRM_PLAN:
            return self._handle_confirm(cid, ctx)
        if plan.intent == INTENT_CANCEL:
            mem.update_state(cid, {"pending_plan": None})
            return {"type": "text", "content": "Dạ anh, em đã huỷ plan đang chờ."}
        if plan.intent == INTENT_EDIT_PLAN:
            return self._handle_edit_plan(cid, message)
        if plan.intent == INTENT_HELP:
            return {"type": "text", "content": "Dạ em là JOY Mockup Agent, chuyên tạo mockup lifestyle cho sản phẩm BurgerPrints. Anh có thể gửi order ID + mô tả scene, em sẽ tạo ảnh mockup cho anh ạ."}
        if plan.intent == INTENT_UNKNOWN:
            return self._agent.chat(cid, message)
        if plan.missing_fields:
            self._save_plan(cid, plan, "waiting_info")
            return {"type": "text", "content": plan.clarifying_question or "Dạ anh cần thêm thông tin để em xử lý."}

        ok, errors = validate_plan(plan)
        if not ok:
            plan = auto_fix_plan(plan)
            ok2, errors2 = validate_plan(plan)
            if not ok2:
                return {"type": "text", "content": f"Dạ lỗi plan: {'; '.join(errors2)}"}

        from .planner import _wants_execute_now
        if needs_confirmation(plan) and not _wants_execute_now(plan.raw_message):
            plan.requires_confirmation = True
        if plan.requires_confirmation:
            plan.status = "waiting_confirmation"
            self._save_plan(cid, plan, "waiting_confirmation")
            mem.update_state(cid, {"last_plan_id": plan.plan_id, "pending_plan": plan_json(plan)})
            return {"type": "plan_preview", "content": plan_display_text(plan), "plan_id": plan.plan_id, "plan": plan.to_dict()}

        result = self._executor.execute(plan)
        plan.status = "completed"
        self._postprocess_result(cid, plan, result, message)
        return result

    def _handle_confirm(self, cid: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        pending = (mem.get_state(cid) or {}).get("pending_plan") or {}
        if not pending:
            return {"type": "text", "content": "Dạ hiện không có plan nào đang chờ anh ạ."}
        plan = plan_from_json(pending)
        plan.requires_confirmation = False
        plan.status = "confirmed"
        result = self._executor.execute(plan)
        plan.status = "completed"
        self._postprocess_result(cid, plan, result, plan.raw_message)
        mem.update_state(cid, {"pending_plan": None})
        return result

    def _handle_edit_plan(self, cid: str, message: str) -> Dict[str, Any]:
        import re
        pending = (mem.get_state(cid) or {}).get("pending_plan") or {}
        if not pending or not pending.get("scenes"):
            return {"type": "text", "content": "Dạ hiện không có plan nào để sửa ạ."}
        m = re.search(r"ảnh\s*(\d{1,2})\s*(thành|làm|vẽ|thay|đổi\s*thành)\s*(.+)", message, re.I)
        if not m:
            return {"type": "text", "content": "Dạ anh nói rõ: 'sửa ảnh N thành mô tả scene mới' ạ."}
        idx = int(m.group(1))
        new_prompt = m.group(3).strip().rstrip(".")
        scenes = pending.get("scenes", [])
        for s in scenes:
            if s.get("index") == idx:
                s["prompt"] = new_prompt
                s["source"] = "explicit"
                break
        else:
            return {"type": "text", "content": f"Dạ hiện plan có {len(scenes)} ảnh, anh muốn sửa ảnh 1 đến {len(scenes)} ạ."}
        pending["scenes"] = scenes
        mem.update_state(cid, {"pending_plan": pending})
        from .plan_schema import plan_display_text
        from .plan_validator import validate_plan
        fixed = plan_from_json(pending)
        fixed.raw_message = message
        fixed.reason = "plan edited by user"
        preview = plan_display_text(fixed)
        ok, errors = validate_plan(fixed)
        if not ok:
            return {"type": "text", "content": f"Dạ plan sau sửa có vấn đề: {'; '.join(errors)}"}
        return {"type": "plan_preview", "content": preview, "plan_id": fixed.plan_id, "plan": fixed.to_dict(), "note": f"Đã sửa ảnh {idx} thành: {new_prompt}"}

    def _postprocess_result(self, cid: str, plan: AgentPlan, result: Dict[str, Any], user_msg: str):
        if result.get("type") == "mockup":
            verified = verify_mockup_result(result)
            result["verification"] = verified
            if not verified["ok"]:
                result["content"] += f"\n(Đã kiểm tra: {'; '.join(verified['problems'])})"
        self._remember_result(cid, plan, result, user_msg)
        self._save_plan(cid, plan, "completed")

    def _save_plan(self, cid: str, plan: AgentPlan, status: str):
        plan.status = status
        mem.save_agent_plan(cid, plan.to_dict(), status=status)
        mem.remember_event(cid, "agent_plan", plan.to_dict())

    def _remember_result(self, cid: str, plan: AgentPlan, result: Dict[str, Any], user_msg: str):
        mem.record_turn(cid, user_msg, result.get("content", ""))
        mem.update_state(cid, {
            "current_order_id": plan.order_id,
            "current_job_id": result.get("job_id"),
            "last_plan_id": plan.plan_id,
            "last_mockup_job": result if result.get("type") == "mockup" else None,
        })


def plan_json(plan: AgentPlan) -> dict:
    return plan.to_dict()


def plan_from_json(data: dict) -> AgentPlan:
    from .plan_schema import SceneSchema, ToolPlanStep
    scenes = [SceneSchema(
        index=s.get("index"), prompt=s.get("prompt"), source=s.get("source", "explicit"),
        camera=s.get("camera", ""), lighting=s.get("lighting", ""), background=s.get("background", ""),
        constraints=s.get("constraints", []), reference_image_id=s.get("reference_image_id"),
    ) for s in data.get("scenes") or []]
    steps = [ToolPlanStep(s["step"], s["tool"], s.get("args", {})) for s in data.get("tool_plan") or []]
    return AgentPlan(
        intent=data.get("intent"), confidence=data.get("confidence", 0),
        requires_confirmation=data.get("requires_confirmation", False), reason=data.get("reason", ""),
        order_id=data.get("order_id"), batch_count=data.get("batch_count"), scenes=scenes,
        missing_fields=data.get("missing_fields", []), clarifying_question=data.get("clarifying_question"),
        tool_plan=steps, plan_id=data.get("plan_id"), session_id=data.get("session_id", ""),
        raw_message=data.get("raw_message", ""),
    )
