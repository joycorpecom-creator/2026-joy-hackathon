# BurgerMockup — Project Spec for Hermes Agent

## 1. Challenge Summary

Sponsor: BurgerPrints

Project: BP2 — BurgerMockup, AI Lifestyle Mockup Engine

One-liner:

> From a flat design to a story customers want to live in. Let the agent be the photographer, stylist, and art director.

Goal: Build a conversational AI mockup agent that turns a seller's flat 2D print design plus a BurgerPrints catalog product into high-quality lifestyle mockups ready for ecommerce listings.

## 2. Problem

Default POD mockups are often plain: white background, hanger, flat product view. These do not sell well on Etsy/Amazon/TikTok Shop/Shopify.

Sellers need many lifestyle mockups for 50–500+ listings but current options are expensive or repetitive:

- Placeit: subscription, template-heavy
- Designer: expensive per product
- Photoshop: slow manual workflow

## 3. Target User

POD sellers using BurgerPrints who have 50–500+ listings and need fast, high-quality lifestyle mockups without hiring a designer.

## 4. Required Input

The intended product workflow is:

```txt
1. Design file
   - PNG/JPG/SVG
   - transparent or colored background
   - text-heavy, complex color, or AOP designs must be handled

2. Target BurgerPrints catalog product
   - Must come from BurgerPrints API v2.0 Product catalog
   - Example short_codes: USG5000, USBC3200, EUAPHS
   - Use API for product info, colors/sizes, print area, design_type, base image/url

3. Natural-language scene prompt
   - Vietnamese or English
   - model / background / lighting / mood / niche / market

4. Multi-turn refinement
   - User can say: change model, change niche, create 5 variants, apply to multiple products
```

## 5. Expected Output

- Lifestyle mockup image ready for listing
- Output size: >= 1500×1500 px
- Design integrity:
  - Flat mockup SSIM > 0.92
  - Lifestyle mockup SSIM > 0.85
- Multiple scene variants
- Metadata:
  - prompt
  - product id/name/color
  - model/provider
  - time
  - cost estimate
  - integrity score
- Bonus:
  - apply one design to multiple products
  - persona / customer avatar library
  - Shopify/Etsy publish
  - brand consistency presets

## 6. Must-have Requirements

- Must use BurgerPrints API v2.0
  - product info
  - print area coordinates
  - base mockups/product images
- Must be a conversational agent
  - not only a static upload form
- Setup <= 15 minutes
- UI must display generated images
- Output >= 1500×1500 px
- No real brand logos
- No celebrity faces

## 7. Important BurgerPrints API Interpretation

BurgerPrints API v2 Product docs expose catalog/base products only:

```txt
GET /v2/product
GET /v2/product/{id}
```

`{id}` means catalog product short_code, for example:

```txt
USG5000
USBC3200
EUAPHS
UKTSBC8800
```

It does NOT mean the seller dashboard product id from URLs like:

```txt
https://dash.burgerprints.com/admin/products/A60992-1
```

`A60992-1` is a seller-created/dashboard product id. Public Product API v2 does not document a direct endpoint for it.

Correct agent behavior:

```txt
If user provides catalog short_code
→ call /v2/product/{short_code}

If user provides dashboard product URL/id like A60992-1
→ classify as seller-created product id
→ do NOT call /v2/product/A60992-1
→ ask user for design file + catalog/base product short_code
```

## 8. Correct Product Strategy

For this competition, the app should NOT require the seller to pre-create a finished BurgerPrints product with print file attached.

Correct challenge interpretation:

```txt
User brings the design file separately.
User selects/mentions target product from BurgerPrints API catalog.
Agent generates the mockup.
```

So the required flow is:

```txt
Design file upload
+ BurgerPrints catalog product short_code
+ scene prompt
→ agent calls BP Product API
→ agent uses product info/print area/base mockup
→ agent generates lifestyle mockup with design preserved
```

Do not rely on a pre-created BP dashboard product like `A60992-1` because Product API v2 does not retrieve that object.

## 9. Recommended Generation Pipeline

Best architecture is hybrid, not pure AI redraw:

```txt
1. Read target product from BurgerPrints API
2. Read print area / product base image / color
3. Generate or select lifestyle scene/product mockup
4. Composite original design file deterministically into print area
5. Apply perspective/warp/shadow/lighting to match scene
6. Run design integrity check
7. If SSIM below threshold, regenerate or re-composite
8. Return final >=1500×1500 image
```

Why hybrid:

```txt
Pure Gemini/Flux redraw can mutate text/logo/detail.
Composite preserves the original design pixels.
```

Minimum viable demo can use Gemini to generate a convincing mockup, but final scoring should emphasize original-design composite.

## 10. Current Prototype Flow

Current implementation:

```txt
User prompt
→ agent detects product short_code
→ BurgerPrints API /v2/product/{short_code}
→ Gemini image generation
→ local PNG saved in outputs/
→ upload to imgbb for HTTPS preview URL
→ upload local PNG to Lark media
→ POST n8n webhook
→ n8n creates Lark Base record + attachment
```

This proves:

- conversational agent
- BurgerPrints API usage
- image UI
- n8n/Base sync demo
- metadata tracking

Need next improvement:

```txt
Add first-class design upload + deterministic composite pipeline.
```

## 11. Agent Brain Rules

The agent should reason like this:

### User mentions product code

```txt
USG5000 / USBC3200 / EUAPHS / similar short_code
→ call BP /v2/product/{code}
→ use returned product info
```

### User mentions dashboard product URL

```txt
https://dash.burgerprints.com/admin/products/A60992-1
→ identify as dashboard product id
→ explain API limitation
→ ask for design file and base product short_code
```

### User uploads design but no product

```txt
Ask: Which BurgerPrints product should I use? Example: USG5000, USBC3200, EUAPHS.
```

### User gives product but no design

```txt
Ask for design PNG/JPG/SVG.
Offer demo placeholder only if user wants quick preview.
```

### User asks for multiple variants

```txt
Keep same design/product.
Generate scene variants.
Track each prompt/time/cost.
```

### User asks refinement

```txt
Reuse prior design + product + generation context.
Only change requested scene/model/lighting/niche.
```

## 12. Core Demo Scenarios

1. Single product lifestyle mockup

```txt
Upload cat design PNG.
Use product USG5000.
Create cozy cafe girl lifestyle mockup, warm morning light.
```

2. Multiple scene variants

```txt
Create 5 variants: cafe girl, streetwear, cozy living room, flat-lay with accessories, outdoor picnic.
```

3. Multi-turn refinement

```txt
That mockup is nice, but the model doesn't fit yoga/wellness. Switch to a middle-aged woman in a yoga studio at sunrise.
```

4. Edge cases for finals

```txt
Text-heavy design
AOP product
multi-print product
complex colors
```

## 13. Deliverables

- GitHub repo
- README with:
  - setup <= 15 min
  - architecture
  - product/design integrity strategy
  - pipeline
  - >=10 sample mockups with prompt/time/cost
- 3–5 min demo video
- Slide deck
- optional live demo
- optional Shopify/Etsy publish flow

## 14. Immediate Next Engineering Tasks

1. Add design upload to chat/UI.
2. Store uploaded design as current conversation state.
3. Add agent tool: `select_product(short_code)` using BP `/v2/product/{id}`.
4. Add agent tool: `generate_mockup(design_file, product_short_code, scene_prompt)`.
5. Add composite pipeline:
   - locate print area from BP product response
   - fit design into print area
   - preserve original pixels
   - optional warp/shadow
6. Add SSIM/design integrity metric.
7. Add variant generation with shared context.
8. Improve router to distinguish catalog product short_code vs dashboard product id.

## 15. Final Answer to Product Ownership Question

The seller should prepare/upload the print design file separately, then choose the target BurgerPrints catalog product.

The agent should create the mockup.

The seller does not need to first create a finished product with print file inside BurgerPrints dashboard.

Reason:

```txt
Competition input explicitly says: Design file + target product from BurgerPrints API catalog + scene prompt.
BurgerPrints Product API v2 reads catalog products, not seller-created dashboard products.
```

Therefore the correct system design is:

```txt
User upload design file
→ User choose BP catalog product
→ Agent call BP Product API
→ Agent generate/composite lifestyle mockup
```

Not:

```txt
User create dashboard product A60992-1 first
→ Agent fetch A60992-1 from /v2/product
```

That route fails because `A60992-1` is not a catalog short_code.
