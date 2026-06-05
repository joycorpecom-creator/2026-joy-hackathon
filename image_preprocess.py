"""Image preprocessing for BurgerMockup.

- Product background removal before scene composite.
- Lightweight uploaded-design validation/warnings.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat


def has_useful_alpha(img: Image.Image, min_transparent_ratio: float = 0.05) -> bool:
    """Return True if image has meaningful transparency."""
    if img.mode not in ("RGBA", "LA") and not (img.mode == "P" and "transparency" in img.info):
        return False
    a = img.convert("RGBA").split()[-1]
    hist = a.histogram()
    total = sum(hist) or 1
    transparent = sum(hist[:245])
    return (transparent / total) >= min_transparent_ratio


def validate_design_file(path: str | Path) -> Dict[str, object]:
    """Non-blocking design diagnostics.

    Telegram photo uploads become JPG and lose transparency, so this function
    returns warnings instead of rejecting. Agent can surface these warnings.
    """
    img = Image.open(path)
    w, h = img.size
    alpha = has_useful_alpha(img)
    warnings = []
    if not alpha:
        warnings.append("no_alpha: PNG/document upload recommended for exact print isolation")
    if w < 800 or h < 800:
        warnings.append("low_resolution: upload ≥1500px design for best listing output")
    # Product-render heuristic: portrait JPG with no alpha often is a mockup/photo, not flat artwork.
    if not alpha and img.format in ("JPEG", "JPG") and 0.65 <= (w / max(h, 1)) <= 1.05:
        warnings.append("possible_product_mockup: image looks like a product/photo render, not a flat print file")
    return {"width": w, "height": h, "has_alpha": alpha, "warnings": warnings}


def remove_product_background(img: Image.Image) -> Image.Image:
    """Return RGBA product cutout. Uses rembg if available, else simple corner-key fallback."""
    rgba = img.convert("RGBA")
    try:
        from rembg import remove
        cut = remove(rgba)
        cut = cut.convert("RGBA")
        # Slight alpha cleanup/feather to avoid cutout jaggies.
        r, g, b, a = cut.split()
        a = a.filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.GaussianBlur(0.6))
        return Image.merge("RGBA", (r, g, b, a))
    except Exception:
        return remove_product_background_fallback(rgba)


def remove_product_background_fallback(img: Image.Image, tolerance: int = 34) -> Image.Image:
    """Cheap background removal using corner colors.

    Works for plain/black/white BP mockup backgrounds; not semantic but prevents
    rectangular black/white boxes when rembg unavailable.
    """
    rgba = img.convert("RGBA")
    w, h = rgba.size
    px = rgba.load()
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    # average RGB corner background
    bg = tuple(int(sum(c[i] for c in corners) / len(corners)) for i in range(3))
    out = rgba.copy()
    opx = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = opx[x, y]
            dist = abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2])
            if dist < tolerance:
                opx[x, y] = (r, g, b, 0)
            elif dist < tolerance * 2:
                # Feather near-bg pixels.
                na = int(a * min(1.0, (dist - tolerance) / tolerance))
                opx[x, y] = (r, g, b, na)
    r, g, b, a = out.split()
    a = a.filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    return Image.merge("RGBA", (r, g, b, a))


def trim_transparent(img: Image.Image, padding: int = 12) -> Image.Image:
    """Crop transparent bounds with padding."""
    rgba = img.convert("RGBA")
    bbox = rgba.split()[-1].getbbox()
    if not bbox:
        return rgba
    x1, y1, x2, y2 = bbox
    x1 = max(0, x1 - padding)
    y1 = max(0, y1 - padding)
    x2 = min(rgba.width, x2 + padding)
    y2 = min(rgba.height, y2 + padding)
    return rgba.crop((x1, y1, x2, y2))


def match_product_lighting(product: Image.Image, scene: Image.Image) -> Image.Image:
    """Gently match product brightness/contrast to scene.

    Keeps color shifts small to protect product/design fidelity.
    """
    prod = product.convert("RGBA")
    alpha = prod.split()[-1]
    if not alpha.getbbox():
        return prod
    scene_rgb = scene.convert("RGB")
    prod_rgb = Image.new("RGB", prod.size, (255, 255, 255))
    prod_rgb.paste(prod.convert("RGB"), mask=alpha)

    scene_mean = sum(ImageStat.Stat(scene_rgb).mean) / 3.0
    prod_mean = sum(ImageStat.Stat(prod_rgb, alpha).mean[:3]) / 3.0 if alpha else scene_mean
    if prod_mean <= 1:
        return prod
    factor = max(0.82, min(1.18, scene_mean / prod_mean))
    prod_rgb = ImageEnhance.Brightness(prod_rgb).enhance(factor)

    # Slightly soften overly flat catalog product for photo scene.
    contrast = 0.96 if scene_mean < 120 else 1.04
    prod_rgb = ImageEnhance.Contrast(prod_rgb).enhance(contrast)
    out = prod_rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def make_contact_shadow(alpha: Image.Image, size: Tuple[int, int], offset: Tuple[int, int]) -> Image.Image:
    """Create layered shadow: soft global + stronger contact under product."""
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    sx, sy = offset
    soft = alpha.filter(ImageFilter.GaussianBlur(26))
    contact = alpha.filter(ImageFilter.GaussianBlur(9))
    shadow.paste(soft, (sx + 30, sy + 38))
    shadow = ImageEnhance.Brightness(shadow).enhance(0.24)
    contact_layer = Image.new("RGBA", size, (0, 0, 0, 0))
    contact_layer.paste(contact, (sx + 10, sy + 18))
    contact_layer = ImageEnhance.Brightness(contact_layer).enhance(0.16)
    return Image.alpha_composite(shadow, contact_layer)


def add_subtle_fabric_shading(layer: Image.Image, strength: int = 14) -> Image.Image:
    """Add very light center highlight/edge shade over placed print layer.

    Designed to look less pasted while preserving most design pixels.
    """
    rgba = layer.convert("RGBA")
    w, h = rgba.size
    shade = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    px = shade.load()
    for y in range(h):
        for x in range(w):
            nx = abs((x / max(w - 1, 1)) - 0.5) * 2
            ny = abs((y / max(h - 1, 1)) - 0.5) * 2
            v = int(strength * (1 - min(1, (nx * 0.7 + ny * 0.3))))
            if v > 0:
                px[x, y] = (255, 255, 255, v)
    return Image.alpha_composite(rgba, shade)
