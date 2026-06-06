"""
Prompt Library — V1 category-specific mockup templates per product type.
Deterministic resolver: product_type + title → category → professional prompt template.

Architecture: 3-tier prompt building
  Tier 1 — Category base: apparel/accessories/drinkware/...
  Tier 2 — Product physics: fabric/stainless/ceramic/canvas...
  Tier 3 — Camera + quality: 8K, Canon, photorealistic, anti-AI-plastic
"""

from typing import Dict, Optional, Any

# ── Category resolver ────────────────────────────────────────────

CATEGORY_MAP = {
    "youth t-shirt": "apparel_tshirt",
    "t-shirt": "apparel_tshirt",
    "tee": "apparel_tshirt",
    "shirt": "apparel_tshirt",
    "polo": "apparel_tshirt",
    "tank top": "apparel_tshirt",
    "long sleeve": "apparel_tshirt",
    "longsleeve": "apparel_tshirt",
    "crewneck": "apparel_tshirt",
    "v-neck": "apparel_tshirt",
    "hoodie": "apparel_hoodie",
    "sweatshirt": "apparel_hoodie",
    "sweater": "apparel_hoodie",
    "zip hoodie": "apparel_hoodie",
    "pullover": "apparel_hoodie",
    "jumper": "apparel_hoodie",
    "cardigan": "apparel_hoodie",
    "tumbler": "drinkware_tumbler",
    "bottle": "drinkware_tumbler",
    "water bottle": "drinkware_tumbler",
    "flask": "drinkware_tumbler",
    "thermos": "drinkware_tumbler",
    "mug": "drinkware_mug",
    "cup": "drinkware_mug",
    "coffee mug": "drinkware_mug",
    "classic mug": "drinkware_mug",
    "poster": "wallart_poster",
    "canvas": "wallart_canvas",
    "framed poster": "wallart_poster",
    "framed canvas": "wallart_canvas",
    "phone case": "accessory_phonecase",
    "case": "accessory_phonecase",
    "tote bag": "accessory_tote",
    "pillow": "home_pillow",
    "cushion": "home_pillow",
    "blanket": "home_blanket",
    "throw blanket": "home_blanket",
    "sticker": "stationery_sticker",
    "notebook": "stationery_notebook",
    "journal": "stationery_notebook",
    "aop": "apparel_tshirt",
    "all over print": "apparel_tshirt",
    "sublimation": "apparel_tshirt",
}


def resolve_category(product_type: str = "", title: str = "", product_id: str = "") -> str:
    """Deterministic: match longest (most specific) keyword first, then shorter.

    Uses word-boundary matching to avoid substring false positives (e.g. "tee" in "steel").
    """
    search_terms = (product_type + " " + title + " " + product_id).lower()
    # Sort keywords by length descending to match most specific first
    for keyword, category in sorted(CATEGORY_MAP.items(), key=lambda x: -len(x[0])):
        if keyword in search_terms:
            kw_len = len(keyword)
            idx = search_terms.index(keyword)
            before = search_terms[max(0, idx - 1):idx]
            after = search_terms[idx + kw_len:idx + kw_len + 1]
            before_ok = (idx == 0 or not before.isalpha())
            after_ok = (idx + kw_len >= len(search_terms) or not after.isalpha())
            if before_ok and after_ok:
                return category
    return "default"


# ── Camera presets ───────────────────────────────────────────────

CAMERA_FASHION = (
    "Canon EOS R5, 85mm f/1.2, shallow depth of field, "
    "golden hour sunlight, realistic shadows"
)
CAMERA_PRODUCT = (
    "Sony A7R V, 90mm macro, f/16, studio softbox lighting, "
    "clean commercial product photography"
)
CAMERA_LIFESTYLE = (
    "Fujifilm GFX 100S, 45mm f/2.8, natural window light, "
    "editorial lifestyle photography, razor-sharp details"
)

# ── Category templates ───────────────────────────────────────────


def _tier2_product_physics(category: str) -> str:
    """Product-specific material/physics rules."""
    physics = {
        "apparel_tshirt": (
            "PRODUCT PHYSICS: Premium heavyweight cotton fabric (220 GSM), "
            "natural fabric folds, realistic draping, detailed shoulder/neck stitching, "
            "authentic clothing physics. The front graphic print is on POD transfer paper — "
            "it must remain fully visible, centered, unwarped, with slight fabric texture visible through the print. "
            "Collar ribbing natural, hem slightly curved."
        ),
        "apparel_hoodie": (
            "PRODUCT PHYSICS: Heavyweight fleece fabric (350 GSM), brushed interior, "
            "thick natural folds, realistic hood draping, metal-tip drawstring details, "
            "ribbed cuffs and waistband with slight tension lines, kangaroo pocket visible. "
            "The front graphic must be cleanly printed, unwarped, centered on chest."
        ),
        "drinkware_tumbler": (
            "PRODUCT PHYSICS: Stainless steel tumbler (20oz), accurate cylindrical shape, "
            "accurate metal reflection and highlight, powder-coated matte finish, "
            "printed design naturally wrapped around curved surface, "
            "seamless lid with slight condensation droplets. No pasted-on flat label look."
        ),
        "drinkware_mug": (
            "PRODUCT PHYSICS: Ceramic mug (11oz / 15oz), glossy glaze finish, "
            "clean handle attachment, slight rim highlight, printed design wrapped around "
            "curved surface with natural cylindrical distortion. "
            "Inside white ceramic visible from top angle."
        ),
        "wallart_poster": (
            "PRODUCT PHYSICS: Premium museum-grade poster paper, matte finish, "
            "clean edges, no curling, either framed (thin black/white/wood frame, glass reflection) "
            "or unframed with clean border. Print must be sharp, colors accurate."
        ),
        "wallart_canvas": (
            "PRODUCT PHYSICS: Gallery-wrapped canvas, wooden stretcher frame visible from edge, "
            "canvas weave texture subtly visible, depth 1.5 inches, clean corners, "
            "either hanging on wall or leaning on floor/table."
        ),
        "accessory_phonecase": (
            "PRODUCT PHYSICS: Premium phone case, accurate device shape, "
            "camera cutout aligned, button details visible, printed design on back, "
            "matte or glossy finish, snug fit, realistic device proportions."
        ),
        "accessory_tote": (
            "PRODUCT PHYSICS: Heavy canvas tote bag, natural fabric weave, "
            "reinforced stitching on handles, printed design centered on front panel, "
            "slight fabric folds, carried by hand or on shoulder."
        ),
        "home_pillow": (
            "PRODUCT PHYSICS: Premium pillow/cushion, soft polyester/linen cover, "
            "visible seam piping, printed design centered, slight plumpness/fill visible, "
            "on sofa/bed/chair in lifestyle setting."
        ),
        "home_blanket": (
            "PRODUCT PHYSICS: Soft fleece/mink blanket, rich drape and folds, "
            "printed design edge-to-edge, realistic fabric texture, "
            "casually draped over sofa or folded."
        ),
    }
    return physics.get(category, "")


# ── Tier 1: Category base templates ──────────────────────────────

CATEGORY_BASE = {
    "apparel_tshirt": (
        "Fashion editorial photo of model wearing the exact POD product. "
        "Model: Vietnamese or Asian, age 22-28, natural makeup, visible skin texture, "
        "natural smile, relaxed confident pose. Product is hero — front graphic must be "
        "fully visible, undistorted, and exactly matching the reference design."
    ),
    "apparel_hoodie": (
        "Streetwear / lifestyle photo of model wearing the exact hoodie. "
        "Model: casual relaxed pose, hood optionally up or down, hands in pocket, "
        "natural street/café setting. Product is hero — front graphic fully visible, "
        "thick fabric folds natural, hoodie branding/design preserved exactly."
    ),
    "drinkware_tumbler": (
        "Premium lifestyle product photo of stainless steel tumbler. "
        "Setting: outdoor café, desk workspace, or picnic table. "
        "Hand model holding tumbler naturally, condensation droplets visible, "
        "laser-engraved/powder-coated design wrapped naturally on curved surface. "
        "Hero product with shallow depth of field."
    ),
    "drinkware_mug": (
        "Cozy lifestyle product photo of ceramic mug. "
        "Setting: morning coffee desk scene, café table, or home kitchen. "
        "Steam wisps optional, hand holding handle naturally, "
        "printed design clearly visible on front/side."
    ),
    "wallart_poster": (
        "Interior decor photo of framed/unframed poster artwork. "
        "Setting: modern living room, gallery wall, or creative office. "
        "Hung on wall at eye level, natural lighting, clean composition. "
        "Print design must be sharp and color-accurate."
    ),
    "wallart_canvas": (
        "Interior decor photo of gallery-wrapped canvas. "
        "Setting: bright living room, bedroom, or hallway gallery wall. "
        "Hung on wall or leaning on floor/console against wall. "
        "Canvas edges and frame depth visible. Print sharp."
    ),
    "accessory_phonecase": (
        "Lifestyle product photo of phone case on actual device. "
        "Either: hand holding phone in natural setting, "
        "or flat lay on desk/marble surface with lifestyle props. "
        "Camera cutout aligned, case design centered and visible."
    ),
    "accessory_tote": (
        "Lifestyle photo of canvas tote bag. "
        "Setting: outdoor market, city street, or casual café. "
        "Model carrying on shoulder or by hand, bag design centered and visible. "
        "Natural fabric folds, reinforced handles."
    ),
    "home_pillow": (
        "Interior decor photo of printed pillow. "
        "Setting: modern living room sofa, bedroom, or cozy reading nook. "
        "Pillow placed naturally on sofa/chair/bed, design centered and visible. "
        "Warm natural lighting."
    ),
    "home_blanket": (
        "Cozy interior photo of printed blanket. "
        "Setting: draped over sofa arm/cushion or folded neatly. "
        "Soft fleece texture visible, edge-to-edge print sharp. "
        "Warm living room or bedroom lighting."
    ),
    "stationery_sticker": (
        "Product photo of premium vinyl sticker. "
        "Setting: flat lay on clean surface with lifestyle accessories (notebook, pen, coffee). "
        "Alternatively on laptop/water bottle surface. "
        "Design crisp, kiss-cut edges visible, weatherproof gloss finish."
    ),
    "stationery_notebook": (
        "Product photo of hardcover/softcover notebook. "
        "Setting: flat lay on clean wooden desk with pen, coffee, plants. "
        "Design centered on cover, binding/spine visible, "
        "lined/dot-grid paper visible when open. "
    ),
    "default": (
        "Premium lifestyle product photography. "
        "Professional commercial quality, natural setting appropriate for product type. "
        "Hero product clearly visible, design preserved exactly from reference. "
        "Clean composition, natural lighting, marketplace-ready."
    ),
}

# ── Tier 3: Camera + Quality ─────────────────────────────────────

QUALITY_DIRECTIVE = (
    "\n\nQUALITY DIRECTIVE:\n"
    "Photorealistic RAW commercial photography, impossible to distinguish from real photography. "
    "Visible skin texture, subtle skin oil reflection, authentic skin imperfections, "
    "realistic hair strands, natural facial asymmetry, realistic eyelashes. "
    "True-to-life color rendering, 8K ultra detailed. "
    "No AI plastic look, no watermarks, no misspelled text, "
    "no distorted hands, no warped fabric, no duplicate products, no clutter."
)

NEGATIVE_PROMPT = (
    "\n\nNEGATIVE:\n"
    "plastic skin, AI-generated face artifacts, doll-like, overexposed, lens flare, "
    "watermarks, signatures, text overlays, logos added by AI, "
    "warped/distorted product print, floating product, compositing seams, "
    "blurry product, wrong colors, recolored product, extra hands/limbs, "
    "duplicate product, pasted-on flat rectangle, unrealistic shadows."
)

# ── Builders ─────────────────────────────────────────────────────


def build_mockup_prompt(
    product_name: str = "",
    product_type: str = "",
    color: str = "",
    user_scene: str = "",
    design_url: str = "",
) -> Dict[str, Any]:
    """Build a professional 3-tier prompt for mockup generation.

    Returns dict with full prompt string + metadata for debugging.
    """
    category = resolve_category(product_type, product_name, design_url)
    base = CATEGORY_BASE.get(category, CATEGORY_BASE["default"])
    physics = _tier2_product_physics(category)

    # Camera selection
    if "apparel" in category:
        camera = CAMERA_FASHION
    elif "drinkware" in category or "accessory" in category:
        camera = CAMERA_PRODUCT
    else:
        camera = CAMERA_LIFESTYLE

    # Assemble top-1 expert 5-criteria prompt.
    # Every final prompt MUST include these 5 blocks regardless of category.
    parts = []

    parts.append(
        "[1. PRODUCT IDENTITY & REFERENCE PRESERVATION]\n"
        f"Product: {product_name}. Product type/category: {product_type or category}. "
        "Use the attached/reference product as the only source of truth. "
        "Preserve product shape, color, print/design, text, layout, proportions and placement 100% exactly. "
        "Do not redesign, recolor, reinterpret, simplify, crop, or distort any product detail."
    )
    if color and color.lower() not in ("none", "null", "as shown", ""):
        parts.append(f"Reference color: {color} — must match reference exactly.")

    parts.append(
        "\n\n[2. PRODUCT-TYPE PHYSICS & MATERIAL REALISM]\n"
        + (physics or "Infer the correct physical material, surface, depth, weight, texture and natural contact points from the product type. Make it believable under real-world physics.")
    )

    parts.append(
        "\n\n[3. SCENE, MODEL & COMMERCIAL COMPOSITION]\n"
        + base + " "
        + (f"User requested style/scene: {user_scene}. " if user_scene else "Choose the most commercially suitable lifestyle scene for this product. ")
        + "The product must be the hero subject, clearly visible, marketplace-ready, with uncluttered premium composition."
    )

    parts.append(
        "\n\n[4. CAMERA, LIGHTING & PHOTOREALISM]\n"
        f"Camera setup: {camera}. Use realistic camera optics, natural shadows, correct perspective, believable contact points, true-to-life color rendering, shallow depth of field where appropriate, RAW commercial photography quality."
    )

    parts.append(
        "\n\n[5. QUALITY CONTROL & NEGATIVE CONSTRAINTS]\n"
        "Before finalizing, self-check: product type correct, print/design readable, product not warped, no duplicate products, no AI plastic look, no watermarks, no extra text, no distorted hands, no wrong color, no compositing seams. "
        + QUALITY_DIRECTIVE + NEGATIVE_PROMPT
    )

    parts.append(
        "\n\nFINAL TOP-1 EXPERT DIRECTIVE:\n"
        "Create a premium POD commercial mockup that looks like a real top-tier advertising photo, not a generic AI image. The result must be usable directly for ecommerce listing and ads."
    )

    full_prompt = "\n".join(parts).strip()

    return {
        "prompt": full_prompt,
        "category": category,
        "product_name": product_name,
        "product_type": product_type,
        "color": color,
    }


def build_mockup_prompt_short(
    product_name: str = "",
    product_type: str = "",
    color: str = "",
    user_scene: str = "",
) -> str:
    """Short variant for faster generation."""
    result = build_mockup_prompt(
        product_name=product_name,
        product_type=product_type,
        color=color,
        user_scene=user_scene,
    )
    category = result["category"]
    # Truncate to essentials
    lines = [
        CATEGORY_BASE.get(category, CATEGORY_BASE["default"])[:300],
        f"PRODUCT: {product_name}",
        f"SCENE: {user_scene or 'premium commercial setting'}",
        CAMERA_FASHION if "apparel" in category else CAMERA_PRODUCT,
        "8K photorealistic, preserve product design 100% exactly as reference.",
    ]
    return "\n".join(lines)
