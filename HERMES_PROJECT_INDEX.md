# JOY-DNSE Basecode — BurgerMockup Bot v1 (7/10)

> File điều hướng cho Hermes. Đọc file này trước khi code/sửa joy-dnse.

**Canonical root:** `/root/joy-dnse`
**App live:** `http://36.50.26.198:8000`
**Runtime:** PM2 (không có — chạy `uvicorn main:app` manual) — check `ps aux | grep main.py`
**Python:** `3.10`, venv tại `/root/joy-dnse/.venv`

---

## Tổng quan kiến trúc

```txt
FastAPI (main.py) ─── static/ (HTML/CSS/JS frontend)
    │
    ├── core.py            ← message router
    │    └── agent.py      ← Gemini function-calling agent
    │         ├── 19 tool declarations
    │         └── 4 chat flow methods
    │
    ├── burgerprints.py    ← BP API v2 client (singleton)
    ├── config_store.py    ← settings.json r/w
    │
    ├── mockup_engine.py   ← mockup generation pipeline
    │    ├── product_layout.py   ← bbox heuristics
    │    ├── design_compositor.py ← Pillow + OpenCV warp
    │    ├── design_store.py     ← file upload manager
    │    ├── design_normalizer.py ← trim/crop/margin
    │    ├── image_preprocess.py ← product cutout (rembg)
    │    ├── integrity.py        ← SSIM gate
    │    ├── providers.py        ← Gemini image generator
    │    └── prompts.py          ← scene prompt builder
    │
    ├── sync_webhook.py    ← n8n Lark sync
    ├── lark_media_sync.py ← Lark media attachment sync
    ├── imgbb_uploader.py  ← ImgBB hosting
    │
    ├── burger_memory.py   ← SQLite + JSON memory
    ├── context_loader.py  ← manual rule-based context
    ├── action_router.py   ← intent parser (rule-based)
    │
    └── telegram_poller.py ← Telegram bot polling mode
```

---

## Entry points (đọc theo thứ tự này)

### 1. `main.py` (370 dòng) — FastAPI app

File chạy chính. Routes:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/settings` | đọc config (masked) |
| POST | `/api/settings` | ghi config |
| POST | `/api/test-burgerprints` | test BP key |
| POST | `/api/test-llm` | test Gemini key |
| POST | `/api/chat` | nhận message → `handle_message()` |
| POST | `/api/upload-design` | upload design file |
| GET | `/api/session-design/{chat_id}` | current design meta |
| GET | `/outputs/{filename}` | serve generated images |
| GET | `/api/logs/agent` | agent log tail |
| POST | `/webhook/larkbase/commands` | Lark Base ingress |
| GET | `/` | serve `static/index.html` |
| | `StaticFiles("/static")` | JS/CSS assets |
| Run block | `uvicorn` on port `8000` | | | | |

Key imports: `core.handle_message`, `config_store.load_settings/save_settings`.

### 2. `agent.py` (980 dòng) — Gemini Tool-Calling Agent

**Class:** `BurgerMockupAgent`

**Init:**
- Load settings → `BURGERPRINTS_API_KEY`, `GEMINI_API_KEY`
- `_sessions` dict in-memory
- `TOOL_DECLARATIONS` — 19 function declarations (xem section 4)

**Key methods:**

| Method | Dòng | Purpose |
|--------|------|---------|
| `__init__` | 207 | khởi tạo client + config |
| `client()` | 226 | lazy Gemini client singleton |
| `_get_history()` | 256 | load history từ JSON file |
| `_execute_tool()` | 274 | dispatch tool name → function call |
| `chat()` | 700 | **main loop** — Gemini → tool → response |
| `_format_product_response()` | 672 | build response text from product data |
| `clear_session()` | 964 | reset session |
| `test_connection()` | 971 | test all configured connections |

**Chat flow** (`chat()` method, 264 dòng):
1. Load session history + context.
2. Call Gemini with tool declarations.
3. If response has `function_calls` → loop execute + send back.
4. If model asks function but data missing → `ASK_CLARIFY` auto-response.
5. Build final text/image response.
6. Save to history + memory.

### 3. `burgerprints.py` (210 dòng) — BP API v2 Client

**Class:** `BurgerPrintsClient`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `authenticated()` | `GET /authenticated` | check key |
| `balance()` | `GET /balance` | số dư |
| `list_orders()` | `GET /order` | params: reference, sandbox, state, page |
| `get_order()` | `GET /order/{id}` | direct → reference fallback → DEMO |
| `tracking()` | `GET /order/{id}/tracking` | vận đơn |
| `cancel_order()` | `PUT /order/{id}/cancel` | hủy đơn |
| `delete_order()` | `DELETE /order/{id}` | xóa đơn |
| `charge_order()` | `POST /order/charge` | charge |
| `products()` | `GET /product` | catalog search |
| `product()` | `GET /product/{short_code}` | product detail |
| `out_of_stock()` | `GET /product/outofstock` | hết hàng |
| `add_webhook()` | POST w/ URL | webhook |
| `extract_first_asset()` | — | parse order → OrderAsset |
| `find_order_id()` | — | regex extract order from text |

**Key dataclass:** `OrderAsset`
```python
order_id, product_name, color_name, color_hex, design_url, mockup_url, product_id
```

**DEMO fallback:** `_demo_order()` returns hardcoded product for `DEMO-*` IDs.

**Known BP quirks** (ghi trong code + docs):
- Auth = HTTP header `api-key`.
- `/v2/product/{short_code}` chỉ accept catalog short_code (USG5000), không accept dashboard ID (A60992-*).
- Order items có `designs[].src`, `mockups[].src` để lấy asset URLs.
- `get_order()` fallback: direct → `GET /order?reference={id}` sandbox=false → sandbox=true.

### 4. `action_router.py` (342 dòng) — Intent Parser

**Legacy.** Được `agent.py` dùng qua `_execute_tool()` nhưng không phải source of truth cho routing. Agent dùng tool declarations trực tiếp.

**Function:** `detect_action(text)` — rule-based intent detection.

Actions: `auth`, `balance`, `tracking`, `cancel`, `delete`, `charge`, `out_of_stock`, `order`, `product_detail`, `product_search`, `product_mockup`, `mockup`, `chat`.

### 5. `mockup_engine.py` (364 dòng) — Mockup Pipeline

| Function | Purpose |
|----------|---------|
| `generate_mockup()` | từ order asset: download design → composite → scene → output |
| `generate_product_mockup()` | từ catalog product: base image + design hoặc no-design |
| `generate_uploaded_design_product_mockup()` | từ uploaded design + product + scene |
| `make_scene()` | deterministic placeholder scene |
| `composite_design()` | design → scene (shirt center) |
| `composite_product_image()` | product → scene |
| `download_image()` | cache URLs → `assets/` |

**Pipeline order cho `generate_uploaded_design_product_mockup`:**
1. validate upload design
2. pick product base image (`pick_base_image`)
3. **Primary:** Gemini dual-input (design + product) → composite → integrity gate ≥ 0.85
4. **Fallback:** deterministic composite → Gemini background scene → composite → output
5. **Final fallback:** deterministic scene + composite → output

### 6. `design_compositor.py` (128 dòng) — Pillow + OpenCV compositing

| Function | Purpose |
|----------|---------|
| `composite_design_on_product()` | warp design → blend with product fabric |
| `composite_product_into_scene()` | product cutout → scene → shadow |
| `perspective_warp_design()` | OpenCV 4-point perspective + fallback |
| `blend_with_fabric()` | integrity-first: design on top + subtle shadow |

### 7. `product_layout.py` (74 dòng) — Bbox heuristics

| Function | Purpose |
|----------|---------|
| `pick_base_image()` | extract URL from product payload |
| `infer_print_bbox()` | normalize print area: BP field → category fallback |
| `_category()` | classify shirt/hoodie/drinkware/flat |

### 8. `integrity.py` (57 dòng) — SSIM quality gate

| Function | Purpose |
|----------|---------|
| `compare_design_to_layer()` | flat SSIM: source vs placed (≥0.92 target) |
| `compare_design_to_final_crop()` | lifestyle SSIM: source vs final crop (≥0.85) |

### 9. `providers.py` (311 dòng) — AI Scene Providers

| Function | Purpose |
|----------|---------|
| `try_generate_ai_scene()` | Gemini single-image input → lifestyle scene |
| `try_generate_dual_input_lifestyle_mockup()` | Gemini design+product → mockup (one-pass) |
| `try_generate_lifestyle_mockup()` | product+design → scene |
| `build_scene_prompt()` | template-based prompt từ `templates/mockup/` |

### 10. `config_store.py` (96 dòng)

| Function | Purpose |
|----------|---------|
| `load_settings()` | read settings.json + .env fallback |
| `save_settings()` | write settings.json |
| `mask_secret()` | mask API keys for UI |

### 11. `burger_memory.py` (188 dòng) — SQLite + JSON memory

| Function | Purpose |
|----------|---------|
| `get_state(chat_id)` | session state JSON |
| `update_state()` | patch state |
| `get_profile()` | user profile |
| `search_memory()` | keyword search trong memory events |
| `build_memory_context()` | build context string cho agent |
| `record_turn()` | log user ↔ assistant turn |
| `record_mockup()` | log mockup generation |

### 12. `design_store.py` (138 dòng) — Upload manager

- Saves to `uploads/{chat_id}/{hash}_src.{ext}`
- SVG → PNG conversion via `cairosvg`
- Normalize via `design_normalizer.normalize_design_file()`

### 13. `telegram_poller.py` — Polling bot

- `getUpdates` polling loop
- Handles `/new`, text, photo/document upload
- `process_message()` → `handle_message()` → send result

---

## Agent tool declarations (19 tools in `agent.py`)

Định nghĩa từ dòng 28-200:

| Tool name | Purpose |
|-----------|---------|
| `bp_authenticated` | test BP key |
| `bp_balance` | balance |
| `bp_get_product` | product by short_code |
| `bp_search_products` | catalog search by keyword |
| `bp_out_of_stock` | list OOS products |
| `bp_get_order` | order detail (by ID/reference) |
| `bp_list_orders` | recent orders + mockup images |
| `bp_tracking` | tracking info |
| `bp_cancel_order` | cancel order (confirm gate) |
| `create_mockup_from_order` | order + scene → mockup |
| `create_mockup_from_product` | product + scene → mockup |
| `create_mockup_from_uploaded_design` | design + product + scene → mockup |
| `memory_save_profile` | user preference |
| `memory_search` | past mockup/prompt recall |
| `memory_get_profile` | get saved profile |
| `clarify_design_url` | return design URL |
| `system_help` | summary of all commands |
| `system_get_memory_context` | recent session summary |
| `system_new_session` | reset (same as `/new`) |

---

## Data flow

```txt
User message
  → main.py /api/chat
  → core.handle_message()
    → agent.chat(chat_id, message)
      → load session history (JSON)
      → Gemini + 19 tools
      → _execute_tool(name, args)
        → BurgerPrintsClient / mockup_engine / design_store / burger_memory
      → loop until final response
      → format text + optional image path
      → save history
      → return {"type": "text|image|error", "content": ..., "image": ...}
```

---

## File paths không nên đọc (noise)

- `__pycache__/` — compiled cache
- `.git/` — git internals
- `memory/` — per-session JSON dumps (state, user_profiles, session_*)
- `outputs/` — generated images (~50 PNGs)
- `assets/` — cached BP images (~15 PNGs)
- `uploads/` — uploaded designs (SVG, PNG, meta JSON)
- `templates/mockup/` — prompt templates (Markdown)

---

## API keys & secrets (lưu trong settings)

- `BURGERPRINTS_API_KEY`: masked `f23d...bbf6`
- `GEMINI_API_KEY`: masked `AQ.A...J7qQ`
- `TELEGRAM_BOT_TOKEN`: masked `8578...JYUs`
- `n8n webhook`: `https://automation.joyex.cloud/webhook/burgermockup-sync`
- `IMGBB_API_KEY`: (trong env)
- `PUBLIC_BASE_URL`: `http://36.50.26.198:8000`

Settings file: `/root/joy-dnse/settings.json` (không trong git)

---

## Các vấn đề cần biết khi code

### Bug/limitation hiện tại

1. **Agent context chưa state machine rõ** — 19 tools flat, không slot filling.
2. **Gemini deprecated model** — `gemini-2.0-flash` hết hạn, đang dùng `gemini-3-flash-preview`.
3. **Print area heuristic** — `infer_print_bbox()` fallback shirt (0.34/0.34/0.32/0.34) có thể sai cho product lạ.
4. **No async job queue** — generation synchronous, dễ timeout.
5. **Memory tách rời** — `burger_memory.py` SQLite + `agent.py` JSON history, không unified.
6. **Settings JSON + .env dual** — source of truth: settings.json. .env chỉ fallback.
7. **Telegram polling** — không webhook, dùng getUpdates.
8. **No test suite đủ** — chỉ có `test_new_command.py` + `test_burgerprints_api.py`.
9. **Product template chỉ heuristic** — không template JSON riêng cho từng short_code.
10. **SSIM threshold cứng** — 0.92 flat, 0.85 lifestyle. Chưa configurable.

### File nào không sửa nếu chỉ patch nhẹ

- Không sửa action_router.py trừ khi port sang intent system mới.
- Không sửa `context_loader.py` — đang deprecated cho joy-dnse.
- `burger_memory.py` và `agent.py` history trùng responsibility — cần unified nếu refactor lớn.

---

## Fast scan command

```bash
cd /root/joy-dnse
# Source tree (exclude noise)
find . -type f -name "*.py" ! -path "./__pycache__/*" | sort
# App file sizes
wc -l main.py agent.py core.py burgerprints.py mockup_engine.py \
      action_router.py config_store.py design_compositor.py \
      design_store.py integrity.py product_layout.py providers.py \
      image_preprocess.py burger_memory.py telegram_poller.py \
      sync_webhook.py lark_media_sync.py context_loader.py
# Running processes
ps aux | grep -E "(joy-dnse|main.py)" | grep -v grep
# Live logs
tail -100 /tmp/joy_dnse_main.log
```
