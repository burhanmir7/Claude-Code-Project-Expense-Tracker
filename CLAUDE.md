# CLAUDE.md

## Project overview

Spendly is a lightweight personal expense tracker built with Flask and SQLite.

---

## Architecture
```
spendly/
├── app.py              # All routes — single file, no blueprints
├── database/
│   ├── db.py           # Schema (init_db), seed_db, auth helpers, CATEGORIES / ACCOUNT_TYPES
│   └── queries.py      # Every other SQL read/write helper — imports nothing from Flask
├── ai/                 # Assistant layer (Steps 10–14) — no Flask imports
│   ├── llm_client.py     # MODEL, lazy client, create_message() seam, AIError hierarchy — the only file that imports an LLM provider's SDK
│   ├── prompts.py        # System prompts (stable constants, cached)
│   ├── chat.py           # Conversation orchestration + tool loop
│   ├── receipts.py       # Receipt image validation + structured extraction
│   ├── insights.py       # Rule-based budget insights (no LLM)
│   └── tools/            # Self-registering tool modules: expenses, analytics, accounts
├── templates/
│   ├── base.html       # Shared layout — all templates must extend this
│   ├── _chat_drawer.html  # Partial included by base.html for logged-in users
│   └── *.html          # One template per page
├── static/
│   ├── css/
│   │   ├── style.css       # Global styles
│   │   └── <page>.css      # One file per page/feature (profile, chat, accounts)
│   └── js/
│       ├── main.js         # Site-wide (theme toggle) — vanilla JS only
│       └── <feature>.js    # chat.js (drawer + receipt attach), dashboard.js (charts)
├── tests/              # pytest; conftest.py holds the client fixture + FakeLLM
├── PLAN_AI.md          # AI roadmap checklist (Steps 10–14)
└── requirements.txt
```

**Where things belong:**
- New routes → `app.py` only, no blueprints
- Schema, seed and auth helpers → `database/db.py`
- Every other SQL read/write helper → `database/queries.py` (never inline in routes; never returns a raw `Row`)
- Anything that talks to an LLM → `ai/` (never in `app.py`, never in `database/`); `ai/llm_client.py` is the only file allowed to import a provider SDK
- Tool definitions + handlers → one module per feature under `ai/tools/`, registered with `register_tool`
- New pages → new `.html` file extending `base.html`
- Page-specific styles → new `.css` file with a matching class prefix, not inline `<style>` tags
- Page-specific JS → new file under `static/js/` loaded via `{% block scripts %}`; site-wide JS goes in `base.html`

---

## Code style

- Python: PEP 8, snake_case for all variables and functions
- Templates: Jinja2 with `url_for()` for every internal link — never hardcode URLs
- Route functions: one responsibility only — fetch data, render template, done
- DB queries: always use parameterized queries (`?` placeholders) — never f-strings in SQL
- Error handling: use `abort()` for HTTP errors, not bare `return "error string"`

---

## Tech constraints

- **Flask only** — no FastAPI, no Django, no other web frameworks
- **SQLite only** — no PostgreSQL, no SQLAlchemy ORM, no external DB
- **Vanilla JS only** — no React, no jQuery, no npm packages. The one named exception is Tailwind CDN (`https://cdn.tailwindcss.com`, loaded in `base.html`) for CSS utility classes — it ships no build step and no interactive behavior of its own; all interactivity remains hand-written vanilla JS
- **No new pip packages** — work within `requirements.txt` as-is. The single sanctioned exception is `google-genai` (pinned in `requirements.txt`), used only by `ai/llm_client.py` for the Gemini free-tier API. Anything else must be flagged and approved first
- Python 3.10+ assumed — f-strings and `match` statements are fine (the project venv is 3.14, so `imghdr` and other 3.13-removed modules are unavailable)

---

## AI layer (Steps 10–14)

- The LLM provider and model are decided entirely inside `ai/llm_client.py`, at implementation time. No other file — not `app.py`, no other `ai/` module, no template, no test — names a vendor, an SDK, or a model id
- The API key comes only from `os.environ["LLM_API_KEY"]` (a provider-neutral name chosen for this project); never hardcoded, never read at import time. The app must boot and every non-AI page must work without it
- `ai/llm_client.create_message()` is the only call into the SDK. It takes plain, provider-neutral arguments (`system_text`, `context_text`, `turns`, optional `tools` / `response_schema` / `image`) and returns a normalized reply (`.text`, `.tool_calls`, `.finish_reason`). Nothing outside `ai/llm_client.py` may assume a specific vendor's request or response shape
- Routes catch `ai.llm_client.AIError` and map `.status` → 503 (not configured), 429 (rate limit), 502 (anything else)
- The system prompt is a stable constant passed as `system_text`; per-turn volatile context (today's date, user name, net-worth snapshot) always travels as the separate `context_text` argument, never baked into the prompt itself. Any caching, reasoning-effort tuning, etc. the chosen provider offers is an internal optimization inside `ai/llm_client.py`, never a functional requirement described elsewhere
- Every tool's `input_schema` sets `additionalProperties: false` and lists every property in `required`; handlers are `handler(user_id, tool_input)`; `user_id` always comes from `session["user_id"]` via the route, never from the model
- Only user text and final assistant text are stored in `chat_messages`; the last 20 rows are sent per request
- Never log prompts, messages, tool inputs, images, or raw provider responses
- Tests must never require `LLM_API_KEY` and must never import a provider SDK: use the `fake_llm` fixture from `tests/conftest.py`, which replaces `ai.llm_client.create_message`. Always call it as `llm_client.create_message(...)` (module attribute) — never `from ai.llm_client import create_message`, which bypasses the fake
- JSON endpoints under `/api/` return `401 {"error": ...}` when logged out; HTML pages redirect to `/login`

---

## Subagent Policy
- Always use a builtin explore subagent for codebase exploration 
  before implementing any new feature
- Always use a subagent to verify test results 
  after any implementation
- When asked to plan, delegate codebase research 
  to a subagent before presenting the plan
- always use a builtin plan subagent in plan mode

---

## Commands
```bash
# Setup
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run dev server (port 5001)
python app.py

# Run all tests
pytest

# Run a specific test file
pytest tests/test_foo.py

# Run a specific test by name
pytest -k "test_name"

# Run tests with output visible
pytest -s
```

---

## Implemented vs stub routes

| Route | Status |
|---|---|
| `GET /` | Implemented — renders `landing.html` |
| `GET, POST /register` | Implemented — Step 2 |
| `GET, POST /login` | Implemented — Step 3 |
| `GET /logout` | Implemented — Step 3 |
| `GET /terms`, `GET /privacy` | Implemented — static pages |
| `GET /profile` | Implemented — Steps 4–6 (date filter via `?date_from&date_to`) |
| `GET, POST /expenses/add` | Implemented — Step 7 |
| `GET, POST /expenses/<int:id>/edit` | Implemented — Step 8 |
| `POST /expenses/<int:id>/delete` | Implemented — Step 9 |
| `GET /api/chat/history` | Implemented — Step 10 |
| `POST /api/chat` | Implemented — Step 10 |
| `DELETE /api/chat/history` | Implemented — Step 10 |
| `POST /api/chat/receipt` | Implemented — dashboard redesign |
| `POST /api/expenses` | Implemented — dashboard redesign |
| `GET /accounts` | Stub — Step 14 |
| `GET, POST /accounts/add` | Stub — Step 14 |
| `GET, POST /accounts/<int:id>/edit` | Stub — Step 14 |
| `POST /accounts/<int:id>/delete` | Stub — Step 14 |

Steps 11 and 13 add no routes — they extend `POST /api/chat` with tools.

**Do not implement a stub route unless the active task explicitly targets that step.**

---

## Warnings and things to avoid

- **Never use raw string returns for stub routes** once a step is implemented — always render a template
- **Never hardcode URLs** in templates — always use `url_for()`
- **Never put DB logic in route functions** — it belongs in `database/queries.py` (schema and auth helpers in `database/db.py`)
- **Never install new packages** mid-feature without flagging it — keep `requirements.txt` in sync
- **Never use JS frameworks** — the frontend is intentionally vanilla
- **Validation failures re-render with status 400** — the code and tests use 400 even where older specs (07/08) said 200
- **FK enforcement is manual** — SQLite foreign keys are off by default; `get_db()` must run `PRAGMA foreign_keys = ON` on every connection
- **Seed data note** — `seed_db()` inserts 8 demo expenses totalling ₹318.24; spec 05 says ₹346.24, which is a documentation error, not a bug
- **`imghdr` is gone in Python 3.13+** — receipt type detection uses magic bytes in `ai/receipts.py`
- The app runs on **port 5001**, not the Flask default 5000 — don't change this