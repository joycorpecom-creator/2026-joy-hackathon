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


DEMO_DESIGN_URL = "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/03/d94aeb361c70821e0331500fc3cc0353.png"
DEMO_MOCKUP_URL = "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/03/d94aeb361c70821e0331500fc3cc0353.png"


class BurgerPrintsClient:
    """BurgerPrints API v2 client.

    Docs source: https://api-docs.burgerprints.com/ (Postman collection)
    Auth: header `api-key`.
    """

    def __init__(self):
        try:
            from config_store import load_settings
            cfg = load_settings()
        except Exception:
            cfg = {}
        self.api_key = (cfg.get("burgerprints_api_key") or os.getenv("BURGERPRINTS_API_KEY", "")).strip()
        self.base_url = (cfg.get("burgerprints_base_url") or os.getenv("BURGERPRINTS_BASE_URL", "https://api.burgerprints.com/v2")).rstrip("/")

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

    # Auth / account
    def authenticated(self) -> Dict[str, Any]:
        return self._request("GET", "/authenticated")

    def balance(self) -> Dict[str, Any]:
        return self._request("GET", "/balance")

    # Orders
    def list_orders(
        self,
        *,
        sandbox: Optional[bool] = None,
        reference: str = "",
        store_id: str = "",
        state: str = "",
        start_date: str = "",
        end_date: str = "",
        page: int = 1,
        page_size: int = 10,
    ) -> Dict[str, Any]:
        params = {"page": page, "page_size": page_size}
        if sandbox is not None:
            params["sandbox"] = str(sandbox).lower()
        if reference:
            params["reference"] = reference
        if store_id:
            params["store_id"] = store_id
        if state:
            params["state"] = state
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self._request("GET", "/order", params=params)

    def get_order(self, order_id: str) -> Dict[str, Any]:
        if order_id.upper().startswith("DEMO"):
            print(f"BP DEMO FALLBACK order={order_id}", flush=True)
            return self._demo_order(order_id)

        # 1) Direct BurgerPrints order id path from docs.
        try:
            payload = self._request("GET", f"/order/{order_id}")
            data = payload.get("data", payload) if isinstance(payload, dict) else payload
            if isinstance(data, dict) and data:
                return data
        except Exception as e:
            print(f"BP direct order miss: {e}", flush=True)

        # 2) Seller-facing reference fallback, live then sandbox.
        for sandbox in (False, True):
            payload = self.list_orders(reference=order_id, sandbox=sandbox, page_size=10)
            rows = self._rows(payload)
            if rows:
                return rows[0]
        raise RuntimeError(f"Order not found via BurgerPrints API: {order_id}")

    def tracking(self, order_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/order/{order_id}/tracking")

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        return self._request("PUT", f"/order/{order_id}/cancel")

    def delete_order(self, order_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/order/{order_id}")

    def charge_order(self, order_ids: List[str]) -> Dict[str, Any]:
        return self._request("POST", "/order/charge", json={"order_ids": order_ids})

    # Product/catalog
    def products(self, page: int = 1, page_size: int = 10, search: str = "") -> Dict[str, Any]:
        params = {"page": page, "page_size": page_size}
        if search:
            params["search"] = search
        return self._request("GET", "/product", params=params)

    def product(self, product_id_or_short_code: str) -> Dict[str, Any]:
        return self._request("GET", f"/product/{product_id_or_short_code}")

    def out_of_stock(self) -> Dict[str, Any]:
        return self._request("GET", "/product/outofstock")

    def add_webhook(self, end_point_url: str, is_active: bool = True) -> Dict[str, Any]:
        url = "https://api.burgerprints.com/notification/api/v1/public/fulfillment/notify/webhook"
        return self._request("POST", url, json={"end_point_url": end_point_url, "is_active": is_active})

    # Helpers
    def _rows(self, payload: Any) -> List[Dict[str, Any]]:
        data = payload.get("data", payload) if isinstance(payload, dict) else payload
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("data", "result", "items", "orders"):
                if isinstance(data.get(key), list):
                    return data[key]
        return []

    def extract_first_asset(self, order_id: str) -> OrderAsset:
        data = self.get_order(order_id)
        item = (data.get("items") or data.get("line_items") or [])[0]

        designs = item.get("designs") or []
        mockups = item.get("mockups") or []
        design_url = (
            (designs[0].get("src") if designs else None)
            or item.get("design_front_url")
            or item.get("design_url_front")
            or item.get("design_url")
        )
        mockup_url = (
            (mockups[0].get("src") if mockups else None)
            or item.get("mockup_front_url")
            or item.get("mockup_url_front")
            or item.get("mockup_url")
        )
        if not design_url:
            raise RuntimeError(f"Order has no design URL: {order_id}")

        return OrderAsset(
            order_id=order_id,
            product_name=item.get("name") or item.get("product_name") or item.get("catalog_sku") or "Unknown product",
            color_name=item.get("color_name") or item.get("color") or "Unknown",
            color_hex=item.get("color_value") or item.get("color_hex") or "#ffffff",
            design_url=design_url,
            mockup_url=mockup_url,
            product_id=item.get("product_id") or item.get("catalog_sku") or item.get("short_code"),
        )

    def find_order_id(self, text: str) -> str:
        m = re.search(r"(?:order\s*)?(DEMO[-_]?\d+|BP[-_]?\d+|ORD[-_]?\d+|A\d{4,}-[A-Z]{2}-\d+)", text, re.I)
        if m:
            return m.group(1)
        m = re.search(r"(?:order\s*)?([A-Za-z0-9][A-Za-z0-9_-]{5,})", text, re.I)
        return m.group(1) if m else "DEMO-1001"

    def _demo_order(self, order_id: str) -> Dict[str, Any]:
        return {
            "id": order_id,
            "items": [{
                "name": "Unisex T-shirt | Gildan 5000 (US Label) - Black - S",
                "product_id": "USG5000",
                "color_value": "#25282A",
                "color_name": "Black",
                "designs": [{"type": "front", "src": DEMO_DESIGN_URL, "resolution": "4200x4800"}],
                "mockups": [{"type": "front", "src": DEMO_MOCKUP_URL}],
            }],
        }
