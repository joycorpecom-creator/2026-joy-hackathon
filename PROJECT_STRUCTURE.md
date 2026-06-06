# PROJECT_STRUCTURE.md — JOY-DNSE Mockup Studio code map

Canonical root: `/root/joy-dnse`  
Live app: `http://127.0.0.1:8000` (configurable)  
Python venv: `.venv`  
Quick start: `./run.sh`

## Current scope

Product-only v1 runtime. Supported:
- list seller products  
- inspect seller product `Axxxxx-xx`  
- create lifestyle mockups from seller product  
- refine latest mockup  
- optional Telegram polling, optional automated sync  

Removed: order-ID flows, BurgerPrints v2 order endpoints.

## Read order (for code review)

1. `README.md`
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
Browser / Telegram
  ↓
main.py / telegram_poller.py
  ↓
core.handle_message()
  ↓
Orchestrator
  ├── context_builder.py     session history, product list, user profile
  ├── planner.py             deterministic product command routing
  ├── plan_validator.py
  ├── executor.py            tool execution + image format
  ├── verifier.py
  └── burger_memory.py       SQLite + sessions + bulk jobs
  ↓
agent.py                     tool implementations
  ├── burgerprints.py         BurgerShop v1 client
  ├── mockup_engine.py        image generation
  └── sync_webhook.py         optional n8n/Lark
```

## File map

### Core

| File | Owns |
|---|---|
| `agent.py` | tool declarations + execution, fallback chat |
| `core.py` | `handle_message` entry point |
| `main.py` | FastAPI: chat, upload, settings, static, webhook |
| `static/index.html` | Web chat frontend |

### Runtime

| File | Owns |
|---|---|
| `agent_runtime/orchestrator.py` | plan → validate → confirm → execute → verify |
| `agent_runtime/planner.py` | deterministic command routing |
| `agent_runtime/executor.py` | deterministic tool execution |
| `agent_runtime/registry.py` | tool inventory |
| `agent_runtime/plan_schema.py` | intents, scenes |
| `agent_runtime/scene_expander.py` | scene expansion, dedupe |
| `agent_runtime/context_builder.py` | context from memory/session |
| `agent_runtime/prompt_library.py` | 12 category product prompts, 5-block expert structure |
| `agent_runtime/image_brief_planner.py` | Gemini creative brief (tier-2 reasoning) |
| `agent_runtime/image_prompt_compiler.py` | brief → deterministic final prompt |
| `agent_runtime/verifier.py` | output verification |
| `agent_runtime/visual_verifier.py` | visual quality checks |
| `agent_runtime/plan_validator.py` | plan validation |

### API connection

| File | Owns |
|---|---|
| `burgerprints.py` | BurgerShop v1 seller product API |
| `config_store.py` | settings persistence |

### Mockup pipeline

| File | Owns |
|---|---|
| `mockup_engine.py` | image generation orchestrator |
| `providers.py` | Gemini image generation providers |
| `prompts.py` | legacy prompt templates |
| `design_compositor.py` | deterministic composite |
| `image_preprocess.py` | image validation, background removal |
| `integrity.py` | SSIM quality gate |
| `product_layout.py` | display area heuristics, base image selection |

### Support

| File | Owns |
|---|---|
| `burger_memory.py` | session state, user profiles |
| `imgbb_uploader.py` | image hosting |
| `lark_media_sync.py` | Lark Base sync |
| `sync_webhook.py` | n8n webhook |

### Config / docs

| File | Owns |
|---|---|
| `README.md` | user-facing overview |
| `PROJECT_STRUCTURE.md` | this file — developer code map |
| `PRODUCT_SPEC.md` | product specification |
| `DEVELOPER_GUIDE.md` | developer quickstart |
| `project.config.json` | file listing / read order metadata |
| `templates/mockup/` | mockup scene prompt templates |

## Runtime data dirs

- `uploads/` — user uploads; keep
- `outputs/` — generated mockups; runtime output
- `memory/` — runtime state
- `archive/` — old generated data (safe to delete)

## Removed legacy

- Gradio `app.py`
- Order router/parser (`action_router.py`, `batch_parser.py`)
- Old text-only wrapper (`gemini_llm.py`)
- v2/order docs/specs
- Old UI backup
- Stale sample images

## Safe commands

```bash
cd /root/joy-dnse
source .venv/bin/activate

# Syntax check
python -m py_compile agent_runtime/*.py agent.py burgerprints.py main.py core.py

# Test
python -m pytest -q

# Start
./run.sh

# Telegram
python telegram_poller.py
```

## Live verification

```bash
curl -s http://127.0.0.1:8000/api/tools
curl -s -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"chat_id":"smoke","message":"lấy toàn bộ sản phẩm"}'
curl -s -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"chat_id":"smoke","message":"tạo 1 ảnh product A53636-28 phong cách cafe chạy luôn"}'
```

## Do NOT reintroduce

- `/v2/order`, `/order`, order IDs like `A60992-14-5706485`
- Tool names: `bp_get_order`, `bp_list_orders`, `create_mockup_from_order`, `bp_tracking`, `bp_cancel_order`
- Dashboard product ID treated as BP catalog short_code
- AI/LLM-agent wording in docs, UI, or filenames — this repo is presented as a web app
