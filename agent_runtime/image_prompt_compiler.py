"""
Image Prompt Compiler — Phase 1.

Takes the structured creative brief from image_brief_planner.py and
compiles a deterministic final prompt for the image generation model.

No AI calls — pure string templating based on the brief JSON fields.
"""

from typing import Any, Dict, List


# ── Builders ──────────────────────────────────────────────────────


def _build_model_description(model: Dict[str, Any]) -> str:
    ethnicity = model.get("ethnicity", "diverse")
    gender = model.get("gender", "")
    age = model.get("age_range", "22-35")
    style = model.get("style", "natural")
    parts = [f"Model: {ethnicity}"]
    if gender:
        parts.append(gender)
    parts.append(f", age {age}")
    parts.append(f", style: {style}")
    return " ".join(parts)


def _build_scene_block(scene: Dict[str, Any]) -> str:
    return (
        f"    Scene: {scene.get('concept', 'premium mockup')}\n"
        f"    Background: {scene.get('background', 'premium setting')}\n"
        f"    Pose: {scene.get('pose', 'natural pose')}\n"
        f"    Camera: {scene.get('camera', 'professional camera')}\n"
        f"    Lighting: {scene.get('lighting', 'professional lighting')}\n"
        f"    Composition: {scene.get('composition', 'hero product centered')}\n"
    )


def _build_negative_block(negatives: List[str]) -> str:
    items = [f"no {n}" if not n.startswith("no ") else n for n in negatives]
    return "NO: " + ", ".join(items) if items else ""


# ── Main compiler ────────────────────────────────────────────────

_COMPILED_PROMPT_TEMPLATE = """ROLE:
You are a top-tier ecommerce lifestyle photographer and POD mockup creative director. Create the exact scene described below using the attached product reference image.

REFERENCE IMAGE:
The attached image is the exact BurgerPrints product reference. This is the ONLY source of truth for product appearance, color, print/design placement, and proportions. Preserve it 100%.

PRODUCT:
- Name: {product_name}
- Type: {product_type_category}
- Color: {color}

TARGET AUDIENCE:
{audience}

CREATIVE BRIEF:
- Direction: {creative_direction}
- Model: {model_description}
- Model age: {model_age} years old
- Ethnic representation: {model_ethnicity}

SCENE {scene_index}:
{scene_block}

PHOTOGRAPHY:
{scene_camera}
{scene_lighting}
{scene_composition}

PRESERVATION RULES (MUST follow):
{preservation_rules}

{preservation_extra}

QUALITY DIRECTIVE:
Photorealistic RAW commercial photography quality. Impossible to distinguish from real photography. Visible skin texture, subtle skin oil reflection, authentic skin imperfections, realistic hair strands, natural facial asymmetry, realistic eyelashes. True-to-life color rendering. No AI plastic look. Marketplace-ready composition.

{negative_block}

FINAL TOP-1 EXPERT DIRECTIVE:
Create a premium POD commercial mockup that looks like a real top-tier advertising photo from a professional shoot, not a generic AI image. The result must be usable directly for Etsy/Amazon/Shopify listing and ads.
"""


def compile_image_prompt(
    brief: Dict[str, Any],
    scene_index: int,
    product_name: str = "",
    product_type: str = "",
    color: str = "",
    user_scene: str = "",
) -> str:
    """Compile deterministic final prompt from creative brief.

    Args:
        brief: Structured brief from plan_image_brief() or build_fallback_image_brief()
        scene_index: which scene to compile (0-indexed)
        product_name: product title
        product_type: product type string
        color: product color
        user_scene: original user scene request text

    Returns:
        Full prompt string ready for image generation model.
    """
    scenes = brief.get("scenes") or [{"concept": user_scene, "background": "", "pose": "",
                                       "camera": "", "lighting": "", "composition": "",
                                       "negative": []}]
    scene_idx = min(scene_index, len(scenes) - 1)
    scene = scenes[scene_idx]
    model = brief.get("model", {})
    rules = brief.get("preservation_rules", [])

    # Format preservation rules as bullet list
    preservation_lines = "\n".join(f"  - {r}" for r in rules)

    # Format scene block
    scene_block = _build_scene_block(scene)

    # Format negatives
    negatives = scene.get("negative", [])
    negative_block = _build_negative_block(negatives) if negatives else ""

    # Build preservation extra sentence
    preservation_extra = (
        "No redesign, no new logos, no text changes. "
        "Product must be hero subject, fully visible, undistorted."
    )

    # Type + category description
    category = brief.get("product_category", "")
    product_type_category = f"{product_type} ({category})" if category else product_type

    return _COMPILED_PROMPT_TEMPLATE.format(
        product_name=product_name or "product",
        product_type_category=product_type_category,
        color=color or "as shown in reference",
        audience=brief.get("audience", "premium ecommerce customers"),
        creative_direction=brief.get("creative_direction", "premium lifestyle photography"),
        model_description=_build_model_description(model),
        model_age=model.get("age_range", "24-50"),
        model_ethnicity=model.get("ethnicity", "diverse"),
        scene_index=scene.get("scene_id", scene_idx + 1),
        scene_block=scene_block,
        scene_camera=scene.get("camera", "professional camera"),
        scene_lighting=scene.get("lighting", "professional lighting"),
        scene_composition=scene.get("composition", "product centered"),
        preservation_rules=preservation_lines,
        preservation_extra=preservation_extra,
        negative_block=negative_block,
    )
