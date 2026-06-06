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


QUALITY_DIRECTIVE = (
    "\n\nQUALITY DIRECTIVE:\n"
    "Create a premium ecommerce lifestyle mockup, not a flat product cutout. "
    "Use realistic camera optics, natural shadows, correct perspective, believable contact points, "
    "clean commercial lighting, sharp product edges, and listing-ready composition. "
    "Keep the original product/design readable and undistorted. "
    "Avoid extra text, misspelled text, watermark, distorted hands, warped fabric, duplicate products, messy clutter."
)


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
    product_type: str = "",
) -> str:
    """Build full scene prompt from category resolver + prompt library.

    Fallback-safe: if prompt_library fails, use older markdown templates.
    """
    try:
        from agent_runtime.prompt_library import build_mockup_prompt
        info = build_mockup_prompt(
            product_name=product_name,
            product_type=product_type,
            color=color_name,
            user_scene=user_prompt,
        )
        return info["prompt"]
    except Exception:
        pass

    category = _detect_product_category(product_name)
    template_raw = _load_template(category)

    if category != FALLBACK_TEMPLATE and template_raw:
        text = re.sub(r'^---.*?---\s*', '', template_raw, flags=re.DOTALL).strip()
        return (
            text.replace("{product_name}", product_name)
            .replace("{color_name}", color_name)
            + f"\n\nUser scene/refinement request:\n{user_prompt or 'premium ecommerce ad mockup'}"
            + QUALITY_DIRECTIVE
        )

    if template_raw and "{user_scene}" in template_raw:
        text = re.sub(r'^---.*?---\s*', '', template_raw, flags=re.DOTALL).strip()
        return (
            text.replace("{product_name}", product_name)
            .replace("{color_name}", color_name)
            .replace("{user_scene}", user_prompt or "professional lifestyle setting")
            + QUALITY_DIRECTIVE
        )

    return (
        "Lifestyle ecommerce product mockup photography. "
        f"Product: {product_name}, color: {color_name}. "
        f"Scene request: {user_prompt}. "
        "No brand logos, no celebrity faces, clean listing-ready image, "
        "front print area visible and unobstructed." + QUALITY_DIRECTIVE
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


def try_generate_dual_input_lifestyle_mockup(
    design_image: Union[bytes, str, Path],
    product_image: Union[bytes, str, Path],
    prompt: str,
) -> Optional[Image.Image]:
    """Generate ONE-PASS lifestyle mockup from TWO inputs: print design + product.

    Sends both images to Gemini with explicit roles:
    - Image 1 = the PRINT DESIGN (exact artwork, preserve 100%)
    - Image 2 = the BLANK GARMENT product mockup (base product, apply design on it)
    Gemini generates the final lifestyle mockup with design applied to product.

    Falls back quietly on any error.
    """
    from google import genai
    from google.genai import types
    from config_store import load_settings

    s = load_settings()
    key = s.get("llm_api_key", "").strip()
    if not key or "..." in key:
        print("Gemini API key missing", flush=True)
        return None

    def _read(path_or_bytes) -> bytes:
        if isinstance(path_or_bytes, Path):
            return path_or_bytes.read_bytes()
        if isinstance(path_or_bytes, str):
            return Path(path_or_bytes).read_bytes()
        return path_or_bytes

    design_bytes = _read(design_image)
    product_bytes = _read(product_image)

    client = genai.Client(api_key=key)
    model = (s.get("image_model") or s.get("llm_image_model") or "gemini-3.1-flash-image").strip()
    model_ref = model if model.startswith("models/") else f"models/{model}"
    print(f"Using Gemini dual-input mockup model: {model_ref}", flush=True)

    dual_prompt = (
        "You are a professional ecommerce mockup artist. I give you TWO images:\n\n"
        "IMAGE 1 (first image) = the PRINT DESIGN. This is the exact artwork to be printed on the product. "
        "You MUST preserve this design 100% — do NOT change colors, crop, distort, or rewrite any text.\n\n"
        "IMAGE 2 (second image) = the BLANK GARMENT/BASE PRODUCT. This is the product mockup without any print applied.\n\n"
        f"TASK: Generate a photorealistic lifestyle mockup of a model wearing/using the product from IMAGE 2, "
        f"with the print design from IMAGE 1 applied EXACTLY onto the product's print area. The design must appear "
        f"undistorted, full-color, and properly placed on the product.\n\n"
        f"Scene/style: {prompt[:1000]}\n\n"
        "CRITICAL RULES:\n"
        "- Preserve the exact design artwork 100% — no changes to colors, text, logos, or layout.\n"
        "- The product must match IMAGE 2 exactly (same color, model, shape).\n"
        "- Photorealistic quality, professional lighting, suitable for Etsy/Amazon listing.\n"
        "- No text/watermarks added by you.\n"
        "- No real brand logos or celebrity faces (do not hallucinate people on the design).\n"
        "- Output single image ≥1500×1500 resolution."
        + QUALITY_DIRECTIVE
    )

    try:
        resp = client.models.generate_content(
            model=model_ref,
            contents=[
                types.Part.from_bytes(data=design_bytes, mime_type="image/png"),
                types.Part.from_bytes(data=product_bytes, mime_type="image/png"),
                types.Part.from_text(text=dual_prompt),
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
                print(f"Gemini dual-input mockup generated: {img.size}, model={model}", flush=True)
                return img
        print("Gemini dual-input response has no image data", flush=True)
        return None
    except Exception as e:
        print(f"Gemini dual-input mockup error: {e}", flush=True)
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
