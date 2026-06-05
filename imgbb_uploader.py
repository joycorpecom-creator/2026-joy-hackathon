"""Upload generated mockup PNGs to imgbb and return public image URL."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import requests

DEFAULT_IMGBB_API_KEY = "5c9d36c4d8f45696febcd30403b28028"


def upload_image(path: str, api_key: str = DEFAULT_IMGBB_API_KEY, timeout: int = 60) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": f"file not found: {path}"}
    try:
        with p.open("rb") as f:
            r = requests.post(
                "https://api.imgbb.com/1/upload",
                params={"key": api_key},
                files={"image": (p.name, f, "image/png")},
                timeout=timeout,
            )
        data = r.json()
        if not r.ok or not data.get("success"):
            return {"ok": False, "error": str(data)[:500], "status_code": r.status_code}
        d = data.get("data", {})
        return {
            "ok": True,
            "url": d.get("url") or d.get("display_url") or "",
            "display_url": d.get("display_url") or "",
            "delete_url": d.get("delete_url") or "",
            "size": d.get("size"),
            "data": d,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
