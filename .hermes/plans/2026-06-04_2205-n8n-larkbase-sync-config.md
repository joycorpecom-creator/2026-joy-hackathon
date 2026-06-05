# Plan: Web Config → n8n Webhook → Lark Base Mockup Sync

## Goal

Build a 15-minute setup path for BurgerMockup users:

1. User runs web app from GitHub.
2. User opens web Settings → Sync.
3. User enters one n8n webhook URL + optional secret.
4. Every generated mockup is sent to n8n.
5. n8n writes the record into Lark Base.

Preferred architecture:

```text
BurgerMockup Web/Telegram
→ create mockup
→ save image locally + expose public image URL
→ POST mockup.created payload to n8n webhook
→ n8n validates secret
→ n8n creates/updates Lark Base record
```

Direct Lark API from the web app is not the default because it makes GitHub setup harder and exposes more credentials.

---

## Current Context

Project path:

```text
/root/joy-dnse
```

Important files:

```text
static/index.html        # web UI/settings
config_store.py          # settings load/save
settings.json            # persisted settings
agent.py                 # agent tool execution + mockup return
mockup_engine.py         # generates image and returns metadata
main.py                  # FastAPI endpoints
telegram_poller.py       # Telegram bridge
```

Current mockup result already contains:

```json
{
  "path": "/root/joy-dnse/outputs/product_USNL3900_xxx.png",
  "filename": "product_USNL3900_xxx.png",
  "width": 1600,
  "height": 1600,
  "integrity_score": 0.92,
  "seconds": 17.29,
  "cost_usd": 0.08,
  "provider": "gemini-image-input"
}
```

Agent response metadata currently includes:

```text
provider, integrity, size, time, cost, product, color
```

Need add:

```text
scene, product_id, image_url, sync_status, sync_error
```

---

## Proposed Architecture

### 1. Web app config first

Add `Sync` tab in settings UI.

Fields:

```text
Enable Sync: checkbox
Provider: n8n webhook
Webhook URL: input
Secret Token: password input
Send Image URL: checkbox default true
Timeout Seconds: number default 10
Test Sync: button
Save All Settings: existing button
```

Settings shape:

```json
{
  "sync_enabled": false,
  "sync_provider": "n8n",
  "sync_webhook_url": "",
  "sync_secret": "",
  "sync_send_image_url": true,
  "sync_timeout_seconds": 10
}
```

Keep flat keys for compatibility with existing `settings.json` style unless `config_store.py` already supports nested objects cleanly.

### 2. Add sync module

Create:

```text
sync_webhook.py
```

Functions:

```python
def build_mockup_payload(*, result, product_id, product_name, color, scene, raw_user_input, public_base_url):
    ...

def post_mockup_created(payload, settings):
    ...
```

Behavior:

- If sync disabled → return `{status: "disabled"}`.
- If URL missing → return `{status: "skipped", error: "missing webhook_url"}`.
- POST JSON to webhook.
- Header:

```http
X-BurgerMockup-Secret: <secret>
X-BurgerMockup-Event: mockup.created
Content-Type: application/json
```

- Timeout from config.
- Do not block user too long.
- For initial version: synchronous with timeout 10s is acceptable.
- Later: background queue/retry.

Payload example:

```json
{
  "event": "mockup.created",
  "version": "1.0",
  "mockup_id": "product_USNL3900_90d4ed50",
  "created_at": "2026-06-04T22:05:00Z",
  "source": "burgermockup-web",
  "product": {
    "id": "USNL3900",
    "name": "Lady's T-Shirt | Next Level 3900 (US)",
    "color": "as shown in BP image"
  },
  "prompt": {
    "scene": "outdoor cafe, female model wearing white t shirt",
    "raw_user_input": "tạo mockup product 3900 outdoor cafe"
  },
  "generation": {
    "provider": "gemini-image-input",
    "model": "gemini-3.1-flash-image",
    "width": 1600,
    "height": 1600,
    "size": "1600x1600",
    "seconds": 17.29,
    "cost_usd": 0.08,
    "integrity_score": 0.92
  },
  "assets": {
    "image_url": "http://36.50.26.198:8000/outputs/product_USNL3900_90d4ed50.png",
    "filename": "product_USNL3900_90d4ed50.png",
    "local_path": "/root/joy-dnse/outputs/product_USNL3900_90d4ed50.png"
  }
}
```

### 3. Wire into agent

In `agent.py`, after `generate_product_mockup(...)` and before returning tool result:

```python
sync_result = post_mockup_created(payload, self.settings)
```

Add return fields:

```python
"sync_status": sync_result["status"],
"sync_error": sync_result.get("error", ""),
```

In final chat response:

```text
• Sync: sent / disabled / failed
```

Do not fail mockup creation if sync fails.

### 4. API endpoints in `main.py`

Add:

```text
POST /api/test-sync-webhook
```

Request body:

```json
{
  "webhook_url": "https://n8n.../webhook/burgermockup",
  "secret": "optional"
}
```

Sends event:

```json
{
  "event": "burgermockup.sync_test",
  "version": "1.0",
  "source": "burgermockup-web",
  "created_at": "..."
}
```

Expected n8n response:

```json
{"ok": true}
```

UI displays:

```text
Success: webhook responded 200
Error: timeout / 401 / invalid URL
```

---

## Lark Base Setup via CLI

### Base name

```text
BurgerMockup Sync
```

### Main table

```text
Mockup_Records
```

### Fields

Use simple field types first. Avoid URL field conversion issues initially; store URLs as text unless verified.

Required fields:

```text
Mockup_ID          text, primary if possible
Created_At         datetime
Status             select: synced, error, pending
Product_ID         text
Product_Name       text
Color              text
Scene              text
Raw_User_Input     text
Provider           text
Model              text
Size               text
Width              number
Height             number
Generation_Time    number
Cost_USD           number
Integrity_Score    number
Image_URL          text
Filename           text
Local_Path         text
Source             text
Error_Message      text
```

Optional later:

```text
Lark_File_URL      text
Lark_File_Token    text
Base_Record_URL    text
```

### CLI command strategy

Use lark-cli shortcuts, not raw API.

Rough sequence:

```bash
# 1. create base
lark-cli base +base-create --name "BurgerMockup Sync" --format json

# 2. list tables / get default table id
lark-cli base +table-list --base-token <base_token> --format json

# 3. rename/create table if needed
# if default table exists, update name if shortcut available; otherwise create new table

# 4. create fields
lark-cli base +field-create --base-token <base_token> --table-id <table_id> --json '{"name":"Mockup_ID","type":"text"}'
lark-cli base +field-create --base-token <base_token> --table-id <table_id> --json '{"name":"Status","type":"select","options":[{"name":"synced"},{"name":"error"},{"name":"pending"}]}'
lark-cli base +field-create --base-token <base_token> --table-id <table_id> --json '{"name":"Created_At","type":"datetime"}'
...
```

If `+base-create`/table shortcuts differ locally, inspect:

```bash
lark-cli base --help
lark-cli base +field-create --help
```

Important pitfall:

- Do not use URL type at first for `Image_URL`; use text to avoid `URLFieldConvFail`.
- Verify field creation with:

```bash
lark-cli base +field-list --base-token <base_token> --table-id <table_id>
```

---

## n8n Workflow via MCP/API

### Workflow shape

```text
Webhook Trigger
→ Code node: validate secret + normalize payload
→ IF node: event == mockup.created or sync_test
→ Lark Base node / HTTP Request to Lark API: create record
→ Respond to Webhook
```

### Minimal n8n workflow nodes

1. `Webhook`
   - Method: POST
   - Path: `burgermockup-sync`
   - Response mode: response node

2. `Code: Validate + Normalize`
   - Read header `x-burgermockup-secret`
   - Compare to configured n8n env/credential/static secret
   - Normalize fields into Lark record fields

3. `IF: Sync Test`
   - If `event == "burgermockup.sync_test"`, respond `{ok:true, event:"sync_test"}` without writing.

4. `HTTP Request: Lark Base Create Record`
   - POST:

```text
/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records
```

   - Auth: Lark app token or credential in n8n.
   - Body:

```json
{
  "fields": {
    "Mockup_ID": "={{$json.mockup_id}}",
    "Created_At": "={{$json.created_at}}",
    "Status": "synced",
    "Product_ID": "={{$json.product.id}}",
    "Product_Name": "={{$json.product.name}}",
    "Color": "={{$json.product.color}}",
    "Scene": "={{$json.prompt.scene}}",
    "Raw_User_Input": "={{$json.prompt.raw_user_input}}",
    "Provider": "={{$json.generation.provider}}",
    "Model": "={{$json.generation.model}}",
    "Size": "={{$json.generation.size}}",
    "Width": "={{$json.generation.width}}",
    "Height": "={{$json.generation.height}}",
    "Generation_Time": "={{$json.generation.seconds}}",
    "Cost_USD": "={{$json.generation.cost_usd}}",
    "Integrity_Score": "={{$json.generation.integrity_score}}",
    "Image_URL": "={{$json.assets.image_url}}",
    "Filename": "={{$json.assets.filename}}",
    "Local_Path": "={{$json.assets.local_path}}",
    "Source": "={{$json.source}}"
  }
}
```

5. `Respond to Webhook`

Success:

```json
{
  "ok": true,
  "status": "synced",
  "record_id": "={{$json.data.record.record_id}}"
}
```

Error path:

```json
{
  "ok": false,
  "status": "error",
  "error": "..."
}
```

### Use MCP n8n tools

Implementation phase should use:

```text
mcp_n8n_create_workflow
mcp_n8n_validate_workflow_structure
mcp_n8n_validate_workflow_expressions
mcp_n8n_activate_workflow
mcp_n8n_trigger_webhook
mcp_n8n_list_executions
```

Before any update to existing workflow:

```text
mcp_n8n_backup_workflow
```

For new workflow:

```text
mcp_n8n_create_workflow(name="BurgerMockup → Lark Base Sync", nodes=[...], connections={...})
```

Need exact node schemas from:

```text
mcp_n8n_get_node_schema("n8n-nodes-base.webhook")
mcp_n8n_get_node_schema("n8n-nodes-base.code")
mcp_n8n_get_node_schema("n8n-nodes-base.httpRequest")
mcp_n8n_get_node_schema("n8n-nodes-base.respondToWebhook")
```

---

## Implementation Steps

### Phase 1 — Web config only

Files:

```text
static/index.html
config_store.py
settings.json
main.py
```

Tasks:

1. Add `Sync` tab to Settings.
2. Add inputs for enabled/webhook/secret/send_image/timeout.
3. Save/load keys via `/api/settings`.
4. Add `/api/test-sync-webhook` endpoint.
5. Test with a temporary webhook.site or n8n test webhook.

Validation:

```text
Open web → Settings → Sync → paste URL → Test Sync → Success
settings.json persists values
```

### Phase 2 — Sync module

Files:

```text
sync_webhook.py
agent.py
mockup_engine.py maybe unchanged
```

Tasks:

1. Build payload helper.
2. POST to configured n8n URL.
3. Add sync result to tool response.
4. Add sync line to final chat response.

Validation:

```text
Generate mockup → webhook receives mockup.created payload
Image_URL is public and reachable
Failure does not block image generation
```

### Phase 3 — Lark Base creation via CLI

Tasks:

1. Create Base `BurgerMockup Sync`.
2. Create/rename table `Mockup_Records`.
3. Create fields above.
4. Insert one test record manually via `lark-cli base +record-batch-create`.
5. Verify record appears in Base UI.

Validation:

```bash
lark-cli base +record-list --base-token <base> --table-id <table> --limit 5
```

### Phase 4 — n8n workflow via MCP

Tasks:

1. Inspect node schemas.
2. Create workflow `BurgerMockup → Lark Base Sync`.
3. Add webhook path `burgermockup-sync`.
4. Add validation/normalize Code node.
5. Add HTTP request to Lark Base Create Record.
6. Add response node.
7. Activate workflow.
8. Test via `/api/test-sync-webhook`.
9. Test via real mockup generation.

Validation:

```text
n8n execution success
Lark Base new row created
Web UI response shows Sync: sent
```

### Phase 5 — README / 15-minute setup

Update README:

```text
1. git clone
2. cp .env.example .env
3. pip install -r requirements.txt
4. python main.py
5. open http://localhost:8000
6. add Gemini + BP keys
7. optional: paste n8n webhook URL under Settings → Sync
8. generate mockup
```

Add optional Lark/n8n setup section:

```text
Use included n8n workflow template OR create via n8n import.
Webhook URL goes into web config.
No Lark secrets are needed inside BurgerMockup app.
```

---

## Risks / Tradeoffs

### Risk 1 — Image URL not public

If app runs locally, n8n cannot fetch `http://localhost:8000/outputs/...`.

Mitigations:

- For local demo: use ngrok/cloudflared/public server.
- In payload include both `image_url` and `local_path`.
- For production: require `PUBLIC_BASE_URL` config.

### Risk 2 — n8n auth to Lark

n8n needs Lark app credentials or a preconfigured Lark node/credential.

Mitigation:

- Keep Lark auth entirely in n8n.
- App only needs webhook URL.
- README separates app setup from n8n admin setup.

### Risk 3 — Webhook abuse

Webhook URL could be called by anyone.

Mitigation:

- `X-BurgerMockup-Secret` header.
- n8n Code node rejects if secret mismatch.

### Risk 4 — Base field type mismatch

Lark Base URL/date fields can fail conversion.

Mitigation:

- Start with text fields for URLs and ISO date string if datetime causes issues.
- Upgrade types later after verified.

### Risk 5 — Sync latency

n8n/Lark could slow user response.

Mitigation:

- Do not block image return on sync failure.
- Timeout 10s default.
- Future: background queue/retry.

---

## Open Questions

1. Do we want Base created in anh Hiếu's current Lark tenant now, or produce reusable CLI script for any user?
2. Should n8n upload image to Lark Drive, or only store public image URL first?
3. Should record be create-only or upsert by `Mockup_ID`?
4. Should sync trigger for Telegram outputs too? Recommended: yes, same agent path.
5. Should web UI show sync status inline under each mockup? Recommended: yes.

---

## Recommended Build Order

Do in this exact order:

```text
1. Web Settings → Sync config
2. /api/test-sync-webhook
3. sync_webhook.py + agent hook
4. Lark Base via CLI
5. n8n workflow via MCP
6. Real end-to-end test
7. README 15-min setup
```

Reason: user-facing config is the product surface; Lark/n8n wiring can then plug into a stable payload contract.
