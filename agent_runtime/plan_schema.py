"""
Plan Schema — product-only V1 runtime.
"""
from typing import List, Optional

INTENT_REFINE = "refine_mockup"
INTENT_SYNC_LARK = "sync_lark"
INTENT_LIST_SELLER_PRODUCTS = "list_seller_products"
INTENT_GET_SELLER_PRODUCT = "get_seller_product"
INTENT_CREATE_FROM_SELLER_PRODUCT = "create_mockup_from_seller_product"
INTENT_CONFIRM_PLAN = "confirm_plan"
INTENT_EDIT_PLAN = "edit_plan"
INTENT_CANCEL = "cancel"
INTENT_GREETING = "greeting"
INTENT_HELP = "help"
INTENT_UNKNOWN = "unknown"

ALL_INTENTS = [
    INTENT_REFINE, INTENT_SYNC_LARK,
    INTENT_LIST_SELLER_PRODUCTS, INTENT_GET_SELLER_PRODUCT, INTENT_CREATE_FROM_SELLER_PRODUCT,
    INTENT_CONFIRM_PLAN, INTENT_EDIT_PLAN, INTENT_CANCEL,
    INTENT_GREETING, INTENT_HELP, INTENT_UNKNOWN,
]

class SceneSchema:
    def __init__(self, index: int, prompt: str, source: str = "explicit",
                 camera: str = "", lighting: str = "", background: str = "",
                 constraints: Optional[List[str]] = None,
                 reference_image_id: Optional[str] = None):
        self.index = index
        self.prompt = prompt
        self.source = source
        self.camera = camera
        self.lighting = lighting
        self.background = background
        self.constraints = constraints or []
        self.reference_image_id = reference_image_id

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "prompt": self.prompt,
            "source": self.source,
            "camera": self.camera,
            "lighting": self.lighting,
            "background": self.background,
            "constraints": self.constraints,
            "reference_image_id": self.reference_image_id,
        }

class ToolPlanStep:
    def __init__(self, step: int, tool: str, args: dict):
        self.step = step
        self.tool = tool
        self.args = args

    def to_dict(self) -> dict:
        return {"step": self.step, "tool": self.tool, "args": self.args}

class AgentPlan:
    def __init__(self,
                 intent: str,
                 confidence: float = 0.0,
                 requires_confirmation: bool = False,
                 reason: str = "",
                 order_id: Optional[str] = None,
                 batch_count: Optional[int] = None,
                 scenes: Optional[List[SceneSchema]] = None,
                 missing_fields: Optional[List[str]] = None,
                 clarifying_question: Optional[str] = None,
                 tool_plan: Optional[List[ToolPlanStep]] = None,
                 plan_id: Optional[str] = None,
                 session_id: str = "",
                 raw_message: str = ""):
        self.intent = intent
        self.confidence = confidence
        self.requires_confirmation = requires_confirmation
        self.reason = reason
        self.order_id = order_id  # compatibility alias: stores product_id in product-only runtime
        self.batch_count = batch_count
        self.scenes = scenes or []
        self.missing_fields = missing_fields or []
        self.clarifying_question = clarifying_question
        self.tool_plan = tool_plan or []
        self.plan_id = plan_id
        self.session_id = session_id
        self.raw_message = raw_message
        self.status = "draft"

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "requires_confirmation": self.requires_confirmation,
            "reason": self.reason,
            "product_id": self.order_id,
            "order_id": self.order_id,
            "batch_count": self.batch_count,
            "scenes": [s.to_dict() for s in self.scenes],
            "missing_fields": self.missing_fields,
            "clarifying_question": self.clarifying_question,
            "tool_plan": [s.to_dict() for s in self.tool_plan],
            "plan_id": self.plan_id,
            "session_id": self.session_id,
            "status": self.status,
        }

AUTO_CONFIRM_BATCH_LIMIT = 4

def needs_confirmation(plan: AgentPlan) -> bool:
    if plan.intent != INTENT_CREATE_FROM_SELLER_PRODUCT:
        return False
    if (plan.batch_count or 1) >= AUTO_CONFIRM_BATCH_LIMIT:
        return True
    if plan.scenes and any(s.source != "explicit" for s in plan.scenes):
        return True
    return False


def plan_display_text(plan: AgentPlan) -> str:
    lines = ["Dạ anh, em đã hiểu. Đây là plan dự kiến:"]
    if plan.order_id:
        lines.append(f"- Product: {plan.order_id}")
    count = plan.batch_count or len(plan.scenes)
    lines.append(f"- Số ảnh: {count}")
    if plan.scenes:
        lines.append("")
        for s in plan.scenes:
            src_map = {"explicit": "", "inferred": "(tự chọn)", "grouped": "", "reference": "(tham chiếu)"}
            tag = src_map.get(s.source, "")
            desc = f"  {s.prompt}" if not tag else f"  {s.prompt} {tag}"
            lines.append(f"  {s.index}.{desc}")
    lines.append("")
    lines.append("Anh nhắn 'ok tạo' để em chạy, hoặc 'sửa scene X' để điều chỉnh.")
    return "\n".join(lines)
