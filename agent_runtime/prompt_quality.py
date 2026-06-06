"""Deterministic prompt QA scoring before image generation."""
from __future__ import annotations

from typing import Dict, List

REQUIRED_SIGNALS = {
    "reference_preservation": ["source of truth", "preserve", "exact", "do not", "no redesign"],
    "commercial_intent": ["ecommerce", "listing", "ads", "shopify", "etsy", "amazon", "marketplace", "commercial"],
    "product_physics": ["physics", "material", "texture", "fabric", "ceramic", "stainless", "canvas", "surface", "folds", "lighting"],
    "scene_clarity": ["scene", "background", "pose", "composition", "camera", "lighting"],
    "negative_constraints": ["negative", "no ", "avoid", "watermark", "distort", "warped"],
}


def score_prompt(prompt: str) -> Dict[str, object]:
    text = (prompt or "").lower()
    scores: Dict[str, int] = {}
    missing: List[str] = []
    for name, signals in REQUIRED_SIGNALS.items():
        hits = sum(1 for s in signals if s in text)
        score = min(10, int(round((hits / max(1, min(len(signals), 5))) * 10)))
        scores[name] = score
        if score < 6:
            missing.append(name)
    overall = min(scores.values()) if scores else 0
    risk = "low" if overall >= 8 else "medium" if overall >= 6 else "high"
    return {"scores": scores, "overall": overall, "risk": risk, "missing": missing}


def append_prompt_qa_contract(prompt: str) -> str:
    qa = score_prompt(prompt)
    if qa["risk"] == "low":
        return prompt
    missing = ", ".join(qa.get("missing") or [])
    return (
        prompt.rstrip()
        + "\n\n[PROMPT QA REINFORCEMENT]\n"
        + f"The deterministic prompt QA detected weak areas: {missing}. Strengthen them in the final image: preserve product reference exactly, make the commercial use obvious, keep material physics realistic, make scene/camera/lighting explicit, and obey all negative constraints."
    )
