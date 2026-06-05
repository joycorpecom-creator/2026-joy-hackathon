"""Core handler — JOY Mockup Agent V2: plan-first orchestration with legacy fallback."""

from typing import Dict, Any

from agent import BurgerMockupAgent
from agent_runtime.orchestrator import AgentOrchestrator

_agent: BurgerMockupAgent = None
_orchestrator: AgentOrchestrator = None


def get_agent() -> BurgerMockupAgent:
    global _agent
    if _agent is None:
        _agent = BurgerMockupAgent()
    return _agent


def get_orchestrator() -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator(get_agent())
    return _orchestrator


async def handle_message(msg: str, chat_id: str = "web") -> Dict[str, Any]:
    """Route message through V2 orchestrator; `/new` resets current chat."""
    text = (msg or "").strip()
    cid = str(chat_id or "web")

    if text == "/new" or text.startswith("/new "):
        agent = get_agent()
        agent.clear_session(cid)
        try:
            import burger_memory as mem
            path = mem.state_path(cid)
            if path.exists():
                path.unlink()
        except Exception:
            pass
        return {
            "type": "text",
            "content": "Dạ anh, em đã mở đoạn chat mới. Context cũ và trạng thái tạm đã được reset."
        }

    # V2: context → planner → validator → executor → verifier.
    try:
        return get_orchestrator().process(text, cid)
    except Exception as e:
        print(f">>> V2_ORCHESTRATOR_ERROR {e}", flush=True)
        # Legacy LLM fallback for unknown/edge cases.
        return get_agent().chat(cid, text)


def clear_session(chat_id: str):
    agent = get_agent()
    agent.clear_session(chat_id)
