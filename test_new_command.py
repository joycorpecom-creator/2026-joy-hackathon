import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_new_command_resets_agent_session_design_and_state():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        session_file = root / "memory" / "session_web.json"
        state_file = root / "memory" / "state" / "web.json"
        upload_dir = root / "uploads" / "web"
        session_file.parent.mkdir(parents=True)
        state_file.parent.mkdir(parents=True)
        upload_dir.mkdir(parents=True)
        session_file.write_text("[]")
        state_file.write_text(json.dumps({"current_product": "USG5000"}))
        (upload_dir / "abc_meta.json").write_text("{}")

        import agent
        import burger_memory
        import design_store
        import core

        with patch.object(agent, "MEMORY_DIR", root / "memory"), \
             patch.object(burger_memory, "MEMORY_DIR", root / "memory"), \
             patch.object(burger_memory, "STATE_DIR", root / "memory" / "state"), \
             patch.object(design_store, "UPLOAD_DIR", root / "uploads"):
            a = agent.BurgerMockupAgent()
            a.sessions["web"] = ["old"]
            with patch.object(core, "get_agent", return_value=a):
                result = asyncio.run(core.handle_message("/new", chat_id="web"))

            assert result["type"] == "text"
            assert "đoạn chat mới" in result["content"].lower()
            assert "web" not in a.sessions
            assert not session_file.exists()
            assert not state_file.exists()
            assert not upload_dir.exists()
