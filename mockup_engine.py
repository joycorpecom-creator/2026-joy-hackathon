import hashlib
import os
import time
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageSequence

from burgerprints import OrderAsset
from providers import build_scene_prompt, try_generate_ai_scene, try_generate_lifestyle_mockup, try_generate_dual_input_lifestyle_mockup
from prompts import build_product_mockup_prompt
from product_layout import pick_base_image, infer_print_bbox
from design_compositor import composite_design_on_product
from integrity import compare_design_to_layer

ROOT = Path(__file__).parent
OUTPUT_DIR = ROOT / "outputs"
ASSET_DIR = ROOT / "assets"
OUTPUT_DIR.mkdir(exist_ok=True)
ASSET_DIR.mkdir(exist_ok=True)


def _safe_name(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)[:80]


def download_image(url: str) -> Path:
    h = hashlib.sha1(url.encode()).hexdigest()[:12]
    suffix = Path(urlparse(url).path).suffix or ".png"
    path = ASSET_DIR / f"{h}{suffix}"
    if path.exists():
        return path
    res = requests.get(url, timeout=60)
    res.raise_for_status()
    path.write_bytes(res.content)
    return path


def make_scene(prompt: str, product_color: str, size: Tuple[int, int] = (1600, 1600)) -> Image.Image:
    """Deterministic placeholder lifestyle scene. Replace with Replicate/Gemini later."""
    w, h = size
    bg = Image.new("RGB", size, "#ead8c0")
    draw = ImageDraw.Draw(bg)

    # warm cafe/studio gradient-ish background
    for y in range(h):
        r = int(235 - y * 25 / h)
        g = int(220 - y * 45 / h)
        b = int(198 - y * 65 / h)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    # floor/table
    draw.rectangle([0, int(h * 0.72), w, h], fill="#b8895f")
    draw.ellipse([100, 100, 360, 360], fill="#f8d88a", outline="#ffe9b5", width=8)
    draw.ellipse([1180, 180, 1450, 430], fill="#fff0b0", outline="#ffe9b5", width=8)

    # simplified torso/shirt
    shirt = product_color or "#25282A"
    body = [430, 330, 1170, 1370]
    draw.rounded_rectangle(body, radius=90, fill=shirt, outline="#111111", width=6)
    draw.polygon([(430, 390), (260, 700), (420, 780), (520, 490)], fill=shirt, outline="#111111")
    draw.polygon([(1170, 390), (1340, 700), (1180, 780), (1080, 490)], fill=shirt, outline="#111111")
    draw.ellipse([650, 180, 950, 470], fill="#c89268", outline="#6f4a35", width=4)
    draw.rectangle([680, 430, 920, 560], fill="#c89268")

    # prompt caption subtle
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except Exception:
        font = None
    caption = prompt[:90]
    draw.rounded_rectangle([70, 1470, 1530, 1550], radius=20, fill=(255, 255, 255, 150))
    draw.text((95, 1490), caption, fill="#3b2d24", font=font)
    return bg


def composite_design(scene: Image.Image, design_path: Path) -> Image.Image:
    design = Image.open(design_path).convert("RGBA")
    design.thumbnail((520, 620), Image.LANCZOS)

    # preserve exact design pixels; only resize once, no redraw
    x = (scene.width - design.width) // 2
    y = 640

    shadow = Image.new("RGBA", scene.size, (0, 0, 0, 0))
    shadow.paste(design.split()[-1].filter(ImageFilter.GaussianBlur(7)), (x + 10, y + 12))
    shadow = ImageEnhance.Brightness(shadow).enhance(0.25)

    out = scene.convert("RGBA")
    out.alpha_composite(shadow)
    out.alpha_composite(design, (x, y))

    # light fabric overlay, does not alter design geometry
    overlay = Image.new("RGBA", scene.size, (255, 255, 255, 0))
    d = ImageDraw.Draw(overlay)
    d.ellipse([420, 520, 1180, 1120], fill=(255, 255, 255, 18))
    out = Image.alpha_composite(out, overlay)
    return out.convert("RGB")


def composite_product_image(scene: Image.Image, product_path: Path) -> Image.Image:
    """Composite an exact BurgerPrints base mockup image onto the AI scene.

    Preserves product pixels; only resize + shadow. Used when user asks for
    product mockup from catalog without an order/design file.
    """
    product = Image.open(product_path).convert("RGBA")
    product.thumbnail((720, 900), Image.LANCZOS)

    out = scene.convert("RGBA")
    x = int(scene.width * 0.60) - product.width // 2
    y = int(scene.height * 0.53) - product.height // 2
    x = max(20, min(x, scene.width - product.width - 20))
    y = max(20, min(y, scene.height - product.height - 20))

    # soft product shadow
    alpha = product.split()[-1]
    shadow = Image.new("RGBA", scene.size, (0, 0, 0, 0))
    shadow.paste(alpha.filter(ImageFilter.GaussianBlur(18)), (x + 24, y + 30))
    shadow = ImageEnhance.Brightness(shadow).enhance(0.35)
    out.alpha_composite(shadow)
    out.alpha_composite(product, (x, y))
    return out.convert("RGB")
