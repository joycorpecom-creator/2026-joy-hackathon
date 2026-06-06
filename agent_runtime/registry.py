"""
Tool Registry — canonical tool inventory for JOY Mockup Agent V2.

Every tool definition has:
- name: unique key
- description: what it does, when to use it
- input_schema: required/optional args
- output_schema: what it returns
- safe: no side effect (read-only)
- side_effect: mutates state / costs $
"""

from typing import Dict, List, Any

TOOL_REGISTRY: List[Dict[str, Any]] = [
    {
        "name": "get_order_info",
        "description": "Lấy thông tin đơn hàng từ BurgerPrints/BG API bao gồm product, design_url, mockup_urls. Dùng khi cần context để tạo mockup hoặc khi user hỏi về order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Mã đơn hàng BP (Axxxxx-xx-xxxxxxx hoặc BP-xxx hoặc DEMO-xxx)"}
            },
            "required": ["order_id"]
        },
        "output_schema": {
            "order_id": "string",
            "product": "object",
            "design_url": "string",
            "mockup_urls": "array"
        },
        "safe": True,
        "side_effect": False,
        "category": "order"
    },
    {
        "name": "list_orders",
        "description": "Liệt kê danh sách đơn hàng gần đây kèm ảnh mockup/design nếu có.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        },
        "safe": True,
        "side_effect": False,
        "category": "order"
    },
    {
        "name": "get_product_info",
        "description": "Lấy thông tin sản phẩm BP catalog theo short_code (VD USG5000, USNL3900).",
        "input_schema": {
            "type": "object",
            "properties": {
                "short_code": {"type": "string"}
            },
            "required": ["short_code"]
        },
        "safe": True,
        "side_effect": False,
        "category": "product"
    },
    {
        "name": "search_products",
        "description": "Tìm sản phẩm trong catalog BP theo từ khóa (tên, mã số).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"]
        },
        "safe": True,
        "side_effect": False,
        "category": "product"
    },
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
        "name": "create_mockup_batch",
        "description": "Tạo nhiều mockup lifestyle từ đơn hàng có sẵn. Tool nhận order_id + danh sách scenes đã expand đầy đủ. Mỗi scene sẽ tạo 1 ảnh mockup riêng biệt. Trả về danh sách ảnh kèm metadata.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Mã đơn hàng"},
                "scenes": {
                    "type": "array",
                    "description": "Danh sách scene đã expand: mỗi scene là object {index, prompt, camera, lighting, background, constraints[]}",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer"},
                            "prompt": {"type": "string"},
                            "camera": {"type": "string"},
                            "lighting": {"type": "string"},
                            "background": {"type": "string"},
                            "constraints": {"type": "array", "items": {"type": "string"}}
                        }
                    }
                }
            },
            "required": ["order_id", "scenes"]
        },
        "output_schema": {
            "job_id": "string",
            "order_id": "string",
            "mockups": "array"
        },
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
        "output_schema": {
            "new_image_id": "string",
            "mockup_url": "string",
            "version": "integer"
        },
        "safe": False,
        "side_effect": True,
        "category": "mockup"
    },
    {
        "name": "sync_lark",
        "description": "Sync job/images sang Lark Base. Dùng khi user yêu cầu đẩy kết quả lên Lark.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job ID muốn sync"},
                "image_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional: chỉ sync ảnh cụ thể (mặc định tất cả)"}
            },
            "required": ["job_id"]
        },
        "safe": False,
        "side_effect": True,
        "category": "integration"
    }
]

# Shortcut: name → definition
TOOL_MAP: Dict[str, Dict[str, Any]] = {t["name"]: t for t in TOOL_REGISTRY}

# Tool names the agent can reference
TOOL_NAMES = list(TOOL_MAP.keys())

def tool_inventory_for_prompt() -> str:
    """Compact tool list injected into planner system prompt."""
    lines = ["AVAILABLE TOOLS:"]
    for t in TOOL_REGISTRY:
        side = " (side-effect)" if t["side_effect"] else " (read-only)"
        lines.append(f"- {t['name']}{side}: {t['description']}")
    return "\n".join(lines)
