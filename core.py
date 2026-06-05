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
    """Route message through LLM agent with tool-calling + session memory.

    Args:
        msg: User message text.
        chat_id: Session identifier for conversation memory.
                  Telegram: use chat.id. Web: use "web" or user id.

    Returns: dict with type, content, optional image/meta.
    """
    agent = get_agent()
    return agent.chat(chat_id, msg)


def clear_session(chat_id: str):
    agent = get_agent()
    agent.clear_session(chat_id)
