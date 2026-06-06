import io
import json
import logging
import os
import re
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config_store import load_settings, save_settings
from core import handle_message
import burger_memory as mem

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(title="BurgerMockup Bot")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
STATIC.mkdir(exist_ok=True)

# ── API ENDPOINTS ──

@app.get("/api/settings")
async def get_settings():
    s = load_settings()
    # mask secrets
    safe = {**s}
    if safe.get("burgerprints_api_key"):
        safe["burgerprints_api_key_masked"] = safe["burgerprints_api_key"][:4] + "..." + safe["burgerprints_api_key"][-4:]
        safe["burgerprints_api_key"] = safe["burgerprints_api_key"][:4] + "..." + safe["burgerprints_api_key"][-4:]
    if safe.get("llm_api_key"):
        safe["llm_api_key_masked"] = safe["llm_api_key"][:4] + "..." + safe["llm_api_key"][-4:]
        safe["llm_api_key"] = safe["llm_api_key"][:4] + "..." + safe["llm_api_key"][-4:]
    if safe.get("telegram_bot_token"):
        safe["telegram_bot_token_masked"] = safe["telegram_bot_token"][:4] + "..." + safe["telegram_bot_token"][-4:]
        safe["telegram_bot_token"] = safe["telegram_bot_token"][:4] + "..." + safe["telegram_bot_token"][-4:]
    if safe.get("replicate_api_key"):
        safe["replicate_api_key_masked"] = safe["replicate_api_key"][:4] + "..." + safe["replicate_api_key"][-4:]
        safe["replicate_api_key"] = safe["replicate_api_key"][:4] + "..." + safe["replicate_api_key"][-4:]
    if safe.get("imgbb_api_key"):
        safe["imgbb_api_key_masked"] = safe["imgbb_api_key"][:4] + "..." + safe["imgbb_api_key"][-4:]
        safe["imgbb_api_key"] = safe["imgbb_api_key"][:4] + "..." + safe["imgbb_api_key"][-4:]
    if safe.get("image_model"):
        safe["image_model"] = safe["image_model"]
    return JSONResponse(safe)


@app.post("/api/settings")
async def update_settings(req: Request):
    body = await req.json()
    result = save_settings(body)
    # Polling mode: do not auto-set Telegram webhook; it conflicts with getUpdates.
    msg = "Settings saved. Telegram remains in polling mode."
    return JSONResponse({"ok": True, "message": msg})


@app.post("/api/test-burgerprints")
async def test_burgerprints(req: Request):
    body = await req.json()
    key = body.get("api_key", "")
    url = body.get("base_url", "https://api.burgerprints.com/v1").rstrip("/")
    import requests
    try:
        r = requests.get(f"{url}/authenticated", headers={"api-key": key}, timeout=20)
        data = r.json()
        if r.status_code == 200:
            return JSONResponse({"ok": True, "message": f"Auth OK: {data.get('data', {}).get('message', 'valid')}"})
        return JSONResponse({"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/test-llm")
async def test_llm(req: Request):
    body = await req.json()
    key = str(body.get("api_key", "") or "").strip()
    model = body.get("model", "gemini-3-flash-preview")
    if "..." in key or "***" in key:
        key = load_settings().get("llm_api_key", "")
    if not key:
        return JSONResponse({"ok": False, "error": "API key empty"})
    try:
        from google import genai
        c = genai.Client(api_key=key)
        resp = c.models.generate_content(model=model, contents="Reply with just 'OK'")
        txt = (resp.text or '').strip()[:80]
        return JSONResponse({"ok": True, "message": f"Model '{model}' responds: {txt}"})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/chat")
async def chat(req: Request):
    body = await req.json()
    msg = body.get("message", "").strip()
    try:
        chat_id = str(body.get("chat_id") or body.get("session_id") or "web")
        d = await handle_message(msg, chat_id=chat_id)
        return JSONResponse(d)
    except Exception as e:
        return JSONResponse({"type": "error", "content": str(e)})


@app.post("/api/agent/plan")
async def api_agent_plan(req: Request):
    body = await req.json()
    msg = (body.get("message") or "").strip()
    session_id = str(body.get("session_id") or body.get("chat_id") or "web")
    from agent_runtime.context_builder import build_context
    from agent_runtime.planner import Planner
    from agent_runtime.plan_schema import plan_display_text
    from agent_runtime.plan_validator import validate_plan
    ctx = build_context(session_id, msg)
    plan = Planner().plan(msg, ctx)
    ok, errors = validate_plan(plan)
    return JSONResponse({"ok": ok, "errors": errors, "plan": plan.to_dict(), "content": plan_display_text(plan)})


@app.post("/api/agent/execute")
async def api_agent_execute(req: Request):
    body = await req.json()
    session_id = str(body.get("session_id") or body.get("chat_id") or "web")
    plan = body.get("plan")
    if not plan:
        import burger_memory as mem
        plan = (mem.get_state(session_id) or {}).get("pending_plan")
    if not plan:
        return JSONResponse({"type": "text", "content": "Dạ hiện không có plan để execute."})
    from core import get_orchestrator
    from agent_runtime.orchestrator import plan_from_json
    p = plan_from_json(plan)
    p.requires_confirmation = False
    result = get_orchestrator()._executor.execute(p)
    return JSONResponse(result)


@app.get("/api/tools")
async def api_tools():
    from agent_runtime.registry import TOOL_REGISTRY
    return JSONResponse({"tools": TOOL_REGISTRY, "count": len(TOOL_REGISTRY)})


@app.post("/api/products/{product_id}/upload-mockup")
async def api_upload_mockup_to_product(product_id: str, req: Request):
    body = await req.json()
    image_url = str(body.get("image_url") or body.get("public_url") or "").strip()
    image_id = str(body.get("image_id") or "").strip()
    try:
        # If the image is a local generated output, upload binary to imgbb first.
        if image_url.startswith("/outputs/"):
            local_path = ROOT / image_url.lstrip("/")
            from imgbb_uploader import upload_image
            up = upload_image(str(local_path))
            if not up.get("ok"):
                return JSONResponse({"ok": False, "error": "imgbb upload failed", "detail": up}, status_code=500)
            image_url = up.get("url") or up.get("display_url") or ""
        if not image_url.startswith(("http://", "https://")):
            return JSONResponse({"ok": False, "error": "image_url must be public http/https URL"}, status_code=400)
        from burgerprints import BurgerPrintsClient
        result = BurgerPrintsClient().bs_append_mockup_to_product(product_id, image_url, image_id=image_id)
        return JSONResponse({"ok": True, "message": "Uploaded mockup to product", **result})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/state/{session_id}")
async def api_state(session_id: str):
    import burger_memory as mem
    return JSONResponse(mem.get_state(session_id))


# ── SERVE OUTPUTS ──

if not (ROOT / "outputs").exists():
    os.makedirs(str(ROOT / "outputs"), exist_ok=True)

@app.get("/outputs/{filename}")
async def get_output(filename: str):
    from fastapi.responses import FileResponse
    path = ROOT / "outputs" / filename
    if path.exists():
        return FileResponse(str(path), media_type="image/png")
    return JSONResponse({"error": "Not found"}, status_code=404)


# ── LIVE LOGS ──

LOG_PATH = Path(os.getenv("AGENT_LOG_PATH", "/tmp/joy_dnse_main.log"))

@app.get("/api/logs/agent")
async def api_agent_logs(lines: int = 400):
    try:
        if not LOG_PATH.exists():
            return JSONResponse({"ok": False, "path": str(LOG_PATH), "content": "log file not found"})
        data = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
        return JSONResponse({"ok": True, "path": str(LOG_PATH), "content": "\n".join(data[-max(1, min(lines, 2000)):])})
    except Exception as e:
        return JSONResponse({"ok": False, "path": str(LOG_PATH), "content": str(e)})

@app.get("/api/bulk/{job_id}")
async def api_get_bulk_job(job_id: str):
    job = mem.get_bulk_job(job_id)
    if not job:
        raise HTTPException(404, "Bulk job not found")
    return JSONResponse(job)


@app.get("/api/bulk/{job_id}/items")
async def api_get_bulk_items(job_id: str):
    return JSONResponse(mem.get_bulk_job(job_id).get("items", []))


@app.get("/logs/agent", response_class=HTMLResponse)
async def agent_logs_page():
    return HTMLResponse("""
<!doctype html><html><head><meta charset='utf-8'><title>Agent Live Logs</title>
<style>body{margin:0;background:#0b1020;color:#d6e2ff;font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}header{position:sticky;top:0;background:#111936;border-bottom:1px solid #26345f;padding:10px 14px;color:#fff}pre{white-space:pre-wrap;word-break:break-word;padding:14px;margin:0}</style></head>
<body><header>Agent live logs — auto refresh 2s — /tmp/joy_dnse_main.log</header><pre id='log'>loading...</pre>
<script>async function load(){try{let r=await fetch('/api/logs/agent?lines=700',{cache:'no-store'});let d=await r.json();log.textContent=d.content||'';scrollTo(0,document.body.scrollHeight)}catch(e){log.textContent=e.message}}load();setInterval(load,2000)</script></body></html>
""")

# ── SERVE HTML DASHBOARD ──

@app.get("/", response_class=HTMLResponse)
async def index():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.on_event("startup")
async def startup():
    log.info(f"Dashboard: http://0.0.0.0:{os.getenv('PORT','8000')}")
    # Polling mode: skip webhook auto-set (setWebhook even when failing
    # interrupts the polling getUpdates connection).


# ── TELEGRAM ──

def _tg_token() -> str:
    s = load_settings()
    return s.get("telegram_bot_token", "").strip()


def _pub_url() -> str:
    s = load_settings()
    return s.get("public_base_url", "").strip().rstrip("/")


@app.post("/api/test-telegram")
async def test_telegram():
    token = _tg_token()
    if not token:
        return JSONResponse({"ok": False, "error": "Token empty"})
    import requests
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15)
        d = r.json()
        if d.get("ok"):
            u = d["result"]
            return JSONResponse({"ok": True, "message": f"@{u['username']} (ID: {u['id']})"})
        return JSONResponse({"ok": False, "error": d.get("description", "Unknown")})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/telegram-webhook-set")
async def telegram_webhook_set():
    token = _tg_token()
    pub = _pub_url()
    if not token:
        return JSONResponse({"ok": False, "error": "Token empty"})
    if not pub or pub in ("http://127.0.0.1:8000", "http://localhost:8000"):
        return JSONResponse({"ok": False, "error": "Set Server > Public Base URL first"})
    import requests
    webhook_url = f"{pub}/webhook/telegram"
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url, "allowed_updates": ["message"]},
            timeout=15,
        )
        d = r.json()
        if d.get("ok"):
            return JSONResponse({"ok": True, "message": f"Webhook set → {webhook_url}"})
        return JSONResponse({"ok": False, "error": d.get("description", "Unknown")})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/telegram-webhook-remove")
async def telegram_webhook_remove():
    token = _tg_token()
    if not token:
        return JSONResponse({"ok": False, "error": "Token empty"})
    import requests
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/deleteWebhook", timeout=15)
        d = r.json()
        return JSONResponse({"ok": d.get("ok", False), "message": d.get("description", "Removed")})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/test-sync-webhook")
async def test_sync_webhook(req: Request):
    body = await req.json()
    webhook_url = body.get("webhook_url", "").strip()
    secret = body.get("secret", "").strip()
    from sync_webhook import post_sync_test
    if not webhook_url:
        return JSONResponse({"ok": False, "error": "Webhook URL empty"})
    res = post_sync_test(webhook_url, secret, timeout=10)
    ok = res.get("status") == "sent"
    detail = res.get("response") or {"status": res.get("status"), "error": res.get("error", "")}
    return JSONResponse({"ok": ok, "message": f"Status: {res['status']}", "detail": detail})



@app.post("/webhook/telegram")
async def telegram_webhook(req: Request):
    token = _tg_token()
    if not token:
        raise HTTPException(404)
    try:
        body = await req.json()
    except Exception:
        raise HTTPException(400)

    msg = body.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return {"ok": True}

    # /start always allowed
    if text.startswith("/start"):
        import requests as rq
        rq.post(f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": "J_agent online! ✨ Give me an Order ID + scene to make a mockup."}, timeout=15)
        return {"ok": True}

    # allowed chat filter — skip if it matches bot's own ID
    s = load_settings()
    allowed = s.get("telegram_allowed_chat_id", "").strip()
    bot_self_id = token.split(":")[0] if ":" in token else ""
    if allowed and allowed != bot_self_id and str(chat_id) != allowed:
        log.warning(f"Blocked msg from {chat_id} (allowed: {allowed})")
        return {"ok": True}

    try:
        result = await handle_message(text, chat_id=str(chat_id))
    except Exception as e:
        result = {"type": "text", "content": f"Error: {e}"}

    import requests as rq
    api = f"https://api.telegram.org/bot{token}"

    if result["type"] == "product":
        meta = result.get("meta", {})
        caption = f"Dạ, em tìm thấy sản phẩm này cho anh:\n{meta.get('code','?')} — {meta.get('name','?')}"
        img = result.get("image") or meta.get("url", "")
        if img:
            try:
                # Download and send as photo
                img_r = rq.get(img, timeout=20)
                img_r.raise_for_status()
                ext = img.rsplit(".", 1)[-1] if "." in img else "jpg"
                fname = f"/tmp/tg_wb_{chat_id}_{int(time.time())}.{ext}"
                with open(fname, "wb") as f:
                    f.write(img_r.content)
                with open(fname, "rb") as f:
                    rq.post(f"{api}/sendPhoto", data={"chat_id": chat_id, "caption": caption}, files={"photo": f})
                try: os.remove(fname)
                except: pass
            except Exception as e:
                rq.post(f"{api}/sendMessage", json={"chat_id": chat_id, "text": caption + f"\nẢnh: {img}\nKhông gửi được ảnh: {e}"}, timeout=15)
        else:
            rq.post(f"{api}/sendMessage", json={"chat_id": chat_id, "text": caption}, timeout=15)
    elif result["type"] == "mockup":
        meta = result.get("meta", {})
        caption = (
            f"Mockup ready\n"
            f"Order: {meta.get('order','?')} | Product: {meta.get('product','?')}\n"
            f"Size: {meta.get('size','?')} | Integrity: {meta.get('integrity','?')}\n"
            f"Time: {meta.get('time','?')} | Cost: {meta.get('cost','?')}"
        )
        img_path = result.get("image", "")
        abs_path = str((ROOT / "outputs" / os.path.basename(img_path)).resolve())
        if os.path.exists(abs_path):
            with open(abs_path, "rb") as f:
                rq.post(f"{api}/sendPhoto", data={"chat_id": chat_id, "caption": caption}, files={"photo": f})
        else:
            rq.post(f"{api}/sendMessage", json={"chat_id": chat_id, "text": f"Image not found", "parse_mode": "Markdown"}, timeout=15)
    else:
        content = result.get("content", "No content")
        # If agent returned markdown images (order list), send them as real Telegram photos.
        image_matches = re.findall(r"!\[([^\]]*)\]\((https?://[^\s)]+)\)", content or "")
        text_without_images = re.sub(r"!\[[^\]]*\]\(https?://[^\s)]+\)", "", content or "").strip()
        if text_without_images:
            rq.post(f"{api}/sendMessage", json={"chat_id": chat_id, "text": text_without_images, "parse_mode": "Markdown"}, timeout=15)
        if image_matches:
            for alt, img in image_matches[:10]:
                try:
                    img_r = rq.get(img, timeout=25)
                    img_r.raise_for_status()
                    ext = img.split("?", 1)[0].rsplit(".", 1)[-1] if "." in img.split("?", 1)[0] else "jpg"
                    fname = f"/tmp/tg_order_{chat_id}_{int(time.time()*1000)}.{ext}"
                    with open(fname, "wb") as f:
                        f.write(img_r.content)
                    with open(fname, "rb") as f:
                        rq.post(f"{api}/sendPhoto", data={"chat_id": chat_id, "caption": alt[:200] if alt else "Order image"}, files={"photo": f}, timeout=30)
                    try: os.remove(fname)
                    except: pass
                except Exception as e:
                    rq.post(f"{api}/sendMessage", json={"chat_id": chat_id, "text": f"Không gửi được ảnh {alt}: {img}\n{e}"}, timeout=15)
        if not text_without_images and not image_matches:
            rq.post(f"{api}/sendMessage", json={"chat_id": chat_id, "text": content, "parse_mode": "Markdown"}, timeout=15)

    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
