# PRODUCT_SPEC.md — JOY-DNSE Mockup Studio

## Product identity

JOY-DNSE Mockup Studio is a web app for generating ecommerce-ready lifestyle mockups from BurgerShop/BurgerPrints seller products.

## Primary users

- POD seller/operator
- Marketplace listing creator
- Product marketing reviewer

## Core flow

1. User asks for product list or specific product detail.
2. System fetches seller-product data from BurgerShop/BurgerPrints v1.
3. Product images/design refs are extracted and shown.
4. User requests a scene/style.
5. System builds a structured creative brief.
6. System compiles image prompt with product preservation rules.
7. System generates mockup image.
8. Optional: upload image, append to product mockups, sync event.

## Supported commands

```txt
lấy toàn bộ sản phẩm
xem sản phẩm A53636-28
xem chi tiết sản phẩm A53636-28
tạo 1 ảnh product A53636-28 phong cách cafe chạy luôn
tạo mockup cho sản phẩm thứ 2 phong cách beach sunset
đổi cảnh ảnh vừa rồi sang office lifestyle
```

## Supported product APIs

- `GET /seller/products`
- seller-product detail endpoint (v1)
- seller-product update/append mockup flow when enabled

## Non-goals

- No order ID flow
- No `/v2/order` flow
- No shipping/tracking/cancel APIs
- No catalog short_code mapping as seller-product ID

## Quality rules

- Final image: at least `1500×1500`, normally `1600×1600`.
- Product print/design must remain recognizable.
- Scene must match product type physics.
- No extra logos/brands.
- No celebrity faces.
- Default human model direction: 24–50, mature/professional/expressive, face optional, crop torso/body language preferred.

## Product categories

Prompt library contains deterministic templates for:

- apparel t-shirt
- apparel hoodie
- tumbler
- mug
- poster
- canvas
- phone case
- tote
- pillow
- blanket
- sticker
- notebook
- default fallback

## Runtime states

- session memory: current product, last product list, latest mockup
- bulk jobs: status + per-item retry state
- product refs: seller product ID, product_type, preview/mockup images

## Acceptance checklist

- Product list returns enough info and saves `last_product_list`.
- “sản phẩm thứ N” resolves from last list.
- Product detail returns product URL/image URLs when API data contains them.
- Mockup creates a visible generated image.
- Cost is displayed when returned by API.
- Telegram/web UI return product/mockup links correctly.
- Tests pass.
