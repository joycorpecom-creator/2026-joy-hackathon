# JOY-DNSE Product Mockup Agent

Conversational AI agent for creating lifestyle mockups from BurgerShop/BurgerPrints seller products.

## Current scope

Product-only v1 runtime.

Supported:
- list seller products
- inspect seller product `Axxxxx-xx`
- create lifestyle mockups from seller product
- refine latest mockup
- optional sync webhook/Lark integration

Removed:
- order-ID flows
- BurgerPrints v2 order endpoints
- Gradio legacy app
- old order router/parser

## Run

```bash
cd /root/joy-dnse
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

Open:

```txt
http://127.0.0.1:8000
```

Telegram polling:

```bash
source .venv/bin/activate
python telegram_poller.py
```

## Required env

```env
BURGERPRINTS_API_KEY=...
BURGERPRINTS_BASE_URL=https://api.burgerprints.com/v1
GEMINI_API_KEY=...
PUBLIC_BASE_URL=http://127.0.0.1:8000
```

Optional:

```env
IMGBB_API_KEY=...
SYNC_WEBHOOK_URL=...
TELEGRAM_BOT_TOKEN=...
```

## Smoke tests

```bash
.venv/bin/python -m py_compile agent_runtime/*.py agent.py burgerprints.py main.py core.py
.venv/bin/pytest -q
curl -s http://127.0.0.1:8000/api/tools
```

## Example prompts

```txt
lấy toàn bộ product
xem product A53636-28
tạo 1 ảnh product A53636-28 phong cách cafe chạy luôn
đổi cảnh ảnh vừa rồi sang beach sunset
```
