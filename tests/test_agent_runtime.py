import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_runtime.planner import deterministic_plan
from agent_runtime.executor import Executor
from agent_runtime.plan_schema import (
    INTENT_CREATE_FROM_SELLER_PRODUCT,
    INTENT_GET_SELLER_PRODUCT,
    INTENT_LIST_SELLER_PRODUCTS,
    INTENT_REFINE,
)


def test_product_mockup_plan_routes_to_seller_product():
    plan = deterministic_plan("tạo 1 ảnh product A53636-28 phong cách cafe chạy luôn", {"session": {"id": "t"}})
    assert plan.intent == INTENT_CREATE_FROM_SELLER_PRODUCT
    assert plan.order_id == "A53636-28"
    assert plan.tool_plan[0].tool == "create_mockup_from_seller_product"


def test_product_info_plan():
    plan = deterministic_plan("xem product A53636-28", {"session": {"id": "t"}})
    assert plan.intent == INTENT_GET_SELLER_PRODUCT
    assert plan.order_id == "A53636-28"


def test_list_products_plan():
    plan = deterministic_plan("lấy toàn bộ product", {"session": {"id": "t"}})
    assert plan.intent == INTENT_LIST_SELLER_PRODUCTS


def test_order_id_no_longer_routes_to_order_flow():
    plan = deterministic_plan("lấy order_id A60992-14-5706485", {"session": {"id": "t"}})
    assert plan.intent != "get_order_info"
    assert plan.intent != "list_orders"


def test_refine_uses_last_mockup_context():
    ctx = {"session": {"id": "t", "current_order_id": "A53636-28"}, "last_mockup_job": {"images": [{"index": 1, "image_id": "img1"}]}}
    plan = deterministic_plan("đổi cảnh ảnh vừa rồi sang beach sunset", ctx)
    assert plan.intent == INTENT_REFINE
    assert plan.order_id == "A53636-28"


def test_format_seller_products():
    ex = Executor(agent=None)
    text = ex._format_seller_products({"products": [{"id": "A53636-28", "title": "full print", "state": "active", "mockup_url": "https://x/img.jpg"}], "total": 1})
    assert "A53636-28" in text
    assert "full print" in text
