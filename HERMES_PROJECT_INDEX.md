# JOY-DNSE — Product-only Mockup Agent

Canonical root: `/root/joy-dnse`  
Live app: `http://36.50.26.198:8000`  
Python venv: `/root/joy-dnse/.venv`  
Runtime: manual background processes (`python main.py`, `python telegram_poller.py`)

## Current scope

Product-only v1 runtime. No order-ID flow. No BurgerPrints v2 order endpoints.

Supported actions:
- list seller products: `bs_list_seller_products`
- get seller product: `bs_get_seller_product`
- create lifestyle mockup from seller product: `create_mockup_from_seller_product`
- refine latest mockup: `refine_mockup`
- optional account checks: `bp_authenticated`, `bp_balance`

Seller product IDs look like `A53636-28`.

## Read order

1. `joyagent.md`
2. `main.py`
3. `core.py`
4. `agent_runtime/orchestrator.py`
5. `agent_runtime/planner.py`
6. `agent_runtime/executor.py`
7. `agent.py`
8. `burgerprints.py`
9. `mockup_engine.py`
10. `static/index.html`

## Architecture

```txt
Web / Telegram
  ↓
main.py / telegram_poller.py
  ↓
core.handle_message()
  ↓
AgentOrchestrator
  ├── context_builder.py
  ├── planner.py              # deterministic product-only planner
  ├── plan_validator.py
  ├── executor.py             # deterministic tool execution
  ├── verifier.py
  └── burger_memory.py
  ↓
agent.py                      # tool implementations + legacy LLM fallback
  ├── burgerprints.py          # BurgerShop v1 seller-product API
  ├── mockup_engine.py         # mockup generation
  └── sync_webhook.py          # optional n8n/Lark sync
```

## Runtime files

- `main.py` — FastAPI, `/api/chat`, `/api/tools`, settings, logs, static UI
- `telegram_poller.py` — Telegram polling; `/new`; image/document upload
- `core.py` — singleton agent + orchestrator bridge
- `agent.py` — tool declarations + tool execution + fallback chat
- `burgerprints.py` — v1 seller product client
- `agent_runtime/` — planner/validator/executor/verifier runtime
- `burger_memory.py` — session state + mockup job/image logs
- `mockup_engine.py` — image generation pipeline
- `providers.py`, `prompts.py`, `design_compositor.py`, `image_preprocess.py`, `integrity.py`, `product_layout.py` — image pipeline helpers
- `static/index.html` — frontend
- `templates/mockup/*.md` — prompt templates

## Data dirs

- `uploads/` — user uploaded files; keep
- `outputs/` — generated mockups; runtime output
- `assets/` — cached/downloaded image assets
- `memory/` — runtime state
- `archive/` — old archived generated data

## Removed legacy areas

- Gradio `app.py`
- order router/parser (`action_router.py`, `batch_parser.py`)
- old LLM wrapper (`gemini_llm.py`)
- v2/order docs/specs
- old UI backup
- stale sample images / tracked test sessions

## Safe commands

```bash
cd /root/joy-dnse
.venv/bin/python -m py_compile agent_runtime/*.py agent.py burgerprints.py main.py core.py
.venv/bin/pytest -q
.venv/bin/python main.py
.venv/bin/python telegram_poller.py
```

## Live verification

```bash
curl -s http://127.0.0.1:8000/api/tools
curl -s -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"chat_id":"smoke","message":"lấy toàn bộ product"}'
curl -s -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"chat_id":"smoke","message":"tạo 1 ảnh product A53636-28 phong cách cafe chạy luôn"}'
```

## Do not reintroduce

- `/v2/order`, `/order`, order IDs like `A60992-14-5706485`
- tool names: `bp_get_order`, `bp_list_orders`, `create_mockup_from_order`, `bp_tracking`, `bp_cancel_order`
- dashboard product ID treated as BP catalog short_code
