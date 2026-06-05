"""Lightweight Hermes-style memory for BurgerMockup.

No external services. Uses JSON + SQLite FTS5.
Tiers:
1) session state: current design/product/scene/last mockup
2) user profile/preferences: durable seller defaults
3) searchable event memory: turns/mockup runs/feedback
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).parent
MEMORY_DIR = ROOT / "memory"
DB_PATH = MEMORY_DIR / "burger_memory.sqlite3"
PROFILE_PATH = MEMORY_DIR / "user_profiles.json"
STATE_DIR = MEMORY_DIR / "state"


def _now() -> int:
    return int(time.time())


def _ensure_dirs() -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _conn() -> sqlite3.Connection:
    _ensure_dirs()
    c = sqlite3.connect(DB_PATH)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute(
        "CREATE TABLE IF NOT EXISTS events ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, kind TEXT, ts INTEGER, data TEXT)"
    )
    c.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(chat_id, kind, text)"
    )
    # Older dev build used contentless FTS, causing stored chat_id/kind to read as NULL.
    try:
        bad = c.execute("SELECT chat_id FROM events_fts LIMIT 1").fetchone()
        if bad and bad[0] is None:
            c.execute("DROP TABLE events_fts")
            c.execute("CREATE VIRTUAL TABLE events_fts USING fts5(chat_id, kind, text)")
            for eid, chat_id, kind, data in c.execute("SELECT id, chat_id, kind, data FROM events").fetchall():
                c.execute(
                    "INSERT INTO events_fts(rowid, chat_id, kind, text) VALUES (?, ?, ?, ?)",
                    (eid, chat_id, kind, data),
                )
    except Exception:
        pass
    return c


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_json(path: Path, data: Any) -> None:
    _ensure_dirs()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def state_path(chat_id: str) -> Path:
    _ensure_dirs()
    safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in str(chat_id))
    return STATE_DIR / f"{safe}.json"


def get_state(chat_id: str) -> Dict[str, Any]:
    return _load_json(state_path(chat_id), {})


def update_state(chat_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    state = get_state(chat_id)
    state.update({k: v for k, v in patch.items() if v is not None})
    state["updated_at"] = _now()
    _write_json(state_path(chat_id), state)
    return state


def get_profile(chat_id: str) -> Dict[str, Any]:
    profiles = _load_json(PROFILE_PATH, {})
    return profiles.get(str(chat_id), {})


def update_profile(chat_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    profiles = _load_json(PROFILE_PATH, {})
    prof = profiles.get(str(chat_id), {})
    prof.update({k: v for k, v in patch.items() if v is not None})
    prof["updated_at"] = _now()
    profiles[str(chat_id)] = prof
    _write_json(PROFILE_PATH, profiles)
    return prof


def remember_event(chat_id: str, kind: str, data: Dict[str, Any]) -> int:
    text = json.dumps(data, ensure_ascii=False, default=str)
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO events(chat_id, kind, ts, data) VALUES (?, ?, ?, ?)",
            (str(chat_id), kind, _now(), text),
        )
        event_id = int(cur.lastrowid)
        c.execute(
            "INSERT INTO events_fts(rowid, chat_id, kind, text) VALUES (?, ?, ?, ?)",
            (event_id, str(chat_id), kind, text),
        )
        return event_id


def search_memory(chat_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    if not query.strip():
        return []
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT e.id, e.kind, e.ts, e.data FROM events_fts f "
                "JOIN events e ON e.id=f.rowid "
                "WHERE f.chat_id=? AND events_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                (str(chat_id), query, int(limit)),
            ).fetchall()
        out = []
        for eid, kind, ts, data in rows:
            try:
                parsed = json.loads(data)
            except Exception:
                parsed = {"text": data}
            out.append({"id": eid, "kind": kind, "ts": ts, "data": parsed})
        return out
    except Exception:
        return []


def _brief_json(d: Dict[str, Any], keys: List[str]) -> str:
    picked = {k: d.get(k) for k in keys if d.get(k) not in (None, "", [], {})}
    return json.dumps(picked, ensure_ascii=False) if picked else "{}"


def build_memory_context(chat_id: str, message: str = "") -> str:
    """Compact prompt block injected each turn."""
    state = get_state(chat_id)
    profile = get_profile(chat_id)
    # keyword recall: use user message as FTS query, fallback to recent mockups
    recall = search_memory(chat_id, message, limit=3) if message else []
    lines = ["MEMORY_CONTEXT:"]
    if profile:
        lines.append("- user_profile: " + _brief_json(profile, [
            "language", "marketplace", "preferred_styles", "brand_tone", "favorite_products", "banned_styles", "persona_library"
        ]))
    if state:
        lines.append("- session_state: " + _brief_json(state, [
            "current_order_id", "current_design_id", "current_product", "current_scene", "last_mockup_url", "last_integrity", "last_provider", "last_warnings"
        ]))
    if recall:
        snippets = []
        for r in recall:
            data = r.get("data", {})
            snippets.append({"kind": r.get("kind"), "data": {k: data.get(k) for k in list(data)[:6]}})
        lines.append("- relevant_past: " + json.dumps(snippets, ensure_ascii=False, default=str))
    lines.append("RULE: use memory as context only; current user request overrides memory.")
    return "\n".join(lines)


def record_turn(chat_id: str, user: str, assistant: str) -> None:
    remember_event(chat_id, "turn", {"user": user[:1000], "assistant": assistant[:1000]})


def record_mockup(chat_id: str, result: Dict[str, Any], scene: str = "") -> None:
    data = {
        "scene": scene,
        "product": result.get("product"),
        "color": result.get("color"),
        "mockup_url": result.get("mockup_url"),
        "provider": result.get("provider"),
        "integrity": result.get("integrity"),
        "size": result.get("size"),
        "time": result.get("time"),
        "cost": result.get("cost"),
        "order_id": result.get("order_id"),
        "design_id": result.get("design_id"),
        "warnings": result.get("warnings"),
    }
    remember_event(chat_id, "mockup_run", data)
    update_state(chat_id, {
        "current_order_id": result.get("order_id"),
        "current_design_id": result.get("design_id"),
        "current_product": result.get("product"),
        "current_scene": scene,
        "last_mockup_url": result.get("mockup_url"),
        "last_integrity": result.get("integrity"),
        "last_provider": result.get("provider"),
        "last_warnings": result.get("warnings"),
    })
