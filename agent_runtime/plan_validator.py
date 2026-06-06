"""
Plan Validator — checks plan before execution.
Catches missing args, unknown tools, count mismatch, duplicate scenes.
Auto-rewrites duplicates if possible.
"""

from typing import List, Tuple
from .plan_schema import AgentPlan
from .registry import TOOL_MAP


def validate_plan(plan: AgentPlan) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    if not plan.intent or plan.intent == "unknown":
        errors.append("unknown intent: agent cannot infer")
    if plan.tool_plan:
        for step in plan.tool_plan:
            if step.tool not in TOOL_MAP:
                errors.append(f"unknown tool: {step.tool}")
            else:
                schema = TOOL_MAP[step.tool]
                required = schema.get("input_schema", {}).get("required", [])
                for arg in required:
                    if arg not in step.args or step.args[arg] in (None, "", []):
                        errors.append(f"tool {step.tool} missing arg {arg}")
    if plan.intent in ("create_mockup_batch", "create_mockup_single", "create_mockup_from_seller_product"):
        if plan.batch_count and plan.scenes:
            if len(plan.scenes) != plan.batch_count:
                errors.append(f"scene count mismatch: batch={plan.batch_count} scenes={len(plan.scenes)}")
        if plan.scenes and len(plan.scenes) > 1:
            prompts = [s.prompt.strip().lower()[:50] for s in plan.scenes]
            if len(set(prompts)) < len(prompts):
                errors.append("duplicate scene prompts detected")
    if plan.missing_fields:
        # missing fields are not an error — they mean we should ask user
        pass

    ok = len(errors) == 0
    return ok, errors


def auto_fix_plan(plan: AgentPlan) -> AgentPlan:
    ok, _ = validate_plan(plan)
    if ok:
        return plan
    # Dedupe
    from .scene_expander import dedupe_and_rewrite
    plan.scenes = dedupe_and_rewrite(plan.scenes)
    if plan.batch_count:
        plan.batch_count = len(plan.scenes)
    return plan
