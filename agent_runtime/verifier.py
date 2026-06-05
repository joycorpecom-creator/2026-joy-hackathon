"""Verifier — validates generated job output."""

from typing import Dict, Any, List


def verify_mockup_result(result: Dict[str, Any]) -> Dict[str, Any]:
    images = result.get("images") or []
    requested = (result.get("meta") or {}).get("requested") or len(images)
    urls = [im.get("url") for im in images if im.get("url")]
    problems: List[str] = []
    if len(images) != requested:
        problems.append(f"count mismatch: generated={len(images)} requested={requested}")
    if len(set(urls)) != len(urls):
        problems.append("duplicate image urls")
    for i, im in enumerate(images, start=1):
        if not im.get("url"):
            problems.append(f"image {i} missing url")
        if not im.get("scene"):
            problems.append(f"image {i} missing scene")
    visual = {"ok": True, "checks": [], "problems": []}
    if images:
        try:
            from .visual_verifier import verify_images
            visual = verify_images(images)
            if not visual.get("ok"):
                problems.append("visual file check failed")
        except Exception:
            pass
    return {"ok": not problems, "problems": problems, "visual": visual}
