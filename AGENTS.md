# JOY Mockup Agent — Product-only Runtime

Read `HERMES_PROJECT_INDEX.md` first.

## Architecture

```txt
User (Telegram / Web)
  ↓
handle_message (core.py)
  ↓
AgentOrchestrator.process()
  ├── Context Builder
  ├── Planner — product-only deterministic routing
  ├── Plan Validator
  ├── Executor — deterministic tool calls
  ├── Verifier
  └── Memory
```

## Active tools

- `bs_list_seller_products`
- `bs_get_seller_product`
- `create_mockup_from_seller_product`
- `refine_mockup`
- `bp_authenticated`
- `bp_balance`

## Rules

- Product-only: use seller product IDs like `A53636-28`.
- No order APIs, no `/v2/order`, no old order tools.
- Keep Vietnamese assistant style: “Dạ”, gọi user “anh”.
- Preserve design integrity; never redraw user artwork unnecessarily.
- After code edits run compile + smoke tests.

## Verification

```bash
cd /root/joy-dnse
.venv/bin/python -m py_compile agent_runtime/*.py agent.py burgerprints.py main.py core.py
.venv/bin/pytest -q
```
