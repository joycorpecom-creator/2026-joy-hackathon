import os
from pathlib import Path

import gradio as gr
import requests
from dotenv import load_dotenv

from burgerprints import BurgerPrintsClient
from config_store import load_settings, mask_secret, save_settings
from mockup_engine import generate_mockup

load_dotenv()
client = BurgerPrintsClient()
ROOT = Path(__file__).parent
settings = load_settings()
SYSTEM_HINT = "Paste an order ID + scene prompt. Demo order: DEMO-1001."


def chat(message, history, state):
    state = state or {}
    try:
        order_id = client.find_order_id(message)
        if "order" not in message.lower() and not message.upper().startswith("DEMO") and state.get("last_order_id"):
            order_id = state["last_order_id"]
        asset = client.extract_first_asset(order_id)
        result = generate_mockup(asset, message)
        state["last_order_id"] = order_id
        state["last_asset"] = asset.__dict__
        state.setdefault("outputs", []).append(result)
        reply = (
            f"✅ Mockup ready\n\n"
            f"Order: {order_id}\n"
            f"Product: {asset.product_name}\n"
            f"Color: {asset.color_name}\n"
            f"Provider: {result['provider']}\n"
            f"Size: {result['width']}x{result['height']}\n"
            f"Design integrity: {result['integrity_score']}\n"
            f"Time: {result['seconds']}s\n"
            f"Cost: ${result['cost_usd']}\n\n"
            f"Image file: {result['path']}"
        )
        return reply, result["path"], state
    except Exception as e:
        return f"❌ Error: {e}", None, state


# ── Settings tab logic ─────────────────────────────────

def test_api_connection(bp_key, bp_url):
    """Test BurgerPrints API with the given key+url."""
    key = bp_key.strip()
    url = bp_url.rstrip("/")
    if not key:
        return "❌ API key trống. Nhập key trước."
    try:
        r = requests.get(f"{url}/authenticated", headers={"api-key": key}, timeout=20)
        if r.status_code == 200:
            return f"✅ Auth OK: {r.json().get('data', {}).get('message', 'valid')}"
        return f"⚠️ HTTP {r.status_code}: {r.text[:200]}"
    except requests.exceptions.ConnectionError:
        return "❌ Không kết nối được. Sai base URL?"
    except Exception as e:
        return f"❌ Lỗi: {e}"


def save_ui_settings(bp_key, bp_url, tg_token, tg_chat, pub_url):
    s = {
        "burgerprints_api_key": bp_key.strip(),
        "burgerprints_base_url": bp_url.strip(),
        "telegram_bot_token": tg_token.strip(),
        "telegram_allowed_chat_id": tg_chat.strip(),
        "public_base_url": pub_url.strip(),
    }
    save_settings(s)
    return f"✅ Saved to .env + settings.json\n\nKey masked: {mask_secret(s['burgerprints_api_key'])}"


def load_ui_settings():
    s = load_settings()
    return (
        mask_secret(s["burgerprints_api_key"]) if s["burgerprints_api_key"] else "",
        s["burgerprints_base_url"],
        mask_secret(s["telegram_bot_token"]) if s["telegram_bot_token"] else "",
        s["telegram_allowed_chat_id"],
        s["public_base_url"],
    )


# ── Telegram bot skeleton ─────────────────────────────

def check_telegram_bot(tg_token):
    token = tg_token.strip()
    if not token:
        return "❌ Bot token trống."
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15)
        d = r.json()
        if d.get("ok"):
            bot_user = d["result"]
            return f"✅ Bot @{bot_user['username']} OK. ID: {bot_user['id']}"
        return f"❌ API error: {d.get('description', 'unknown')}"
    except Exception as e:
        return f"❌ Lỗi: {e}"


def set_telegram_webhook(tg_token, pub_url):
    token = tg_token.strip()
    webhook_url = pub_url.strip().rstrip("/") + "/webhook/telegram"
    if not token:
        return "❌ Bot token trống."
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url},
            timeout=15,
        )
        d = r.json()
        if d.get("ok"):
            return f"✅ Webhook set → {webhook_url}"
        return f"❌ Webhook fail: {d.get('description', 'unknown')}"
    except Exception as e:
        return f"❌ Lỗi: {e}"


def remove_telegram_webhook(tg_token):
    token = tg_token.strip()
    if not token:
        return "❌ Bot token trống."
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/deleteWebhook", timeout=15
        )
        return "✅ Webhook xóa." if r.json().get("ok") else "❌ Xóa fail."
    except Exception as e:
        return f"❌ Lỗi: {e}"


# ── Build UI ──────────────────────────────────────────

with gr.Blocks(title="BurgerMockup Bot") as demo:
    gr.Markdown("# 🍔 BurgerMockup Bot")
    with gr.Tabs():
        # ── Chat tab ──
        with gr.TabItem("💬 Chat"):
            state = gr.State({})
            chatbot = gr.Chatbot(height=360)
            msg = gr.Textbox(
                label="Prompt",
                placeholder="Get order DEMO-1001 and create a cozy cafe girl lifestyle mockup, warm morning light",
            )
            img = gr.Image(label="Latest mockup", type="filepath")
            clear = gr.Button("🗑 Clear")

            def respond(message, history, state):
                reply, image, state = chat(message, history, state)
                history = history + [(message, reply)]
                return "", history, image, state

            msg.submit(respond, [msg, chatbot, state], [msg, chatbot, img, state])
            clear.click(lambda: ([], None, {}), None, [chatbot, img, state])

        # ── Settings tab ──
        with gr.TabItem("⚙️ Settings"):
            gr.Markdown("### BurgerPrints API")
            bp_key = gr.Textbox(
                label="API Key",
                value="",
                placeholder="f4226953-...",
                type="password",
            )
            bp_url = gr.Textbox(
                label="Base URL",
                value=settings["burgerprints_base_url"],
            )
            test_btn = gr.Button("🔍 Test API Connection")
            test_out = gr.Textbox(label="Result", interactive=False)

            gr.Markdown("---")
            gr.Markdown("### Telegram Bot")
            tg_token = gr.Textbox(
                label="Bot Token",
                value="",
                placeholder="123456:ABC-def...",
                type="password",
            )
            tg_chat = gr.Textbox(
                label="Allowed Chat ID (optional)",
                value=settings["telegram_allowed_chat_id"],
                placeholder="-1001234567890",
            )
            tg_check = gr.Button("🤖 Check Bot")
            tg_check_out = gr.Textbox(label="Bot status", interactive=False)
            with gr.Row():
                tg_set_webhook = gr.Button("🌐 Set Webhook")
                tg_rm_webhook = gr.Button("❌ Remove Webhook")
            tg_webhook_out = gr.Textbox(label="Webhook result", interactive=False)

            gr.Markdown("---")
            gr.Markdown("### Server")
            pub_url = gr.Textbox(
                label="Public Base URL (for webhook)",
                value=settings["public_base_url"],
                placeholder="http://36.50.26.198:8765",
            )
            save_btn = gr.Button("💾 Save All")
            save_out = gr.Textbox(label="Save result", interactive=False)

            # wire events
            test_btn.click(
                fn=test_api_connection,
                inputs=[bp_key, bp_url],
                outputs=[test_out],
            )
            tg_check.click(
                fn=check_telegram_bot,
                inputs=[tg_token],
                outputs=[tg_check_out],
            )
            tg_set_webhook.click(
                fn=set_telegram_webhook,
                inputs=[tg_token, pub_url],
                outputs=[tg_webhook_out],
            )
            tg_rm_webhook.click(
                fn=remove_telegram_webhook,
                inputs=[tg_token],
                outputs=[tg_webhook_out],
            )
            save_btn.click(
                fn=save_ui_settings,
                inputs=[bp_key, bp_url, tg_token, tg_chat, pub_url],
                outputs=[save_out],
            )
            demo.load(
                fn=load_ui_settings,
                inputs=[],
                outputs=[bp_key, bp_url, tg_token, tg_chat, pub_url],
            )


if __name__ == "__main__":
    try:
        demo.launch(
            server_name="0.0.0.0",
            server_port=int(os.getenv("PORT", "7860")),
        )
    except KeyboardInterrupt:
        pass
