# JOY Mockup Agent V2

## Architecture

```
User (Telegram / Web)
  ↓
handle_message (core.py)
  ↓
AgentOrchestrator.process()
  ├── Context Builder → context rich with session/tools/state
  ├── Planner → deterministic_plan (intent, scenes, tool_plan)
  ├── Plan Validator → checks count, tools, dedupes scenes
  ├── Confirm Gate → batch≥4 or inferred scenes → plan_preview
  ├── Executor → runs tool_plan deterministically (no LLM per step)
  ├── Verifier → checks count, duplicates, missing
  └── Memory → saves plan, job, images, state
```

## Files

| File | Role |
|------|------|
| `agent_runtime/registry.py` | Tool inventory (7 tools) + prompt helper |
| `agent_runtime/plan_schema.py` | AgentPlan, SceneSchema, ToolPlanStep, intents |
| `agent_runtime/planner.py` | Deterministic planner (no LLM) + Gemini fallback |
| `agent_runtime/scene_expander.py` | Expand explicit/grouped/inferred scenes |
| `agent_runtime/plan_validator.py` | Validate + auto-fix duplicates |
| `agent_runtime/executor.py` | Run tool_plan, generate batch, retry missing |
| `agent_runtime/verifier.py` | Verify count, duplicates, missing URLs |
| `agent_runtime/context_builder.py` | Build context dict from session/memory/tools |
| `agent_runtime/orchestrator.py` | Plan → Validate → Confirm → Execute → Verify → Memory |

## API Endpoints

| Endpoint | Function |
|----------|----------|
| `POST /api/chat` | Main chat (V2 orchestrator + legacy fallback) |
| `POST /api/agent/plan` | Plan only, no execution |
| `POST /api/agent/execute` | Execute pending plan |
| `GET /api/tools` | Tool registry |
| `GET /api/state/{session_id}` | Session state |
| `GET /api/logs/agent` | Live logs |

## Scene Expansion

Supports:
- **Explicit list**: `ảnh 1: beach\nảnh 2: office`
- **Grouped**: `2 ảnh nữ ở biển, 2 ảnh nam văn phòng, 1 ảnh tự chọn`
- **Inferred fallback**: auto-fill from scene library if count not met
- **Constraints**: global rules (black shirt, female model, readable text)
- **Dedupe**: auto-rewrite if duplicate prompts detected

## Confirmation Rules

- batch_count >= 4 → preview plan, wait confirm
- Inferred scenes > 0 → preview plan
- All explicit + batch ≤ 3 → execute directly
- User says "tạo luôn" / "không cần hỏi" → skip confirm
