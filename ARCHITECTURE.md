# Architecture

WISEX (formerly Spendly) is a personal expense tracker: server-rendered Flask
app, SQLite storage, and an LLM-backed chat assistant. This doc is a brief
orientation — for the authoritative rules on where code belongs, see
`CLAUDE.md`.

## Stack

| Layer | Choice |
|---|---|
| Backend | Flask 3, single-process, no blueprints |
| Database | SQLite, hand-written SQL (no ORM) |
| Frontend | Server-rendered Jinja2 templates, vanilla CSS, vanilla JS |
| AI / LLM | Groq API, isolated behind one seam (`ai/llm_client.py`) |
| Tests | pytest + pytest-flask |

No frontend framework, no build step, no ORM — everything ships as plain
files the Flask dev server serves directly.

## Request flow

```
browser → app.py route → database/queries.py (SQL)  → template render
                        → ai/chat.py (AI routes only) → ai/llm_client.py → Groq
```

- **`app.py`** — every route lives here (registration, login, expenses,
  accounts, `/api/chat*`). A route's job is: read the session, call a
  `queries.py`/`ai/` function, render a template or return JSON. No SQL and
  no LLM calls happen inline in a route.
- **`database/`** — `db.py` owns the schema (`init_db`), demo data
  (`seed_db`), password hashing, and the `CATEGORIES`/`ACCOUNT_TYPES`
  constants. `queries.py` owns every other SQL statement, always
  parameterized, always returning plain dicts (never a raw `sqlite3.Row`).
  SQLite foreign keys are off by default, so `get_db()` enables
  `PRAGMA foreign_keys = ON` on every connection.
- **`ai/`** — the assistant layer. No file in here imports Flask; no file
  outside `ai/llm_client.py` imports the Groq SDK or names a model. See
  below.
- **`templates/` + `static/`** — one template per page, all extending
  `base.html`; one CSS file per page/feature; small vanilla-JS files loaded
  per page via `{% block scripts %}` (site-wide JS — the theme toggle —
  lives in `base.html` itself).

## The AI layer

The assistant is a **tool-calling agent**: the LLM itself never touches
SQLite. It can only read or change data by emitting a *tool call* — a
structured `{name, input}` request — which Flask-side Python code validates,
executes against `database/queries.py`, and feeds the result back to the
model as text. The model never sees a connection string, a table name, or
SQL; it only sees the small, named, schema-checked operations it's been
handed.

```
                         ┌─────────────────────────────────────────────┐
                         │              ai/chat.run_chat_turn()          │
browser                  │                                               │
  │  POST /api/chat      │   1. build_messages()  → last 20 turns        │
  ▼                      │   2. build_turn_context() → date, name,       │
app.py: chat_send()  ───►│      net-worth snapshot (CONTEXT_PROVIDERS)   │
  reads session[user_id] │   3. loop (≤ 8 rounds):                       │
  loads chat history     │        create_message(system, context, turns,│
                         │                        tools=get_tool_definitions())
                         │        finish_reason == "tool_calls"?         │
                         │          ├─ yes → execute_tool(name, input,   │
                         │          │        user_id) for each call      │
                         │          │        → append tool_result turns  │
                         │          │        → loop again                │
                         │          └─ no  → done, return reply text     │
                         └─────────────────────┬─────────────────────────┘
                                                │
                                  ai/tools/registry.execute_tool()
                                                │
                        ┌───────────────────────┴───────────────────────┐
                        │                                                │
              ai/tools/expenses.py                              ai/tools/accounts.py
              list / add / update / delete                      list / add / update
                        │                                        balance / delete
                        └──────────────────┬─────────────────────────────┘
                                            │  handler(user_id, tool_input)
                                            ▼
                                database/queries.py
                        (parameterized SQL, every WHERE scoped
                         to `user_id = ?`)
                                            │
                                            ▼
                                       SQLite file
```

### How the model reads, writes, updates and deletes data

The model never gets raw DB access — it gets a fixed menu of **tools**,
each one a thin, validated wrapper around one `database/queries.py`
function:

| Tool | Mutating? | `queries.py` call | What it does |
|---|---|---|---|
| `list_expenses` | no (read) | `get_recent_transactions` | Searches the user's expenses by date range / category — the model calls this first to find an `id` before editing or deleting anything |
| `add_expense` | yes (create) | `insert_expense` | Validates amount/category/date/description, then inserts a row |
| `update_expense` | yes (update) | `get_expense_by_id` + `update_expense` | Loads the existing row (to fill in any field left `null`), re-validates the merged result, then updates |
| `delete_expense` | yes (delete) | `delete_expense_by_id` | Deletes one row by id |
| `list_accounts` / `get_net_worth` | no (read) | `get_accounts` / `get_net_worth` | Reads the user's accounts and computed net worth |
| `add_account` | yes (create) | `insert_account` | Validates name/type/balance, then inserts a row |
| `update_account_balance` | yes (update) | `get_account_by_id` + `update_account` | Loads the account, re-validates, updates its balance |
| `delete_account` | yes (delete) | `delete_account_by_id` | Deletes one row by id |

That table *is* the AI's entire read/write surface — there is no generic
"run SQL" or "run arbitrary query" tool, and there never should be.

**How each layer keeps this safe:**

1. **Schema-constrained input.** Every tool's `input_schema` (in
   `ai/tools/*.py`) sets `additionalProperties: false` and lists every
   field as `required` — Groq rejects a tool call with an extra or missing
   field before it ever reaches Python. Enums (`CATEGORIES`,
   `ACCOUNT_TYPES`) constrain string fields to real values.
2. **Ownership is never model-supplied.** `execute_tool(name, tool_input,
   user_id)` in `ai/tools/registry.py` always calls
   `handler(user_id, tool_input)` with `user_id` taken from
   `session["user_id"]` in the Flask route (`app.py: chat_send()`) — the
   model's tool-call JSON has no `user_id` field to spoof. Every
   `queries.py` read/write scopes its `WHERE`/`INSERT` to that same
   `user_id` (e.g. `delete_expense_by_id`: `DELETE FROM expenses WHERE id
   = ? AND user_id = ?`), so one user's chat session structurally cannot
   touch another user's rows, and a bogus id just yields "not found"
   (`rowcount == 0`) rather than an error leaking whether the row exists
   for someone else.
3. **Same validation as the web forms, re-run server-side.** `add_expense`
   and `update_expense` both call the same `_validate_expense_fields()`
   used elsewhere (amount > 0, category in `CATEGORIES`, valid date,
   description ≤ 200 chars); accounts have the analogous
   `_validate_account_fields()`. The model can *ask* for anything; the
   handler still enforces the real constraints and returns
   `{"error": "..."}` (fed back to the model as a `tool_result`, not
   trusted) instead of writing bad data.
4. **Every write still goes through `database/queries.py`'s parameterized
   SQL** — same `?`-placeholder discipline as every other code path in the
   app. A tool handler is not allowed to build or run SQL itself.
5. **Deletes require an explicit, in-turn user confirmation** — enforced
   only by prompt instruction, not by code: `delete_expense`'s and
   `delete_account`'s tool `description` explicitly tell the model to only
   call them "after the user has explicitly confirmed, in their most
   recent message, that they want this specific [expense/account]
   deleted" and to describe the item and ask first otherwise. This is a
   soft guardrail (the model could misbehave), not a hard one — there is
   no server-side "are you sure" step between a `delete_expense` tool call
   and the row actually being deleted.
6. **The tool loop is bounded.** `ai/chat.py: run_chat_turn()` calls
   `create_message()` and, whenever `finish_reason == "tool_calls"`,
   executes every requested tool and appends each result as a
   `tool_result` turn before looping back for another model turn — up to
   `MAX_TOOL_ROUNDS = 8`. This lets the model chain calls (e.g.
   `list_expenses` to find an id, then `delete_expense` on it) within one
   user message, while capping runaway loops.
7. **The dashboard reflects writes immediately.** `chat_send()` checks
   `is_mutating(tool_name)` for every tool the model actually invoked; if
   any of them mutate data, the JSON response sets `"refresh": true` and
   `static/js/chat.js` reloads the page data — so an expense added or
   deleted via chat shows up without a manual refresh.
8. **What gets stored vs. what's ephemeral.** Only the user's message and
   the model's final reply text are written to `chat_messages` — the
   intermediate tool-call/tool-result turns are never persisted; they
   exist only for the duration of one `run_chat_turn()` call. Every chat
   turn is re-supplied with the last 20 stored messages plus a freshly
   built `context_text` (today's date, user's name, current net-worth
   snapshot via `CONTEXT_PROVIDERS`) — so the model always reasons over
   live data, not a stale cached copy.

### Everything else in the AI layer

- **`ai/llm_client.py`** is the only file that imports the Groq SDK or names
  a model. It exposes one seam, `create_message(system_text, context_text,
  turns, tools=None, response_schema=None, image=None)`, returning a
  normalized reply (`.text`, `.tool_calls`, `.finish_reason`). Every other
  file — routes, templates, tests — is provider-agnostic. Tests replace this
  one function with the `fake_llm` fixture, so nothing in the suite touches
  the network or imports `groq`.
- **`ai/prompts.py`** holds the stable system prompt as a constant.
  Volatile per-turn context (today's date, user name, net-worth snapshot)
  is passed separately as `context_text` — it's never baked into the
  prompt string.
- **`ai/tools/registry.py`** is the plumbing shared by every tool module:
  `register_tool(definition, mutating=...)` is a decorator that files a
  tool's JSON schema + handler + mutating flag into an in-process registry
  at import time; `get_tool_definitions()` hands the whole schema list to
  `create_message()`; `execute_tool()` looks up a call by name, runs its
  handler, and catches any handler exception into a `{"error": ...}`
  tool-result rather than letting it crash the request.
- **`ai/insights.py`** — rule-based budget insights (spending trend vs.
  last month, category deltas, etc.) computed directly from
  `database/queries.py` aggregates. No LLM call, and not a registered
  tool — it feeds the `/profile` page's insights card directly, not chat.
- **`ai/receipts.py`** — receipt image intake: magic-byte type detection
  (`imghdr` doesn't exist on Python 3.13+) and structured extraction via
  the same `create_message` seam, using `response_schema` to get back
  normalized `{amount, category, date, description}` fields. This *reads*
  an image and *proposes* an expense — it never writes to the database
  itself; the browser still calls `POST /api/expenses` to actually save
  the parsed result, so a bad extraction never silently creates a row.
- **Error handling** — routes catch `ai.llm_client.AIError` and map
  `.status` → 503 (not configured), 429 (rate limited), 502 (anything
  else). The API key comes only from `os.environ["LLM_API_KEY"]`, read
  lazily (never at import time, never hardcoded) — the app boots and every
  non-AI page works with no key set.
- Prompts, messages, tool inputs, images, and raw provider responses are
  never logged.

## Practices and conventions

- **PEP 8**, snake_case throughout.
- **Parameterized SQL only** — no f-strings ever touch a query string.
- **`url_for()`** for every internal link in templates — no hardcoded URLs.
- **`abort()`** for HTTP errors — no bare `return "error string"`.
- **400, not 200**, on validation failures that re-render a form.
- **JSON API routes** (`/api/...`) return `401 {"error": ...}` when logged
  out; HTML pages redirect to `/login`.
- **No new pip packages** without updating `requirements.txt` and
  flagging it — the only sanctioned addition is `groq`, for
  `ai/llm_client.py`.
- **No JS framework, no CSS framework** — vanilla only, one CSS file per
  page/feature with a matching class prefix, hand-inlined SVG icons
  (no icon-font/CDN dependency).

## Dev workflow (this repo's own tooling)

Feature work follows a fixed pipeline, driven by the slash commands and
subagents under `.claude/`:

```
/create-spec <N> <name>  →  implement  →  /test-feature <slug>
    →  /code-review-feature <slug>  →  /ship-feature
```

- `.claude/specs/*.md` — one spec per shipped feature; the durable design
  record for "why does this route/table/tool look like this."
- `.claude/agents/` — `spendly-test-writer` / `spendly-test-runner` /
  `spendly-quality-reviewer` / `spendly-security-reviewer`, invoked by the
  commands above.
- `.claude/skills/frontend-design/` — house style for generating new UI
  (Nocturne palette, layout and icon conventions).
- `PLAN_AI.md` — the (now fully checked-off) roadmap that took the AI
  layer from nothing to Steps 10–14; kept as a historical record of what
  shipped in what order.

## Tests

`tests/` is one file roughly per shipped feature (`pytest`, `pytest-flask`).
`conftest.py` provides the Flask test client fixture and `FakeLLM` — the
fake that backs `fake_llm` and stands in for `ai.llm_client.create_message`
in every test, so the suite never needs `LLM_API_KEY` and never imports the
Groq SDK.

## Known naming/documentation quirks

- `seed_db()` inserts demo data totalling ₹318.24; an older spec says
  ₹346.24 — that's a stale spec number, not a bug.
- The app runs on **port 5001**, not Flask's default 5000.
