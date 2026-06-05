"""
Scene Expander — turns natural language/grouped style requests into exact scene list.
Deterministic first, LLM-free for reliability/cost.
"""

import re
from typing import Any, Dict, List, Optional
from .plan_schema import SceneSchema

DEFAULT_CONSTRAINTS = [
    "preserve original shirt/product design",
    "print/text must stay readable and not warped",
    "natural human anatomy",
    "no extra logo or changed artwork",
]

AUTO_SCENE_LIBRARY = [
    "urban streetwear lifestyle in New York evening, confident model wearing the product",
    "minimal fashion studio, clean neutral background, premium catalog lifestyle pose",
    "coffee shop lifestyle, young professional model, warm ambient light",
    "beach resort golden hour, relaxed vacation lifestyle, natural pose",
    "modern office workspace, young creative professional, bright window light",
    "countryside picnic vintage lifestyle, soft natural light, authentic candid pose",
    "gym activewear lifestyle, energetic pose, modern fitness background",
    "data center vibe coding scene, tech founder style, cinematic blue lighting",
    "downtown rooftop sunset, premium lifestyle fashion, city skyline background",
    "campus casual lifestyle, young model, clean daylight photography",
]


def extract_order_ids(text: str) -> List[str]:
    ids = re.findall(r"(?:A\d{5}-\d{1,2}-\d{7}|BP-\d+|DEMO-\d+)", text.upper())
    seen = set()
    return [x for x in ids if not (x in seen or seen.add(x))]


def extract_count(text: str) -> Optional[int]:
    patterns = [
        r"tạo\s*(\d+)\s*(?:ảnh|mockup|hình|bức)",
        r"(\d+)\s*(?:ảnh|mockup|hình|bức)",
        r"batch\s*(\d+)",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            try:
                return max(1, min(int(m.group(1)), 20))
            except Exception:
                pass
    return None


def _clean_scene(s: str) -> str:
    s = re.sub(r"^(?:là|la|style|scene|phong\s*cách)\s*[:\-]?\s*", "", s.strip(), flags=re.I)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" .,-:;")


def extract_explicit_scenes(text: str) -> List[SceneSchema]:
    scenes: List[SceneSchema] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # ảnh 1: ..., 1. ..., 1) ..., phong cách 1: ...
        m = re.match(r"^(?:ảnh|hình|scene|phong\s*cách)?\s*(\d{1,2})\s*[\.:\)\-]\s*(.+)$", line, re.I)
        if m:
            idx = int(m.group(1))
            prompt = _clean_scene(m.group(2))
            if len(prompt) > 2:
                scenes.append(SceneSchema(index=idx, prompt=prompt, source="explicit", constraints=list(DEFAULT_CONSTRAINTS)))
                continue
        # - scene / * scene
        m = re.match(r"^[-*]\s+(.+)$", line)
        if m:
            prompt = _clean_scene(m.group(1))
            if len(prompt) > 2:
                scenes.append(SceneSchema(index=len(scenes) + 1, prompt=prompt, source="explicit", constraints=list(DEFAULT_CONSTRAINTS)))
    scenes.sort(key=lambda s: s.index)
    # Re-index if duplicate/missing weirdness.
    seen = set()
    out = []
    for s in scenes:
        if s.index in seen:
            s.index = len(out) + 1
        seen.add(s.index)
        out.append(s)
    return out


def extract_global_constraints(text: str) -> List[str]:
    t = text.lower()
    out = list(DEFAULT_CONSTRAINTS)
    if "áo đen" in t or "black shirt" in t:
        out.append("scene and lighting must fit a black shirt")
    if "áo trắng" in t or "white shirt" in t:
        out.append("scene and lighting must fit a white shirt")
    if "giữ chữ" in t or "chữ rõ" in t or "readable" in t:
        out.append("shirt text must be sharp and readable")
    if "mỹ" in t or "us" in t or "america" in t:
        out.append("US lifestyle aesthetic")
    if "nữ" in t or "female" in t:
        out.append("prefer female model when compatible with the scene")
    if "nam" in t or "male" in t:
        out.append("prefer male model when compatible with the scene")
    return list(dict.fromkeys(out))


def expand_grouped_quantities(text: str, count: Optional[int]) -> List[SceneSchema]:
    """Parse '2 ảnh nữ ở biển, 2 ảnh nam văn phòng, 1 ảnh tự chọn'."""
    scenes: List[SceneSchema] = []
    # split by comma/semicolon/newline but keep phrases
    parts = re.split(r"[,;\n]+", text)
    constraints = extract_global_constraints(text)
    for part in parts:
        p = part.strip()
        m = re.search(r"(\d{1,2})\s*(?:ảnh|mockup|hình|bức)\s*(.+)", p, re.I)
        if not m:
            continue
        n = int(m.group(1))
        desc = _clean_scene(m.group(2))
        if not desc or re.search(r"^(cho|với|order|order_id)\b", desc, re.I):
            continue
        for i in range(n):
            variant = desc
            if n > 1:
                variant = make_variation(desc, i)
            scenes.append(SceneSchema(index=len(scenes) + 1, prompt=variant, source="grouped", constraints=list(constraints)))
    if count and len(scenes) > count:
        scenes = scenes[:count]
    return scenes


def make_variation(base: str, i: int) -> str:
    variants = [
        "morning natural light",
        "golden hour warm light",
        "cinematic evening light",
        "premium catalog composition",
        "candid lifestyle pose",
    ]
    suffix = variants[i % len(variants)]
    if suffix.lower() in base.lower():
        return base
    return f"{base}, {suffix}"


def fill_missing_scenes(existing: List[SceneSchema], count: int, text: str, product_context: Optional[Dict[str, Any]] = None) -> List[SceneSchema]:
    scenes = list(existing)
    constraints = extract_global_constraints(text)
    used = {normalize_prompt(s.prompt) for s in scenes}
    for candidate in AUTO_SCENE_LIBRARY:
        if len(scenes) >= count:
            break
        norm = normalize_prompt(candidate)
        if norm in used:
            continue
        idx = len(scenes) + 1
        prompt = candidate
        if "áo đen" in text.lower():
            prompt += ", balanced lighting for black shirt"
        scenes.append(SceneSchema(index=idx, prompt=prompt, source="inferred", constraints=list(constraints)))
        used.add(norm)
    return scenes[:count]


def normalize_prompt(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def dedupe_and_rewrite(scenes: List[SceneSchema]) -> List[SceneSchema]:
    seen = {}
    out = []
    for i, s in enumerate(scenes, start=1):
        s.index = i
        norm = normalize_prompt(s.prompt)
        if norm in seen:
            s.prompt = make_variation(s.prompt, seen[norm])
            s.source = s.source or "inferred"
            norm = normalize_prompt(s.prompt)
        seen[norm] = seen.get(norm, 0) + 1
        if not s.constraints:
            s.constraints = list(DEFAULT_CONSTRAINTS)
        out.append(s)
    return out


def expand_scenes(raw_message: str, count: Optional[int] = None, product_context: Optional[Dict[str, Any]] = None) -> List[SceneSchema]:
    """Main scene expansion entrypoint."""
    explicit = extract_explicit_scenes(raw_message)
    if count is None:
        count = extract_count(raw_message) or len(explicit) or 1
    count = max(1, min(int(count), 20))

    if explicit:
        scenes = explicit
    else:
        scenes = expand_grouped_quantities(raw_message, count)

    if len(scenes) < count:
        scenes = fill_missing_scenes(scenes, count, raw_message, product_context)

    scenes = dedupe_and_rewrite(scenes[:count])
    return scenes
