"""
Executor — runs tool_plan deterministically.
One tool at a time, no LLM interference.
Records each step to tool_runs table.
"""

import json
import time
import uuid
import traceback
from typing import Any, Dict, List, Optional

from .plan_schema import AgentPlan, INTENT_REFINE


class Executor:
    def __init__(self, agent):
        """agent = BurgerMockupAgent instance (has real tool impl + BP client)."""
        self._agent = agent
        self._results: List[Dict[str, Any]] = []

    def execute(self, plan: AgentPlan) -> Dict[str, Any]:
        """Execute plan and return chat response dict."""
        self._results = []
        plan.status = "executing"

        job_id = f"job_{uuid.uuid4().hex[:12]}"
        order_id = plan.order_id or ""
        started = time.time()

        try:
            # Step 1: fetch order info if needed
            order_data = {}
            if order_id:
                order_data = self._execute_tool("bp_get_order", {"order_id": order_id})
                if not order_data or order_data.get("error"):
                    return {
                        "type": "text",
                        "content": f"Dạ, lỗi khi lấy order {order_id}: {order_data.get('error', 'không tìm thấy')}",
                        "job_id": job_id,
                    }

            # Step 2: generate mockups
            if plan.intent in ("create_mockup_batch", "create_mockup_single"):
                result = self._generate_batch(plan, job_id, order_data)
                return result

            elif plan.intent == INTENT_REFINE:
                result = self._refine(plan, job_id, order_data)
                return result

            elif plan.intent == "list_orders":
                data = self._execute_tool("bp_list_orders", {})
                content = self._format_orders(data)
                return {"type": "text", "content": content, "job_id": job_id}

            elif plan.intent == "get_order_info":
                data = self._execute_tool("bp_get_order", {"order_id": order_id or plan.order_id})
                content = self._format_order(data)
                images = self._extract_order_images(data)
                return {"type": "text", "content": content, "images": images, "job_id": job_id}

            elif plan.intent == "greeting":
                return {"type": "text", "content": "Dạ anh, em đây. Anh cần tạo mockup cho order nào ạ?"}

            else:
                return {"type": "text", "content": "Dạ anh nói rõ hơn được không ạ? Em chưa hiểu ý anh.", "job_id": job_id}

        except Exception as e:
            duration = time.time() - started
            return {
                "type": "text",
                "content": f"Dạ, có lỗi khi xử lý: {str(e)}",
                "job_id": job_id,
                "error": str(e),
                "duration_sec": round(duration, 1),
            }

    def _generate_batch(self, plan: AgentPlan, job_id: str, order_data: dict) -> Dict[str, Any]:
        scenes = plan.scenes
        order_id = plan.order_id or ""
        mockups = []
        errors = []

        for scene in scenes:
            try:
                scene_prompt = scene.prompt
                camera = scene.camera
                lighting = scene.lighting
                bg = scene.background

                # Build full prompt
                full = scene_prompt
                if camera:
                    full += f", {camera}"
                if lighting:
                    full += f", {lighting}"
                if bg:
                    full += f", {bg}"
                if scene.constraints:
                    full += ". " + ". ".join(scene.constraints)

                result = self._agent._execute_tool("create_mockup_from_order", {
                    "order_id": order_id,
                    "scene": full,
                })
                if result.get("error"):
                    errors.append({"index": scene.index, "error": result["error"]})
                else:
                    mockups.append({
                        "index": scene.index,
                        "scene": scene_prompt,
                        "mockup_url": result.get("mockup_url", ""),
                        "product": result.get("product", ""),
                        "color": result.get("color", ""),
                        "provider": result.get("provider", ""),
                        "integrity": result.get("integrity", 0),
                        "cost": result.get("cost", ""),
                        "time": result.get("time", ""),
                    })
            except Exception as e:
                errors.append({"index": scene.index, "error": str(e)})

        # Retry missing
        if errors:
            for err in errors:
                idx = err["index"]
                try:
                    scene = next(s for s in scenes if s.index == idx)
                    result = self._agent._execute_tool("create_mockup_from_order", {
                        "order_id": order_id,
                        "scene": scene.prompt,
                    })
                    if not result.get("error"):
                        mockups.append({
                            "index": idx,
                            "scene": scene.prompt,
                            "mockup_url": result.get("mockup_url", ""),
                            "product": result.get("product", ""),
                            "color": result.get("color", ""),
                            "provider": result.get("provider", ""),
                            "integrity": result.get("integrity", 0),
                            "cost": result.get("cost", ""),
                            "time": result.get("time", ""),
                        })
                        errors = [e for e in errors if e["index"] != idx]
                except Exception:
                    pass

        mockups.sort(key=lambda m: m["index"])
        images = [{"url": m["mockup_url"], "scene": m["scene"], "index": m["index"]} for m in mockups]

        product_name = order_data.get("product") or (mockups[0].get("product", "") if mockups else "")
        color = mockups[0].get("color", "") if mockups else ""

        # Build response text
        lines = [f"Dạ anh, em đã tạo xong {len(mockups)}/{len(scenes)} mockup."]
        for m in mockups:
            lines.append(f"• Ảnh {m['index']}: {m['scene']}")
        if errors:
            lines.append(f"Còn {len(errors)} ảnh chưa tạo được: {', '.join(str(e['index']) for e in errors)}")
        if product_name:
            lines.append(f"\nSản phẩm: {product_name} ({color})" if color else f"\nSản phẩm: {product_name}")

        return {
            "type": "mockup",
            "content": "\n".join(lines),
            "images": images,
            "job_id": job_id,
            "meta": {
                "product": product_name,
                "color": color,
                "count": len(mockups),
                "requested": len(scenes),
                "errors": len(errors),
                "order": plan.order_id or "",
            },
        }

    def _refine(self, plan: AgentPlan, job_id: str, order_data: dict) -> Dict[str, Any]:
        step = plan.tool_plan[0] if plan.tool_plan else None
        if not step:
            return {"type": "text", "content": "Dạ anh cần nói rõ ảnh nào để em sửa."}
        image_id = step.args.get("image_id", "")
        instruction = step.args.get("instruction", plan.raw_message)
        result = self._agent._execute_tool("refine_mockup", {"new_scene": instruction})
        if result.get("error"):
            return {"type": "text", "content": f"Dạ, lỗi khi refine: {result['error']}"}
        return {
            "type": "mockup",
            "content": f"Dạ anh, em đã refine xong ảnh.",
            "images": [{"url": result.get("mockup_url", ""), "scene": instruction, "index": 1}],
            "job_id": job_id,
        }

    def _execute_tool(self, name: str, args: dict) -> Any:
        return self._agent._execute_tool(name, args)

    def _format_orders(self, data: Any) -> str:
        if not data or isinstance(data, dict) and data.get("error"):
            return "Dạ, không lấy được danh sách order."
        items = data.get("items") or data.get("data", {}).get("results") or []
        if not items:
            return "Dạ hiện không có order nào."
        lines = ["Dạ anh, đây là các order:"]
        for item in items[:10]:
            oid = item.get("order_id") or item.get("id", "")
            product = item.get("product") or item.get("items", [{}])[0].get("name", "")
            status = item.get("status") or item.get("fulfillment_status", "?")
            lines.append(f"- {oid}: {product} ({status})")
        return "\n".join(lines)

    def _format_order(self, data: Any) -> str:
        if not data:
            return "Dạ không tìm thấy order."
        oid = data.get("order_id") or data.get("id", "")
        product = data.get("product") or ""
        status = data.get("status") or data.get("fulfillment_status", "?")
        price = data.get("total") or data.get("price", "?")
        return f"Dạ order {oid}:\n- Sản phẩm: {product}\n- Trạng thái: {status}\n- Giá: {price}"

    def _extract_order_images(self, data: Any) -> list:
        if not data:
            return []
        images = []
        items = data.get("items") or [data]
        for item in items:
            for m in item.get("mockups") or []:
                if m.get("src"):
                    images.append({"url": m["src"], "scene": "order mockup", "index": len(images) + 1})
            for d in item.get("designs") or []:
                if d.get("src"):
                    images.append({"url": d["src"], "scene": "design preview", "index": len(images) + 1})
        return images
