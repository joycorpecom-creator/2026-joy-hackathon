# JOY-DNSE Agent Guide

Read `HERMES_PROJECT_INDEX.md` first before editing. It maps entrypoints, runtime lanes, BP API flow, mockup pipeline, skip paths, and known pitfalls.

Rules:
- Do not edit generated/runtime noise: `__pycache__/`, `.git/`, `outputs/`, `assets/`, `uploads/`, `memory/` unless task explicitly targets them.
- Keep `settings.json` secrets masked in reports.
- For BurgerPrints product calls, use catalog `short_code` (e.g. `USG5000`), not dashboard IDs (`A60992-*`).
- `/new` must reset agent session, design store, and transient memory state.
