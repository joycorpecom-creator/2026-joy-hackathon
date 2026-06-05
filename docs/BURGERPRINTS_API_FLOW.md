# BurgerPrints API Flow for Joy Agent

## Core truth
- Base URL: `https://api.burgerprints.com/v2`
- Auth: header `api-key`
- First health check: `GET /authenticated`
- Product endpoints = BP catalog/base products only.
- Order endpoints = seller/order data; order item may expose seller design URLs + BP-rendered mockups.
- Demo fallback allowed only for explicit `DEMO-*`.

## Product catalog flow

### User intent examples
- "get product USG5000"
- "lấy ảnh sản phẩm Gildan 5000"
- "cho xem product Next Level 3900"

### Logic
1. If exact catalog short_code (`USG5000`, `USNL3900`, `EUAPHS`) → `GET /product/{short_code}`.
2. If numeric/model fragment (`5000`, `3900`, `18500`) → NEVER call `/product/{number}`.
3. Load catalog via `GET /product?page=1&page_size=500`.
4. Fuzzy match by:
   - exact short_code
   - short_code prefix
   - display_name substring
   - word-boundary model number
5. Then call `GET /product/{resolved_short_code}`.
6. Return structured payload with image:
   - `type=product`
   - `content`
   - `image`
   - `meta.code/name/url`

## Product ID traps

### Catalog short_code (valid for `/product/{id}`)
Examples:
- `USG5000`
- `USG5000B`
- `USNL3900`
- `EUAPHS`

### Seller dashboard product id (NOT valid)
Examples:
- `A60992-1`
- dashboard URLs: `/admin/products/A60992-*`

Do not call `/v2/product/A60992-*`. Ask for:
- uploaded design file
- BP catalog base product short_code/name
- scene prompt

## Order lookup flow

### User intent examples
- "get order BP-xxx"
- "tạo mockup order ORD-xxx cafe"
- "tracking order ..."

### Logic
1. Extract only explicit order-like IDs:
   - `DEMO-*`
   - `BP-*`
   - `ORD-*`
   - `A####-CT-#`
2. Try `GET /order/{id}`.
3. If fail/miss → `GET /order?reference={id}&sandbox=false`.
4. If fail/miss → `GET /order?reference={id}&sandbox=true`.
5. If real order still not found → fail closed. No fake/demo.
6. `DEMO-*` only → demo fallback OK.

## Order asset extraction

From order first item, inspect:
- `items[]` or `line_items[]`
- `designs[].src`
- `mockups[].src`
- fallback fields: `design_front_url`, `design_url_front`, `design_url`, `mockup_front_url`, `mockup_url_front`, `mockup_url`

Return:
- `product_name`
- `color_name` / `color`
- `color_hex`
- `design_url`
- `mockup_url`
- `product_id` / `catalog_sku` / `short_code`

## Mockup creation flows

### A) Uploaded design + BP catalog product
Best competition flow.

Input:
- current uploaded print design in session
- product name/code
- scene prompt

Steps:
1. Resolve product via catalog fuzzy search.
2. `GET /product/{short_code}`.
3. Pick BP base mockup/product image from `url`/base image fields.
4. Generate lifestyle scene using design + product image.
5. Composite/preserve original design; SSIM gate.
6. Return `type=mockup` with `image`, provider, integrity, size, cost, time.

### B) Product-only mockup
Input:
- product name/code
- scene prompt
- no uploaded design, no order

Steps:
1. Resolve catalog product.
2. Use BP base mockup image.
3. Generate lifestyle product mockup.
4. Return image.

### C) Order ID mockup
Input:
- order ID
- scene prompt

Steps:
1. Resolve order via lookup sequence.
2. Extract design/mockup assets from order item.
3. Prefer BP-rendered `mockup_url` as source image when available.
4. Generate lifestyle mockup from the real order asset.
5. Return image.

## Routing priority
1. Destructive order actions: cancel/delete/charge → require explicit confirmation.
2. Auth/balance/out-of-stock/tracking.
3. Order ID + mockup intent → `create_mockup_from_order`.
5. Product + mockup intent, no design/order → `create_mockup_from_product`.
6. Product view/info intent only → product lookup.
7. Otherwise free chat/clarify.

## Color rule
Never default missing `color_name` to Black.
Use:
`color_name or color or "as shown in the attached BP product image"`

## Output style
- Vietnamese.
- Start with `Dạ anh`.
- Image must be real image payload, not markdown image text.
- For product lookup: product image first + compact code/name.
- For mockup: image + scene/size/time/cost/provider/integrity.
