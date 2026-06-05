"""Image preprocessing for BurgerMockup.

- Product background removal before scene composite.
- Lightweight uploaded-design validation/warnings.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

from PIL import Image, ImageFilter, ImageOps


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
