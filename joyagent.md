# joyagent.md — Joy Agent Project Manifest (Product-only)

Joy Agent reads this file first before operating on this project.

## Project identity

- Project: JOY Mockup — AI Lifestyle Mockup Engine
- Agent callsign: J_agent
- Language: Vietnamese (“Dạ”, “anh”)
- Goal: create lifestyle mockups from BurgerShop seller products via natural language

## Entry points

| What | File | Port |
|---|---|---|
| Web UI | `main.py` | 8000 |
| Chat API | `POST /api/chat` | 8000 |
| Agent core | `agent_runtime/orchestrator.py` | — |
| Tool layer | `agent.py` | — |
| Telegram | `telegram_poller.py` | — |
| Memory | `burger_memory.py` | — |

## File map

### Core

| File | Owns |
|---|---|
| `agent.py` | tool declarations + execution, fallback chat |
| `core.py` | singleton agent, `handle_message` |
| `main.py` | FastAPI: chat, upload, settings, static, webhook |
| `static/index.html` | Web chat UI |

### Runtime

| File | Owns |
|---|---|
| `agent_runtime/orchestrator.py` | pipeline: plan → validate → confirm → execute → verify → memory |
| `agent_runtime/planner.py` | deterministic product-only routing |
| `agent_runtime/executor.py` | deterministic tool execution |
| `agent_runtime/registry.py` | tool inventory |
| `agent_runtime/plan_schema.py` | agent plans, intents, scenes |
| `agent_runtime/scene_expander.py` | scene expansion and dedupe |
| `agent_runtime/context_builder.py` | context from memory/session |
| `agent_runtime/verifier.py` | output verification |
| `agent_runtime/visual_verifier.py` | visual quality checks |

### API

| File | Owns |
|---|---|
| `burgerprints.py` | BurgerShop v1 seller product API |
| `config_store.py` | settings persistence |

### Mockup pipeline

| File | Owns |
|---|---|
| `mockup_engine.py` | orchestrates mockup generation |
| `providers.py` | image generation providers |
| `prompts.py` | prompt templates |
| `design_compositor.py` | deterministic composite |
| `image_preprocess.py` | validation, background removal |
| `integrity.py` | SSIM quality gate |
| `product_layout.py` | bbox heuristics, base image selection |

### Support

| File | Owns |
|---|---|
| `burger_memory.py` | session state, user profile, recall |
| `imgbb_uploader.py` | image hosting |
| `lark_media_sync.py` | Lark Base sync |
| `sync_webhook.py` | n8n webhook |

### Config / docs

| File | Owns |
|---|---|
| `HERMES_PROJECT_INDEX.md` | canonical code map |
| `joyagent.config.json` | read order + core file listing |
| `AGENTS.md` | Hermes agent quickstart |
| `README.md` | project overview |
| `templates/mockup/` | mockup scene prompt templates |

## Rules

1. Product-only: seller product IDs like `A53636-28` — no order IDs, no bp_get_order/bp_list_orders.
2. API base: v1 (`https://api.burgerprints.com/v1`).
3. Vietnamese style: “Dạ anh”, gọi user “anh”.
4. Preserve design pixels when compositing (integrity gate ≥ 0.85).
5. Output ≥ 1500×1500 px.
6. No brand logos, no celebrity faces.
7. Current user request overrides memory.
8. Small patches, verify with py_compile + curl after edits.

## Safe commands

```bash
# Compile
cd /root/joy-dnse && source .venv/bin/activate && python -m py_compile agent_runtime/*.py agent.py burgerprints.py main.py core.py

# Start
python main.py

# Test
curl -s -X POST http://localhost:8000/api/chat -H 'Content-Type: application/json' -d '{"chat_id":"smoke","message":"lấy toàn bộ product"}'
```

## Do not touch

- `.venv/` — Python venv
- `.git/` — Git history
- `uploads/` — User content
- `.env` — Secrets
- `archive/` — Archived old outputs
