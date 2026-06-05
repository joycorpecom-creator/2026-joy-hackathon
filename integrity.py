"""Design integrity metrics for BurgerMockup."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

from PIL import Image


def _rgb(img: Image.Image) -> Image.Image:
    if img.mode == "RGBA":
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.alpha_composite(img)
        return bg.convert("RGB")
    return img.convert("RGB")


def _ssim(a: Image.Image, b: Image.Image) -> float:
    import numpy as np
    try:
        from skimage.metrics import structural_similarity
        aa = np.asarray(_rgb(a))
        bb = np.asarray(_rgb(b).resize(a.size))
        return float(structural_similarity(aa, bb, channel_axis=2, data_range=255))
    except Exception:
        # Lightweight fallback: normalized inverse MSE.
        aa = np.asarray(_rgb(a)).astype("float32")
        bb = np.asarray(_rgb(b).resize(a.size)).astype("float32")
        mse = ((aa - bb) ** 2).mean()
        return max(0.0, 1.0 - mse / (255.0 ** 2))


def compare_design_to_layer(source_design: str | Path, placed_design: Image.Image) -> Dict[str, float | bool | str]:
    """Flat SSIM: source design vs resized placed design before scene effects."""
    src = Image.open(source_design).convert("RGBA")
    score = _ssim(src, placed_design.convert("RGBA"))
    return {"score": round(score, 4), "threshold": 0.92, "pass": score >= 0.92, "method": "flat_ssim"}


def compare_design_to_final_crop(
    source_design: str | Path,
    final_image: Image.Image,
    bbox: Tuple[int, int, int, int],
) -> Dict[str, float | bool | str]:
    """Lifestyle SSIM: source design vs final crop region."""
    src = Image.open(source_design).convert("RGBA")
    x, y, w, h = bbox
    crop = final_image.crop((x, y, x+w, y+h)).convert("RGBA")
    score = _ssim(src, crop)
    return {"score": round(score, 4), "threshold": 0.85, "pass": score >= 0.85, "method": "lifestyle_ssim_crop"}
