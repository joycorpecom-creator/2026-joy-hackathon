"""Context Builder — builds compact state for planner."""

from typing import Any, Dict, List
import burger_memory as mem
from .registry import TOOL_REGISTRY


def build_context(session_id: str, user_message: str = "") -> Dict[str, Any]:
    state = mem.get_state(session_id)
    profile = mem.get_profile(session_id)
    last_job = state.get("last_mockup_job") or {}
    recent = mem.search_memory(session_id, user_message, limit=3) if user_message else []
    return {
        "session": {
            "id": str(session_id),
            "current_order_id": state.get("current_order_id"),
            "current_job_id": state.get("current_job_id"),
            "last_plan_id": state.get("last_plan_id"),
        },
        "profile": profile,
        "recent_memory": recent,
        "last_mockup_job": last_job,
        "available_tools": TOOL_REGISTRY,
        "user_message": user_message,
    }
