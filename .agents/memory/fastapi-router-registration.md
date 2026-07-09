---
name: FastAPI router registration
description: Lesson — a router defined but never include_router'd in main.py is silently ignored.
---

## Rule
After adding or moving a FastAPI router, always verify `backend/app/main.py` has a matching `app.include_router(...)` call. FastAPI does not warn when a router file exists but is never registered — all its endpoints simply 404 silently.

**Why:** The `/tenders` v2 router (`backend/app/api/routes/tenders.py`) was defined and fully implemented but never imported into `main.py`, so every v2 endpoint returned 404 in production despite passing unit-level import checks.

**How to apply:** When you add a new router module, check `main.py` immediately. When debugging mysterious 404s on routes that look correct, check `main.py` first.
