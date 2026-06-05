"""Webhook sync for BurgerMockup outputs.

Keeps Lark/n8n integration optional: if sync is disabled or webhook URL is empty,
mockup generation still succeeds.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import requests


def _truthy(v: Any) -> bool:
    return str(v).lower() in {"1", "true", "yes", "on", "enabled"}


def build_mockup_payload(
    *,
    result: Dict[str, Any],
    product_id: str,
    product_name: str,
    color: str,
    scene: str,
    raw_user_input: str,
    public_base_url: str,
) -> Dict[str, Any]:
    filename = result.get("filename") or str(result.get("path", "")).rsplit("/", 1)[-1]
    public = (public_base_url or "").rstrip("/")
    image_url = f"{public}/outputs/{filename}" if public and filename else ""
    width = int(result.get("width") or 0)
    height = int(result.get("height") or 0)
    return {
        "event": "mockup.created",
        "version": "1.0",
        "mockup_id": filename.rsplit(".", 1)[0] if filename else f"mockup-{int(datetime.now().timestamp())}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "burgermockup-agent",
        "product": {
            "id": product_id,
            "name": product_name,
            "color": color,
        },
        "prompt": {
            "scene": scene,
            "raw_user_input": raw_user_input or scene,
        },
        "generation": {
            "provider": result.get("provider", ""),
            "model": "gemini-3.1-flash-image",
            "width": width,
            "height": height,
            "size": f"{width}x{height}" if width and height else "",
            "seconds": result.get("seconds", 0),
            "cost_usd": result.get("cost_usd", 0),
            "integrity_score": result.get("integrity_score", 0),
        },
        "assets": {
            "image_url": image_url,
            "filename": filename,
            "local_path": result.get("path", ""),
        },
    }


def post_mockup_created(payload: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
    if not _truthy(settings.get("sync_enabled", False)):
        return {"status": "disabled"}
    url = (settings.get("sync_webhook_url") or "").strip()
    if not url:
        return {"status": "skipped", "error": "missing webhook URL"}
    timeout = int(settings.get("sync_timeout_seconds") or 10)
    secret = (settings.get("sync_secret") or "").strip()
    headers = {
        "Content-Type": "application/json",
        "X-BurgerMockup-Event": payload.get("event", "mockup.created"),
    }
    if secret and "..." not in secret and "***" not in secret:
        headers["X-BurgerMockup-Secret"] = secret
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=timeout)
        ok = 200 <= r.status_code < 300
        data = None
        try:
            data = r.json()
        except Exception:
            data = {"text": r.text[:500]}
        return {
            "status": "sent" if ok else "failed",
            "http_status": r.status_code,
            "response": data,
            "record_id": (data or {}).get("record_id") or (data or {}).get("id", ""),
            "error": "" if ok else str(data)[:300],
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def post_sync_test(webhook_url: str, secret: str = "", timeout: int = 10) -> Dict[str, Any]:
    payload = {
        "event": "burgermockup.sync_test",
        "version": "1.0",
        "source": "burgermockup-web",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    settings = {
        "sync_enabled": True,
        "sync_webhook_url": webhook_url,
        "sync_secret": secret,
        "sync_timeout_seconds": timeout,
    }
    return post_mockup_created(payload, settings)
