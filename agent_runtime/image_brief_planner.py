"""
Image Brief Planner — Gemini Reasoning Phase 1.

Uses the configured Gemini text model (gemini-3-flash-preview) to reason about
the user request + product context and produce a structured creative brief JSON.

The brief is then compiled into the final image prompt by image_prompt_compiler.py.
This replaces the old static template approach with dynamic Gemini reasoning.
"""

import json
import re
from typing import Any, Dict, List, Optional

from config_store import load_settings

# ── Gemini reasoning prompt ──────────────────────────────────────

_REASONING_SYSTEM_PROMPT = (
    "You are a top-tier ecommerce POD creative director specializing in "
    "BurgerPrints print-on-demand product mockup photography. "
    "Your job is to analyze the user request, product context, and target "
    "audience to produce a structured creative brief (JSON only, no markdown). "
    "The brief will be compiled into the final image generation prompt later. "
    "Be specific, professional, and commercially focused. "
    "Respect cultural sensitivity for all audiences."
)

_REASONING_USER_TEMPLATE = """Product: {product_name}
Product type: {product_type}
Color: {color}
Images per product: {count}
User request: {user_scene}

{facts_blurb}

{previous_scenes_blurb}

You MUST output exactly one JSON object with NO markdown wrapping, NO code fences, NO commentary. The JSON schema:

{{
  "audience": "target customer demographic with cultural specificity",
  "product_category": "apparel_tshirt|apparel_hoodie|drinkware_tumbler|drinkware_mug|accessory_tote|wallart_poster|wallart_canvas|accessory_phonecase|home_pillow|home_blanket|default",
  "creative_direction": "overall creative concept and mood (1 sentence)",
  "model": {{
    "ethnicity": "specific, respectful descriptor",
    "gender": "male|female|unisex",
    "age_range": "e.g. 22-35",
    "style": "e.g. urban confident, casual relaxed, premium classic"
  }},
  "scenes": [
    {{
      "scene_id": 1,
      "concept": "scene concept description",
      "background": "specific background/environment",
      "pose": "model pose description",
      "camera": "lens, focal length, depth of field",
      "lighting": "light direction, quality, color temperature",
      "composition": "framing and product placement",
      "negative": ["list of things to avoid for this scene"]
    }}
  ],
  "preservation_rules": [
    "list of rules that MUST be preserved from reference",
    "e.g. preserve exact product color",
    "e.g. front design fully visible"
  ]
}}

RULES:
- Scenes MUST be diverse: different backgrounds, poses, lighting between scenes.
- If user mentions "da màu" or "Mỹ" or "American", model ethnicity MUST be "Black / African American" or specific.
- If user says "cá tính", creative direction should be bold, expressive, confident.
- Every scene must have all fields filled — no nulls, no placeholders.
- Model description must be specific and respectful, not stereotypical.
- The product print/design must ALWAYS be preserved exactly in preservation_rules.
"""


def _call_gemini_text(prompt: str) -> Optional[str]:
    """Call Gemini text model for reasoning."""
    s = load_settings()
    key = s.get("llm_api_key", "").strip()
    if not key or "..." in key:
        return None
    model = s.get("llm_model", "gemini-3-flash-preview")
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=model if model.startswith("models/") else f"models/{model}",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.9,
                top_p=0.95,
                top_k=40,
                max_output_tokens=2048,
            ),
        )
        return resp.text if resp and resp.text else None
    except Exception as e:
        print(f"Gemini reasoning error: {e}", flush=True)
        return None


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON from Gemini response (may include markdown fences)."""
    if not text:
        return None
    text = text.strip()
    # Remove markdown fences if present
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object boundaries
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return None


def plan_image_brief(
    user_scene: str,
    product_name: str = "",
    product_type: str = "",
    color: str = "",
    count: int = 1,
    previous_scenes: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Gemini reasoning → structured creative brief JSON.

    Returns None if Gemini fails, in which case the caller should fall back to
    build_fallback_image_brief().
    """
    facts_blurb = ""
    prev_blurb = ""
    if previous_scenes and len(previous_scenes) > 1:
        prev_blurb = (
            f"This is a batch of {count} images. Scenes must use DIFFERENT backgrounds, "
            f"poses, and lighting to ensure output diversity. "
            f"Previous scenes: {', '.join(previous_scenes[:5])}"
        )

    prompt = _REASONING_USER_TEMPLATE.format(
        product_name=product_name,
        product_type=product_type,
        color=color,
        count=count,
        user_scene=user_scene,
        facts_blurb=facts_blurb,
        previous_scenes_blurb=prev_blurb,
    )

    text = _call_gemini_text(prompt)
    if not text:
        return None

    brief = _extract_json(text)
    if not brief:
        return None

    # Ensure scenes list length matches count
    if len(brief.get("scenes") or []) < count:
        # Pad with diverse defaults
        existing = brief.setdefault("scenes", [])
        default_scenes = _generate_default_scenes(count)
        while len(existing) < count:
            for ds in default_scenes:
                if len(existing) >= count:
                    break
                ds_copy = dict(ds)
                ds_copy["scene_id"] = len(existing) + 1
                existing.append(ds_copy)

    return brief


def build_fallback_image_brief(
    user_scene: str,
    product_name: str = "",
    product_type: str = "",
    color: str = "",
    count: int = 1,
) -> Dict[str, Any]:
    """Deterministic fallback when Gemini reasoning is unavailable.

    Normalizes audience keywords and creates diverse scene templates.
    """
    from agent_runtime.prompt_library import resolve_category

    category = resolve_category(product_type, product_name)

    # Detect audience from Vietnamese keywords
    audience = "general US market customers"
    model_ethnicity = "diverse / mixed"
    model_style = "casual relaxed"
    creative = "premium product lifestyle photography"

    user_lower = user_scene.lower()

    if any(k in user_lower for k in ["mỹ", "america", "american", "us "]):
        if any(k in user_lower for k in ["da màu", "black", "african"]):
            audience = "Black / African American customers in the US market"
            model_ethnicity = "Black / African American"
            model_style = "confident, expressive, streetwear personality"
            creative = "bold streetwear editorial, confident and premium"
        else:
            audience = "American customers in the US market"
            model_ethnicity = "diverse American"
    elif any(k in user_lower for k in ["việt", "vietnam", "châu á", "asian"]):
        audience = "Vietnamese / Asian customers"
        model_ethnicity = "Vietnamese / Asian"
        model_style = "natural, fresh, modern"
    elif any(k in user_lower for k in ["nhật", "japan", "korean", "hàn"]):
        audience = "East Asian customers"
        model_ethnicity = "East Asian"
        model_style = "minimalist, refined, premium casual"

    if any(k in user_lower for k in ["cá tính", "bold", "street", "edgy"]):
        model_style = "bold, expressive, streetwear personality"
        creative = "bold streetwear editorial, confident and premium"

    if any(k in user_lower for k in ["nữ", "female", "woman", "girl"]):
        model_gender = "female"
    elif any(k in user_lower for k in ["nam", "male", "man"]):
        model_gender = "male"
    else:
        model_gender = "male or female depending on product fit"

    # Generate diverse scenes
    scenes = _generate_default_scenes(count)

    return {
        "audience": audience,
        "product_category": category,
        "creative_direction": creative,
        "model": {
            "ethnicity": model_ethnicity,
            "gender": model_gender,
            "age_range": "22-35",
            "style": model_style,
        },
        "scenes": scenes,
        "preservation_rules": [
            "preserve exact product color from reference",
            "preserve exact print/design placement from reference",
            "front design must be fully visible",
            "no redesign, no new logos, no text changes",
        ],
    }


def _generate_default_scenes(count: int) -> List[Dict[str, Any]]:
    """Generate count diverse default scene templates."""
    templates = [
        {
            "scene_id": 1,
            "concept": "urban outdoor lifestyle portrait",
            "background": "clean modern city wall, late afternoon light",
            "pose": "confident standing pose, hands relaxed, product front fully visible",
            "camera": "85mm f/1.2, shallow depth of field",
            "lighting": "golden hour side light, warm tones",
            "composition": "hero product centered, clean framing, no clutter",
            "negative": ["no warped print", "no cluttered background", "no extra people"],
        },
        {
            "scene_id": 2,
            "concept": "studio editorial fashion look",
            "background": "seamless neutral backdrop, soft gray or cream",
            "pose": "casual seated pose on studio stool, product front visible",
            "camera": "50mm f/1.4, medium depth of field",
            "lighting": "softbox key light + rim light, clean commercial",
            "composition": "product centered, fashion editorial framing, stylish minimal",
            "negative": ["no harsh shadows", "no busy background", "no weird face angles"],
        },
        {
            "scene_id": 3,
            "concept": "cozy indoor lifestyle scene",
            "background": "modern apartment interior, natural window light, plants",
            "pose": "relaxed leaning against wall or sitting on sofa edge",
            "camera": "45mm f/2.8, natural depth of field",
            "lighting": "soft window light, natural ambient",
            "composition": "product in context, warm inviting tone, lifestyle authentic",
            "negative": ["no messy room", "no distracting decor", "no off-brand vibe"],
        },
        {
            "scene_id": 4,
            "concept": "outdoor park / nature lifestyle",
            "background": "urban park, greenery, soft natural light",
            "pose": "walking naturally, mid-stride, candid feel",
            "camera": "135mm f/2.0, compressed background blur",
            "lighting": "open shade, soft flattering light",
            "composition": "product as outfit hero, natural candid capture style",
            "negative": ["no harsh sunlight", "no random people in background", "no unnatural pose"],
        },
    ]
    result = []
    for i in range(count):
        t = templates[i % len(templates)]
        d = dict(t)
        d["scene_id"] = i + 1
        result.append(d)
    return result
