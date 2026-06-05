"""
Deterministic batch mockup parser — runs before LLM.
Detects "tạo N ảnh/phong cách/mockup ... order_id" with numbered scene list.
Returns structured batch instruction or None.
"""
import re
from typing import List, Optional, Tuple


def _find_order_ids(text: str) -> List[str]:
    """Extract all BP order IDs from text."""
    ids = re.findall(r"(?:A\d{5}-\d{1,2}-\d{7}|BP-\d+|DEMO-\d+)", text.upper())
    # dedup preserving order
    seen = set()
    return [x for x in ids if not (x in seen or seen.add(x))]


def _find_scenes(text: str) -> List[str]:
    """Extract individual scenes from numbered/bullet lists."""
    scenes = []

    # Pattern 1: Numbered "1. ... 2. ..." or "ảnh 1. ... ảnh 2. ..."
    # or "phong cách 1 : ... phong cách 2 : ..."
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        # Match: "1. text" or "ảnh 1. text" or "ảnh 1 : text" or "phong cách 1 : text"
        m = re.match(r"(?:ảnh\s*)?(?:\d+)[.\s:]*(.+)$", line, re.I)
        if m:
            s = re.sub(r"^(?:là|la)\s+", "", m.group(1).strip(), flags=re.I)
            if s and len(s) > 3:
                scenes.append(s)
                continue
        # Match: "- text" or "* text"
        m = re.match(r"^[-\*]\s+(.+)$", line)
        if m:
            s = m.group(1).strip()
            if s and len(s) > 3:
                scenes.append(s)

    # Pattern 2: Explicit "tạo N ảnh" or "N phong cách" with commas in a single line
    count_m = re.search(r"tạo\s*(\d+)\s+(?:ảnh|mockup|phong cách|bức)", text, re.I)
    if count_m and not scenes:
        # Try comma separation
        count = int(count_m.group(1))
        # Look for comma-separated styles after "phong cách :" or "style:"
        style_m = re.search(r"phong cách\s*[\s:]*(.+)", text, re.I)
        if style_m:
            parts = [s.strip() for s in style_m.group(1).replace("\n", ",").split(",") if s.strip()]
            if len(parts) >= count:
                scenes = parts

    # Extract "số 1" / "số 2" style references from the order context
    if not scenes:
        # Fallback: look for "với / và / hoặc" separated styles
        conjunction_m = re.search(r"(?:phong cách|style|scene|với|theo)\s+(.+?)(?:với|và|hoặc)\s+(.+)", text, re.I)
        if conjunction_m:
            s1 = conjunction_m.group(1).strip()
            s2 = conjunction_m.group(2).strip()
            if s1 and s2:
                # Filter out order ID noise
                if not re.search(r"A\d|BP-|DEMO", s1) and not re.search(r"A\d|BP-|DEMO", s2):
                    scenes = [s1, s2]

    return scenes


def try_parse_batch_mockup(text: str) -> Optional[dict]:
    """
    Try to parse a batch mockup request from natural language.
    Returns {"order_id": str, "scenes": List[str]} or None.
    """
    order_ids = _find_order_ids(text)
    if not order_ids:
        return None

    # Must have mockup intent
    if not any(k in text.lower() for k in ["tạo", "mockup", "hình ảnh", "lifestyle","ảnh"]):
        return None

    # Must have multiple scenes or explicit multi count
    scenes = _find_scenes(text)
    if not scenes:
        return None

    # Use first order ID
    oid = order_ids[0]
    return {"order_id": oid, "scenes": scenes, "count": len(scenes)}

