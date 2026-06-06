import json
import os
from pathlib import Path
from typing import Dict

from dotenv import dotenv_values

ROOT = Path(__file__).parent
ENV_PATH = ROOT / ".env"
SETTINGS_PATH = ROOT / "settings.json"

DEFAULTS = {
    "burgerprints_base_url": "https://api.burgerprints.com/v1",
    "burgerprints_api_key": "",
    "telegram_bot_token": "",
    "telegram_allowed_chat_id": "",
    "public_base_url": "http://127.0.0.1:8000",
    "llm_provider": "google",
    "llm_model": "gemini-3-flash-preview",
    "llm_api_key": "",
    "image_model": "gemini-3.1-flash-image",
    "replicate_api_key": "",
    "imgbb_api_key": "",
    "sync_enabled": "false",
    "sync_provider": "n8n",
    "sync_webhook_url": "",
    "sync_secret": "",
    "sync_send_image_url": "true",
    "sync_timeout_seconds": "10",
    "lark_app_id": "",
    "lark_app_secret": "",
    "lark_base_token": "",
    "lark_table_id": "",
}


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "..." + value[-4:]


def _env_val(env, key, fallback):
    """Get env value, reject masked placeholders."""
    v = (env.get(key) or "").strip()
    if not v or "..." in v or "***" in v:
        return fallback
    return v


def load_settings() -> Dict[str, str]:
    data = DEFAULTS.copy()
    if SETTINGS_PATH.exists():
        try:
            data.update(json.loads(SETTINGS_PATH.read_text()))
        except Exception:
            pass
    if ENV_PATH.exists():
        env = dotenv_values(ENV_PATH)
        data.update({
            "burgerprints_api_key": _env_val(env, "BURGERPRINTS_API_KEY", data["burgerprints_api_key"]),
            "burgerprints_base_url": env.get("BURGERPRINTS_BASE_URL") or data["burgerprints_base_url"],
            "telegram_bot_token": _env_val(env, "TELEGRAM_BOT_TOKEN", data["telegram_bot_token"]),
            "telegram_allowed_chat_id": env.get("TELEGRAM_ALLOWED_CHAT_ID") or data["telegram_allowed_chat_id"],
            "public_base_url": env.get("PUBLIC_BASE_URL") or data["public_base_url"],
            "llm_provider": env.get("LLM_PROVIDER") or data["llm_provider"],
            "llm_model": env.get("LLM_MODEL") or data["llm_model"],
            "llm_api_key": _env_val(env, "GEMINI_API_KEY", _env_val(env, "GOOGLE_API_KEY", data["llm_api_key"])),
            "image_model": env.get("IMAGE_MODEL") or env.get("LLM_IMAGE_MODEL") or data["image_model"],
            "replicate_api_key": _env_val(env, "REPLICATE_API_KEY", _env_val(env, "REPLICATE_API_TOKEN", data["replicate_api_key"])),
            "imgbb_api_key": _env_val(env, "IMGBB_API_KEY", data["imgbb_api_key"]),
        })
        for k in ("SYNC_ENABLED", "SYNC_PROVIDER", "SYNC_WEBHOOK_URL", "SYNC_SECRET", "SYNC_SEND_IMAGE_URL", "SYNC_TIMEOUT_SECONDS"):
            data[k.lower()] = env.get(k) or data.get(k.lower(), "")
        for k in ("LARK_APP_ID", "LARK_APP_SECRET", "LARK_BASE_TOKEN", "LARK_TABLE_ID"):
            data[k.lower()] = env.get(k) or data.get(k.lower(), "")
    return data


def save_settings(settings: Dict[str, str]) -> Dict[str, str]:
    data = load_settings()
    secret_keys = {"burgerprints_api_key", "telegram_bot_token", "llm_api_key", "replicate_api_key", "imgbb_api_key", "sync_secret"}
    for k in DEFAULTS:
        if k in settings:
            v = (settings[k] or "").strip()
            if k in secret_keys and ("..." in v or "***" in v):
                continue  # masked value, keep existing
            data[k] = v
    SETTINGS_PATH.write_text(json.dumps(data, indent=2))
    ENV_PATH.write_text(
        "\n".join([
            f"BURGERPRINTS_API_KEY={data['burgerprints_api_key']}",
            f"BURGERPRINTS_BASE_URL={data['burgerprints_base_url']}",
            f"TELEGRAM_BOT_TOKEN={data['telegram_bot_token']}",
            f"TELEGRAM_ALLOWED_CHAT_ID={data['telegram_allowed_chat_id']}",
            f"PUBLIC_BASE_URL={data['public_base_url']}",
            f"LLM_PROVIDER={data['llm_provider']}",
            f"LLM_MODEL={data['llm_model']}",
            "GEMINI_API_KEY=" + data["llm_api_key"],
            "IMAGE_MODEL=" + data.get("image_model", "gemini-3.1-flash-image"),
            "REPLICATE_API_KEY=" + data["replicate_api_key"],
            "IMGBB_API_KEY=" + data.get("imgbb_api_key", ""),
            f"SYNC_ENABLED={data['sync_enabled']}",
            f"SYNC_PROVIDER={data['sync_provider']}",
            f"SYNC_WEBHOOK_URL={data['sync_webhook_url']}",
            f"SYNC_SECRET={data['sync_secret']}",
            f"SYNC_SEND_IMAGE_URL={data['sync_send_image_url']}",
            f"SYNC_TIMEOUT_SECONDS={data['sync_timeout_seconds']}",
            "",
        ])
    )
    os.environ["BURGERPRINTS_API_KEY"] = data["burgerprints_api_key"]
    os.environ["BURGERPRINTS_BASE_URL"] = data["burgerprints_base_url"]
    os.environ["TELEGRAM_BOT_TOKEN"] = data["telegram_bot_token"]
    os.environ["TELEGRAM_ALLOWED_CHAT_ID"] = data["telegram_allowed_chat_id"]
    os.environ["PUBLIC_BASE_URL"] = data["public_base_url"]
    os.environ["REPLICATE_API_KEY"] = data["replicate_api_key"]
    os.environ["IMGBB_API_KEY"] = data.get("imgbb_api_key", "")
    os.environ["SYNC_ENABLED"] = data["sync_enabled"]
    os.environ["SYNC_WEBHOOK_URL"] = data["sync_webhook_url"]
    os.environ["SYNC_SECRET"] = data["sync_secret"]
    return data
