import re
from typing import Dict, Any, List, Optional

from burgerprints import BurgerPrintsClient
from mockup_engine import generate_mockup


# In-memory product cache for fuzzy search
_product_cache: Optional[List[Dict[str, Any]]] = None


def _get_product_cache(bp: BurgerPrintsClient) -> List[Dict[str, Any]]:
    global _product_cache
    if _product_cache is None:
        try:
            p = bp.products(page_size=500)
            _product_cache = p.get("data", {}).get("result", [])
        except Exception:
            _product_cache = []
    return _product_cache


def _fuzzy_find_product(name_or_code: str, bp: BurgerPrintsClient) -> Optional[str]:
    """Search product list by partial name or code. Returns short_code or None."""
    q = name_or_code.lower().strip()
    if not q:
        return None
    products = _get_product_cache(bp)
    best = None
    best_score = 0
    for p in products:
        sc = (p.get("short_code") or "").lower()
        dn = (p.get("display_name") or p.get("name") or "").lower()
        # Exact short_code match
        if q == sc:
            return p.get("short_code")
        # Short_code starts with query
        if sc.startswith(q):
            score = 90 + len(q)
            if score > best_score:
                best, best_score = p.get("short_code"), score
        # Name contains query
        if q in dn:
            score = 80 + len(q)
            if score > best_score:
                best, best_score = p.get("short_code"), score
        # Word boundary match (e.g. "5000" in "Gildan 5000")
        for word in dn.split():
            if word == q:
                score = 85 + len(q)
                if score > best_score:
                    best, best_score = p.get("short_code"), score
    return best


def _extract_product_search(text: str) -> str:
    """Extract a likely product name/ID from text when structured short_code not found."""
    # Try to extract a product identifier: "Gildan 5000B", "USG5000", "5000", etc.
    # Remove common wrapper words
    t = text.lower()
    for phrase in [
        "lấy hình ảnh product", "show product", "get product", "product này", "product",
        "với sản phẩm", "sản phẩm", "với product", "tạo ảnh mockup với", "tạo mockup với",
        "làm mockup với", "mockup với", "tạo ảnh", "tạo hình", "làm mockup", "mockup"
    ]:
        idx = t.find(phrase)
        if idx >= 0:
            t = t[idx + len(phrase):]
    # Extract what looks like a product name/number in quotes or after those keywords
    m = re.search(r'"([^"]+)"', t)
    if m:
        return m.group(1).strip()
    # Try code-like pattern
    m = re.search(r'\b([A-Z0-9]{2,8}[-_]?\d{2,5}[A-Z]?)\b', text, re.I)
    if m:
        return m.group(1).strip()
    # Fallback: take the remaining meaningful words
    words = [w for w in t.split() if len(w) > 1]
    if words:
        return " ".join(words[:3]).strip('",\' ')
    return ""


def _fmt_money(v):
    try:
        return f"${float(v):.2f}"
    except Exception:
        return str(v)


def _summarize_product_rows(rows: List[Dict[str, Any]], limit: int = 5) -> str:
    if not rows:
        return "No products found."
    lines = []
    for p in rows[:limit]:
        code = p.get("short_code") or p.get("shortCode") or p.get("catalog_sku") or "?"
        name = p.get("name") or p.get("shortCodeName") or p.get("display_name") or "Unknown"
        lines.append(f"- {code}: {name}")
    return "\n".join(lines)


def _summarize_order(order: Dict[str, Any]) -> str:
    oid = order.get("id") or order.get("order_id") or order.get("reference_order") or "?"
    state = order.get("state") or order.get("status") or "?"
    amount = order.get("amount") or order.get("total") or "?"
    items = order.get("items") or []
    item_line = ""
    if items:
        names = [i.get("name") or i.get("catalog_sku") or "item" for i in items[:3]]
        item_line = "\nItems: " + ", ".join(names)
    return f"Order: {oid}\nState: {state}\nAmount: {amount}{item_line}"


def detect_action(text: str) -> Dict[str, Any]:
    t = text.lower().strip()
    bp = BurgerPrintsClient()
    order_id = bp.find_order_id(text)

    # Strong intent keywords first.
    if any(k in t for k in ["auth", "xác thực", "test api", "kiểm tra api", "api ok"]):
        return {"action": "auth"}
    if any(k in t for k in ["balance", "số dư", "tiền", "credit"]):
        return {"action": "balance"}
    if any(k in t for k in ["tracking", "track", "vận đơn", "mã vận", "shipment"]):
        return {"action": "tracking", "order_id": order_id}
    if any(k in t for k in ["cancel", "huỷ", "hủy", "refund"]):
        return {"action": "cancel", "order_id": order_id}
    if any(k in t for k in ["delete", "xoá", "xóa"]):
        return {"action": "delete", "order_id": order_id}
    if any(k in t for k in ["charge", "thanh toán", "pay order"]):
        return {"action": "charge", "order_id": order_id}
    if any(k in t for k in ["out of stock", "hết hàng", "oos"]):
        return {"action": "out_of_stock"}
    wants_mockup = any(k in t for k in ["mockup", "scene", "lifestyle", "tạo ảnh", "tạo hình", "tạo mock", "làm mockup", "cafe", "streetwear", "studio", "outdoor"])

    if any(k in t for k in ["catalog", "product", "base", "sản phẩm", "sku"]):
        code = ""
        # Try structured short_code first: USG5000, G5000, 5000B, etc.
        m = re.search(r"\b([A-Z]{2,5}\d{3,5}[A-Z]?)\b", text, re.I)
        if m:
            code = m.group(1).upper()
        # Also try code-like: just numbers+optional letter (e.g. "5000", "5000B")
        if not code:
            m = re.search(r"\b(\d{3,5}[A-Z]?)\b", text)
            if m:
                code = m.group(1)
        # Product + mockup intent => create product mockup, not just product detail.
        if wants_mockup:
            # Numeric-only fragments like "3900" are not valid BP short_code; keep full text for fuzzy resolve.
            if code and code.isdigit():
                return {"action": "product_mockup", "product_id": "", "search": _extract_product_search(text)}
            return {"action": "product_mockup", "product_id": code, "search": _extract_product_search(text)}
        # If no structured code, or numeric-only fragment, use fuzzy catalog search.
        if not code or code.isdigit():
            return {"action": "product_search", "search": _extract_product_search(text)}
        return {"action": "product_detail", "product_id": code}

    # Mockup intent: order-like ID + scene/mockup/generate keywords.
    explicit_order = re.search(r"(DEMO[-_]?\d+|BP[-_]?\d+|ORD[-_]?\d+|A\d{4,}-[A-Z]{2}-\d+)", text, re.I)
    wants_order = "order" in t or "đơn" in t
    if explicit_order and wants_mockup:
        return {"action": "mockup", "order_id": explicit_order.group(1)}
    if explicit_order or wants_order:
        return {"action": "order", "order_id": order_id}
    if wants_mockup:
        # No explicit order but wants mockup → try extract product code
        code = ""
        m = re.search(r"\b([A-Z]{2,5}\d{3,5}[A-Z]?)\b", text, re.I)
        if m:
            code = m.group(1).upper()
        if not code:
            m = re.search(r"\b(\d{3,5}[A-Z]?)\b", text)
            if m:
                code = m.group(1)
        if code:
            if code.isdigit():
                return {"action": "product_mockup", "product_id": "", "search": _extract_product_search(text)}
            return {"action": "product_mockup", "product_id": code, "search": ""}
        search = _extract_product_search(text)
        if search:
            return {"action": "product_mockup", "product_id": "", "search": search}
    return {"action": "chat"}


async def run_action(text: str) -> Dict[str, Any]:
    bp = BurgerPrintsClient()
    route = detect_action(text)
    action = route["action"]

    try:
        if action == "auth":
            res = bp.authenticated()
            ok = res.get("data", {}).get("is_success")
            return {"type": "text", "content": f"Dạ, BurgerPrints API: {'OK rồi anh' if ok else 'có vấn đề'}"}

        if action == "balance":
            b = bp.balance()
            return {"type": "text", "content": "Dạ, số dư\n" + "\n".join(f"{k}: {_fmt_money(v)}" for k, v in b.items())}

        if action == "products":
            p = bp.products(page_size=5)
            data = p.get("data", {})
            rows = data.get("result", [])
            total = data.get("total", len(rows))
            return {"type": "text", "content": f"Dạ, danh mục có {total} sản phẩm\n" + _summarize_product_rows(rows)}

        if action == "product_detail":
            product_id = route["product_id"]
            try:
                p = bp.product(product_id)
            except Exception:
                resolved = _fuzzy_find_product(product_id, bp)
                if not resolved:
                    raise
                p = bp.product(resolved)
            d = p.get("data", p)
            name = d.get("display_name") or d.get("name") or "?"
            code = d.get("short_code") or route["product_id"]
            url = d.get("url") or d.get("image") or d.get("mockup_url") or ""
            return {
                "type": "product",
                "content": f"Dạ, thông tin sản phẩm {code}\n{name}",
                "image": url,
                "meta": {"code": code, "name": name, "url": url},
            }

        if action == "product_search":
            q = route.get("search") or ""
            resolved = _fuzzy_find_product(q, bp)
            if resolved:
                p = bp.product(resolved)
                d = p.get("data", p)
                name = d.get("display_name") or d.get("name") or "?"
                url = d.get("url") or d.get("image") or d.get("mockup_url") or ""
                return {
                    "type": "product",
                    "content": f"Dạ, sản phẩm {resolved}: {name}",
                    "image": url,
                    "meta": {"code": resolved, "name": name, "url": url},
                }
            p = bp.products(page_size=5, search=q)
            data = p.get("data", {})
            rows = data.get("result", [])
            total = data.get("total", len(rows))
            return {"type": "text", "content": f"Dạ, tìm thấy {total} sản phẩm\n" + _summarize_product_rows(rows)}

        if action == "out_of_stock":
            p = bp.out_of_stock()
            data = p.get("data", {})
            rows = data.get("result", [])
            total = data.get("total", len(rows))
            return {"type": "text", "content": f"Dạ, có {total} sản phẩm hết hàng\n" + _summarize_product_rows(rows)}

        if action == "order":
            oid = route["order_id"]
            order = bp.get_order(oid)
            return {"type": "text", "content": "Dạ, " + _summarize_order(order).lower()}

        if action == "tracking":
            oid = route["order_id"]
            tr = bp.tracking(oid)
            return {"type": "text", "content": f"Dạ, thông tin vận đơn {oid}\n{tr}"}

        if action == "cancel":
            oid = route["order_id"]
            return {"type": "text", "content": "Dạ, cancel là hành động không thể hoàn tác. Anh gửi CONFIRM CANCEL " + oid + " nếu chắc chắn nhé."}

        if action == "delete":
            oid = route["order_id"]
            return {"type": "text", "content": "Dạ, delete là hành động không thể hoàn tác. Anh gửi CONFIRM DELETE " + oid + " nếu chắc chắn nhé."}

        if action == "charge":
            oid = route["order_id"]
            return {"type": "text", "content": "Dạ, charge sẽ tính tiền order. Anh gửi CONFIRM CHARGE " + oid + " nếu muốn thực hiện nhé."}

        if action == "mockup":
            oid = route["order_id"]
            asset = bp.extract_first_asset(oid)
            result = generate_mockup(asset, text)
            return {
                "type": "mockup",
                "content": "Dạ, em đã tạo mockup xong rồi anh",
                "meta": {
                    "order": oid,
                    "product": asset.product_name,
                    "color": asset.color_name,
                    "provider": result["provider"],
                    "size": f"{result['width']}×{result['height']}",
                    "integrity": result["integrity_score"],
                    "time": f"{result['seconds']}s",
                    "cost": f"${result['cost_usd']}",
                },
                "image": f"/outputs/{result['path'].split('/')[-1]}",
                "order_id": oid,
            }

        if action == "product_mockup":
            from mockup_engine import generate_product_mockup
            pid = route.get("product_id") or ""
            search = route.get("search") or ""
            if not pid and search:
                resolved = _fuzzy_find_product(search, bp)
                if resolved:
                    pid = resolved
                else:
                    return {"type": "text", "content": f"Dạ, em không tìm thấy sản phẩm '{search}' trong catalog."}
            if not pid:
                return {"type": "text", "content": "Dạ, anh cho em biết tên sản phẩm cần tạo mockup nhé."}
            try:
                prod_data = bp.product(pid).get("data", {})
            except Exception:
                resolved = _fuzzy_find_product(pid, bp)
                if not resolved:
                    resolved = _fuzzy_find_product(search, bp) if search else None
                if not resolved:
                    return {"type": "text", "content": f"Dạ, em không tìm thấy sản phẩm '{pid}' trong catalog."}
                pid = resolved
                prod_data = bp.product(pid).get("data", {})
            pname = prod_data.get("display_name") or prod_data.get("name") or pid
            pcolor = prod_data.get("color_name") or "Black"
            base_mockup_url = prod_data.get("url") or prod_data.get("image") or ""
            result = generate_product_mockup(pid, pname, pcolor, base_mockup_url, text)
            return {
                "type": "mockup",
                "content": f"Dạ, em đã tạo mockup cho {pid} — {pname}",
                "meta": {
                    "order": "product-mockup",
                    "product": f"{pid} — {pname}",
                    "color": pcolor,
                    "provider": result["provider"],
                    "size": f"{result['width']}×{result['height']}",
                    "integrity": result["integrity_score"],
                    "time": f"{result['seconds']}s",
                    "cost": f"${result['cost_usd']}",
                },
                "image": f"/outputs/{result['path'].split('/')[-1]}",
            }

        return {"type": "chat"}

    except Exception as e:
        return {"type": "error", "content": str(e)}
