# BurgerMockup Bot

AI Lifestyle Mockup Engine for BurgerPrints.

From a flat product/design prompt to listing-ready lifestyle mockups, then sync demo data to Lark Base through n8n.

## What this prototype does

- Conversational mockup agent, not a static upload form.
- Uses BurgerPrints API v2 catalog/product data.
- Uses Gemini image generation for lifestyle mockups.
- Shows generated images in the web UI.
- Uploads generated image to imgbb for a stable HTTPS preview URL.
- Uploads generated file to Lark media, then sends metadata to n8n.
- n8n creates a Lark Base record and appends the attachment token.

Current demo flow:

```txt
User prompt
→ BurgerPrints product lookup
→ Gemini generates PNG locally
→ app uploads image to imgbb
→ app uploads local PNG to Lark media, gets file_token
→ app POSTs n8n webhook
→ n8n creates Lark Base record
→ n8n appends attachment using file_token
```

## Local setup, ≤15 min

### 1. Clone

```bash
git clone <your-repo-url>
cd <repo-folder>
```

### 2. Create Python env

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure env

```bash
cp .env.example .env
```

Edit `.env`:

```env
BURGERPRINTS_API_KEY=your_burgerprints_key
GEMINI_API_KEY=your_gemini_key
IMGBB_API_KEY=your_imgbb_key

PUBLIC_BASE_URL=http://127.0.0.1:8000
SYNC_ENABLED=true
SYNC_PROVIDER=n8n
SYNC_WEBHOOK_URL=https://your-n8n.example/webhook/burgermockup-sync
```

Default public URL is local:

```txt
http://127.0.0.1:8000
```

For local judge/demo, keep it as-is.

### 4. Run web app

```bash
python main.py
```

Open:

```txt
http://127.0.0.1:8000
```

## Settings UI

You can also configure from the web UI Settings tab:

- BurgerPrints API key
- Gemini API key
- Public base URL: default `http://127.0.0.1:8000`
- Sync enabled: `true`
- n8n webhook URL
- Optional Telegram bot token/chat ID

## Required config for judge machine

Minimum required:

```txt
BURGERPRINTS_API_KEY
GEMINI_API_KEY
IMGBB_API_KEY
SYNC_WEBHOOK_URL
PUBLIC_BASE_URL=http://127.0.0.1:8000
```

No Lark setup needed for the default demo path.

The judge’s local app sends data to the provided n8n webhook. The webhook is already connected to the demo Lark Base.

## Optional Telegram mode

If using Telegram bot:

```env
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_ALLOWED_CHAT_ID=xxx
```

Run the poller separately:

```bash
python telegram_poller.py
```

If using only the web UI, skip Telegram.

## Demo n8n webhook

Current demo webhook:

```txt
https://your-n8n.example/webhook/burgermockup-sync
```

n8n responsibilities:

```txt
receive mockup.created JSON
→ create Lark Base record
→ append Lark attachment if lark_file_token is present
→ return { ok, record_id, file_token, imgbb_url }
```

## Lark/Base setup

Default demo mode:

```txt
Judge does not need Lark App ID / Secret / Base Token.
```

Those are preconfigured in the n8n workflow.

Optional self-host mode requires:

```env
LARK_APP_ID=
LARK_APP_SECRET=
LARK_BASE_TOKEN=
LARK_TABLE_ID=
LARK_ATTACHMENT_FIELD_ID=fldfkDRB21
```

Use self-host mode only if you want to run your own Lark Base instead of the demo Base.

## Expected webhook payload

The app sends JSON like:

```json
{
  "event": "mockup.created",
  "mockup_id": "product_USBC3200_xxxxxxxx",
  "product": {
    "id": "USBC3200",
    "name": "Unisex Raglan Shirt",
    "color": "Black"
  },
  "prompt": {
    "scene": "streetwear model, urban wall",
    "raw_user_input": "create streetwear lifestyle mockup"
  },
  "generation": {
    "provider": "gemini-image-input",
    "model": "gemini-3.1-flash-image",
    "size": "1600x1600",
    "seconds": 16.5,
    "cost_usd": 0.08,
    "integrity_score": 0.92
  },
  "assets": {
    "image_url": "https://i.ibb.co/.../mockup.png",
    "imgbb_url": "https://i.ibb.co/.../mockup.png",
    "lark_file_token": "xxx",
    "filename": "mockup.png"
  }
}
```

## Demo prompts

```txt
Create a professional lifestyle mockup for product USBC3200, streetwear model, urban wall background, natural pose.
```

```txt
Create cozy living room lifestyle mockup for a Christmas shirt, warm light, Etsy listing style.
```

```txt
Make it more yoga/wellness niche: middle-aged woman in yoga studio at sunrise.
```

## Product/design integrity strategy

Core requirement: preserve design as much as possible.

Current prototype strategy:

- Use BurgerPrints product data and mockup references as grounding.
- Ask Gemini to preserve the product artwork/design area.
- Keep original generated file as local PNG.
- Store preview URL and Lark attachment for side-by-side review.
- Track metadata: model, size, time, cost, integrity score.

Recommended final pipeline improvement:

```txt
AI lifestyle scene generation
→ deterministic product/design composite with Pillow/OpenCV
→ SSIM check against original design region
→ reject/regenerate if score below threshold
```

Targets:

```txt
Flat mockup SSIM > 0.92
Lifestyle mockup SSIM > 0.85
Output ≥1500×1500 px
```

## Troubleshooting

### Web page not loading

Check server:

```bash
curl http://127.0.0.1:8000
```

Restart:

```bash
python main.py
```

### Sync not appearing in Base

Check:

```txt
SYNC_ENABLED=true
SYNC_WEBHOOK_URL is correct
n8n workflow is active
Gemini generation completed
```

The app response should include:

```txt
sync_status: sent
sync_record_id: rec...
sync_image_url: https://i.ibb.co/...
```

### imgbb upload fails

Check:

```txt
IMGBB_API_KEY is valid
local PNG exists in outputs/
internet access is available
```

### BurgerPrints product lookup fails

Check:

```txt
BURGERPRINTS_API_KEY is valid
BURGERPRINTS_BASE_URL=https://api.burgerprints.com/v2
```

## Project structure

```txt
main.py                 FastAPI web app
agent.py                Conversational agent + mockup generation tool call
bp_api.py               BurgerPrints API client
image_gen.py            Gemini image generation
imgbb_uploader.py       Upload generated PNG to imgbb
lark_media_sync.py      Upload local PNG to Lark media / attachment token
sync_webhook.py         Build and POST n8n sync payload
telegram_poller.py      Optional Telegram interface
static/index.html       Web UI
outputs/                Generated mockups
.env.example            Local config template
```

## Submission checklist

- GitHub repo
- README with setup steps
- ≥10 sample mockups with prompt/time/cost
- 3–5 min demo video
- Slide deck
- Live demo optional

Recommended live demo path:

```txt
Open http://127.0.0.1:8000
→ enter prompt
→ generate image
→ show image in UI
→ open Lark Base
→ show synced record + attachment
```
