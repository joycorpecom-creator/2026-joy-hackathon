"""Upload generated mockup PNGs to imgbb and return public image URL."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import requests

DEFAULT_IMGBB_API_KEY = ""


def get_imgbb_api_key(explicit: str = "") -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    env_key = os.environ.get("IMGBB_API_KEY", "").strip()
    if env_key:
        return env_key
    try:
        from config_store import load_settings
        cfg_key = str(load_settings().get("imgbb_api_key", "")).strip()
        if cfg_key:
            return cfg_key
    except Exception:
        pass
    return DEFAULT_IMGBB_API_KEY


def upload_image(path: str, api_key: str = "", timeout: int = 60) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": f"file not found: {path}"}
    key = get_imgbb_api_key(api_key)
    if not key:
        return {"ok": False, "error": "missing IMGBB_API_KEY"}
    try:
        with p.open("rb") as f:
            r = requests.post(
                "https://api.imgbb.com/1/upload",
                params={"key": key},
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
