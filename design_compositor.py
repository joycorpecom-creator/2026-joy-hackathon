"""Deterministic design/product/lifestyle compositing.

Supports: flat composite, perspective warp, fabric blending.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple, List

from PIL import Image, ImageEnhance, ImageFilter, ImageDraw


def normalize_design_layer(design_path: str | Path, target_size: Tuple[int, int]) -> Image.Image:
    """Resize design to fit target print box while preserving aspect ratio."""
    design = Image.open(design_path).convert("RGBA")
    box_w, box_h = target_size
    design.thumbnail((box_w, box_h), Image.LANCZOS)
    canvas = Image.new("RGBA", target_size, (0, 0, 0, 0))
    x = (box_w - design.width) // 2
    y = (box_h - design.height) // 2
    canvas.alpha_composite(design, (x, y))
    return canvas


def _bbox_to_polygon(print_bbox: Dict[str, int]) -> List[Tuple[int, int]]:
    x, y, w, h = int(print_bbox["x"]), int(print_bbox["y"]), int(print_bbox["w"]), int(print_bbox["h"])
    # Mild perspective: top slightly narrower than bottom for worn apparel look.
    inset = int(w * 0.06)
    return [(x + inset, y), (x + w - inset, y), (x + w, y + h), (x, y + h)]


def perspective_warp_design(design_path: str | Path, polygon: List[Tuple[int, int]], canvas_size: Tuple[int, int]) -> tuple[Image.Image, Image.Image, tuple[int, int, int, int]]:
    """Warp design into a quadrilateral using OpenCV perspective transform.

    Returns (warped_rgba_full_canvas, placed_flat_design, bbox_tuple).
    Falls back to a non-warped paste if OpenCV/numpy unavailable.
    """
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    x, y, x2, y2 = min(xs), min(ys), max(xs), max(ys)
    w, h = max(1, x2 - x), max(1, y2 - y)
    placed = normalize_design_layer(design_path, (w, h))
    try:
        import cv2
        import numpy as np
        src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        dst = np.float32(polygon)
        M = cv2.getPerspectiveTransform(src, dst)
        arr = np.array(placed)
        warped = cv2.warpPerspective(arr, M, canvas_size, flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_TRANSPARENT)
        return Image.fromarray(warped, "RGBA"), placed, (x, y, w, h)
    except Exception:
        layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        layer.alpha_composite(placed, (x, y))
        return layer, placed, (x, y, w, h)


def blend_with_fabric(product: Image.Image, warped_design: Image.Image, polygon: List[Tuple[int, int]]) -> Image.Image:
    """Composite warped design with subtle fabric lighting while preserving artwork.

    The original design layer remains source-of-truth; only low-alpha shadows/highlights
    are applied so text/graphics remain readable.
    """
    base = product.convert("RGBA")
    design = warped_design.convert("RGBA")
    alpha = design.getchannel("A")

    # Soft print contact shadow from design alpha.
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    shadow.putalpha(alpha.filter(ImageFilter.GaussianBlur(5)))
    shadow = ImageEnhance.Brightness(shadow).enhance(0.18)

    # Very subtle highlight following print polygon.
    highlight = Image.new("RGBA", base.size, (255, 255, 255, 0))
    mask = Image.new("L", base.size, 0)
    d = ImageDraw.Draw(mask)
    d.polygon(polygon, fill=14)
    highlight.putalpha(mask.filter(ImageFilter.GaussianBlur(7)))

    # Integrity-first: product/contact shadow underneath; original design last.
    # Do NOT put highlights over the artwork; even low-alpha white shifts colors
    # and hurts text-heavy SSIM. Lifestyle realism is handled by product/scene,
    # not by recoloring the print file.
    out = Image.alpha_composite(base, shadow)
    out = Image.alpha_composite(out, highlight)
    out = Image.alpha_composite(out, design)
    return out


def composite_design_on_product(product_image: Image.Image, design_path: str | Path, print_bbox: Dict[str, int]) -> tuple[Image.Image, Image.Image, tuple[int, int, int, int]]:
    """Place original design on product image.

    Returns: (product_with_design, placed_design_layer, bbox_tuple).
    """
    product = product_image.convert("RGBA")
    polygon = _bbox_to_polygon(print_bbox)
    warped, placed, bbox = perspective_warp_design(design_path, polygon, product.size)
    out = blend_with_fabric(product, warped, polygon)
    return out, placed, bbox

def composite_product_into_scene(scene: Image.Image, product: Image.Image, scale: float = 0.55) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Place product layer into lifestyle scene with shadow.

    Removes product background automatically before compositing.
    """
    from image_preprocess import remove_product_background, trim_transparent, match_product_lighting, make_contact_shadow

    scene = scene.convert("RGBA")
    product = product.convert("RGBA")
    # Remove BP product background to avoid rectangular cutout artifacts.
    product = trim_transparent(remove_product_background(product), padding=18)
    product = match_product_lighting(product, scene)
    product = Image.alpha_composite(Image.new("RGBA", product.size, (255, 255, 255, 0)), product)
    max_w = int(scene.width * scale)
    max_h = int(scene.height * 0.76)
    product.thumbnail((max_w, max_h), Image.LANCZOS)

    x = (scene.width - product.width) // 2
    y = int(scene.height * 0.52 - product.height / 2)
    y = max(20, min(y, scene.height - product.height - 20))

    alpha = product.split()[-1]
    shadow = make_contact_shadow(alpha, scene.size, (x, y))

    out = scene.copy()
    out.alpha_composite(shadow)
    out.alpha_composite(product, (x, y))
    return out.convert("RGB"), (x, y, product.width, product.height)
