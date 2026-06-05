"""
Lark Media Sync — upload generated mockup to Lark Base as attachment.

Uses Python `requests` (not lark-cli) to call Lark OpenAPI directly.
Flow: Drive medias upload_all → create Base record → append_attachments.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

# ── Default credentials (pre-configured for hackathon judge demo) ──
# Override with env vars or lark_sync_config overrides dict
_DEFAULT = {
    "app_id": "",
    "app_secret": "",
    "base_token": "",
    "table_id": "",
    "lark_base_url": "https://open.larksuite.com",
    "attachment_field_id": "fldfkDRB21",
    "dry_run": False,
}

LARK_BASE_URL = "https://open.larksuite.com"


def _load_config(overrides: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Merge defaults, env vars, and explicit overrides."""
    cfg = dict(_DEFAULT)
    # env overrides
    for key, env_key in [
        ("app_id", "LARK_APP_ID"),
        ("app_secret", "LARK_APP_SECRET"),
        ("base_token", "LARK_BASE_TOKEN"),
        ("table_id", "LARK_TABLE_ID"),
        ("attachment_field_id", "LARK_ATTACHMENT_FIELD_ID"),
    ]:
        if os.environ.get(env_key):
            cfg[key] = os.environ[env_key]

    # try reading /root/.hermes/.env for FEISHU vars
    hermes_env = Path("/root/.hermes/.env")
    if hermes_env.exists():
        for line in hermes_env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                if k == "FEISHU_APP_ID" and not os.environ.get("LARK_APP_ID"):
                    cfg["app_id"] = v
                elif k == "FEISHU_APP_SECRET" and not os.environ.get("LARK_APP_SECRET"):
                    cfg["app_secret"] = v
                elif k == "FEISHU_DOMAIN" and v == "cn":
                    cfg["lark_base_url"] = "https://open.feishu.cn"

    # explicit overrides
    if overrides:
        cfg.update(overrides)
    return cfg


def _get_tenant_token(app_id: str, app_secret: str, base_url: str) -> str:
    url = f"{base_url}/open-apis/auth/v3/tenant_access_token/internal"
    r = requests.post(url, json={"app_id": app_id, "app_secret": app_secret}, timeout=20)
    data = r.json()
    if not r.ok or data.get("code") != 0:
        raise RuntimeError(f"tenant token failed: {data}")
    return data["tenant_access_token"]


def _upload_to_base_media(
    file_path: str,
    base_token: str,
    token: str,
    base_url: str,
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload a local file to Base attachment media (drive/v1/medias/upload_all)."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    name = file_name or path.name
    size = path.stat().st_size
    url = f"{base_url}/open-apis/drive/v1/medias/upload_all"
    with open(path, "rb") as f:
        files = {
            "file": (name, f, "image/png"),
        }
        data = {
            "file_name": name,
            "parent_node": base_token,
            "parent_type": "bitable_file",
            "size": str(size),
        }
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            data=data,
            files=files,
            timeout=60,
        )
    resp = r.json()
    if not r.ok or resp.get("code") != 0:
        raise RuntimeError(f"media upload failed: {resp}")
    return resp["data"]


def _append_attachments(
    record_id: str,
    field_id: str,
    file_token: str,
    token: str,
    base_token: str,
    table_id: str,
    base_url: str,
    image_width: int = 0,
    image_height: int = 0,
) -> Dict[str, Any]:
    """Append uploaded file token(s) to the target attachment cell."""
    url = f"{base_url}/open-apis/base/v3/bases/{base_token}/tables/{table_id}/append_attachments"
    attachment_entry = {
        "file_token": file_token,
    }
    if image_width and image_height:
        attachment_entry["image_width"] = image_width
        attachment_entry["image_height"] = image_height
    body = {
        "attachments": {
            record_id: {
                field_id: [attachment_entry],
            }
        }
    }
    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=30,
    )
    resp = r.json()
    if not r.ok or resp.get("code") != 0:
        raise RuntimeError(f"append attachment failed: {resp}")
    return resp


def _create_record(
    fields: Dict[str, Any],
    token: str,
    base_token: str,
    table_id: str,
    base_url: str,
) -> Dict[str, Any]:
    """Create a Base record with the given fields (no attachment)."""
    url = f"{base_url}/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records"
    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"fields": fields},
        timeout=30,
    )
    resp = r.json()
    if not r.ok or resp.get("code") != 0:
        raise RuntimeError(f"record create failed: {resp}")
    return resp["data"]["record"]


def sync_mockup(
    *,
    local_path: str,
    mockup_id: str,
    status: str = "created",
    product_id: str = "",
    product_name: str = "",
    color: str = "",
    scene: str = "",
    raw_user_input: str = "",
    provider: str = "",
    model: str = "",
    size: str = "",
    seconds: float = 0,
    cost_usd: float = 0,
    integrity_score: float = 0,
    image_url: str = "",
    config_overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Full sync to Lark Base:
    1. Create Base record (without attachment)
    2. Upload local image to Base media
    3. Append attachment to the record

    Returns {record_id, file_token, ok, error?, time_seconds}
    """
    t0 = time.time()
    cfg = _load_config(config_overrides)
    try:
        token = _get_tenant_token(cfg["app_id"], cfg["app_secret"], cfg["lark_base_url"])

        if cfg.get("dry_run"):
            return {
                "ok": True,
                "dry_run": True,
                "file_token": "dry-run-token",
                "record_id": "dry-run-record",
                "time_seconds": round(time.time() - t0, 2),
            }

        # Step 1: Create Base record (without attachment field)
        fields = {
            "Mockup_ID": mockup_id,
            "Status": status,
            "Product_ID": product_id,
            "Product_Name": product_name,
            "Color": color,
            "Scene": scene,
            "Raw_User_Input": raw_user_input,
            "Provider": provider,
            "Model": model,
            "Size": size,
            "Generation_Time": round(seconds, 3),
            "Cost_USD": round(cost_usd, 6),
            "Integrity_Score": round(integrity_score, 4),
            "Created_At": int(time.time() * 1000),
        }
        # Avoid writing Image_URL URL-style fields; Lark may reject local/public-http URLs.
        if image_url:
            fields["Raw_User_Input"] = (fields.get("Raw_User_Input") or "") + f"\nImage URL: {image_url}"
        record = _create_record(fields, token, cfg["base_token"], cfg["table_id"], cfg["lark_base_url"])
        record_id = record["record_id"]

        # Step 2: Upload local file to Base media
        file_name = Path(local_path).name
        media = _upload_to_base_media(
            local_path, cfg["base_token"], token, cfg["lark_base_url"], file_name=file_name
        )
        file_token = media["file_token"]

        # Step 3: Append attachment to the record
        _append_attachments(
            record_id=record_id,
            field_id=cfg["attachment_field_id"],
            file_token=file_token,
            token=token,
            base_token=cfg["base_token"],
            table_id=cfg["table_id"],
            base_url=cfg["lark_base_url"],
            image_width=media.get("image_width", 0),
            image_height=media.get("image_height", 0),
        )

        lap = round(time.time() - t0, 2)
        return {
            "ok": True,
            "record_id": record_id,
            "file_token": file_token,
            "mode": "media_sync",
            "time_seconds": lap,
        }

    except Exception as e:
        lap = round(time.time() - t0, 2)
        return {
            "ok": False,
            "mode": "media_sync",
            "error": str(e),
            "time_seconds": lap,
        }
