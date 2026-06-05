"""
Design Store — per-chat session design file management.

Saves uploaded designs (PNG/JPG/SVG) to `uploads/{chat_id}/`.
Converts SVG→PNG via CairoSVG. Stores metadata JSON.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent
UPLOAD_DIR = ROOT / "uploads"


def _ensure_chat_dir(chat_id: str) -> Path:
    d = UPLOAD_DIR / chat_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _normalize_svg_to_png(svg_path: Path, output_path: Path) -> Path:
    """Convert SVG to normalized PNG. Requires cairosvg."""
    try:
        import cairosvg
        cairosvg.svg2png(url=str(svg_path), write_to=str(output_path))
        return output_path
    except ImportError:
        raise RuntimeError("cairosvg not installed. Install: pip install cairosvg")


def save_design(
    chat_id: str,
    file_bytes: bytes,
    original_filename: str,
    mime: str,
) -> dict:
    """
    Save uploaded design file to disk + metadata.

    Returns dict: {design_id, original_filename, normalized_path, source_path,
                   mime, width, height, has_alpha, created_at}
    """
    chat_dir = _ensure_chat_dir(chat_id)

    # Short unique design_id
    design_id = hashlib.sha1(file_bytes).hexdigest()[:12]

    # Determine file extension
    suffix = Path(original_filename).suffix.lower() or ".png"
    if suffix not in (".png", ".jpg", ".jpeg", ".svg"):
        raise ValueError(f"Unsupported file type: {suffix}")

    source_name = f"{design_id}_src{suffix}"
    source_path = chat_dir / source_name
    source_path.write_bytes(file_bytes)

    # Normalize to PNG
    normalized_path: Path

    if suffix == ".svg":
        normalized_name = f"{design_id}_normalized.png"
        normalized_path = chat_dir / normalized_name
        _normalize_svg_to_png(source_path, normalized_path)
        from PIL import Image
    else:
        normalized_name = source_name
        normalized_path = source_path

    # Read dimensions + alpha
    from PIL import Image
    img = Image.open(normalized_path)
    width, height = img.size
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)

    metadata = {
        "design_id": design_id,
        "chat_id": chat_id,
        "original_filename": original_filename,
        "source_path": str(source_path),
        "normalized_path": str(normalized_path),
        "mime": mime or f"image/{suffix.lstrip('.')}",
        "width": width,
        "height": height,
        "has_alpha": has_alpha,
        "created_at": int(Path(source_path).stat().st_mtime),
        "file_size": len(file_bytes),
    }

    # Save metadata JSON
    meta_path = chat_dir / f"{design_id}_meta.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    return metadata


def get_current_design(chat_id: str) -> Optional[dict]:
    """Get the most recent design for a chat session. Returns metadata dict or None."""
    chat_dir = UPLOAD_DIR / chat_id
    if not chat_dir.exists():
        return None

    # Find latest metadata file
    meta_files = sorted(chat_dir.glob("*_meta.json"), reverse=True)
    for mf in meta_files:
        try:
            return json.loads(mf.read_text())
        except Exception:
            continue
    return None


def clear_design(chat_id: str):
    """Remove all designs for a chat session."""
    chat_dir = UPLOAD_DIR / chat_id
    if chat_dir.exists():
        import shutil
        shutil.rmtree(chat_dir)
