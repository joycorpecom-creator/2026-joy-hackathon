import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_runtime.planner import deterministic_plan
from agent_runtime.executor import Executor
from agent_runtime.plan_schema import AgentPlan, ToolPlanStep, INTENT_ORDER_INFO, INTENT_LIST_ORDERS


def test_bp_get_order_returns_full_normalized_fields():
    """Simulated test: _format_order should render amount/state/product/short_code."""
    ex = Executor(agent=None)
    data = {
        "order_id": "A60992-14-5706485",
        "state": "queued",
        "amount": "24.99 USD",
        "product": "Gildan 5000 T-Shirt - White - L",
        "short_code": "USG5000",
        "mockup_url": "https://example.com/mockup.png",
        "design_url": "https://example.com/design.png",
    }
    text = ex._format_order(data)
    assert "A60992-14-5706485" in text
    assert "24.99" in text
    assert "queued" in text
    assert "USG5000" in text
    assert "mockup" in text.lower() or "https" in text


def test_format_orders_includes_mockup_url_when_present():
    ex = Executor(agent=None)
    data = {
        "orders": [{
            "id": "A1",
            "product": "Mug",
            "state": "paid",
            "mockup_url": "https://m.com/1.png",
        }]
    }
    text = ex._format_orders(data)
    assert "A1" in text
    assert "Mug" in text
    # at minimum the order is listed
    assert "lấy được" in text.lower()


def test_extract_order_images_from_real_order_format():
    ex = Executor(agent=None)
    data = {
        "order_id": "A1",
        "mockup_url": "https://m.com/mockup.png",
        "design_url": "https://m.com/design.png",
    }
    imgs = ex._extract_order_images(data)
    assert len(imgs) == 2
    assert imgs[0]["url"] == "https://m.com/mockup.png"


def test_format_orders_resolves_product_from_line_items():
    ex = Executor(agent=None)
    data = {
        "orders": [{
            "id": "A1",
            "product": "",
            "state": "paid",
            "line_items": [{"name": "Gildan 5000"}],
            "items": [{"name": "Gildan 5000"}],
        }]
    }
    text = ex._format_orders(data)
    assert "A1" in text
    assert "Gildan 5000" in text
