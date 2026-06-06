import os
import re
import requests
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class OrderAsset:
    order_id: str
    product_name: str
    color_name: str
    color_hex: str
    design_url: str
    mockup_url: Optional[str]
    product_id: Optional[str]
    product_type: str = ""
    product_types: Optional[List[str]] = None


DEMO_DESIGN_URL = "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/03/d94aeb361c70821e0331500fc3cc0353.png"
DEMO_MOCKUP_URL = "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/03/d94aeb361c70821e0331500fc3cc0353.png"


class BurgerPrintsClient:
    """BurgerPrints/BurgerShop v1 product client.

    Runtime focus: seller products via BurgerShop v1 public product API.
    Auth: header `api-key`.
    """

    def __init__(self):
        try:
            from config_store import load_settings
            cfg = load_settings()
        except Exception:
            cfg = {}
        self.api_key = (cfg.get("burgerprints_api_key") or os.getenv("BURGERPRINTS_API_KEY", "")).strip()
        self.base_url = (cfg.get("burgerprints_base_url") or os.getenv("BURGERPRINTS_BASE_URL", "https://api.burgerprints.com/v1")).rstrip("/")

    def _headers(self) -> Dict[str, str]:
        if not self.api_key or "..." in self.api_key or "***" in self.api_key:
            raise RuntimeError("BurgerPrints API key missing/corrupted. Save full key in Settings.")
        return {"api-key": self.api_key}

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        print(f"BP API HIT {method.upper()} {url}", flush=True)
        res = requests.request(method, url, headers=self._headers(), timeout=40, **kwargs)
        res.raise_for_status()
        try:
            payload = res.json()
        except Exception:
            return {"status": res.status_code, "text": res.text}
        if isinstance(payload, dict) and payload.get("code") not in (None, 200, "200"):
            raise RuntimeError(payload)
        return payload

    # ── Auth / account ──

    def authenticated(self) -> Dict[str, Any]:
        return self._request("GET", "/authenticated")

    def balance(self) -> Dict[str, Any]:
        return self._request("GET", "/balance")

    # ── BurgerShop seller products (v1 public product API) ──

    def bs_products(self, page: int = 1, page_size: int = 10, search: str = "") -> Dict[str, Any]:
        params = {"page": page, "page_size": page_size}
        if search:
            params["search"] = search
        url = "https://api.burgershop.io/product/api/v1/public/products"
        return self._request("GET", url, params=params)

    def bs_product(self, product_id: str) -> Dict[str, Any]:
        pid = (product_id or "").strip()
        if not pid:
            raise RuntimeError("Missing BurgerShop seller product id")
        url = f"https://api.burgershop.io/product/api/v1/public/products/{pid}"
        return self._request("GET", url)

    def bs_update_product(self, product_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        pid = (product_id or "").strip()
        if not pid:
            raise RuntimeError("Missing BurgerShop seller product id")
        url = f"https://api.burgershop.io/product/api/v1/public/products/{pid}"
        return self._request("PUT", url, json=payload)

    def bs_append_mockup_to_product(self, product_id: str, image_url: str, image_id: str = "") -> Dict[str, Any]:
        """Safely append a generated mockup URL to product.mockups via GET→merge→PUT.

        BurgerShop v1 update product requires a broad product body; never send a tiny partial body.
        """
        pid = (product_id or "").strip()
        url = (image_url or "").strip()
        if not pid:
            raise RuntimeError("Missing product_id")
        if not url.startswith(("http://", "https://")):
            raise RuntimeError("image_url must be public http/https URL")
        detail = self.bs_product(pid)
        data = detail.get("data", detail) if isinstance(detail, dict) else {}
        if not isinstance(data, dict) or not data:
            raise RuntimeError(f"Product not found: {pid}")
        payload = dict(data)
        mockups = [dict(m) for m in (payload.get("mockups") or []) if isinstance(m, dict)]
        base = dict(mockups[0]) if mockups else {
            "media_type": "image", "host": "", "source": "generate", "thumbnail_url": None, "video_id": ""
        }
        next_pos = max([int(m.get("position") or 0) for m in mockups] + [-1]) + 1
        mockup_id = image_id or f"joy{int(__import__('time').time())}"
        new_mockup = dict(base)
        new_mockup.update({"id": mockup_id, "position": next_pos, "src": url, "source": "joy_agent"})
        mockups.append(new_mockup)
        payload["mockups"] = mockups
        # The docs body includes collections; keep list shape if absent.
        payload.setdefault("collections", data.get("collections") or [])
        result = self.bs_update_product(pid, payload)
        # BurgerShop may rewrite mockup id on save; verify by GET.
        verified = self.bs_product(pid).get("data", {})
        saved = next((m for m in (verified.get("mockups") or []) if isinstance(m, dict) and m.get("src") == url), {})
        return {"ok": True, "product_id": pid, "image_url": url, "mockup_id": saved.get("id") or mockup_id, "position": saved.get("position", next_pos), "result": result, "verified": bool(saved)}

    def extract_first_seller_product_asset(self, product_id: str) -> OrderAsset:
        payload = self.bs_product(product_id)
        data = payload.get("data", payload) if isinstance(payload, dict) else {}
        if not isinstance(data, dict) or not data:
            raise RuntimeError(f"Seller product not found: {product_id}")
        designs = data.get("designs") or []
        mockups = data.get("mockups") or []
        variants = data.get("variants") or []
        product_types_raw = data.get("product_types") or []
        product_type_names = []
        for pt in product_types_raw:
            if isinstance(pt, dict):
                name = pt.get("name") or pt.get("title") or pt.get("type") or ""
                if name:
                    product_type_names.append(str(name))
            elif pt:
                product_type_names.append(str(pt))
        product_type = data.get("product_type") or (product_type_names[0] if product_type_names else "")
        first_variant = variants[0] if variants and isinstance(variants[0], dict) else {}
        design = designs[0] if designs and isinstance(designs[0], dict) else {}
        mockup = mockups[0] if mockups and isinstance(mockups[0], dict) else {}
        design_url = design.get("src") or data.get("design_url") or data.get("mockup_url") or ""
        mockup_url = (mockup.get("src") or first_variant.get("mockup_url")
                      or data.get("mockup_url") or data.get("generated_mockup_url") or design_url)
        if not (design_url and mockup_url):
            raise RuntimeError(f"Seller product has no design/mockup URL: {product_id}")
        return OrderAsset(
            order_id=product_id,
            product_name=data.get("title") or first_variant.get("short_code_name") or product_id,
            color_name=first_variant.get("color_name") or "as shown in seller product mockup",
            color_hex=first_variant.get("color_value") or "#ffffff",
            design_url=design_url or mockup_url,
            mockup_url=mockup_url or design_url,
            product_id=product_id,
            product_type=product_type,
            product_types=product_type_names,
        )

    # ── Webhook ──

    def out_of_stock(self) -> Dict[str, Any]:
        return self._request("GET", "/product/outofstock")

    def add_webhook(self, end_point_url: str, is_active: bool = True) -> Dict[str, Any]:
        url = "https://api.burgerprints.com/notification/api/v1/public/fulfillment/notify/webhook"
        return self._request("POST", url, json={"end_point_url": end_point_url, "is_active": is_active})
