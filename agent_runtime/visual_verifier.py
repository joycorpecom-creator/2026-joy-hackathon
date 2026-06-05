"""Visual verifier — lightweight image sanity checks.

Current v1 avoids remote AI calls for cost/reliability. It verifies that generated files
exist, are decodable images, and have reasonable dimensions. Future: add LLM vision
semantic checks (shirt visible, print preserved, scene match).
"""

import os
from pathlib import Path
from typing import Dict, Any, List

ROOT = Path(__file__).resolve().parents[1]


def verify_image(image: Dict[str, Any]) -> Dict[str, Any]:
    url = image.get("url") or image.get("image_url") or ""
    local = image.get("local_path") or ""
    if not local and url.startswith("/outputs/"):
        local = str(ROOT / url.lstrip("/"))
    problems: List[str] = []
    meta: Dict[str, Any] = {}
    if not local or not os.path.exists(local):
        problems.append("local file missing")
        return {"ok": False, "problems": problems, "meta": meta}
    try:
        from PIL import Image
        with Image.open(local) as im:
            meta["width"], meta["height"] = im.size
            meta["mode"] = im.mode
            if im.size[0] < 512 or im.size[1] < 512:
                problems.append("image too small")
            if im.size[0] > 4096 or im.size[1] > 4096:
                problems.append("image unusually large")
    except Exception as e:
        problems.append(f"image decode failed: {e}")
    return {"ok": not problems, "problems": problems, "meta": meta}


def verify_images(images: list) -> Dict[str, Any]:
    checks = [verify_image(im) for im in images]
    problems = []
    for i, c in enumerate(checks, start=1):
        if not c["ok"]:
            problems.append({"index": i, "problems": c["problems"]})
    return {"ok": not problems, "checks": checks, "problems": problems}
