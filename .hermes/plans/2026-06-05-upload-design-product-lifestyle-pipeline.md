# Upload Design → BP Product → Lifestyle Mockup Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a chat-first flow where seller uploads a print file, asks for a BP product + scene, and the system creates a lifestyle mockup using BP catalog product data while preserving the original design.

**Architecture:** Add explicit design session state + upload endpoint. Use BP `/v2/product/{short_code}` as product source of truth. Generate product/base layer via deterministic composite first; Gemini only creates lifestyle scene/context or light background, never redraws the uploaded design.

**Tech Stack:** FastAPI, Pillow/OpenCV/scikit-image, Gemini image generation, BurgerPrints API v2, existing chat UI, existing sync pipeline.

---

## Current State

- `agent.py`: Gemini tool-calling agent, supports product lookup + product mockup.
- `mockup_engine.py`: currently has two paths:
  - order design → AI scene → `composite_design()` hardcoded placement.
  - product catalog → Gemini full lifestyle generation from BP product image.
- `burgerprints.py`: supports `/product` and `/product/{short_code}`.
- `static/index.html`: chat UI text-only input; displays image response.
- `core.py`: only `handle_message(msg, chat_id)`; no file payload support.
- Missing: upload design endpoint, session design memory, print area extraction/normalization, design-on-product composite, SSIM report.

## Product Reality

BP API public product endpoint gives catalog base products, not dashboard product IDs. Correct flow:

1. User uploads design file.
2. User asks: “tạo áo Gildan 5000 bối cảnh đường phố New York”.
3. Agent resolves product → `USG5000`.
4. Call `/v2/product/USG5000`.
5. Extract usable base mockup URL + color/options + print area if present.
6. Composite original uploaded design onto product area.
7. Use Gemini for scene/background/lifestyle context, not design redraw.
8. Validate design integrity via SSIM.

## Core Design Principle

**Never ask image model to redraw the print design.**

Recommended pipeline:

```txt
uploaded design file
  → normalize transparent PNG
  → BP product info/base mockup
  → deterministic design placement/composite
  → lifestyle scene generation/background
  → final composite product+design into scene
  → crop design region → SSIM against source
```

## Pipeline Options

### Option A — Safest for judging: AI background + deterministic product composite

Flow:
- Use BP base mockup as product layer.
- Composite original design onto shirt/tumbler print area with Pillow/OpenCV.
- Ask Gemini to generate scene background only: “New York street, model placeholder silhouette, empty center space/product display area”.
- Place product layer into scene.

Pros:
- Highest design integrity.
- Easy SSIM proof.
- Stable demo.

Cons:
- Less realistic garment deformation.
- Product may look pasted if shadows/masks weak.

Use for: semi-final live test, text-heavy design, logo/text edge cases.

### Option B — Hybrid realism: Gemini creates lifestyle product placeholder, then composite design

Flow:
- Gemini generates model wearing blank product matching BP product/color/angle.
- Detect shirt/tumbler print area in generated image (manual bbox fallback first; later SAM/segmentation).
- Composite original design with perspective warp + lighting blend.

Pros:
- Better lifestyle realism.
- Still preserves original design because design applied after AI.

Cons:
- Need robust print area detection.
- Harder SSIM due warp/lighting.

Use for: final polish.

### Option C — Pure image-to-image with design reference

Flow:
- Give Gemini product + design + prompt, ask to preserve design.

Pros:
- Fast prototype.

Cons:
- High risk: text altered, colors changed → fails core requirement.

Use only as optional variant, never primary.

## Recommended MVP Architecture

Primary = Option A with partial Option B styling.

Modules:

- `design_store.py`
  - save uploaded file per `chat_id`
  - metadata: path, original name, size, mime, hash, created_at
  - convert SVG/JPG to normalized transparent PNG

- `product_layout.py`
  - parse BP product payload
  - choose base image URL
  - choose color
  - infer print area bbox
  - fallback bbox by product category

- `design_compositor.py`
  - resize design to print area preserving aspect ratio
  - optional perspective warp
  - alpha composite onto product image
  - shadows/highlights/fabric blend mask

- `integrity.py`
  - crop final design region
  - resize to source design dimensions
  - compute SSIM/RMSE/color delta
  - output `integrity_score`, `pass_threshold`, `notes`

- `mockup_engine.py`
  - add `generate_uploaded_design_product_mockup(chat_id, design_path, product, scene)`

- `agent.py`
  - add tools:
    - `get_current_design(chat_id)` internal helper, not LLM tool maybe.
    - `create_mockup_from_uploaded_design(short_code, scene, color?)` Gemini function.
  - prompt rule: if user asks for mockup and design exists → use uploaded design flow.

- `main.py`
  - add `POST /api/upload-design`
  - add optional `GET /api/session-design/{chat_id}`

- `static/index.html`
  - add attach button
  - preview uploaded design chip in chat input
  - send upload first, then text prompt separately

## Data Model

Design session file:

```json
{
  "chat_id": "web",
  "design_id": "sha1-12",
  "original_filename": "cat-shirt.png",
  "source_path": "uploads/web/sha1-original.png",
  "normalized_path": "uploads/web/sha1-normalized.png",
  "mime": "image/png",
  "width": 4200,
  "height": 4800,
  "has_alpha": true,
  "created_at": 1710000000
}
```

Final result payload:

```json
{
  "type": "mockup",
  "image": "/outputs/uploaded_USG5000_xxx.png",
  "meta": {
    "product_id": "USG5000",
    "product_name": "Gildan 5000",
    "scene": "New York street",
    "size": "1600x1600",
    "provider": "gemini-background+deterministic-composite",
    "integrity_score": 0.94,
    "integrity_method": "ssim_flat_crop",
    "design_id": "..."
  }
}
```

## Print Area Strategy

Priority order:

1. If BP product payload contains explicit print area / templates / sides → use it.
2. If payload gives mockup/template image dimensions → map print area to that coordinate system.
3. Product category fallback:
   - T-shirt front: center chest `x=0.34w, y=0.34h, w=0.32w, h=0.34h`.
   - Hoodie front: `x=0.34w, y=0.36h, w=0.32w, h=0.30h`.
   - Tumbler/mug: curved/perspective bbox, narrower center.
   - Poster/canvas: near-full surface.
4. If confidence low → ask user: “Dạ anh muốn in mặt trước hay sau / màu nào?”

Important: store `print_bbox` in result for SSIM crop.

## SSIM Strategy

Two metrics:

- `flat_ssim`: source design vs design layer after resize before scene placement. Target > 0.92.
- `lifestyle_ssim`: source design vs extracted final crop after lighting/scene. Target > 0.85.

Implementation detail:
- Convert source and crop to RGB.
- Resize both to same dimensions.
- If transparent source: compare only alpha mask area.
- Use `skimage.metrics.structural_similarity(channel_axis=2)`.
- For text-heavy designs, also compute OCR-ish sanity later; MVP: SSIM + color histogram.

Acceptance:
- If `flat_ssim < 0.92` → fail output, retry with larger design/no warp/no blend.
- If `lifestyle_ssim < 0.85` → return warning + fallback safer composite.

## Agent Conversation Rules

Cases:

1. User uploads design only:
   - Reply: “Dạ anh, em đã nhận file in. Anh muốn lên sản phẩm nào và bối cảnh gì?”

2. User asks product+scene after upload:
   - Resolve product → call BP → generate.

3. User asks product+scene before upload:
   - Reply: “Dạ anh gửi file in PNG/JPG/SVG trước giúp em.”

4. User gives dashboard product ID like `A60992-1`:
   - Explain public API không lấy dashboard product; ask for catalog base (`USG5000`) or product name.

5. Multi-turn refinement:
   - Keep same design + product unless user changes.
   - Only scene changes regenerate background/final composite.

## Implementation Phases

### Phase 1 — Upload + Design Memory

- Create `uploads/` ignored by git.
- Add `design_store.py`.
- Add `POST /api/upload-design` in `main.py`.
- UI attach button + preview.
- Verify: upload PNG/JPG/SVG returns design metadata.

### Phase 2 — Product Resolution + Session-Aware Tool

- Add agent tool `create_mockup_from_uploaded_design`.
- Update system prompt rules.
- `agent._execute_tool()` checks session design exists.
- Verify: upload design, then “tạo Gildan 5000 đường phố New York” triggers BP search/product + new tool.

### Phase 3 — Deterministic Composite Engine

- Add `product_layout.py` fallback bbox.
- Add `design_compositor.py`.
- Use BP base image + design composite.
- Verify output >=1500x1500; design visible exactly.

### Phase 4 — Gemini Background/Lifestyle Layer

- Add `providers.try_generate_lifestyle_background(scene, product_name, color)`.
- Composite product+design onto background with shadow/reflection.
- Verify no brand logos/celebrity faces via prompt constraints.

### Phase 5 — SSIM Integrity Gate

- Add `integrity.py`.
- Return integrity metadata.
- If score below threshold, fallback to flat-safe composite.
- Verify with text-heavy sample.

### Phase 6 — Sync + README Samples

- Extend sync payload with design_id/integrity/product_short_code.
- Update README with design-integrity strategy + setup.
- Generate 10 samples with prompt/time/cost.

## Risks / Edge Cases

- BP product payload may not contain print coordinates → need fallback bbox library.
- SVG conversion may need `cairosvg`; if not installed, reject with clear message or convert through browser/libreoffice fallback.
- Transparent designs on black product: need optional white underbase or preserve as-is based on user choice.
- All-over-print: default bbox is insufficient; treat AOP as separate phase.
- Multi-print front/back/sleeve: MVP front only; ask user to choose side.
- Gemini may create real logos/signage in NYC scene → prompt: generic street, no visible real brand marks.
- Final pasted look → add contact shadow, fabric highlight overlay, slight displacement but keep flat SSIM.

## Global QA Gate

- [ ] Upload PNG/JPG/SVG works.
- [ ] Chat remembers current design per `chat_id`.
- [ ] Product name resolves to BP short_code.
- [ ] `/v2/product/{short_code}` called for catalog product.
- [ ] Dashboard IDs are not sent to product endpoint blindly.
- [ ] Output image displayed in UI.
- [ ] Output >= 1500x1500.
- [ ] Original design not redrawn by Gemini.
- [ ] SSIM flat > 0.92 or fallback triggered.
- [ ] Lifestyle SSIM > 0.85 or warning/fallback.
- [ ] No secrets committed.

## Execution Order

1. Build upload/design memory first.
2. Build deterministic composite with fallback bbox.
3. Wire agent tool.
4. Add SSIM.
5. Add Gemini background.
6. Polish UI + sync/report.

