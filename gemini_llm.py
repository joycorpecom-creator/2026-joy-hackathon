import json
import os
from typing import Any, Dict, List, Optional

import requests
from google import genai
from google.genai import types

from config_store import load_settings


class GeminiBrain:
    """LLM orchestrator using Gemini — speaks briefly, cheerfully, knows the flow."""

    def __init__(self):
        self.settings = load_settings()
        self.client = None
        self.model = self.settings.get("llm_model", "gemini-3-flash-preview")

    def _ensure_client(self):
        key = self.settings.get("llm_api_key", "").strip()
        if not key:
            raise RuntimeError("Gemini API key chưa set. Vào Settings tab nhé!")
        if not self.client:
            self.client = genai.Client(api_key=key)

    def _tool_declarations(self) -> List[types.Tool]:
        return [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name="fetch_order",
                        description="Get product & design info from a BurgerPrints order ID",
                        parameters={
                            "type": "object",
                            "properties": {
                                "order_id": {"type": "string", "description": "Order ID e.g. DEMO-1001 or real BP order"}
                            },
                            "required": ["order_id"],
                        },
                    ),
                    types.FunctionDeclaration(
                        name="generate_mockup",
                        description=(
                            "Create a lifestyle mockup image: composite original design onto a scene. "
                            "Call AFTER fetch_order returns valid data."
                        ),
                        parameters={
                            "type": "object",
                            "properties": {
                                "order_id": {"type": "string", "description": "Order ID from fetch_order"},
                                "scene_prompt": {
                                    "type": "string",
                                    "description": "Full scene description: model, setting, mood, lighting. "
                                                   "E.g. 'cozy cafe girl warm morning light, streetwear style'"
                                },
                            },
                            "required": ["order_id", "scene_prompt"],
                        },
                    ),
                ]
            )
        ]

    def chat(self, message: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        sys_prompt = (
            "You are J_agent, a cheerful BurgerMockup bot for BurgerPrints sellers. "
            "You reply SHORT and FRIENDLY. Know the flow: user gives order ID + scene desire. "
            "You call fetch_order to check order, then generate_mockup to create mockup. "
            "If only order given, ask what scene they want. If only scene, ask for order. "
            "If both given, do both tools in sequence. "
            "Use user's language (Vietnamese or English). Be happy, use light emojis like 😊👍 occasionally."
        )
        try:
            self._ensure_client()
        except RuntimeError as e:
            return {"error": str(e), "type": "text"}

        inputs = [
            types.Content(role="user", parts=[types.Part.from_text(text=sys_prompt)]),
            types.Content(role="model", parts=[types.Part.from_text(text="Got it! I'm J_agent. Let's make some mockups 😊")]),
            types.Content(role="user", parts=[types.Part.from_text(text=message)]),
        ]

        try:
            resp = self.client.models.generate_content(
                model=self.model,
                contents=inputs,
                config=types.GenerateContentConfig(
                    tools=self._tool_declarations(),
                    temperature=0.3,
                ),
            )
        except Exception as e:
            return {"error": str(e), "type": "text"}

        if not resp.candidates:
            return {"type": "text", "content": "Bot chưa phản hồi. Thử lại nhé!"}
        candidate = resp.candidates[0]
        if not candidate.content or not candidate.content.parts:
            return {"type": "text", "content": "Bot trả về trống 🤔"}

        text = ""
        func_calls = []
        for part in candidate.content.parts:
            if part.function_call:
                func_calls.append({
                    "name": part.function_call.name,
                    "args": dict(part.function_call.args),
                })
            if part.text:
                text += part.text

        if func_calls:
            return {"type": "function_calls", "text": text.strip(), "function_calls": func_calls}
        return {"type": "text", "content": text.strip()}

    def test_connection(self) -> Dict[str, Any]:
        try:
            self._ensure_client()
            resp = self.client.models.generate_content(
                model=self.model,
                contents="Reply with just 'OK'",
            )
            return {"ok": True, "model": self.model, "prov": self.settings.get("llm_provider")}
        except Exception as e:
            return {"ok": False, "error": str(e)}
