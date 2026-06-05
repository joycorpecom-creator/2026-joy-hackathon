"""Agent Orchestrator V2 — Planner → Validator → Executor → Verifier → Memory."""

import json
import time
import uuid
from typing import Any, Dict

import burger_memory as mem
from .context_builder import build_context
from .planner import Planner
from .plan_schema import AgentPlan, INTENT_CONFIRM_PLAN, INTENT_EDIT_PLAN, INTENT_CANCEL, needs_confirmation, plan_display_text
from .plan_validator import validate_plan, auto_fix_plan
from .executor import Executor
from .verifier import verify_mockup_result


class AgentOrchestrator:
    def __init__(self, agent):
        self._agent = agent  # BurgerMockupAgent
        self._planner = Planner()
        self._executor = Executor(agent)

    def process(self, message: str, session_id: str = "web") -> Dict[str, Any]:
        cid = str(session_id)

        # 1. Build context
        ctx = build_context(cid, message)

        # 2. Plan
        plan = self._planner.plan(message, ctx)

        # Handle special intents without plan flow
        if plan.intent == INTENT_CONFIRM_PLAN:
            return self._handle_confirm(cid, ctx)
        if plan.intent == INTENT_CANCEL:
            return {"type": "text", "content": "Dạ anh, em đã huỷ plan đang chờ."}
        if plan.intent == INTENT_EDIT_PLAN:
            # Future: edit plan scenes
            return {"type": "text", "content": "Dạ anh muốn sửa scene nào? (vd: 'sửa ảnh 3 thành...')"}
        if plan.missing_fields:
            self._save_plan(cid, plan, "waiting_confirmation")
            return {"type": "text", "content": plan.clarifying_question or "Dạ anh cần thêm thông tin để em xử lý."}

        # 3. Validate plan
        ok, errors = validate_plan(plan)
        if not ok:
            plan = auto_fix_plan(plan)
            ok2, errors2 = validate_plan(plan)
            if not ok2:
                return {"type": "text", "content": f"Dạ lỗi plan: {'; '.join(errors2)}"}

        # 4. Confirm gate
        if needs_confirmation(plan) and not plan.requires_confirmation:
            plan.requires_confirmation = True
        if plan.requires_confirmation:
            plan.status = "waiting_confirmation"
            self._save_plan(cid, plan, "waiting_confirmation")
            mem.update_state(cid, {"last_plan_id": plan.plan_id, "pending_plan": plan_json(plan)})
            preview = plan_display_text(plan)
            return {"type": "plan_preview", "content": preview, "plan_id": plan.plan_id}

        # 5. Execute
        result = self._executor.execute(plan)
        plan.status = "completed"

        # 6. Verify
        if result.get("type") == "mockup":
            verified = verify_mockup_result(result)
            if not verified["ok"]:
                result["content"] += f"\n(Đã kiểm tra: {'; '.join(verified['problems'])})"

        # 7. Save context
        self._remember_result(cid, plan, result, message)
        self._save_plan(cid, plan, "completed")

        return result

    def _handle_confirm(self, cid: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        state = mem.get_state(cid)
        pending = state.get("pending_plan") or {}
        if not pending:
            return {"type": "text", "content": "Dạ hiện không có plan nào đang chờ anh ạ."}
        plan = plan_from_json(pending)
        plan.requires_confirmation = False
        plan.status = "confirmed"
        result = self._executor.execute(plan)
        plan.status = "completed"
        self._remember_result(cid, plan, result, plan.raw_message)
        self._save_plan(cid, plan, "completed")
        mem.update_state(cid, {"pending_plan": None})
        return result

    def _save_plan(self, cid: str, plan: AgentPlan, status: str):
        plan.status = status
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
        index=s.get("index"),
        prompt=s.get("prompt"),
        source=s.get("source", "explicit"),
        camera=s.get("camera", ""),
        lighting=s.get("lighting", ""),
        background=s.get("background", ""),
        constraints=s.get("constraints", []),
        reference_image_id=s.get("reference_image_id"),
    ) for s in data.get("scenes") or []]
    steps = [ToolPlanStep(s["step"], s["tool"], s.get("args", {})) for s in data.get("tool_plan") or []]
    return AgentPlan(
        intent=data.get("intent"),
        confidence=data.get("confidence", 0),
        requires_confirmation=data.get("requires_confirmation", False),
        reason=data.get("reason", ""),
        order_id=data.get("order_id"),
        batch_count=data.get("batch_count"),
        scenes=scenes,
        missing_fields=data.get("missing_fields", []),
        clarifying_question=data.get("clarifying_question"),
        tool_plan=steps,
        plan_id=data.get("plan_id"),
        session_id=data.get("session_id", ""),
        raw_message=data.get("raw_message", ""),
    )
