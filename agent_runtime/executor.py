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

import burger_memory as mem
from .plan_schema import AgentPlan, INTENT_REFINE

ROOT = None  # set at runtime


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
        self._current_job_id = job_id
        self._current_plan_id = plan.plan_id or ""
        order_id = plan.order_id or ""
        started = time.time()

        try:
            # Step 1: fetch order info only for tool flows that need product context.
            order_data = {}
            if order_id and plan.intent in ("create_mockup_batch", "create_mockup_single", INTENT_REFINE):
                order_data = self._execute_tool("bp_get_order", {"order_id": order_id})
                if not isinstance(order_data, dict) or not order_data or order_data.get("error"):
                    err = order_data.get("error") if isinstance(order_data, dict) else str(order_data)
                    return {
                        "type": "text",
                        "content": f"Dạ, lỗi khi lấy order {order_id}: {err or 'không tìm thấy'}",
                        "job_id": job_id,
                    }
            # Step 2: execute intent

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
                    img_id = f"img_{uuid.uuid4().hex[:10]}"
                    mockups.append({
                        "id": img_id,
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
                    try:
                        mem.save_mockup_image({
                            "id": img_id, "job_id": job_id, "order_id": order_id,
                            "scene_index": scene.index, "scene_prompt": scene_prompt,
                            "image_url": result.get("mockup_url", ""), "version": 1,
                        })
                    except Exception:
                        pass
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
        images = [{"url": m["mockup_url"], "scene": m["scene"], "index": m["index"], "image_id": m.get("id")} for m in mockups]

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

        try:
            mem.save_mockup_job(plan.session_id or "web", {
                "id": job_id,
                "order_id": order_id,
                "plan_id": plan.plan_id,
                "requested_count": len(scenes),
                "generated_count": len(mockups),
                "status": "completed" if not errors else "partial",
                "created_at": int(time.time()),
                "completed_at": int(time.time()),
            })
        except Exception:
            pass

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
        started = int(time.time())
        result = self._agent._execute_tool(name, args)
        try:
            mem.save_tool_run(
                getattr(self, "_current_plan_id", ""), getattr(self, "_current_job_id", ""),
                name, args, result if isinstance(result, dict) else {"text": result},
                status="success", started_at=started,
            )
        except Exception:
            pass
        return result

    def _format_orders(self, data: Any) -> str:
        if not data or (isinstance(data, dict) and data.get("error")):
            return "Dạ, không lấy được danh sách order."
        if not isinstance(data, dict):
            return "Dạ, không lấy được danh sách order."
        items = data.get("orders") or data.get("items") or data.get("data", {}).get("results") or data.get("data", {}).get("result") or []
        if not items:
            return "Dạ hiện không có order nào."
        lines = [f"Dạ anh, em lấy được {len(items)} order gần đây:"]
        for item in items[:10]:
            if not isinstance(item, dict):
                continue
            oid = item.get("order_id") or item.get("id") or item.get("reference_order") or ""
            product = item.get("product") or ""
            if not product:
                raw_items = item.get("items") or item.get("line_items") or []
                first = raw_items[0] if raw_items and isinstance(raw_items[0], dict) else {}
                product = first.get("name") or first.get("product_name") or first.get("catalog_sku") or ""
            status = item.get("state") or item.get("status") or item.get("fulfillment_status") or "?"
            mu = item.get("mockup_url") or ""
            line = f"- {oid}: {product} ({status})"
            if mu:
                line += f" | ảnh: {mu}"
            lines.append(line)
        return "\n".join(lines)

    def _format_order(self, data: Any) -> str:
        if not data or not isinstance(data, dict):
            return "Dạ không tìm thấy order."
        oid = data.get("order_id") or data.get("id", "")
        product = data.get("product") or ""
        state = data.get("state") or data.get("status", "?")
        amount = data.get("amount") or "?"
        currency = data.get("currency") or ""
        short_code = data.get("short_code") or ""
        fulfill = data.get("fulfillment") or ""
        shipping = data.get("shipping_fee") or ""
        ship = data.get("shipping") or {}
        recipient = (ship.get("name") or "") if isinstance(ship, dict) else ""

        lines = [f"Dạ anh, đây là thông tin order {oid}:",
                 f"- Sản phẩm: {product}",
                 f"- Mã catalog: {short_code}" if short_code else "",
                 f"- Trạng thái: {state}",
                 f"- Fulfillment: {fulfill}" if fulfill else "",
                 f"- Tổng tiền: {amount} {currency}",
                 f"- Phí ship: {shipping} {currency}" if shipping else "",
                 f"- Người nhận: {recipient}" if recipient else ""]

        # Product meta: print area, resolution
        pm = data.get("product_meta") or {}
        if pm:
            pa = pm.get("print_area")
            res = pm.get("resolution")
            if pa:
                lines.append(f"- Vị trí in: {', '.join(pa) if isinstance(pa, list) else str(pa)}")
            if res:
                lines.append(f"- Độ phân giải: {res}")

        # Line items
        lis = data.get("line_items") or []
        for li in lis[:5]:
            if not isinstance(li, dict):
                continue
            li_name = li.get("name") or li.get("sku") or ""
            li_color = li.get("color") or ""
            li_size = li.get("size") or ""
            li_qty = li.get("quantity", "")
            li_price = li.get("price") or ""
            li_sku = li.get("sku") or ""
            parts = []
            if li_color:
                parts.append(li_color)
            if li_size:
                parts.append(li_size)
            detail = f"x{li_qty}" if li_qty else ""
            cost = f"(${li_price})" if li_price else ""
            extra = f" | {li_sku}" if li_sku else ""
            lines.append(f"- Item: {li_name} {', '.join(parts)} {detail} {cost}{extra}".strip())

        if data.get("mockup_url"):
            lines.append(f"- Ảnh mockup: {data['mockup_url']}")
        if data.get("design_url") and data.get("design_url") != data.get("mockup_url"):
            lines.append(f"- Ảnh design: {data['design_url']}")

        return "\n".join(filter(None, lines))

    def _extract_order_images(self, data: Any) -> list:
        if not data or not isinstance(data, dict):
            return []
        images = []
        mp = data.get("mockup_url") or ""
        if mp:
            images.append({"url": mp, "scene": "order mockup", "index": 1})
        dp = data.get("design_url") or ""
        if dp and dp != mp:
            images.append({"url": dp, "scene": "design", "index": len(images) + 1})
        return images
