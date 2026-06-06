import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_runtime.planner import deterministic_plan
from agent_runtime.scene_expander import expand_scenes
from agent_runtime.plan_validator import validate_plan
from agent_runtime.verifier import verify_mockup_result
from agent_runtime.orchestrator import resolve_image_reference


def test_grouped_quantity_expands_to_requested_count():
    scenes = expand_scenes("tạo 5 ảnh, 2 ảnh nữ ở biển, 2 ảnh nam văn phòng, 1 ảnh tự chọn hợp áo đen", 5)
    assert len(scenes) == 5
    assert scenes[0].prompt != scenes[1].prompt
    assert any("áo đen" in " ".join(s.constraints).lower() or "black" in " ".join(s.constraints).lower() for s in scenes)


def test_batch_5_requires_confirmation_and_has_tool_plan():
    plan = deterministic_plan(
        "tạo 5 ảnh cho order_id A60992-14-5706485\nảnh 1: beach\nảnh 2: office\nảnh 3: street\nảnh 4: farm\nảnh 5: studio",
        {"session": {"id": "t"}},
    )
    ok, errors = validate_plan(plan)
    assert ok, errors
    assert plan.batch_count == 5
    assert plan.requires_confirmation is True
    assert [s.tool for s in plan.tool_plan] == ["get_order_info", "create_mockup_batch"]


def test_verify_result_detects_duplicate_urls():
    result = {"type": "mockup", "images": [{"url": "/a.png", "scene": "a"}, {"url": "/a.png", "scene": "b"}], "meta": {"requested": 2}}
    verified = verify_mockup_result(result)
    assert verified["ok"] is False
    assert "duplicate image urls" in verified["problems"]


def test_resolve_image_reference_from_last_job():
    context = {"last_mockup_job": {"images": [{"index": 2, "image_id": "img_2", "scene": "office"}]}}
    assert resolve_image_reference("sửa ảnh 2 sáng hơn", context) == "img_2"


def test_pending_plan_edit_intent_detected():
    plan = deterministic_plan(
        "sửa ảnh 3 thành văn phòng luxury",
        {"session": {"id": "t"}, "pending_plan": {"scenes": [{"index": 3, "prompt": "old"}]}}
    )
    assert plan.intent == "edit_plan"


def test_order_id_info_request_is_not_misclassified_as_list_orders():
    plan = deterministic_plan(
        "lấy toàn bộ thông tin order_id DEMO-1001",
        {"session": {"id": "t"}}
    )
    assert plan.intent == "get_order_info"
    assert plan.order_id == "DEMO-1001"


def test_format_orders_supports_normalized_orders_key():
    from agent_runtime.executor import Executor
    ex = Executor(agent=None)
    text = ex._format_orders({"orders": [{"id": "A1", "product": "Mug", "state": "paid"}]})
    assert "A1" in text
    assert "Mug" in text
