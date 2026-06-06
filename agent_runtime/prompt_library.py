"""
Prompt Library — V2 enhanced category-specific mockup templates.
Includes shot type system, commercial intent labels, persona library,
stronger negative constraints, reference preservation contract.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

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
    search_terms = (product_type + " " + title + " " + product_id).lower()
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


# ── Shot types ──────────────────────────────────────────────────

SHOT_TYPES = {
    "hero product shot": (
        "Hero product shot — product is the single subject, full front/side view, "
        "studio lighting, clean background, sharp detail on product surface, "
        "hero framing with premium commercial quality"
    ),
    "lifestyle model shot": (
        "Lifestyle model shot — real person in natural setting wearing/using the product, "
        "product is hero of the image, model supports product story, "
        "authentic scene with professional lighting"
    ),
    "close-up detail shot": (
        "Close-up detail shot — macro/close framing showing product texture, "
        "material quality, print precision, stitching or finish details, "
        "shallow depth of field emphasizing print surface"
    ),
    "in-use scene": (
        "In-use action scene — product being actively used in a real functional context, "
        "natural interaction, dynamic angle, shows utility and lifestyle fit"
    ),
    "premium catalog shot": (
        "Premium catalog shot — editorial quality, magazine-grade composition, "
        "polished lighting, perfect styling, high-end brand photography language"
    ),
    "social ad creative": (
        "Social ad creative — optimized for scroll-stopping social media, "
        "bold visual, clear product visibility, modern fashion aesthetic, "
        "bright colors, high contrast, ad-ready format"
    ),
}


def resolve_shot_type(user_text: str) -> str:
    """Deterministic shot type from user request text."""
    text = user_text.lower()
    if any(k in text for k in ["detail", "macro", "texture", "close up", "zoom"]):
        return "close-up detail shot"
    if any(k in text for k in ["social", "ad", "instagram", "tiktok", "facebook"]):
        return "social ad creative"
    if any(k in text for k in ["hero", "studio", "isolated", "plain background"]):
        return "hero product shot"
    if any(k in text for k in ["catalog", "magazine", "premium", "editorial"]):
        return "premium catalog shot"
    if any(k in text for k in ["in use", "action", "wearing", "using", "functional"]):
        return "in-use scene"
    return "lifestyle model shot"


# ── Commercial intent labels ────────────────────────────────────

COMMERCIAL_INTENTS = {
    "amazon main listing": "Amazon main listing image — white/grey clean background or lifestyle, high conversion composition, A+ content standard",
    "etsy lifestyle image": "Etsy lifestyle image — warm authentic scene, handmade product feel, cozy composition, buyer trust aesthetic",
    "facebook ad": "Facebook ad creative — bold visual, clear text area, high saturation, social scroll-stopping format",
    "instagram square post": "Instagram square post — 1:1 format, trendy aesthetic, polished but authentic, engagement-optimized",
    "shopify product gallery": "Shopify product gallery — clean consistent style across images, multiple angles, size reference, premium brand feel",
    "pod catalog mockup": "POD catalog mockup — standard marketplace template, clean product visibility, neutral background, print demonstration",
    "listing image": "General marketplace listing image — sharp product focused, clean styling, marketplace standard quality",
}


def resolve_commercial_intent(user_text: str) -> str:
    text = user_text.lower()
    if "amazon" in text:
        return "amazon main listing"
    if "etsy" in text or "handmade" in text:
        return "etsy lifestyle image"
    if "facebook" in text or "fb" in text:
        return "facebook ad"
    if "instagram" in text or "ig" in text or "1:1" in text or "square" in text:
        return "instagram square post"
    if "shopify" in text:
        return "shopify product gallery"
    if "catalog" in text or "template" in text:
        return "pod catalog mockup"
    if "listing" in text or "main image" in text:
        return "listing image"
    return "shopify product gallery"


# ── Persona / Model direction library ───────────────────────────

PERSONAS = {
    "default": {
        "description": "Adult model age 24-50, professional mature appearance, expressive body language, face optional — crop from neck/torso or turned away, emotion through posture and garment movement, product is hero",
        "age": "24-50",
        "style": "professional, mature, emotionally expressive, confident commercial presence",
    },
    "office professional": {
        "description": "Office professional model age 28-45, business casual look, polished appearance, seated at desk or walking in corporate corridor, natural expression, product fits office lifestyle",
        "age": "28-45",
        "style": "polished, professional, refined, executive presence",
    },
    "outdoor lifestyle": {
        "description": "Outdoor enthusiast model age 24-45, active fit look, casual outdoors appearance, park/garden/trail setting, relaxed natural posture, product in lifestyle context, face optional depending on composition",
        "age": "24-45",
        "style": "active, natural, relaxed, outdoor-ready, confident casual",
    },
    "gym active": {
        "description": "Fit active model age 22-40, athletic build, gym/park setting, dynamic pose, sweat/movement realism, product shown in active context, no face required, crop from chest/torso natural",
        "age": "22-40",
        "style": "athletic, energetic, powerful, dynamic activewear",
    },
    "cozy home": {
        "description": "Cozy home model age 24-50, soft comfortable look, home setting sofa/bed/chair, relaxed warm pose, natural indoor light, product in cozy context, face can be cropped for warmth-focused composition",
        "age": "25-50",
        "style": "warm, relaxed, approachable, comfortable",
    },
    "coffee shop": {
        "description": "Coffee shop casual model age 22-40, urban casual style, sitting at café table holding coffee, natural street style vibe, window light, product integrated naturally, face not required",
        "age": "22-40",
        "style": "casual, urban, relaxed, lifestyle-candid",
    },
    "premium buyer": {
        "description": "Premium lifestyle model age 30-55, affluent appearance, sophisticated scene, elevated taste, fine materials and fabrics, product shown as luxury item, face not required",
        "age": "30-55",
        "style": "premium, sophisticated, elegant, high-end commercial",
    },
    "urban streetwear": {
        "description": "Urban streetwear model age 18-35, confident edgy style, bold body language, city background graffiti/gritty wall/urban architecture, expressive posture, face can be cropped or partially visible through stance",
        "age": "18-35",
        "style": "bold, expressive, street-smart, urban confident",
    },
}


def resolve_persona(user_text: str) -> dict:
    text = user_text.lower()
    for key, persona in PERSONAS.items():
        if any(k in text for k in key.split("_")):
            return persona
    # Substring match
    if any(k in text for k in ["office", "corporate", "business"]):
        return PERSONAS["office professional"]
    if any(k in text for k in ["outdoor", "park", "garden", "nature", "travel"]):
        return PERSONAS["outdoor lifestyle"]
    if any(k in text for k in ["gym", "active", "sport", "fitness", "workout"]):
        return PERSONAS["gym active"]
    if any(k in text for k in ["cozy", "home", "sofa", "bedroom", "indoor"]):
        return PERSONAS["cozy home"]
    if any(k in text for k in ["coffee", "cafe", "café", "cà phê"]):
        return PERSONAS["coffee shop"]
    if any(k in text for k in ["premium", "luxury", "high end", "affluent", "rich"]):
        return PERSONAS["premium buyer"]
    if any(k in text for k in ["street", "urban", "young", "teen", "hip"]):
        return PERSONAS["urban streetwear"]
    return PERSONAS["default"]


# ── Camera presets ───────────────────────────────────────────────

CAMERA_FASHION = "Canon EOS R5, 85mm f/1.2, shallow depth of field, golden hour sunlight, realistic shadows"
CAMERA_PRODUCT = "Sony A7R V, 90mm macro, f/16, studio softbox lighting, clean commercial product photography"
CAMERA_LIFESTYLE = "Fujifilm GFX 100S, 45mm f/2.8, natural window light, editorial lifestyle photography, razor-sharp details"


# ── Reference preservation contract ─────────────────────────────

PRESERVATION_CONTRACT = (
    "[REFERENCE PRESERVATION CONTRACT (MANDATORY)]\n"
    "The provided product image is the sole source of truth. This contract is binding:\n"
    "  - Preserve artwork, design, color palette 100% exactly as shown in reference.\n"
    "  - Preserve product shape, proportions, print position, design scale.\n"
    "  - Do not change artwork. Do not invent extra logos, text, or brand marks.\n"
    "  - Do not add misspelled text, fake brands, or decorative text.\n"
    "  - Do not crop, warp, or distort the product design.\n"
    "  - Product must not be transformed into a different item type.\n"
    "  - Only change: environment, lighting, model pose, camera angle.\n"
    "  - If any instruction conflicts with this contract, this contract wins."
)


# ── Strong negative constraints ──────────────────────────────────

NEGATIVE_CONSTRAINTS = (
    "[NEGATIVE CONSTRAINTS (STRICT)]\n"
    "STRICTLY PROHIBITED:\n"
    "  - Changing artwork, design, text, or colors from reference\n"
    "  - Adding extra logos, brands, captions, or misspelled words\n"
    "  - Cropping, warping, distorting, or stretching the product design\n"
    "  - Making product look like a different item type\n"
    "  - Plastic skin, AI-generated face artifacts, doll-like appearance\n"
    "  - Extra hands, broken fingers, deformed body, wrong limb count\n"
    "  - Flat pasted-on rectangle (design must integrate with product surface)\n"
    "  - Watermarks, signatures, text overlays, AI-added logos\n"
    "  - Duplicate product placed side by side\n"
    "  - Cartoon, CGI, over-smoothed texture, fake plastic surface\n"
    "  - Floating product with no surface contact\n"
    "  - Compositing seams between design and product\n"
    "  - Overexposure, excessive lens flare, unrealistic color casts\n"
    "  - Cluttered background that distracts from product\n"
    "  - Recoloring the product to a different shade than reference\n"
    "  - Mirroring or flipping the reference design asymmetrically"
)


# ── Quality directive ────────────────────────────────────────────

QUALITY_DIRECTIVE = (
    "[QUALITY DIRECTIVE]\n"
    "Photorealistic RAW commercial photography. Indistinguishable from real camera work.\n"
    "Required: visible skin texture, subtle skin oil reflection, authentic skin imperfections,\n"
    "realistic hair strands, natural facial asymmetry, realistic eyelashes.\n"
    "True-to-life color rendering, 8K ultra detailed.\n"
    "No AI plastic look, no watermarks, no misspelled text, no distorted hands,\n"
    "no warped fabric, no duplicate products, no clutter."
)


# ── Final directive ──────────────────────────────────────────────

FINAL_DIRECTIVE = (
    "[FINAL TOP-1 EXPERT DIRECTIVE]\n"
    "Create a premium POD commercial mockup that looks like a real top-tier advertising photo\n"
    "from a professional brand photoshoot. NOT a generic AI image.\n"
    "The result must be usable directly for Etsy/Amazon/Shopify/dropshipping listing and ads."
)


# ── Tier 2: Product physics ──────────────────────────────────────


def _tier2_product_physics(category: str) -> str:
    physics = {
        "apparel_tshirt": (
            "PRODUCT PHYSICS: Premium heavyweight cotton fabric (220 GSM), "
            "natural fabric folds, realistic draping, detailed shoulder/neck stitching, "
            "authentic clothing physics. The front graphic print is on POD transfer paper — "
            "it must remain fully visible, centered, unwarped, with slight fabric texture visible through the print. "
            "Collar ribbing natural, hem slightly curved. "
            "No floating fabric, no invisible edges, no printed shoulder area distortion."
        ),
        "apparel_hoodie": (
            "PRODUCT PHYSICS: Heavyweight fleece fabric (350 GSM), brushed interior, "
            "thick natural folds, realistic hood draping, metal-tip drawstring details, "
            "ribbed cuffs and waistband with slight tension lines, kangaroo pocket visible. "
            "The front graphic must be cleanly printed, unwarped, centered on chest. "
            "No funnel neck, no flattened hood, no CGI stiffness."
        ),
        "drinkware_tumbler": (
            "PRODUCT PHYSICS: Stainless steel tumbler (20oz), accurate cylindrical shape, "
            "accurate metal reflection and highlight, powder-coated matte finish, "
            "printed design naturally wrapped around curved surface, "
            "seamless lid with slight condensation droplets. "
            "No pasted-on flat label look — design must follow cylinder curvature naturally."
        ),
        "drinkware_mug": (
            "PRODUCT PHYSICS: Ceramic mug (11oz / 15oz), glossy glaze finish, "
            "clean handle attachment, slight rim highlight, printed design wrapped around "
            "curved surface with natural cylindrical distortion. "
            "Inside white ceramic visible from top angle. "
            "No flat printed sticker look — must look directly screen-printed on ceramic."
        ),
        "wallart_poster": (
            "PRODUCT PHYSICS: Premium museum-grade poster paper, matte finish, "
            "clean edges, no curling, either framed (thin black/white/wood frame, glass reflection) "
            "or unframed with clean border. Print must be sharp, colors accurate. "
            "No wrinkled paper, no bent corners, no fake floor reflection."
        ),
        "wallart_canvas": (
            "PRODUCT PHYSICS: Gallery-wrapped canvas, wooden stretcher frame visible from edge, "
            "canvas weave texture subtly visible, depth 1.5 inches, clean corners, "
            "either hanging on wall or leaning on floor/table. "
            "No plastic-looking canvas surface, no unrealistic canvas sagging."
        ),
        "accessory_phonecase": (
            "PRODUCT PHYSICS: Premium phone case, accurate device shape, "
            "camera cutout aligned, button details visible, printed design on back, "
            "matte or glossy finish, snug fit, realistic device proportions. "
            "No generic rectangle shape — must match actual phone silhouette."
        ),
        "accessory_tote": (
            "PRODUCT PHYSICS: Heavy canvas tote bag, natural fabric weave, "
            "reinforced stitching on handles, printed design centered on front panel, "
            "slight fabric folds, carried by hand or on shoulder. "
            "No paper-thin bag look, no blank inside visible in unnatural way."
        ),
        "home_pillow": (
            "PRODUCT PHYSICS: Premium pillow/cushion, soft polyester/linen cover, "
            "visible seam piping, printed design centered, slight plumpness/fill visible, "
            "on sofa/bed/chair in lifestyle setting. No under-stuffed look."
        ),
        "home_blanket": (
            "PRODUCT PHYSICS: Soft fleece/mink blanket, rich drape and folds, "
            "printed design edge-to-edge, realistic fabric texture, "
            "casually draped over sofa or folded. No plastic fabric, no stiff blanket geometry."
        ),
    }
    return physics.get(category, "")


# ── Tier 1: Category base ───────────────────────────────────────


CATEGORY_BASE = {
    "apparel_tshirt": (
        "Fashion editorial photo of model wearing the exact POD t-shirt. "
        "Model: casual relaxed confident pose, front graphic must be fully visible, undistorted. "
        "Photorealistic fabric folds, natural lighting, street or studio setting."
    ),
    "apparel_hoodie": (
        "Streetwear / lifestyle photo of model wearing the exact hoodie. "
        "Model: relaxed pose, hood optionally up or down, hands in pocket, "
        "natural street/café setting. Front graphic fully visible and unwarped."
    ),
    "drinkware_tumbler": (
        "Premium lifestyle product photo of stainless steel tumbler. "
        "Hand model holding tumbler, condensation visible, design wrapped naturally on curved surface."
    ),
    "drinkware_mug": (
        "Cozy lifestyle product photo of ceramic mug. "
        "Morning coffee scene, hand holding handle, design visible on front/side."
    ),
    "wallart_poster": (
        "Interior decor photo of framed/unframed poster artwork. "
        "Hung on wall at eye level, natural lighting, clean composition, sharp print."
    ),
    "wallart_canvas": (
        "Interior decor photo of gallery-wrapped canvas. "
        "Bright living room setting, canvas edges visible, print sharp."
    ),
    "accessory_phonecase": (
        "Lifestyle product photo of phone case on actual device. "
        "Hand holding phone or flat lay on desk with props. Design centered and visible."
    ),
    "accessory_tote": (
        "Lifestyle photo of canvas tote bag. "
        "Outdoor market or café setting, model carrying bag, design centered."
    ),
    "home_pillow": (
        "Interior decor photo of printed pillow. "
        "Living room sofa or bedroom, pillow placed naturally, design centered."
    ),
    "home_blanket": (
        "Cozy interior photo of printed blanket. "
        "Draped over sofa or folded, edge-to-edge print visible, warm lighting."
    ),
    "stationery_sticker": (
        "Product photo of premium vinyl sticker. "
        "Flat lay on clean surface with lifestyle accessories. "
        "Kiss-cut edges visible, weatherproof gloss finish."
    ),
    "stationery_notebook": (
        "Product photo of hardcover notebook. "
        "Flat lay on wooden desk with pen and coffee. "
        "Design on cover, spine visible, lined paper when open."
    ),
    "default": (
        "Premium lifestyle product photography. "
        "Professional commercial quality, natural setting, hero product clearly visible, "
        "design preserved exactly from reference."
    ),
}


# ── Main builder ────────────────────────────────────────────────


def build_mockup_prompt(
    product_name: str = "",
    product_type: str = "",
    color: str = "",
    user_scene: str = "",
    design_url: str = "",
    shot_type_override: str = "",
    commercial_intent_override: str = "",
) -> Dict[str, Any]:
    category = resolve_category(product_type, product_name, design_url)
    base = CATEGORY_BASE.get(category, CATEGORY_BASE["default"])
    physics = _tier2_product_physics(category)

    # Shot type
    shot_type = shot_type_override or resolve_shot_type(user_scene)
    shot_desc = SHOT_TYPES.get(shot_type, SHOT_TYPES["lifestyle model shot"])

    # Commercial intent
    intent = commercial_intent_override or resolve_commercial_intent(user_scene)
    intent_desc = COMMERCIAL_INTENTS.get(intent, COMMERCIAL_INTENTS["shopify product gallery"])

    # Persona
    persona = resolve_persona(user_scene)
    persona_desc = persona["description"]

    # Camera
    if "apparel" in category:
        camera = CAMERA_FASHION
    elif "drinkware" in category or "accessory" in category:
        camera = CAMERA_PRODUCT
    else:
        camera = CAMERA_LIFESTYLE

    # Build structured 7-block prompt
    parts = []

    # Block 1: Role + shot type + commercial intent
    parts.append(
        "[ROLE & ASSIGNMENT]\n"
        f"You are a senior ecommerce product photographer and POD creative director. "
        f"Shot type: {shot_type} — {shot_desc}. "
        f"Commercial use: {intent_desc}."
    )

    # Block 2: Reference preservation contract
    parts.append(
        f"\n\n{PRESERVATION_CONTRACT}"
    )

    # Block 3: Product identity
    parts.append(
        f"\n\n[PRODUCT IDENTITY]\n"
        f"Product: {product_name}. Product type/category: {product_type or category}. "
        f"Color: {color or 'as shown in reference'}. "
        f"Use the attached/reference product as the only source of truth."
    )

    # Block 4: Physics & Material Realism
    parts.append(
        "\n\n[PRODUCT-TYPE PHYSICS & MATERIAL REALISM]\n"
        + (physics or "Infer the correct physical material, surface, depth, weight, texture and natural contact points from the product type. Make it believable under real-world physics.")
    )

    # Block 5: Scene, Model & Commercial Composition
    parts.append(
        "\n\n[SCENE, MODEL & COMMERCIAL COMPOSITION]\n"
        + base + " "
        + (f"User requested style/scene: {user_scene}. " if user_scene else "Choose the most commercially suitable lifestyle scene for this product. ")
        + f"Model direction: {persona_desc}. "
        + "The product must be the hero subject, clearly visible, marketplace-ready, with uncluttered premium composition."
    )

    # Block 6: Camera, Lighting & Photorealism
    parts.append(
        "\n\n[CAMERA, LIGHTING & PHOTOREALISM]\n"
        f"Camera setup: {camera}. "
        f"Use realistic camera optics, natural shadows, correct perspective, "
        f"believable contact points, true-to-life color rendering, "
        f"shallow depth of field where appropriate, RAW commercial photography quality."
    )

    # Block 7: Quality control, negative constraints, final directive
    parts.append(
        "\n\n[QUALITY & NEGATIVE CONSTRAINTS]\n"
        "Before finalizing, self-check: product type correct, print/design readable, "
        "product not warped, no duplicate products, no AI plastic look, "
        "no watermarks, no extra text, no distorted hands, no wrong color, "
        "no compositing seams.\n"
        + QUALITY_DIRECTIVE
        + "\n\n"
        + NEGATIVE_CONSTRAINTS
    )

    # Final directive
    parts.append("\n\n" + FINAL_DIRECTIVE)

    full_prompt = "\n".join(parts).strip()

    return {
        "prompt": full_prompt,
        "category": category,
        "shot_type": shot_type,
        "commercial_intent": intent,
        "persona": persona_desc,
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
    result = build_mockup_prompt(product_name=product_name, product_type=product_type, color=color, user_scene=user_scene)
    category = result["category"]
    lines = [
        f"Shot: {result.get('shot_type', 'lifestyle')}",
        f"Intent: {result.get('commercial_intent', 'marketplace')}",
        f"Persona: {result.get('persona', 'professional adult')[:200]}",
        CATEGORY_BASE.get(category, CATEGORY_BASE["default"])[:300],
        f"PRODUCT: {product_name}",
        f"SCENE: {user_scene or 'premium commercial setting'}",
        CAMERA_FASHION if "apparel" in category else CAMERA_PRODUCT,
        PRESERVATION_CONTRACT[:200] + "...",
        NEGATIVE_CONSTRAINTS[:200] + "...",
    ]
    return "\n".join(lines)
