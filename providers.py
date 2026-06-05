import io
import os
import time
import re
from pathlib import Path
from typing import Optional, Dict, Any, Union

from PIL import Image

TEMPLATES_DIR = Path(__file__).parent / "templates" / "mockup"
PRODUCT_ALIAS = {
    "tumbler": "tumbler_premium_ad",
    "bottle": "tumbler_premium_ad",
    "cup": "tumbler_premium_ad",
    "mug": "tumbler_premium_ad",
    "flask": "tumbler_premium_ad",
    "thermos": "tumbler_premium_ad",
}
FALLBACK_TEMPLATE = "generic_lifestyle"


def _detect_product_category(product_name: str) -> str:
    name_lower = product_name.lower()
    for keyword, template in PRODUCT_ALIAS.items():
        if keyword in name_lower:
            return template
    return FALLBACK_TEMPLATE


def _load_template(category: str) -> Optional[str]:
    path = TEMPLATES_DIR / f"{category}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    path = TEMPLATES_DIR / f"{FALLBACK_TEMPLATE}.md"
    return path.read_text(encoding="utf-8") if path.exists() else None


GEMINI_IMAGE_MODELS = [
    "gemini-3.1-flash-image",
    "nano-banana-pro-preview",
    "gemini-3-pro-image",
    "gemini-3-pro-image-preview",
]


def _load_gemini_client():
    """Load Gemini client. Returns (client, model) or (None, None)."""
    from google import genai
    from config_store import load_settings
    s = load_settings()
    key = s.get("llm_api_key", "").strip()
    if not key or "..." in key:
        return None, None
    client = genai.Client(api_key=key)
    # Try models in order, pick first available
    for model_name in GEMINI_IMAGE_MODELS:
        try:
            client.models.get(model=f"models/{model_name}")
            return client, model_name
        except Exception:
            continue
    # Fallback: try the list
    try:
        for m in client.models.list():
            name = m.name
            if "image" in name and "generateContent" in (m.supported_actions or []):
                return client, name
    except Exception:
        pass
    return client, GEMINI_IMAGE_MODELS[0]  # best guess


def build_scene_prompt(
    user_prompt: str,
    product_name: str,
    color_name: str,
) -> str:
    """Build full scene prompt from template + product context."""
    category = _detect_product_category(product_name)
    template_raw = _load_template(category)

    if category != FALLBACK_TEMPLATE and template_raw:
        text = re.sub(r'^---.*?---\s*', '', template_raw, flags=re.DOTALL).strip()
        return (
            text.replace("{product_name}", product_name)
            .replace("{color_name}", color_name)
            + f"\n\nUser scene/refinement request:\n{user_prompt or 'premium ecommerce ad mockup'}"
        )

    if template_raw and "{user_scene}" in template_raw:
        text = re.sub(r'^---.*?---\s*', '', template_raw, flags=re.DOTALL).strip()
        return (
            text.replace("{product_name}", product_name)
            .replace("{color_name}", color_name)
            .replace("{user_scene}", user_prompt or "professional lifestyle setting")
        )

    return (
        "Lifestyle ecommerce product mockup photography. "
        f"Product: {product_name}, color: {color_name}. "
        f"Scene request: {user_prompt}. "
        "No brand logos, no celebrity faces, clean listing-ready image, "
        "front print area visible and unobstructed."
    )


def try_generate_ai_scene(prompt: str, product_color: str) -> Optional[Image.Image]:
    """Generate AI lifestyle scene using Gemini image models (gemini-3.1-flash-image / nano-banana-pro-preview).

    Uses same GEMINI_API_KEY already configured. No extra key needed."""
    from google import genai
    from google.genai import types
    from config_store import load_settings

    s = load_settings()
    key = s.get("llm_api_key", "").strip()
    if not key or "..." in key:
        print("Gemini API key missing", flush=True)
        return None

    client = genai.Client(api_key=key)

    # Use Gemini/Nano Banana image model directly. Avoid pre-test call to save quota.
    model = (s.get("image_model") or s.get("llm_image_model") or "gemini-3.1-flash-image").strip()
    if model.startswith("models/"):
        model_ref = model
    else:
        model_ref = f"models/{model}"
    print(f"Using Gemini image model: {model_ref}", flush=True)

    # Custom prompt: shorter prompt for faster generation.
    scene_prompt = (
        f"Generate a photorealistic lifestyle product mockup photograph. "
        f"Style: {prompt[:800]}. Ultra realistic, 8k detail. "
        f"Leave the product area clear for composite overlay. "
        f"No text, no watermarks."
    )

    try:
        resp = client.models.generate_content(
            model=model_ref,
            contents=scene_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
                safety_settings=[
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
                    ),
                ],
            ),
        )

        for part in resp.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type and "image" in part.inline_data.mime_type:
                img = Image.open(io.BytesIO(part.inline_data.data)).convert("RGBA")
                print(f"Gemini image generated: {img.size}, model={model}", flush=True)
                return img

        print("Gemini response has no image data, falling back", flush=True)
        return None

    except Exception as e:
        print(f"Gemini image generation error: {e}", flush=True)
        return None


def try_generate_lifestyle_mockup(
    product_image: Union[bytes, str, Path],
    prompt: str,
    mime_type: str = "image/png",
) -> Optional[Image.Image]:
    """Generate final lifestyle mockup in ONE Gemini pass.

    Sends BP product/base mockup as inline image reference + preservation prompt.
    No background-only generation, no rectangle compositing.
    """
    from google import genai
    from google.genai import types
    from config_store import load_settings

    s = load_settings()
    key = s.get("llm_api_key", "").strip()
    if not key or "..." in key:
        print("Gemini API key missing", flush=True)
        return None

    if isinstance(product_image, Path):
        image_bytes = product_image.read_bytes()
    elif isinstance(product_image, str):
        image_bytes = Path(product_image).read_bytes()
    else:
        image_bytes = product_image

    client = genai.Client(api_key=key)
    model = (s.get("image_model") or s.get("llm_image_model") or "gemini-3.1-flash-image").strip()
    model_ref = model if model.startswith("models/") else f"models/{model}"
    print(f"Using Gemini lifestyle mockup model: {model_ref}", flush=True)

    try:
        resp = client.models.generate_content(
            model=model_ref,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                types.Part.from_text(text=prompt),
            ],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
                safety_settings=[
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
                    ),
                ],
            ),
        )
        for part in resp.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type and "image" in part.inline_data.mime_type:
                img = Image.open(io.BytesIO(part.inline_data.data)).convert("RGBA")
                print(f"Gemini lifestyle mockup generated: {img.size}, model={model}", flush=True)
                return img
        print("Gemini lifestyle response has no image data", flush=True)
        return None
    except Exception as e:
        print(f"Gemini lifestyle mockup error: {e}", flush=True)
        return None
