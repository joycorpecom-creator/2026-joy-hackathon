"""Core handler: routes user messages through BurgerMockupAgent (tool-calling LLM)."""

from typing import Dict, Any

from agent import BurgerMockupAgent

# Singleton agent (shared across requests)
_agent: BurgerMockupAgent = None


def get_agent() -> BurgerMockupAgent:
    global _agent
    if _agent is None:
        _agent = BurgerMockupAgent()
    return _agent


async def handle_message(msg: str, chat_id: str = "web") -> Dict[str, Any]:
    """Route message through BurgerMockupAgent; `/new` resets current chat."""
    text = (msg or "").strip()
    cid = str(chat_id or "web")

    if text == "/new" or text.startswith("/new "):
        agent = get_agent()
        agent.clear_session(cid)
        try:
            from design_store import clear_design
            clear_design(cid)
        except Exception:
            pass
        try:
            import burger_memory as mem
            path = mem.state_path(cid)
            if path.exists():
                path.unlink()
        except Exception:
            pass
        return {
            "type": "text",
            "content": "Dạ anh, em đã mở đoạn chat mới. Context cũ, file in đang giữ và trạng thái tạm đã được reset."
        }

    agent = get_agent()
    return agent.chat(cid, text)


def clear_session(chat_id: str):
    agent = get_agent()
    agent.clear_session(chat_id)
