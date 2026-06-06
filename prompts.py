# BurgerMockup — Optimized Prompt Templates
# Architecture: Gemini image model receives product image AS INPUT (inline) + this prompt.
# The model generates the complete lifestyle mockup in one pass — no composite needed.
from typing import Optional

SYSTEM_ROLE = """You are an elite product photographer for a premium e-commerce brand.
Your specialty is creating natural, realistic lifestyle mockups where real models wear
or use the exact product shown in the reference image."""

PRESERVATION_RULES = """CRITICAL PRESERVATION RULES — VIOLATION MEANS FAILURE:
- The design/print on the product must be 100% IDENTICAL to the reference image.
- Preserve ALL text EXACTLY: every character, font style, size, color, spelling, kerning, placement.
- Preserve ALL graphics EXACTLY: every shape, color, line weight, position, proportion.
- Preserve the product's BASE COLOR exactly as seen in the reference image.
- Do NOT recolor the product. If the reference product is white, it must remain white. If black, it must remain black. Same for every color.
- Ignore scene mood, lighting, or fashion styling if they would change the product color.
- Preserve fabric/sheen texture, collar/neckline style exactly.
- The product in the final image MUST be recognizable as the SAME product from the reference.
- Violation = failure. DO NOT redesign, reinterpret, stylize, or simplify ANY element.
- If there is text on the product, reproduce it letter‑for‑letter with zero typos or omissions.
- The design placement on the final product must match the reference placement (chest, full‑front, etc.)."""

TECHNICAL_SPEC = """Technical specifications:
- Premium commercial product photography quality, marketplace-ready
- 4K‑8K resolution equivalent, crisp edges, clean high-detail texture
- Soft natural lighting with believable shadows and contact points
- Correct perspective, realistic fabric folds/hand contact, no pasted-on look
- Shallow depth of field: background slightly blurred, product/model sharp
- Front-facing or 3/4 angle, full product clearly visible and readable
- Balanced composition with product as hero subject, no clutter
- Natural human anatomy, realistic skin/hands, no plastic AI look
- No harsh studio lights, no overexposed areas, no lens flare"""

SCENE_TEMPLATES = {
    "cafe": "A stylish young woman sitting at an outdoor cafe terrace, warm morning sunlight filtering through plants, wooden table with a coffee cup, natural candid pose, cozy urban atmosphere with brick wall background and hanging greenery.",
    "streetwear": "A confident young person standing on a city street corner, golden hour sunset lighting, urban architecture background with murals and concrete textures, relaxed street style pose, cinematic color grading.",
    "studio": "Clean minimalist studio with warm beige backdrop, soft diffused lighting from large windows, professional model pose showing the product naturally, subtle shadow on the floor, high‑end catalog aesthetic.",
    "living_room": "Cozy modern living room with natural light from large windows, person relaxing on a comfortable sofa with plants and books nearby, warm homey atmosphere, candid lifestyle moment.",
    "beach": "Person standing on a tropical beach at golden hour, soft ocean waves in the background, warm breeze, relaxed vacation vibe, natural pose, palm trees framing the composition.",
    "flat_lay": "Overhead flat‑lay composition on a textured wooden surface or clean marble, product neatly arranged with complementary lifestyle accessories (plants, coffee, books, sunglasses), soft natural window light, editorial aesthetic.",
    "park": "Person in a lush green park under soft dappled sunlight through trees, natural walking pose, spring/summer atmosphere, blurred greenery background, fresh and vibrant.",
    "office": "Professional person in a bright modern co‑working space or home office, natural light, minimal desk setup, contemporary professional vibe, relaxed but polished.",
}

CONSTRAINTS = """ABSOLUTE CONSTRAINTS:
- NO brand logos, NO celebrity faces, NO copyrighted characters or artwork.
- NO watermarks, NO text overlays, NO UI elements, NO borders.
- NO unrealistic product distortions, warping, or stretching.
- NO background removal artifacts, NO floating product effect, NO compositing seams.
- The product must look NATURALLY worn by the model — not pasted on, not floating.
- The model should look like a real person in a real environment — not AI‑generated plastic.
- NO more than one person visible in the frame unless explicitly requested."""


def build_product_mockup_prompt(
    product_name: str,
    color: Optional[str] = "as shown in reference",
    scene: str = "naturally lit professional setting",
    scene_key: str = "",
) -> str:
    """Build the optimized prompt for Gemini image generation with product reference image.

    The product image MUST be sent as an inline image part alongside this text prompt.
    """
    if not color or color.lower() in ("none", "null", ""):
        color = "as shown in the attached reference image — use the exact visual color"
    if scene_key and scene_key in SCENE_TEMPLATES:
        scene_desc = SCENE_TEMPLATES[scene_key]
    else:
        scene_desc = scene

    prompt = f"""{SYSTEM_ROLE}

TASK: Create a professional lifestyle mockup photograph.
The attached image is the EXACT product — it must appear in the final photo,
worn naturally by a real model in a realistic setting.
Use the visual product in the attached image as the source of truth. The product name helps identify the item type only; DO NOT infer or change color from product name, scene, model outfit, or metadata.

PRODUCT: {product_name}
REFERENCE PRODUCT COLOR: {color} — must match the attached image exactly. No recoloring.

{PRESERVATION_RULES}

SCENE: {scene_desc}

{TECHNICAL_SPEC}

{CONSTRAINTS}

Generate the final photograph now. The product in the output must be INDISTINGUISHABLE
from the reference product — same design, same details, same quality.
CRITICAL REMINDER: The product COLOR must be EXACTLY IDENTICAL to the reference image.
If the reference shows a WHITE product, the output MUST be WHITE.
Do NOT recolor. Do NOT darken. Do NOT reinterpret the product color.
The reference image is the ONLY source of truth for the product appearance."""
    return prompt


# ── Short prompt for fast generation (lower latency, Hackathon-friendly) ──

def build_product_mockup_prompt_short(
    product_name: str,
    color: str = "as shown",
    scene: str = "lifestyle setting",
) -> str:
    return f"""Lifestyle product photo: a model naturally wearing this exact {product_name} ({color}).
Preserve ALL text, graphics, colors, and design details 100% IDENTICALLY from the reference image.
Scene: {scene}.
Professional product photography, natural lighting, marketplace-ready.
Product color MUST match reference image exactly — do NOT recolor or darken.
NO logos, NO watermarks, NO distorted designs, NO compositing artifacts."""
