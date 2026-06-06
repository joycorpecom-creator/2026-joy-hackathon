# JOY-DNSE Mockup Studio

Web app for creating product lifestyle mockups from BurgerShop/BurgerPrints seller products.

## What it does

- Reads seller products from BurgerShop/BurgerPrints v1 API.
- Shows product detail, preview images, mockup URLs, cost when available.
- Creates lifestyle mockups from product IDs such as `A53636-28`.
- Supports Vietnamese natural-language commands, product list memory, “sản phẩm thứ N”, single/bulk mockup flow.
- Runs locally with FastAPI backend + plain HTML frontend.

## Fastest setup

```bash
git clone <repo-url> joy-dnse
cd joy-dnse
./setup.sh
```

First run creates `.env`. Open it and fill required keys:

```env
BURGERPRINTS_API_KEY=your_burgerprints_key
GEMINI_API_KEY=your_gemini_key
```

Then start:

```bash
./run.sh
```

Open:

```txt
http://127.0.0.1:8000
```

## Manual setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env
python main.py
```

## Required config

```env
BURGERPRINTS_API_KEY=
BURGERPRINTS_BASE_URL=https://api.burgerprints.com/v1
GEMINI_API_KEY=
TEXT_MODEL=gemini-3-flash-preview
IMAGE_MODEL=gemini-3.1-flash-image
PUBLIC_BASE_URL=http://127.0.0.1:8000
```

Optional:

```env
IMGBB_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_ID=
SYNC_WEBHOOK_URL=
```

## Useful commands

```bash
# Setup dependencies
./setup.sh

# Run web app
./run.sh

# Run checks
./scripts/test.sh

# Start Telegram polling, optional
source .venv/bin/activate
python telegram_poller.py
```

## Example messages

```txt
lấy toàn bộ sản phẩm
xem chi tiết sản phẩm A53636-28
tạo 1 ảnh product A53636-28 phong cách cafe chạy luôn
tạo mockup cho sản phẩm thứ 2 phong cách beach sunset
đổi cảnh ảnh vừa rồi sang office lifestyle
```

## API endpoints

- `GET /` — web UI
- `POST /api/chat` — chat command
- `GET /api/tools` — available actions
- `GET /api/settings` — current settings
- `POST /api/settings` — update settings
- `GET /api/bulk/{job_id}` — bulk job status
- `GET /api/bulk/{job_id}/items` — bulk job items

## Project structure

Read `PROJECT_STRUCTURE.md` for full codebase map.

Short map:

```txt
main.py                     FastAPI backend + static UI
static/index.html           Frontend
core.py                     Request bridge
agent.py                    Runtime service/tool layer
agent_runtime/              Planner, executor, validator, memory context
burgerprints.py             BurgerShop/BurgerPrints v1 client
mockup_engine.py            Image prompt + generation pipeline
providers.py                Gemini/image provider calls
burger_memory.py            SQLite/session/bulk job storage
telegram_poller.py          Optional Telegram interface
scripts/                    setup/run/test helpers
```

## Verification

```bash
./scripts/test.sh
curl -s http://127.0.0.1:8000/api/tools
curl -s -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"chat_id":"smoke","message":"lấy toàn bộ sản phẩm"}'
```

## Notes

- Product flow uses seller-product IDs only (`Axxxxx-xx`).
- Default API base is `https://api.burgerprints.com/v1`.
- Generated images are written to `outputs/`.
- Uploads are written to `uploads/`.
- Runtime state is written to `memory/`.
- Do not commit `.env`, `outputs/`, `uploads/`, `memory/`, `.venv/`.
