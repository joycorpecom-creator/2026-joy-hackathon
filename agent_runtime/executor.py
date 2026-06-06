"""
Executor — product-only V1 runtime.
"""
import json
import time
import uuid
import traceback
from urllib.parse import urlparse
from typing import Any, Dict

import burger_memory as mem
from .plan_schema import AgentPlan, SceneSchema, INTENT_REFINE, INTENT_LIST_SELLER_PRODUCTS, INTENT_GET_SELLER_PRODUCT, INTENT_CREATE_FROM_SELLER_PRODUCT, INTENT_BULK_PRODUCT_MOCKUPS

ROOT = None


class Executor:
    def __init__(self, agent):
        self._agent = agent
        self._results = []

    def execute(self, plan: AgentPlan) -> Dict[str, Any]:
        self._results = []
        plan.status = "executing"
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        self._current_job_id = job_id
        self._current_plan_id = plan.plan_id or ""
        product_id = plan.order_id or ""
        started = time.time()

        try:
            if plan.intent in (INTENT_CREATE_FROM_SELLER_PRODUCT,):
                result = self._generate_product_batch(plan, job_id)
                return result

            if plan.intent == INTENT_BULK_PRODUCT_MOCKUPS:
                result = self._generate_bulk_product_mockups(plan, job_id)
                return result

            if plan.intent == INTENT_REFINE:
                result = self._refine(plan, job_id)
                return result

            if plan.intent == INTENT_LIST_SELLER_PRODUCTS:
                data = self._execute_tool("bs_list_seller_products", {})
                if self._wants_full_bp_specs(plan.raw_message):
                    data = self._enrich_seller_product_list(data)
                    content = self._format_seller_products_full(data)
                else:
                    # Always enrich for compact mode to get type + product_url
                    data = self._enrich_seller_product_list(data)
                    content = self._format_seller_products_compact(data)
                images = self._extract_seller_product_images(data)
                # ── Save ordered product id list into session state so "sản phẩm thứ 4" resolves ──
                try:
                    product_order = []
                    for item in (data.get("details") or data.get("products") or []):
                        if isinstance(item, dict):
                            product_order.append({
                                "idx": len(product_order) + 1,
                                "title": item.get("title") or item.get("product_id") or item.get("id") or "",
                                "product_id": item.get("product_id") or item.get("id") or "",
                            })
                    mem.update_state(plan.session_id or "web", {"last_product_list": product_order})
                except Exception:
                    pass
                return {"type": "text", "content": content, "images": images, "job_id": job_id}

            if plan.intent == INTENT_GET_SELLER_PRODUCT:
                data = self._execute_tool("bs_get_seller_product", {"product_id": product_id or plan.order_id})
                content = self._format_seller_product(data)
                images = self._extract_seller_product_images(data)
                return {"type": "text", "content": content, "images": images, "job_id": job_id}

            if plan.intent == "greeting":
                return {"type": "text", "content": "Dạ anh, em đây. Anh cần tạo mockup cho product nào ạ?"}

            return {"type": "text", "content": "Dạ anh nói rõ hơn được không ạ? Em chưa hiểu ý anh.", "job_id": job_id}

        except Exception as e:
            return {"type": "text", "content": f"Dạ, có lỗi khi xử lý: {str(e)}", "job_id": job_id, "error": str(e), "duration_sec": round(time.time() - started, 1)}

    def _generate_product_batch(self, plan: AgentPlan, job_id: str) -> Dict[str, Any]:
        product_id = plan.order_id or ""
        mockups = []
        errors = []
        for scene in plan.scenes:
            try:
                full = scene.prompt
                if scene.camera:
                    full += f", {scene.camera}"
                if scene.lighting:
                    full += f", {scene.lighting}"
                if scene.background:
                    full += f", {scene.background}"
                if scene.constraints:
                    full += ". " + ". ".join(scene.constraints)
                result = self._agent._execute_tool("create_mockup_from_seller_product", {"product_id": product_id, "scene": full, "no_split": True})
                if result.get("error"):
                    errors.append({"index": scene.index, "error": result["error"]})
                    continue
                img_id = f"img_{uuid.uuid4().hex[:10]}"
                product_id_val = result.get("product_id") or product_id
                mockup_url = result.get("mockup_url") or ""
                public_url = ""
                if mockup_url.startswith("/outputs/"):
                    public_url = f"http://36.50.26.198:8000{mockup_url}"
                elif mockup_url.startswith("/"):
                    public_url = f"http://36.50.26.198:8000{mockup_url}"
                mockups.append({
                    "id": img_id, "index": scene.index, "scene": scene.prompt,
                    "mockup_url": mockup_url, "public_url": public_url,
                    "product_id": product_id_val, "product": result.get("product", ""),
                    "color": result.get("color", ""), "provider": result.get("provider", ""),
                    "integrity": result.get("integrity", 0), "cost": result.get("cost", ""), "time": result.get("time", ""),
                })
                try:
                    mem.save_mockup_image({"id": img_id, "job_id": job_id, "order_id": product_id, "scene_index": scene.index, "scene_prompt": scene.prompt, "image_url": result.get("mockup_url", ""), "version": 1})
                except Exception:
                    pass
            except Exception as e:
                errors.append({"index": scene.index, "error": str(e)})
        mockups.sort(key=lambda m: m["index"])
        images = [{"url": m["mockup_url"], "public_url": m.get("public_url", ""), "scene": m["scene"], "index": m["index"], "image_id": m.get("id"), "product_id": m.get("product_id", "")} for m in mockups]
        product_name = mockups[0].get("product", "") if mockups else product_id
        color = mockups[0].get("color", "") if mockups else ""
        lines = [f"Dạ anh, em đã tạo xong {len(mockups)}/{len(plan.scenes)} mockup từ product {product_id}."]
        for m in mockups:
            lines.append(f"• Ảnh {m['index']}: {m['scene']}")
        if errors:
            lines.append(f"Còn {len(errors)} ảnh chưa tạo được: {', '.join(str(e['index']) for e in errors)}")
        if product_name:
            lines.append(f"\nSản phẩm: {product_name} ({color})" if color else f"\nSản phẩm: {product_name}")
        try:
            mem.save_mockup_job(plan.session_id or "web", {"id": job_id, "order_id": product_id, "plan_id": plan.plan_id, "requested_count": len(plan.scenes), "generated_count": len(mockups), "status": "completed" if not errors else "partial", "created_at": int(time.time()), "completed_at": int(time.time())})
        except Exception:
            pass
        return {"type": "mockup", "content": "\n".join(lines), "images": images, "job_id": job_id, "meta": {"product": product_name, "product_id": product_id, "color": color, "count": len(mockups), "requested": len(plan.scenes), "errors": len(errors)}}

    def _generate_bulk_product_mockups(self, plan: AgentPlan, job_id: str) -> Dict[str, Any]:
        """List all products, then for each create N mockups with auto scenes.

        Safe: rate-limited, sequential, per-item retry, progress DB-saved every step.
        UI polls GET /api/bulk/{job_id} for live progress.
        """
        import random
        per_product = plan.batch_count or 2
        session_id = plan.session_id or "web"

        # Step 1: list products
        data = self._execute_tool("bs_list_seller_products", {})
        products = (data.get("products") or []) if isinstance(data, dict) else []
        if not products:
            return {"type": "text", "content": "Dạ anh, không có sản phẩm nào trên BP."}

        # Enrich with detail to get type_name for auto-scene selection
        enriched = self._enrich_seller_product_list(data)
        details = enriched.get("details") or []
        total_products = len(details) or len(products)
        max_products = min(total_products, 10)
        total_images = max_products * per_product

        # Step 2: create bulk job
        bulk_id = f"bulk_{uuid.uuid4().hex[:12]}"
        mem.save_bulk_job(session_id, {
            "id": bulk_id, "plan_id": plan.plan_id, "status": "running",
            "total": total_images, "done": 0, "failed": 0,
            "config": {"per_product": per_product, "max_products": max_products, "total_products_in_shop": total_products},
        })

        # Scene template per product type
        SCENES = {
            "apparel": ["model wearing on street, natural sunlight, casual", "flat lay on wooden table, studio light"],
            "mug": ["on desk next to laptop, morning coffee vibe", "held by hand, outdoor cafe"],
            "default": ["clean lifestyle shot, natural setting", "close-up product detail, studio lighting"],
        }

        results = []
        errors = []
        all_images = []

        for i, d_item in enumerate(details[:max_products]):
            pid = d_item.get("product_id") or d_item.get("id") or ""
            title = d_item.get("title", pid)
            ptype = (d_item.get("product_type") or "").lower()
            # Pick scene group
            scenes = SCENES.get("apparel", SCENES["default"])
            if "mug" in ptype or "cốc" in ptype.lower():
                scenes = SCENES["mug"]
            elif "apparel" not in ptype:
                # try to guess from title
                if any(k in (pid + title).lower() for k in ["áo", "shirt", "tee", "hoodie", "sweater"]):
                    scenes = SCENES["apparel"]

            for si in range(per_product):
                item_id = f"{bulk_id}_{pid}_{si}"
                scene_text = scenes[si % len(scenes)]
                # Random variation per product to avoid duplicates
                angles = ["", "slightly tilted angle", "overhead shot", "45 degree angle", "eye-level shot"]
                scene_text += f", {random.choice(angles)}"
                mem.save_bulk_item({
                    "id": item_id, "job_id": bulk_id, "product_id": pid,
                    "product_title": title, "scene_index": si + 1, "scene_prompt": scene_text,
                    "status": "running", "retry_count": 0,
                })
                result = None
                for retry in range(2):
                    try:
                        result = self._agent._execute_tool("create_mockup_from_seller_product", {
                            "product_id": pid, "scene": scene_text, "no_split": True,
                        })
                        if result and result.get("error"):
                            if retry < 1:
                                time.sleep(2)
                                continue
                            errors.append({"product_id": pid, "scene_index": si + 1, "error": result["error"]})
                            mem.save_bulk_item({
                                "id": item_id, "job_id": bulk_id, "product_id": pid,
                                "status": "failed", "error": str(result["error"]), "retry_count": retry + 1,
                            })
                        else:
                            mockup_url = result.get("mockup_url", "") if result else ""
                            public_url = ""
                            if mockup_url.startswith("/"):
                                public_url = f"http://36.50.26.198:8000{mockup_url}"
                            img_id = f"img_{uuid.uuid4().hex[:10]}"
                            all_images.append({
                                "id": img_id, "url": mockup_url, "public_url": public_url,
                                "scene": scene_text, "index": len(all_images) + 1,
                                "product_id": pid, "product_title": title,
                                "cost": result.get("cost", ""), "time": result.get("time", ""),
                            })
                            mem.save_bulk_item({
                                "id": item_id, "job_id": bulk_id, "product_id": pid,
                                "status": "completed", "image_id": img_id, "image_url": mockup_url, "retry_count": retry,
                            })
                            try:
                                mem.save_mockup_image({
                                    "id": img_id, "job_id": job_id, "order_id": pid,
                                    "scene_index": si + 1, "scene_prompt": scene_text,
                                    "image_url": mockup_url, "version": 1,
                                })
                            except Exception:
                                pass
                        break
                    except Exception as e:
                        if retry >= 1:
                            errors.append({"product_id": pid, "scene_index": si + 1, "error": str(e)})
                            mem.save_bulk_item({
                                "id": item_id, "job_id": bulk_id, "product_id": pid,
                                "status": "failed", "error": str(e), "retry_count": retry + 1,
                            })
                # Update progress
                done = len(all_images)
                failed = len(errors)
                mem.save_bulk_job(session_id, {"id": bulk_id, "status": "running", "done": done, "failed": failed})
                # Rate limit between images
                time.sleep(3)

        # Complete
        done = len(all_images)
        failed = len(errors)
        mem.save_bulk_job(session_id, {
            "id": bulk_id, "status": "completed", "done": done, "failed": failed,
            "completed_at": int(time.time()),
        })
        mem.update_state(session_id, {"last_bulk_job_id": bulk_id})

        lines = [f"Dạ anh, em đã tạo xong {done}/{total_images} mockup từ {max_products} sản phẩm."]
        if failed:
            lines.append(f"Có {failed} lỗi.")
            for e in errors[:5]:
                lines.append(f"• {e.get('product_id')} ảnh {e.get('scene_index')}: {e.get('error', '')}")
        lines.append(f"\nBulk job ID: `{bulk_id}` — anh xem chi tiết tại /api/bulk/{bulk_id}")

        try:
            mem.save_mockup_job(session_id, {
                "id": job_id, "order_id": "bulk", "plan_id": plan.plan_id,
                "requested_count": total_images, "generated_count": done,
                "status": "completed" if not errors else "partial",
                "created_at": int(time.time()), "completed_at": int(time.time()),
            })
        except Exception:
            pass

        return {
            "type": "mockup", "content": "\n".join(lines),
            "images": all_images, "job_id": job_id, "bulk_job_id": bulk_id,
            "meta": {"total_products": max_products, "images_per_product": per_product, "total_images": done, "errors": failed},
        }

    def _refine(self, plan: AgentPlan, job_id: str) -> Dict[str, Any]:
        step = plan.tool_plan[0] if plan.tool_plan else None
        if not step:
            return {"type": "text", "content": "Dạ anh cần nói rõ ảnh nào để em sửa."}
        instruction = step.args.get("instruction", plan.raw_message)
        result = self._agent._execute_tool("refine_mockup", {"new_scene": instruction})
        if result.get("error"):
            return {"type": "text", "content": f"Dạ, lỗi khi refine: {result['error']}"}
        mockup_url = result.get("mockup_url", "")
        public_url = f"http://36.50.26.198:8000{mockup_url}" if mockup_url.startswith("/") else mockup_url
        return {
            "type": "mockup",
            "content": "Dạ anh, em đã refine xong ảnh.",
            "images": [{"url": mockup_url, "public_url": public_url, "scene": instruction, "index": 1, "product_id": result.get("product_id", plan.order_id or "")}],
            "job_id": job_id,
            "meta": {"product_id": result.get("product_id", plan.order_id or "")},
        }

    def _execute_tool(self, name: str, args: dict) -> Any:
        started = int(time.time())
        result = self._agent._execute_tool(name, args)
        try:
            mem.save_tool_run(getattr(self, "_current_plan_id", ""), getattr(self, "_current_job_id", ""), name, args, result if isinstance(result, dict) else {"text": result}, status="success", started_at=started)
        except Exception:
            pass
        return result

    def _wants_full_bp_specs(self, text: str) -> bool:
        t = (text or "").lower()
        return any(k in t for k in ["toàn bộ thông số", "tất cả thông số", "full thông số", "đầy đủ thông số", "toàn bộ field", "bp trả ra", "api trả ra", "chi tiết toàn bộ"])

    def _enrich_seller_product_list(self, data: Any) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return {"products": [], "details": []}
        products = data.get("products") or []
        details = []
        for p in products[:12]:
            if not isinstance(p, dict) or not p.get("id"):
                continue
            detail = self._execute_tool("bs_get_seller_product", {"product_id": p.get("id")})
            if isinstance(detail, dict) and not detail.get("error"):
                details.append(detail)
            else:
                details.append({**p, "detail_error": (detail or {}).get("error", "unknown") if isinstance(detail, dict) else "unknown"})
        out = dict(data)
        out["details"] = details
        return out

    def _format_seller_products_full(self, data: Any) -> str:
        if not isinstance(data, dict) or data.get("error"):
            return "Dạ, không lấy được thông số BP."
        details = data.get("details") or []
        if not details:
            return self._format_seller_products(data)
        lines = [f"Dạ anh, em đã call BurgerShop v1 và lấy toàn bộ thông số BP cho {len(details)} product:"]
        for d in details:
            pid = d.get("product_id") or d.get("id") or "?"
            title = d.get("title", "")
            lines.append(f"\n## {title} ({pid})")
            lines.append(f"- Source: {d.get('source', 'BurgerShop v1 Product API')}")
            lines.append(f"- Status: {d.get('status') or d.get('state') or ''}")
            lines.append(f"- Price: {d.get('price')} | Compare: {d.get('compare_price')}")
            lines.append(f"- Vendor: {d.get('vendor')} | Type: {d.get('product_type')} | Format: {d.get('product_format')}")
            lines.append(f"- URL: {d.get('product_url') or ''}")
            lines.append(f"- Mockup: {d.get('mockup_src') or ''}")
            lines.append(f"- Design: {d.get('design_src') or ''}")
            counts = d.get('counts') or {}
            lines.append(f"- Counts: designs={counts.get('designs', 0)}, mockups={counts.get('mockups', 0)}, variants={counts.get('variants', 0)}, product_types={counts.get('product_types', 0)}, store_channels={counts.get('store_channels', 0)}")
            if d.get("short_codes"):
                lines.append(f"- Short codes: {', '.join([str(x) for x in d.get('short_codes') if x])}")
            if d.get("bp_fields"):
                lines.append(f"- BP fields: {', '.join(d.get('bp_fields') or [])}")
            for v in (d.get("variants") or [])[:6]:
                if isinstance(v, dict):
                    lines.append(f"    • Variant: {v.get('sku')} | {v.get('color_name')} / {v.get('size_name')} | cost={v.get('cost')} | price={v.get('price')} | state={v.get('state')}")
            if len(d.get("variants") or []) > 6:
                lines.append(f"    • ... +{len(d.get('variants') or []) - 6} variants")
        return "\n".join(lines)

    def _format_seller_products_compact(self, data: Any) -> str:
        if not isinstance(data, dict) or data.get("error"):
            return "Dạ, không lấy được danh sách product."
        details = data.get("details") or []
        items = details or data.get("products") or []
        total = data.get("total") or len(items)
        if not items:
            return "Dạ không có seller product nào."
        lines = [f"Dạ anh, em lấy được {total} sản phẩm trên BP:"]
        for idx, item in enumerate(items[:20], start=1):
            if not isinstance(item, dict):
                continue
            pid = item.get("product_id") or item.get("id") or "?"
            title = item.get("title") or "Untitled"
            ptypes = item.get("product_types") or []
            type_name = ""
            if ptypes and isinstance(ptypes[0], dict):
                type_name = ptypes[0].get("name") or ""
            type_name = type_name or item.get("product_type") or item.get("product_format") or ""
            product_url = item.get("product_url") or next((c.get("url") for c in (item.get("store_channels") or []) if isinstance(c, dict) and c.get("url")), "")
            lines.append(f"\n{idx}. {title} - {pid}")
            lines.append(f"   Type: {type_name or 'N/A'}")
            if product_url:
                lines.append(f"   Link sản phẩm: {product_url}")
        return "\n".join(lines)

    def _format_seller_products(self, data: Any) -> str:
        return self._format_seller_products_compact(data)

    def _format_seller_product(self, data: Any) -> str:
        if not isinstance(data, dict) or data.get("error"):
            return f"Dạ, không tìm thấy product. {data.get('error', '')}"
        d = data.get("data", data) if isinstance(data, dict) else {}
        pid = d.get("product_id") or d.get("id") or "?"
        title = d.get("title", "")
        price = d.get("price", "?")
        compare_price = d.get("compare_price", "")
        vendor = d.get("vendor", "")
        status = d.get("status") or d.get("state", "")
        product_type = d.get("product_type", "")
        product_format = d.get("product_format", "")
        is_custom = d.get("is_custom")
        uri = d.get("uri", "")
        mockup = d.get("mockup_src") or d.get("mockup_url") or ""
        product_url = d.get("product_url") or next((c.get("url") for c in (d.get("store_channels") or []) if isinstance(c, dict) and c.get("url")), "")
        counts = d.get("counts", {})
        designs = d.get("designs") or []
        mockups_arr = d.get("mockups") or []
        variants = d.get("variants") or []
        options = d.get("options") or []
        layers = d.get("layers") or []
        bp_fields = d.get("bp_fields") or []
        source = d.get("source") or "BurgerShop v1"

        lines = [f"Dạ anh, đây là toàn bộ thông tin từ {source}:"]
        lines.append(f"- ID: {pid}")
        lines.append(f"- Tên: {title}")
        lines.append(f"- Giá: {price}")

        if compare_price:
            lines.append(f"- Compare price: {compare_price}")
        if vendor:
            lines.append(f"- Vendor: {vendor}")
        if status:
            lines.append(f"- Trạng thái: {status}")
        if product_type:
            lines.append(f"- Product type: {product_type}")
        if product_format:
            lines.append(f"- Product format: {product_format}")
        if is_custom is not None:
            lines.append(f"- Is custom: {is_custom}")
        if d.get("is_personalize") is not None:
            lines.append(f"- Is personalize: {d.get('is_personalize')}")
        if d.get("download_limit"):
            lines.append(f"- Download limit: {d.get('download_limit')}")
        if d.get("store_id"):
            lines.append(f"- Store ID: {d.get('store_id')}")
        if uri:
            lines.append(f"- URI: {uri}")
        if product_url:
            lines.append(f"- Link sản phẩm BP: {product_url}")
        if d.get("seo_title"):
            lines.append(f"- SEO title: {d.get('seo_title')}")
        if d.get("seo_desc"):
            lines.append(f"- SEO desc: {d.get('seo_desc')}")
        if d.get("short_desc"):
            lines.append(f"- Short desc: {d.get('short_desc')}")
        if d.get("desc"):
            desc = d.get("desc", "")
            lines.append(f"- Description: {desc[:200]}{'...' if len(desc) > 200 else ''}")
        if d.get("created_at"):
            lines.append(f"- Created at: {d.get('created_at')}")
        if d.get("updated_at"):
            lines.append(f"- Updated at: {d.get('updated_at')}")
        if d.get("category"):
            lines.append(f"- Category: {d.get('category')}")

        if bp_fields:
            lines.append(f"- BP API fields ({len(bp_fields)}): {', '.join(bp_fields)}")

        lines.append(f"- Số design: {counts.get('designs', len(designs))}")
        for ds in designs[:10]:
            if isinstance(ds, dict):
                lines.append(f"    • {ds.get('type', '?')} ({ds.get('short_code', '')}) — printable: {ds.get('printable_width')}×{ds.get('printable_height')}")

        lines.append(f"- Số mockup: {counts.get('mockups', len(mockups_arr))}")
        for m in mockups_arr[:5]:
            if isinstance(m, dict):
                lines.append(f"    • {m.get('media_type', '')} — {m.get('source', '')}")

        lines.append(f"- Số variant: {counts.get('variants', len(variants))}")
        for v in variants[:10]:
            if isinstance(v, dict):
                lines.append(f"    • {v.get('sku', '?')} — {v.get('color_name', '')} / {v.get('size_name', '')} — giá {v.get('price', '?')}")

        if options:
            lines.append(f"- Options: {len(options)} groups")

        if d.get("layers"):
            lines.append(f"- Layers: {len(d.get('layers') or [])} print areas")

        if d.get("store_channels"):
            lines.append(f"- Store channels ({len(d.get('store_channels', []))}):")
            for sc in (d.get("store_channels") or [])[:5]:
                if isinstance(sc, dict):
                    lines.append(f"    • {sc.get('channel', '')}: {sc.get('url', '')}")

        if mockup:
            lines.append(f"- Ảnh mockup: {mockup}")
        if d.get("design_src"):
            lines.append(f"- Ảnh design: {d.get('design_src')}")
        if d.get("image_markdown"):
            lines.append(f"  {d.get('image_markdown')}")

        return "\n".join(lines)

    def _extract_seller_product_images(self, data: Any) -> list:
        if not isinstance(data, dict):
            return []
        result = []
        seen = set()

        def add(url: str, scene: str):
            url = (url or "").strip()
            if not url or url in seen:
                return
            seen.add(url)
            result.append({"url": url, "scene": scene, "index": len(result) + 1})

        # List/detail response: prefer enriched details so each image maps to product_id + type + product_url.
        items = data.get("details") or data.get("products") or data.get("data", {}).get("result") or data.get("result") or []
        if isinstance(items, list) and items:
            for item in items[:20]:
                if isinstance(item, dict):
                    ptypes = item.get("product_types") or []
                    type_name = (ptypes[0].get("name") if ptypes and isinstance(ptypes[0], dict) else "") or item.get("product_type") or ""
                    product_url = item.get("product_url") or next((c.get("url") for c in (item.get("store_channels") or []) if isinstance(c, dict) and c.get("url")), "")
                    before = len(result)
                    add(item.get("mockup_src", "") or item.get("mockup_url", ""), item.get("title", "") or item.get("id", ""))
                    if len(result) > before:
                        result[-1].update({
                            "title": item.get("title") or "",
                            "product_id": item.get("product_id") or item.get("id") or "",
                            "product_url": product_url,
                            "type_name": type_name,
                        })

        # Single product response (agent.py flattened format or nested data)
        d = data.get("data", data)
        # If agent.py returned product fields at top level, use data itself
        if "product_id" in data and "bp_fields" in data:
            d = data
        add(d.get("mockup_url", ""), "product mockup")
        add(d.get("mockup_src", ""), "product mockup")
        add(d.get("design_src", ""), "design")

        mockup_obj = d.get("mockup") if isinstance(d.get("mockup"), dict) else {}
        add(mockup_obj.get("src", ""), "product mockup")

        for m in (d.get("mockups") or [])[:8]:
            if isinstance(m, dict):
                add(m.get("src", ""), "product mockup")

        for v in (d.get("variants") or [])[:20]:
            if isinstance(v, dict):
                add(v.get("mockup_src", ""), "variant mockup")
                vm = v.get("mockup") if isinstance(v.get("mockup"), dict) else {}
                add(vm.get("src", ""), "variant mockup")

        for des in (d.get("designs") or [])[:8]:
            if isinstance(des, dict):
                add(des.get("src", ""), "design")

        return result
