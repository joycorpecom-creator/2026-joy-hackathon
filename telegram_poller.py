import json
import logging
import os
import re
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




async def process_message(token: str, chat_id: int, text: str, msg: dict = None):
    # File upload is intentionally disabled; stable flows are order/product only.
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
        warnings = meta.get("warnings") or []
        warn_text = ""
        if warnings:
            warn_text = ""
        caption = (
            f"Mockup ready\n"
            f"Order: {meta.get('order','?')}\n"
            f"Product: {meta.get('product','?')}\n"
            f"Size: {meta.get('size','?')} | Integrity: {meta.get('integrity','?')}\n"
            f"Time: {meta.get('time','?')} | Cost: {meta.get('cost','?')}"
            f"{warn_text}"
        )
        images = result.get("images") or []
        if images:
            send_text(token, chat_id, result.get("content", caption))
            for idx, im in enumerate(images[:10], start=1):
                img_path = im.get("url", "")
                abs_path = str((ROOT / "outputs" / os.path.basename(img_path)).resolve())
                cap = f"{idx}. {im.get('scene','Mockup')}"
                if os.path.exists(abs_path):
                    send_photo(token, chat_id, abs_path, cap)
                else:
                    send_text(token, chat_id, cap + "\nImage file missing.")
        else:
            img_path = result.get("image", "")
            abs_path = str((ROOT / "outputs" / os.path.basename(img_path)).resolve())
            log.info("mockup image path=%s exists=%s", abs_path, os.path.exists(abs_path))
            if os.path.exists(abs_path):
                log.info("sending mockup photo to chat_id=%s", chat_id)
                send_photo(token, chat_id, abs_path, caption)
            else:
                send_text(token, chat_id, caption + "\nImage file missing.")
    else:
        content = result.get("content", "No response")
        image_matches = re.findall(r"!\[([^\]]*)\]\((https?://[^\s)]+)\)", content or "")
        text_clean = re.sub(r"!\[[^\]]*\]\(https?://[^\s)]+\)", "", content or "").strip()
        if text_clean:
            send_text(token, chat_id, text_clean)
        if image_matches:
            for alt, url in image_matches[:10]:
                try:
                    send_photo_url(token, chat_id, url, alt[:200] if alt else "Order")
                except Exception as e:
                    send_text(token, chat_id, f"Không gửi được ảnh: {url}\n{e}")
        if not text_clean and not image_matches:
            send_text(token, chat_id, content)


def main():
    import asyncio
    import fcntl
    lock_path = ROOT / "telegram_poller.lock"
    lock_file = open(lock_path, "w")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.error("Another Telegram poller is already running; exiting to avoid duplicate replies.")
        return
    lock_file.write(str(os.getpid()))
    lock_file.flush()
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
                text = (msg.get("text") or msg.get("caption") or "").strip()
                has_file = bool(msg.get("photo") or msg.get("document"))
                if not chat_id or (not text and not has_file):
                    continue
                if not allowed_chat(token, chat_id, allowed):
                    log.warning("blocked chat_id=%s allowed=%s", chat_id, allowed)
                    continue
                log.info("msg chat_id=%s text=%s", chat_id, text[:80])
                try:
                    asyncio.run(process_message(token, chat_id, text, msg))
                except Exception as e:
                    log.exception("process failed")
                    send_text(token, chat_id, f"Error: {e}")
        except Exception:
            log.exception("poll loop error")
            time.sleep(5)


if __name__ == "__main__":
    main()
