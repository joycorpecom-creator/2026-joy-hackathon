"""Product layout heuristics for BP catalog products."""
from __future__ import annotations

from typing import Any, Dict, Tuple


def pick_base_image(product: Dict[str, Any]) -> str:
    """Pick best base/mockup image URL from BP product payload."""
    for k in ("url", "image", "mockup_url", "front_image", "thumbnail", "preview_url"):
        v = product.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
    for k in ("images", "mockups", "previews"):
        rows = product.get(k) or []
        if isinstance(rows, list):
            for item in rows:
                if isinstance(item, str) and item.startswith("http"):
                    return item
                if isinstance(item, dict):
                    for kk in ("url", "src", "image", "thumbnail"):
                        v = item.get(kk)
                        if isinstance(v, str) and v.startswith("http"):
                            return v
    return ""


def _category(product_name: str, short_code: str = "") -> str:
    s = f"{product_name} {short_code}".lower()
    if any(x in s for x in ("mug", "tumbler", "cup", "bottle", "flask")):
        return "drinkware"
    if any(x in s for x in ("hoodie", "sweatshirt")):
        return "hoodie"
    if any(x in s for x in ("poster", "canvas", "print")):
        return "flat"
    return "shirt"


def infer_print_bbox(product: Dict[str, Any], image_size: Tuple[int, int]) -> Dict[str, Any]:
    """Return print area bbox in image pixels with confidence.

    Priority: explicit BP fields if present → category fallback.
    """
    w, h = image_size

    # Search common direct print-area shapes.
    candidates = []
    for key in ("print_area", "printArea", "print_area_front", "front_print_area", "design_area", "template_area"):
        v = product.get(key)
        if isinstance(v, dict):
            candidates.append(v)
    for c in candidates:
        try:
            x = float(c.get("x", c.get("left")))
            y = float(c.get("y", c.get("top")))
            bw = float(c.get("width", c.get("w")))
            bh = float(c.get("height", c.get("h")))
            # Normalize if values look 0..1
            if bw <= 1 and bh <= 1:
                return {"x": int(x*w), "y": int(y*h), "w": int(bw*w), "h": int(bh*h), "source": "bp", "confidence": 0.95}
            return {"x": int(x), "y": int(y), "w": int(bw), "h": int(bh), "source": "bp", "confidence": 0.95}
        except Exception:
            pass

    cat = _category(product.get("display_name") or product.get("name") or "", product.get("short_code") or "")
    if cat == "drinkware":
        vals = (0.37, 0.28, 0.26, 0.42)
    elif cat == "hoodie":
        vals = (0.34, 0.37, 0.32, 0.30)
    elif cat == "flat":
        vals = (0.16, 0.16, 0.68, 0.68)
    else:
        vals = (0.34, 0.34, 0.32, 0.34)
    x, y, bw, bh = vals
    return {"x": int(x*w), "y": int(y*h), "w": int(bw*w), "h": int(bh*h), "source": f"fallback:{cat}", "confidence": 0.65}
