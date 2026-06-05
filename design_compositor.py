"""Deterministic design/product/lifestyle compositing."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

from PIL import Image, ImageEnhance, ImageFilter


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


def composite_design_on_product(product_image: Image.Image, design_path: str | Path, print_bbox: Dict[str, int]) -> tuple[Image.Image, Image.Image, tuple[int, int, int, int]]:
    """Place original design on product image.

    Returns: (product_with_design, placed_design_layer, bbox_tuple).
    """
    product = product_image.convert("RGBA")
    x, y, w, h = int(print_bbox["x"]), int(print_bbox["y"]), int(print_bbox["w"]), int(print_bbox["h"])
    placed = normalize_design_layer(design_path, (w, h))
    # Slight fabric highlight to reduce pasted look while keeping artwork mostly intact.
    try:
        from image_preprocess import add_subtle_fabric_shading
        placed_visual = add_subtle_fabric_shading(placed, strength=10)
    except Exception:
        placed_visual = placed

    # Subtle shadow from alpha; design pixels remain untouched.
    shadow = Image.new("RGBA", product.size, (0, 0, 0, 0))
    alpha = placed.split()[-1]
    shadow.paste(alpha.filter(ImageFilter.GaussianBlur(5)), (x + 4, y + 5))
    shadow = ImageEnhance.Brightness(shadow).enhance(0.22)

    out = product.copy()
    out.alpha_composite(shadow)
    out.alpha_composite(placed_visual, (x, y))

    # Very light fabric highlight over whole print area (low alpha).
    highlight = Image.new("RGBA", product.size, (255, 255, 255, 0))
    mask = Image.new("L", (w, h), 18)
    highlight.paste((255, 255, 255, 18), (x, y), mask)
    out = Image.alpha_composite(out, highlight)

    return out, placed, (x, y, w, h)


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
