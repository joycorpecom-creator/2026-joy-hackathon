"""
Tool Registry — V1 seller product tools only.
"""
from typing import Dict, List, Any

TOOL_REGISTRY: List[Dict[str, Any]] = [
    {
        "name": "bs_list_seller_products",
        "description": "Liệt kê tất cả seller products BurgerShop/BurgerPrints đã add file in, có product_id dạng Axxxxx-xxx và mockup_url.",
        "input_schema": {"type": "object", "properties": {"page": {"type": "integer"}, "page_size": {"type": "integer"}}, "required": []},
        "safe": True,
        "side_effect": False,
        "category": "seller_product"
    },
    {
        "name": "bs_get_seller_product",
        "description": "Lấy chi tiết seller product đã add file in theo product_id dạng Axxxxx-xxx, gồm designs[], mockups[], variants[], printable area.",
        "input_schema": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]},
        "safe": True,
        "side_effect": False,
        "category": "seller_product"
    },
    {
        "name": "create_mockup_from_seller_product",
        "description": "Tạo nhiều mockup lifestyle từ seller product đã add design/mockup. Nhận product_id + scenes, không cần order_id.",
        "input_schema": {"type": "object", "properties": {"product_id": {"type": "string"}, "scenes": {"type": "array"}}, "required": ["product_id", "scenes"]},
        "safe": False,
        "side_effect": True,
        "category": "mockup"
    },
    {
        "name": "refine_mockup",
        "description": "Điều chỉnh/thay đổi mockup đã tạo trước đó. Dùng khi user nói 'sửa ảnh 3 cho sáng hơn', 'đổi background ảnh 2 thành biển'. Agent tự lấy image_id từ last_mockup_job.images[index]. Trả về ảnh mới với version tăng dần.",
        "input_schema": {
            "type": "object",
            "properties": {
                "image_id": {"type": "string", "description": "ID ảnh cần refine (từ last_mockup_job.images)"},
                "instruction": {"type": "string", "description": "Mô tả thay đổi (scene mới hoặc delta)"},
                "reference_image_id": {"type": "string", "description": "Optional: ID ảnh tham chiếu nếu 'làm giống ảnh X nhưng Y'"}
            },
            "required": ["image_id", "instruction"]
        },
        "safe": False,
        "side_effect": True,
        "category": "mockup"
    },
    {
        "name": "bp_authenticated",
        "description": "Kiểm tra kết nối và xác thực BurgerPrints API key. Dùng khi user nói 'kiểm tra kết nối' hoặc 'test api'.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "safe": True,
        "side_effect": False,
        "category": "utility"
    },
    {
        "name": "bp_balance",
        "description": "Kiểm tra số dư BurgerPrints. Dùng khi user hỏi 'còn bao nhiêu tiền' hoặc 'balance'.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "safe": True,
        "side_effect": False,
        "category": "utility"
    },
]

TOOL_MAP: Dict[str, Dict[str, Any]] = {t["name"]: t for t in TOOL_REGISTRY}
TOOL_NAMES = list(TOOL_MAP.keys())

def tool_inventory_for_prompt() -> str:
    lines = ["AVAILABLE TOOLS:"]
    for t in TOOL_REGISTRY:
        side = " (side-effect)" if t["side_effect"] else " (read-only)"
        lines.append(f"- {t['name']}{side}: {t['description']}")
    return "\n".join(lines)
