import json
import logging
import os
import time
from pathlib import Path

import requests

from config_store import load_settings
from core import handle_message

ROOT = Path(__file__).parent

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("telegram_poller")


def send_text(token: str, chat_id: int, text: str):
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text[:3900]},
        timeout=20,
    )


def send_photo(token: str, chat_id: int, path: str, caption: str):
    with open(path, "rb") as f:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data={"chat_id": chat_id, "caption": caption[:1000]},
            files={"photo": f},
            timeout=60,
        )


def send_photo_url(token: str, chat_id: int, url: str, caption: str):
    """Download remote image and send as Telegram photo."""
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    ext = url.rsplit(".", 1)[-1] if "." in url else "jpg"
    fname = f"/tmp/tg_img_{chat_id}_{int(time.time())}.{ext}"
    with open(fname, "wb") as f:
        f.write(r.content)
    send_photo(token, chat_id, fname, caption)
    try:
        os.remove(fname)
    except Exception:
        pass


def allowed_chat(token: str, chat_id: int, allowed: str) -> bool:
    if not allowed:
        return True
    bot_id = token.split(":", 1)[0]
    if allowed == bot_id:
        return True  # common config mistake: bot id used as chat id; don't block
    return str(chat_id) == allowed


async def process_message(token: str, chat_id: int, text: str):
    if text.startswith("/start"):
        send_text(token, chat_id, "Dạ J_agent online. Anh gửi Order ID + mô tả scene, em tạo mockup nhé.")
        return
    result = await handle_message(text, chat_id=str(chat_id))
    if result.get("type") == "product":
        meta = result.get("meta", {})
        caption = f"Dạ, em tìm thấy sản phẩm này cho anh:\n{meta.get('code','?')} — {meta.get('name','?')}"
        img = result.get("image") or meta.get("url")
        if img:
            try:
                send_photo_url(token, chat_id, img, caption)
            except Exception as e:
                send_text(token, chat_id, caption + f"\nẢnh: {img}\nKhông gửi được ảnh: {e}")
        else:
            send_text(token, chat_id, caption)
    elif result.get("type") == "mockup":
        meta = result.get("meta", {})
        caption = (
            f"Mockup ready\n"
            f"Order: {meta.get('order','?')}\n"
            f"Product: {meta.get('product','?')}\n"
            f"Size: {meta.get('size','?')} | Integrity: {meta.get('integrity','?')}\n"
            f"Time: {meta.get('time','?')} | Cost: {meta.get('cost','?')}"
        )
        img_path = result.get("image", "")
        abs_path = str((ROOT / "outputs" / os.path.basename(img_path)).resolve())
        log.info("mockup image path=%s exists=%s", abs_path, os.path.exists(abs_path))
        if os.path.exists(abs_path):
            log.info("sending mockup photo to chat_id=%s", chat_id)
            send_photo(token, chat_id, abs_path, caption)
        else:
            send_text(token, chat_id, caption + "\nImage file missing.")
    else:
        send_text(token, chat_id, result.get("content", "No response"))


def main():
    import asyncio
    offset = 0
    log.info("Telegram poller starting")
    while True:
        try:
            s = load_settings()
            token = s.get("telegram_bot_token", "").strip()
            allowed = s.get("telegram_allowed_chat_id", "").strip()
            if not token or "..." in token or "***" in token:
                log.warning("Telegram token missing/corrupted; retry in 10s")
                time.sleep(10)
                continue

            # Disable webhook, polling requires no webhook.
            requests.post(f"https://api.telegram.org/bot{token}/deleteWebhook", timeout=15)

            r = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"offset": offset, "timeout": 30, "allowed_updates": json.dumps(["message"])},
                timeout=45,
            )
            data = r.json()
            if not data.get("ok"):
                log.warning("getUpdates failed: %s", data)
                time.sleep(5)
                continue
            for upd in data.get("result", []):
                offset = max(offset, upd["update_id"] + 1)
                msg = upd.get("message") or {}
                chat_id = msg.get("chat", {}).get("id")
                text = (msg.get("text") or "").strip()
                if not chat_id or not text:
                    continue
                if not allowed_chat(token, chat_id, allowed):
                    log.warning("blocked chat_id=%s allowed=%s", chat_id, allowed)
                    continue
                log.info("msg chat_id=%s text=%s", chat_id, text[:80])
                try:
                    asyncio.run(process_message(token, chat_id, text))
                except Exception as e:
                    log.exception("process failed")
                    send_text(token, chat_id, f"Error: {e}")
        except Exception:
            log.exception("poll loop error")
            time.sleep(5)


if __name__ == "__main__":
    main()
