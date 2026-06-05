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


def _format_batch_response(result: Dict[str, Any], user_message: str, chat_id: str) -> Dict[str, Any]:
    """Convert create_mockup_from_order batch tool result into API response."""
    mockups = result.get("mockups") or []
    images = [
        {
            "url": m.get("mockup_url", ""),
            "scene": m.get("scene", ""),
            "product": m.get("product", ""),
            "provider": m.get("provider", ""),
            "integrity": m.get("integrity", 0),
            "cost": m.get("cost", ""),
        }
        for m in mockups if m.get("mockup_url")
    ]
    product = (mockups[0].get("product", "") if mockups else result.get("product", ""))
    color = (mockups[0].get("color", "") if mockups else result.get("color", ""))
    final_text = f"Dạ anh, em đã tạo {len(images)} mockup cho {product} ({color})."
    for idx, im in enumerate(images, start=1):
        final_text += f"\n• Ảnh {idx}: {im.get('scene','')}"

    try:
        import burger_memory as mem
        mem.record_turn(str(chat_id), user_message, final_text)
        for m in mockups:
            mem.record_mockup(str(chat_id), m, scene=m.get("scene", ""))
    except Exception:
        pass

    return {
        "type": "mockup",
        "content": final_text,
        "images": images,
        "meta": {"product": product, "color": color, "count": len(images), "order": result.get("order_id", "")},
    }


async def handle_message(msg: str, chat_id: str = "web") -> Dict[str, Any]:
    """Route message through BurgerMockupAgent; `/new` resets current chat."""
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

    agent = get_agent()

    # Deterministic batch parser: natural language list -> exact scenes.
    # This prevents LLM tool-call arg loss where only the last scene is passed.
    try:
        from batch_parser import try_parse_batch_mockup
        parsed = try_parse_batch_mockup(text)
        if parsed and parsed.get("count", 0) > 1:
            print(f">>> BATCH_PRE_ROUTER order={parsed['order_id']} scenes={parsed['scenes']}", flush=True)
            result = agent._execute_tool("create_mockup_from_order", {
                "order_id": parsed["order_id"],
                "scene": ", ".join(parsed["scenes"]),
            })
            if result.get("error"):
                return {"type": "text", "content": f"Dạ, có lỗi khi tạo batch mockup: {result['error']}"}
            # Single result fallback should not happen for count>1, but handle safely.
            if result.get("type") != "mockup_batch":
                result = {"type": "mockup_batch", "order_id": parsed["order_id"], "mockups": [result]}
            return _format_batch_response(result, text, cid)
    except Exception as e:
        print(f">>> BATCH_PRE_ROUTER_ERROR {e}", flush=True)
        # Fall back to LLM path.

    return agent.chat(cid, text)


def clear_session(chat_id: str):
    agent = get_agent()
    agent.clear_session(chat_id)
