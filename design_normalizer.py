"""Uploaded print-design normalization utilities.

Purpose: keep original artwork pixels as source-of-truth while preparing a clean
transparent RGBA layer for deterministic compositing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

from PIL import Image, ImageChops


def _corner_bg_color(rgb: Image.Image) -> tuple[int, int, int]:
    """Robust bg sample from corners (handles black/white/solid color)."""
    pts = [
        rgb.getpixel((0, 0)),
        rgb.getpixel((rgb.width - 1, 0)),
        rgb.getpixel((0, rgb.height - 1)),
        rgb.getpixel((rgb.width - 1, rgb.height - 1)),
    ]
    # median per channel avoids one noisy corner
    return tuple(sorted(p[i] for p in pts)[len(pts)//2] for i in range(3))


def _alpha_bbox(img: Image.Image) -> Tuple[int, int, int, int] | None:
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")
    if alpha.getextrema()[0] < 255:
        return alpha.getbbox()
    return None


def _solid_bg_mask(img: Image.Image, tolerance: int = 22) -> Image.Image:
    """Return L mask where non-background pixels are 255.

    Fixes JPG/SVG renders with opaque black/white/color backgrounds.
    """
    rgb = img.convert("RGB")
    bg = _corner_bg_color(rgb)
    bg_img = Image.new("RGB", rgb.size, bg)
    diff = ImageChops.difference(rgb, bg_img)
    # max channel distance; keeps text/colored art, removes near-solid bg
    r, g, b = diff.split()
    m = ImageChops.lighter(ImageChops.lighter(r, g), b)
    return m.point(lambda p: 255 if p > tolerance else 0)


def _content_bbox(img: Image.Image) -> Tuple[int, int, int, int] | None:
    rgba = img.convert("RGBA")
    bbox = _alpha_bbox(rgba)
    if bbox:
        return bbox
    return _solid_bg_mask(rgba).getbbox()


def _remove_solid_background(img: Image.Image, tolerance: int = 22) -> tuple[Image.Image, bool, tuple[int, int, int]]:
    """If image is fully opaque, remove near-solid corner background.

    Conservative: only for no-alpha uploads. Transparent PNG source remains untouched.
    """
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")
    if alpha.getextrema()[0] < 255:
        return rgba, False, (0, 0, 0)

    rgb = rgba.convert("RGB")
    bg = _corner_bg_color(rgb)
    fg_mask = _solid_bg_mask(rgb, tolerance=tolerance)
    if not fg_mask.getbbox():
        return rgba, False, bg

    # Smooth edge a little, preserve exact RGB of artwork.
    out = rgba.copy()
    out.putalpha(fg_mask)
    return out, True, bg


def normalize_design_file(
    design_path: str | Path,
    *,
    max_side: int = 1600,
    padding: int = 24,
    bg_tolerance: int = 22,
) -> Dict[str, object]:
    """Trim transparent/empty padding and output clean RGBA PNG.

    Returns metadata:
      normalized_path, width, height, bbox, has_alpha, removed_background, bg_color
    """
    src = Path(design_path)
    raw = Image.open(src).convert("RGBA")
    has_alpha = raw.getchannel("A").getextrema()[0] < 255
    img, removed_bg, bg_color = _remove_solid_background(raw, tolerance=bg_tolerance)

    bbox = _content_bbox(img) or (0, 0, img.width, img.height)
    cropped = img.crop(bbox)

    canvas = Image.new("RGBA", (cropped.width + padding * 2, cropped.height + padding * 2), (0, 0, 0, 0))
    canvas.alpha_composite(cropped, (padding, padding))

    if max(canvas.width, canvas.height) > max_side:
        canvas.thumbnail((max_side, max_side), Image.LANCZOS)

    out = src.with_name(src.stem + "_clean.png")
    canvas.save(out, "PNG")
    return {
        "normalized_path": str(out),
        "width": canvas.width,
        "height": canvas.height,
        "bbox": {"x1": bbox[0], "y1": bbox[1], "x2": bbox[2], "y2": bbox[3]},
        "has_alpha": has_alpha,
        "removed_background": removed_bg,
        "bg_color": bg_color,
        "bg_tolerance": bg_tolerance,
    }
