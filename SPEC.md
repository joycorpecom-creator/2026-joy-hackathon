# BurgerMockup Bot Spec + Plan

> **For Hermes:** Prototype-first. Keep setup trivial. No Hermes required for judges.

**Goal:** Build a standalone conversational mockup bot: BurgerPrints order ID + natural prompt → image mockup preview/URL.

**Architecture:** Thin web chat UI calls a Python engine. Engine fetches order assets, parses artwork/product, generates/loads scene, composites original artwork deterministically, returns local URL. BurgerPrints API can be mocked for judge/demo.

**Tech Stack:** Python, Gradio, requests, Pillow, OpenCV optional, scikit-image optional.

---

## Gap Map

- Done: project dir, README, spec
- Missing: API client, mock data, composite engine, UI, samples, tests
- Deferred: real AI provider, Telegram bot, Shopify/Etsy publish, Lark/Hermes integration

---

## Phase Plan

### Phase 1 — Skeleton + Mock Order [DONE]

Deliverable: local app starts, demo order resolves.

Files:
- `app.py`
- `burgerprints.py`
- `mock_data.py`
- `.env.example`
- `requirements.txt`

Acceptance:
- `python app.py` starts Gradio
- prompt containing `DEMO-1001` returns parsed order summary

Checklist:
- [x] `requirements.txt` exists
- [x] `.env.example` exists
- [x] `burgerprints.py` supports real key + mock fallback
- [x] `DEMO-1001` returns product + artwork path

### Phase 2 — Composite Engine [DONE]

Deliverable: generate at least 1500x1500 mockup with preserved design.

Files:
- `mockup_engine.py`
- `samples/demo_design.png`
- `outputs/`

Acceptance:
- generated image file exists
- output size >= 1500x1500
- artwork pixels placed without AI redraw

Checklist:
- [x] create placeholder lifestyle scene
- [x] paste original design on product area
- [x] save PNG output
- [x] return file URL/path in chat

### Phase 3 — Conversational Refinement [DONE]

Deliverable: multi-turn cache remembers last order/design.

Acceptance:
- user can say `change scene to yoga studio sunrise`
- app reuses previous order/design

Checklist:
- [x] session state stores `last_order_id`
- [x] session state stores last output list
- [x] refinement prompt works without repeating order ID

### Phase 4 — Real Provider Hook [PARTIAL]

Deliverable: optional Replicate/Gemini image generation.

Acceptance:
- no token → deterministic placeholder scene
- token present → provider call path available

Checklist:
- [x] `REPLICATE_API_TOKEN` optional
- [x] provider failure falls back cleanly
- [x] cost/time metadata returned

---

## Global QA Gate

- Output image >= 1500x1500
- No brand logo/celebrity prompt encouraged
- Original artwork layer never sent as redraw-only instruction
- Setup commands documented and <= 15 min
- BurgerPrints API usage documented even if demo uses mock fallback

---

## Execution Order

1. Build Phase 1 + Phase 2 now.
2. Validate app boots.
3. Add Phase 3 if time.
4. Add provider hook last.
