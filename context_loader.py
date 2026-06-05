"""Load project-local context for Joy Agent.

Reads joyagent.config.json to know which docs to load and in what order.
No Hermes dependency — pure Python + JSON.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "joyagent.config.json"
MANIFEST_PATH = ROOT / "joyagent.md"


def _read_file(path: Path, max_chars: int = 4000) -> str:
    try:
        content = path.read_text(encoding="utf-8")
        if len(content) > max_chars:
            return content[:max_chars] + "\n…[truncated]"
        return content.strip()
    except Exception:
        return ""


def load_config() -> Dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {"read_order": [], "core_files": {}, "rules": {}}


def load_manifest(max_chars: int = 3000) -> str:
    return _read_file(MANIFEST_PATH, max_chars=max_chars)


def resolve_path(name_or_path: str) -> str:
    """Resolve a path from config value. Relative vs absolute."""
    p = Path(name_or_path)
    if p.is_absolute():
        return name_or_path
    return str(ROOT / name_or_path)


def load_context(message: str = "", max_total: int = 5000) -> str:
    """Load the relevant context block for agent injection.

    Reads joyagent.config.json:
    1. Always inject joyagent.md core rules + file map.
    2. If message matches a skill trigger, inject that skill.
    """
    config = load_config()
    manifest_section = _read_file(MANIFEST_PATH, max_chars=2000)

    parts = [f"# JOY AGENT CONTEXT\n"]
    parts.append(manifest_section)

    # Match message to skill triggers
    t_lower = message.lower().strip()
    read_order = config.get("read_order", [])

    # Which skills to load based on intent match
    skill_triggers = {
        "design|màu|màu sắc|nền|background|ssim|integrity|warp|bh|crop|composite|normalize": "design-integrity",
        "bp|burgerprint|product|short_code|api|catalog|order|api key": "bp-api",
        "memory|nhớ|preference|profile|lưu|lại|style|ưa thích|persona": "memory",
        "routing|tool|route|intent|sai|không đúng|lỗi|wrong": "agent-routing",
        "demo|judge|zip|setup|telegram|cài|run|chạy|install": "demo-ops",
    }

    loaded_skills = set()
    for trigger_keywords, skill_name in skill_triggers.items():
        if any(kw in t_lower for kw in trigger_keywords.split("|")):
            skill_path = resolve_path(f"skills/burgermockup-{skill_name}/SKILL.md")
            skill_content = _read_file(Path(skill_path), max_chars=1500)
            if skill_content:
                parts.append(f"\n## Loaded Skill: {skill_name}\n")
                parts.append(skill_content)
                loaded_skills.add(skill_name)

    result = "\n".join(parts)
    if len(result) > max_total:
        result = result[:max_total] + "\n…[context truncated]"
    return result


def get_rules_summary() -> str:
    """Compact rules for system prompt."""
    config = load_config()
    rules = config.get("rules", {})
    lines = ["RULES:"]
    for k, v in rules.items():
        if k == "no_real_brand_logos":
            lines.append("- No real brand logos, no celebrity faces")
        elif k == "preserve_design_pixels":
            lines.append("- Design pixels are source of truth — never AI-redraw")
        elif k == "output_min_size":
            lines.append(f"- Output ≥ {v}")
        elif k == "current_request_overrides_memory":
            lines.append("- Current user request overrides memory")
        elif k == "judge_setup_max_minutes":
            lines.append(f"- Judge setup ≤ {v} min")
    return "\n".join(lines)
