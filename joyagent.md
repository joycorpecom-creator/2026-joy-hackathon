# joyagent.md — Joy Agent Project Manifest

> Joy Agent reads this file first before operating on this project.
> It tells the agent: who we are, what files matter, what rules to follow, and where to find deeper docs.

---

## 1. Project Identity

- **Project:** BurgerMockup — AI Lifestyle Mockup Engine
- **Sponsor:** BurgerPrints
- **Agent callsign:** J_agent
- **Language:** Vietnamese (xưng "Dạ", gọi user "anh")
- **Goal:** Turn flat print design + BP catalog product → lifestyle mockup via natural language

---

## 2. Entry Points

| What | File | Port |
|------|------|------|
| Web UI | `main.py` → `python main.py` | `8000` |
| Chat API | `POST /api/chat` | `8000` |
| Live logs | `GET /logs/agent` | `8000` |
| Agent core | `agent.py` — Gemini tool-calling loop | — |
| Telegram | `telegram_poller.py` (optional) | — |
| Memory | `burger_memory.py` — session/profile/recall | — |

---

## 3. File Map

### Core Pipeline
| File | Owns |
|------|------|
| `agent.py` | LLM loop, routing, system prompt, memory injection |
| `core.py` | Singleton agent, `handle_message` |
| `main.py` | FastAPI: chat, upload, settings, logs, Telegram webhook |
| `static/index.html` | Web chat UI |

### BurgerPrints
| File | Owns |
|------|------|
| `burgerprints.py` | BP API v2 client |
| `product_layout.py` | Print area bbox, base image selection |

### Mockup Generation
| File | Owns |
|------|------|
| `mockup_engine.py` | Orchestration: design upload validate → generate scene → composite → integrity |
| `design_compositor.py` | Deterministic composite, perspective warp, blend |
| `integrity.py` | SSIM gate (flat >0.92, lifestyle >0.85) |

### Memory / State
| File | Owns |
|------|------|
| `burger_memory.py` | 3-tier memory: session state, user profile, SQLite FTS recall |
| `memory/*` | JSON state files, SQLite DB |

### Support
| File | Owns |
|------|------|
| `image_preprocess.py` | Validation, background removal, lighting match |
| `config_store.py` | Settings persistence |
| `gemini_llm.py` | Gemini API wrapper |
| `prompts.py` | Prompt templates |
| `providers.py` | Image generation providers |
| `action_router.py` | Legacy regex intent extraction |
| `imgbb_uploader.py` | Image hosting |
| `lark_media_sync.py` | Lark Base sync |
| `sync_webhook.py` | n8n webhook |

---

## 4. Non-Negotiable Rules

1. **Design preservation**: original artwork pixels are source of truth. Never redraw by AI.
2. **Output size**: ≥1500×1500 px.
3. **No brand logos, no celebrity faces**.
4. **BP API v2 only**: catalog `short_code` (USG5000), not dashboard `A60992-*`.
5. **Current user request always overrides memory**.
6. **Setup ≤15 min for judge**: `venv → pip install → python main.py`.
7. **Small patches, no broad refactors before demo**.

---

## 5. Where to Find Things

| Looking for | Path |
|-------------|------|
| Project spec | `PROJECT_SPEC_BURGERMOCKUP.md` |
| Agent routing rules | `skills/burgermockup-agent-routing/SKILL.md` |
| Design integrity guide | `skills/burgermockup-design-integrity/SKILL.md` |
| BP API guide | `skills/burgermockup-bp-api/SKILL.md` |
| Memory guide | `skills/burgermockup-memory/SKILL.md` |
| Demo setup guide | `skills/burgermockup-demo-ops/SKILL.md` |
| Code map | `HERMES_PROJECT_INDEX.md` |
| Context contracts | `docs/context/*.md` |
| Runbooks | `docs/runbooks/*.md` |
| Previous plans | `.hermes/plans/*.md` |

---

## 6. Safe Commands

```bash
# Verify compile
cd /root/joy-dnse && source .venv/bin/activate && python -m py_compile agent.py

# Start app
python main.py

# Health check
curl http://localhost:8000/api/logs/agent

# Test API
curl -X POST http://localhost:8000/api/chat -H 'Content-Type: application/json' -d '{"message":"hello"}'

# View logs
tail -f /tmp/joy_dnse_main.log
```

---

## 7. Do Not Touch

- `.venv/` — Python venv
- `.git/` — Git history
- `memory/session_*.json` — Live session data
- `uploads/` — User uploads
- `outputs/` — Generated mockups
- `assets/` — Static images
- `.env` — Secrets
- `env/` — Environment files

---

## 8. Agent Identity

```yaml
name: J_agent
role: BurgerMockup conversational assistant
personality: polite, warm, Vietnamese
call_to_action: "Dạ anh, ..."
platforms: web, telegram
default_model: gemini-3-flash-preview
```
