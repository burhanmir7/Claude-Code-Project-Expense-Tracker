# Spec: AI Chat Interface

## Overview
Step 10 adds a floating, collapsible chat drawer to every authenticated page,
backed by a JSON endpoint that sends the user's message plus their recent
conversation history to an LLM and returns the reply. Conversation history is
persisted per user in a new `chat_messages` SQLite table so it survives page
reloads and logins. This step creates the `ai/` package — the only part of
the codebase allowed to know which LLM provider is in use. `ai/llm_client.py`
is the single seam: it is the only file that imports a provider SDK, and it
exposes a small, provider-neutral function, `create_message()`, that every
other `ai/` module calls instead of talking to any vendor directly. No
provider or model is chosen in this spec — that decision, and the one new pip
package it requires, is made when this step is implemented. No tools are
wired yet; the assistant can only talk. The app must boot and every existing
page must keep working when the provider's API key is unset. Steps 11–14 all
build on the plumbing established here without ever importing a vendor SDK
themselves.

## Depends on
- Step 1: Database setup (`users` table, `init_db()` pattern, `get_db()`)
- Step 3: Login / Logout (`session["user_id"]` gates the drawer and endpoints)
- Step 5: Backend routes for profile page (`database/queries.py` helper
  conventions this step follows)

## Routes
- `GET /api/chat/history` — return the user's stored messages, oldest first —
  logged-in only (JSON 401 otherwise)
- `POST /api/chat` — send one message, get one reply — logged-in only (JSON
  401 otherwise)
- `DELETE /api/chat/history` — clear the user's conversation — logged-in only
  (JSON 401 otherwise)

View function names: `chat_history`, `chat_send`, `chat_clear`.

JSON contracts:

`GET /api/chat/history`
- `200 {"messages": [{"role": "user"|"assistant", "content": str,
  "created_at": str}, ...]}` — the last 50 stored rows, oldest first

`POST /api/chat` with body `{"message": str}`
- `200 {"reply": str}`
- `400 {"error": "Message is required."}` — missing, blank, or non-JSON body
- `400 {"error": "Message must be 2000 characters or fewer."}`
- `401 {"error": "Authentication required."}`
- `429 {"error": "The assistant is busy. Please try again in a moment."}`
- `502 {"error": "The assistant is temporarily unavailable. Please try
  again."}`
- `503 {"error": "The AI assistant is not configured. Set LLM_API_KEY to
  enable it."}`
- Nothing is stored on any error. On success the user message is stored
  first, then the assistant reply, so history never contains orphaned turns.

`DELETE /api/chat/history`
- `200 {"cleared": int}`

## Database changes
Add to `init_db()` in `database/db.py`, after the `expenses` table:

```sql
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
)
```

One conversation thread per user — there is no `conversations` table.
Trade-off: users cannot keep several named chats; "Clear" is the reset. That
is enough for a teaching app and keeps the schema to one table.

## Templates
- **Create**: `templates/_chat_drawer.html`
  - A partial included by `base.html`; it does not extend `base.html`
  - Root: `<aside id="chat-drawer" class="chat-drawer chat-drawer-collapsed"
    data-history-url="{{ url_for('chat_history') }}"
    data-send-url="{{ url_for('chat_send') }}">`
  - `<button id="chat-toggle" class="chat-toggle" type="button"
    aria-expanded="false">` — the floating bubble
  - `.chat-header` with the title "Spendly Assistant", a
    `<button id="chat-clear" class="chat-clear">` and a close button
  - `<div id="chat-messages" class="chat-messages" aria-live="polite">`
    containing an empty-state `<p class="chat-empty">Ask me about your
    spending.</p>`
  - `<form id="chat-form" class="chat-form">` with
    `<textarea id="chat-input" class="chat-input" maxlength="2000"
    rows="1">` and `<button type="submit" class="chat-send">Send</button>`
  - `<p id="chat-status" class="chat-status" hidden>` for "Thinking…" and
    error text
- **Modify**: `templates/base.html`
  - Inside `<head>`, wrapped in `{% if session.get('user_id') %}`:
    `<link rel="stylesheet" href="{{ url_for('static',
    filename='css/chat.css') }}">`
  - After `</footer>`, wrapped in `{% if session.get('user_id') %}`:
    `{% include "_chat_drawer.html" %}` followed by
    `<script src="{{ url_for('static', filename='js/chat.js') }}"></script>`,
    placed before `{% block scripts %}`
  - `chat.js` is loaded directly in `base.html` rather than via
    `{% block scripts %}` because the drawer must appear on every
    authenticated page without each template opting in; `scripts` stays
    reserved for page-specific JS (first used in Step 12)

None of the templates, CSS, or JS in this step reference any LLM provider —
they only talk to Spendly's own `/api/chat*` endpoints.

## Files to change
- `database/db.py` — add the `chat_messages` DDL to `init_db()`
- `database/queries.py` — add `get_chat_messages`, `insert_chat_message`,
  `delete_chat_messages`
- `app.py`
  - Import `jsonify` from Flask
  - Import `run_chat_turn` from `ai.chat`, `AIError` from `ai.llm_client`,
    and the three chat helpers from `database.queries`
  - Add `_json_error(message, status)` under the `# Helpers` banner —
    returns `jsonify({"error": message}), status`
  - Add the three routes under a new `# AI routes` banner
  - `chat_send` flow: validate JSON body → load
    `get_chat_messages(user_id, limit=HISTORY_LIMIT)` → load
    `get_user_by_id(user_id)` for the name → call `run_chat_turn(...)` inside
    `try/except AIError as e: return _json_error(e.user_message, e.status)`
    → `insert_chat_message` for user then assistant → return JSON
- `templates/base.html` — conditional CSS link, include, and script tag
- `requirements.txt` — add exactly one new line: the SDK package for
  whichever LLM provider is chosen when this step is implemented (for
  example `<provider-sdk>==<version>`). This spec makes no provider
  assumption; record the choice made here in `CLAUDE.md` once decided
- `tests/conftest.py` — add the shared fake described under Tests

## Files to create
- `ai/__init__.py` — empty
- `ai/llm_client.py` — the only file in the codebase that imports a
  provider SDK. Everything it exposes is provider-neutral:
  - Constants: `MODEL` (the chosen provider's model id — decided and set
    here at implementation time; never restated as a literal anywhere
    else), `CHAT_MAX_TOKENS = 4096`, `EXTRACT_MAX_TOKENS = 1024`,
    `REQUEST_TIMEOUT_SECONDS = 30.0`
  - `class AIError(Exception)` with attributes `status` (int) and
    `user_message` (str); subclasses `AIConfigError` (503),
    `AIRateLimitError` (429), `AIUnavailableError` (502)
  - `get_client()` — raises `AIConfigError` if
    `os.environ.get("LLM_API_KEY")` is falsy; otherwise lazily builds the
    chosen provider's client and caches it in a module-level `_client`
  - `create_message(system_text, context_text="", turns=None, tools=None,
    response_schema=None, image=None)` — the seam and the only place that
    calls the provider SDK. Parameters, all provider-neutral:
    - `system_text` — the stable system prompt (required)
    - `context_text` — volatile per-call context (today's date, user name,
      later a net-worth snapshot); never merged into `system_text`
    - `turns` — a list of plain dicts describing the conversation so far,
      each either `{"role": "user"|"assistant", "content": str}` or, once
      Step 11 adds tools, `{"role": "assistant", "content": str,
      "tool_calls": [{"id", "name", "input"}]}` /
      `{"role": "tool_result", "tool_call_id": str, "content": str,
      "is_error": bool}`; defaults to `[]`
    - `tools` — optional list of tool definitions (JSON Schema dicts with
      `name`, `description`, `input_schema`)
    - `response_schema` — optional JSON Schema requesting constrained,
      structured JSON output
    - `image` — optional `{"media_type": str, "data": <base64 str>}`
      attached to the conversation's user content, for vision input
    - Translates the provider SDK's exceptions into `AIError` subclasses:
      an authentication/credentials failure → `AIConfigError`; a rate-limit
      failure → `AIRateLimitError`; any other API or network failure →
      `AIUnavailableError`
    - Returns a normalized reply object exposing `.text` (str, possibly
      empty), `.tool_calls` (list of objects with `.id`, `.name`, `.input`;
      empty when none), and `.finish_reason` (one of `"stop"`,
      `"tool_calls"`, `"length"`, `"refused"`). This normalized shape — not
      any provider's raw response object — is what every other `ai/` module
      is written against
    - How `system_text`, `context_text`, `turns`, `tools`,
      `response_schema`, and `image` map onto the chosen provider's actual
      request format (single system string vs. array, native structured
      output vs. prompted JSON, how an image attaches to a turn, whether
      the provider offers prompt caching or an effort/reasoning control) is
      entirely this function's internal business. None of it is specified
      here, and nothing outside this file may assume a particular mapping
- `ai/prompts.py` — `CHAT_SYSTEM_PROMPT` (see Rules)
- `ai/chat.py`
  - `HISTORY_LIMIT = 20`
  - `build_messages(history, user_text)` — keeps only the last
    `HISTORY_LIMIT` rows of `history`, converts them to
    `{"role", "content"}` turn dicts, drops any leading `assistant` rows so
    the first turn is `user`, and appends the new user turn
  - `CONTEXT_PROVIDERS = []` — list of callables `(user_id) -> str | None`;
    later steps append to it
  - `build_turn_context(user_id, user_name, today)` — joins
    `"Today is YYYY-MM-DD."`, `"The user's name is <name>."` and every
    non-`None` provider result with spaces
  - `run_chat_turn(user_id, history, user_text, user_name, today)` — calls
    `llm_client.create_message(system_text=CHAT_SYSTEM_PROMPT,
    context_text=build_turn_context(user_id, user_name, today),
    turns=build_messages(history, user_text))` and returns
    `{"reply": str, "tools_used": []}`; `finish_reason == "refused"` → reply
    "I can't help with that request."; `"length"` → text so far plus " …";
    empty text → "Done."
- `templates/_chat_drawer.html`
- `static/css/chat.css` — class prefix `chat-`; fixed bottom-right; tokens
  only (`--paper-card`, `--border`, `--accent`, `--accent-light`,
  `--paper-warm`, `--danger-light`, `--ink`, `--radius-lg`, `--font-body`);
  `.chat-bubble-user`, `.chat-bubble-assistant`, `.chat-bubble-error`;
  `.chat-drawer-collapsed` hides the panel and shows only the toggle;
  max-width 360px, `max-height: 70vh`; `@media (max-width: 600px)` full width
- `static/js/chat.js` — ES5 IIFE with `var`, null-guarded lookups,
  localStorage key `"spendly-chat-open"`; on load restores open state and
  `fetch(historyUrl)` to render history; on submit trims, ignores empty,
  disables input, appends a user bubble, shows "Thinking…", then
  `fetch(sendUrl, {method: "POST", headers: {"Content-Type":
  "application/json"}, body: JSON.stringify({message: text})})`; on
  `!response.ok` reads `error` and renders an error bubble; Clear runs
  `confirm("Clear this conversation?")` then `fetch(historyUrl,
  {method: "DELETE"})`; Enter sends, Shift+Enter inserts a newline;
  auto-scrolls to the newest bubble

## New dependencies
Exactly one new pip package: the SDK for whichever LLM provider is chosen
when this step is implemented. This spec deliberately does not name one —
pick it during implementation, add `<package>==<version>` to
`requirements.txt`, and update the "sanctioned exception" line in
`CLAUDE.md` to name it. It is the sole exception to the "no new pip
packages" rule and the sole package `ai/llm_client.py` imports. Everything
else in this step is stdlib: `os`, `json`.

## Rules for implementation
- The LLM provider and model are decided entirely inside `ai/llm_client.py`
  at implementation time. No other file — not `app.py`, not any other `ai/`
  module, not a template, not a test — names a vendor, an SDK, or a model id
- The API key is read only via `os.environ.get("LLM_API_KEY")` inside
  `get_client()` — never hardcoded, never read at import time; `python
  app.py` must start with the variable unset. `LLM_API_KEY` is a
  provider-neutral name chosen for this project; it does not need to match
  whatever environment-variable convention the chosen SDK itself defaults to
- The provider SDK is imported only in `ai/llm_client.py`; the client
  object is built lazily on first use
- `create_message()` is the only function that calls the SDK and the only
  place its exceptions are caught and translated into `AIError` subclasses
- Callers must reference the seam as `llm_client.create_message(...)` after
  `from ai import llm_client` — never `from ai.llm_client import
  create_message` — otherwise the test fake is bypassed
- Everything outside `ai/llm_client.py` — `ai/chat.py`, later
  `ai/tools/*`, `ai/receipts.py`, `ai/insights.py` — is written only
  against `create_message()`'s plain arguments and its normalized reply
  (`.text`, `.tool_calls`, `.finish_reason`). None of it may assume a
  specific vendor's request or response shape
- Nothing in `ai/` imports Flask (same rule as `database/queries.py`)
- `CHAT_SYSTEM_PROMPT` must state: you are Spendly's assistant; currency is
  always ₹ (never $ or £); the only categories are Food, Transport, Bills,
  Health, Entertainment, Shopping, Other; answer only about the user's
  finances and this app; reply in short plain text with no markdown tables or
  headers (the drawer renders plain text); never invent figures
- `system_text` must be passed as a stable constant on every call; today's
  date and the user's name are never baked into it — they always travel as
  `context_text`. If the chosen provider supports prompt caching or a
  similar optimization for a stable system prompt, `ai/llm_client.py` may
  use it internally; that is a performance detail invisible to every caller,
  never a functional requirement
- `max_tokens=CHAT_MAX_TOKENS` for chat calls. If the chosen provider
  exposes a reasoning-depth or verbosity control, tune it for a fast, short
  chat reply — this is optional tuning done inside `ai/llm_client.py`, not a
  requirement this spec dictates
- History policy: store every user and assistant text turn; send only the
  last `HISTORY_LIMIT = 20` stored rows; ensure the first sent turn has role
  `user`
- Message validation: required, stripped, at most 2000 characters; otherwise
  400 and nothing stored
- Never log message contents, prompts, tool inputs, images, or raw provider
  responses; on failure log only the exception class name
- Do not hold a SQLite connection open across the API call: read history →
  close → call the LLM → insert rows
- JSON endpoints return `401 {"error": "Authentication required."}` when
  logged out; they never use `abort()` and never redirect
- Read bodies with `request.get_json(silent=True)`; a non-JSON body is a 400.
  The app has no CSRF protection; requiring a JSON body is the only barrier
  on these endpoints and the spec must not claim more
- `chat.js` must render message text with `textContent`, never `innerHTML`
- The drawer is only rendered when `session.get('user_id')` is set; landing,
  login and register pages must not include it
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Foreign keys PRAGMA must be enabled on every connection (already done in
  `get_db()`)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html` (the drawer partial is an `include`, not
  a page)
- No inline styles
- Currency must always display as ₹ — never £ or $

## Tests to write
File: `tests/test_ai_chat_interface.py`

Shared fake, added to `tests/conftest.py` in this step and reused by Steps
11–14 (no test may ever require `LLM_API_KEY`, and no test may import a
provider SDK):

```python
from types import SimpleNamespace

def text_reply(text, finish_reason="stop"):
    return SimpleNamespace(text=text, tool_calls=[], finish_reason=finish_reason)

def tool_call_reply(name, tool_input, tool_id="call_01", text=None):
    call = SimpleNamespace(id=tool_id, name=name, input=tool_input)
    return SimpleNamespace(text=text or "", tool_calls=[call], finish_reason="tool_calls")

class FakeLLM:
    def __init__(self):
        self.responses = []   # queue; an Exception entry is raised
        self.calls = []       # kwargs of every create_message call

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr("ai.llm_client.create_message", fake)
    return fake
```

The 503 test uses `monkeypatch.delenv("LLM_API_KEY", raising=False)` and
does not use the fake.

### Unit tests
| Function | Input | Expected output |
|---|---|---|
| `insert_chat_message` | `user_id=1, role="user", content="hi"` | row exists with that role and content; returns an int id |
| `get_chat_messages` | 3 rows inserted, no limit | 3 dicts oldest-first, each with `id`, `role`, `content`, `created_at` |
| `get_chat_messages` | 5 rows, `limit=2` | the 2 newest rows, still oldest-first |
| `get_chat_messages` | rows for two users | only the requested user's rows |
| `delete_chat_messages` | user with 2 rows, other user with 1 | returns 2; requesting user has none left; other user's row intact |
| `build_messages` | 25 alternating rows, new text | 21 turns; first role is `user`; last is the new text |
| `build_messages` | a 20-row window whose first row is `assistant` | leading assistant row dropped; first role is `user` |
| `build_turn_context` | `user_name="Demo User", today=date(2026, 9, 7)` | contains `"Today is 2026-09-07."` and `"Demo User"` |
| `run_chat_turn` (with `fake_llm`) | fake returns `text_reply("Hello")` | `reply == "Hello"`; `fake.calls[0]["system_text"] == CHAT_SYSTEM_PROMPT`; `fake.calls[0]["context_text"]` contains `"Today is"`; `len(fake.calls[0]["turns"]) == 21` for a 30-row history |
| `run_chat_turn` | fake returns `finish_reason="refused"` | reply is the refusal sentence; no exception |
| `get_client` | `LLM_API_KEY` unset | raises `AIConfigError` without touching the network |
| `create_message` | key unset | raises `AIConfigError` |

### Route tests
`GET /api/chat/history` — unauthenticated:
- Returns 401 with JSON body containing `error`

`GET /api/chat/history` — authenticated, two stored rows:
- Returns 200; `messages` has 2 entries oldest-first with `role` and
  `content`

`POST /api/chat` — unauthenticated:
- Returns 401 JSON

`POST /api/chat` — authenticated, valid message, fake queued
`text_reply("Sure")`:
- Returns 200 `{"reply": "Sure"}`
- DB has a `user` row then an `assistant` row for this user, in that order

`POST /api/chat` — authenticated, blank message:
- Returns 400; nothing stored

`POST /api/chat` — authenticated, 2001-character message:
- Returns 400; nothing stored

`POST /api/chat` — authenticated, non-JSON body:
- Returns 400

`POST /api/chat` — authenticated, `LLM_API_KEY` unset, no fake:
- Returns 503 with the "not configured" message; nothing stored

`POST /api/chat` — authenticated, fake raises `AIUnavailableError`:
- Returns 502; nothing stored

`POST /api/chat` — authenticated, fake raises `AIRateLimitError`:
- Returns 429; nothing stored

`DELETE /api/chat/history` — authenticated, three rows:
- Returns 200 `{"cleared": 3}`; rows gone

`GET /profile` — authenticated:
- Body contains `id="chat-drawer"` and `js/chat.js`

`GET /` — unauthenticated:
- Body does not contain `chat-drawer`

## Definition of done
- [ ] `pip install -r requirements.txt` installs the chosen provider's SDK; `python app.py` starts with no `LLM_API_KEY` set
- [ ] Logged-out pages show no chat drawer; logged-in pages show a floating toggle bottom-right
- [ ] Sending a message with a valid key returns a reply, and amounts in the reply use ₹
- [ ] Sending a message with no key shows the "not configured" error bubble and nothing else breaks
- [ ] Reloading the page restores the conversation from SQLite
- [ ] "Clear" empties the conversation after confirmation
- [ ] Drawer open/closed state persists across page navigation
- [ ] Drawer respects dark mode without any hardcoded colours
- [ ] All tests in `tests/test_ai_chat_interface.py` pass without `LLM_API_KEY` set and without importing any provider SDK
