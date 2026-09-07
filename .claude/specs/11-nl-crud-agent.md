# Spec: NL CRUD Agent

## Overview
Step 11 turns the chat assistant into an agent that can create, find, edit
and delete the user's own expenses from natural language ("add 250 for lunch
today", "change yesterday's cab to 180", "delete the pharmacy one"). It
introduces an extensible tool registry in `ai/tools/`, four strict-schema
tools backed by the existing `database/queries.py` helpers, and a hand-written
loop in `ai/chat.py` that calls `llm_client.create_message()`, executes any
tool calls the reply asks for with the session user's id, and feeds the
results back until the model stops asking for tools. The loop is written
entirely against the provider-neutral contract from Step 10 (`.text`,
`.tool_calls`, `.finish_reason`) — it never touches a vendor-specific
response shape, so it needs no changes when a provider is chosen or later
swapped. Every tool runs with `session["user_id"]` supplied by the route —
the model never sees or supplies a user id. Deleting requires the model to
obtain explicit confirmation in conversation before calling the tool. When a
mutating tool runs, the chat endpoint tells the drawer to refresh the page so
the profile reflects the change. Steps 13 and 14 add their own tool modules
to the registry without editing this step's code.

## Depends on
- Step 7: Add Expense (`insert_expense`, validation rules for amount /
  category / date / description)
- Step 8: Edit Expense (`get_expense_by_id`, `update_expense`, ownership
  scoping)
- Step 9: Delete Expense (`delete_expense_by_id`)
- Step 10: AI Chat Interface (the `create_message` seam and its normalized
  reply shape, `run_chat_turn`, `build_messages`, the drawer, and
  `fake_llm` / `tool_call_reply` / `text_reply` in `tests/conftest.py`)

## Routes
No new routes. The existing `POST /api/chat` response gains one field:
- `200 {"reply": str, "refresh": bool}` — `refresh` is `true` when any
  mutating tool ran during the turn

## Database changes
No database changes.

## Templates
- **Modify**: `static/js/chat.js` (no template changes)
  - After rendering a reply whose JSON has `refresh === true`, call
    `window.location.reload()` after roughly 600 ms so the user sees the
    reply before the page refreshes; drawer state (localStorage) and
    history (DB) survive the reload

## Files to change
- `ai/chat.py`
  - `MAX_TOOL_ROUNDS = 8`
  - `run_chat_turn` now runs a loop instead of a single call:
    1. `turns = build_messages(history, user_text)`
    2. `tools_used = []`, `rounds = 0`
    3. Loop: call `llm_client.create_message(system_text=CHAT_SYSTEM_PROMPT,
       context_text=build_turn_context(...), turns=turns,
       tools=get_tool_definitions())`
    4. If the reply's `finish_reason` is not `"tool_calls"`, or
       `rounds >= MAX_TOOL_ROUNDS`, stop looping
    5. Otherwise append `{"role": "assistant", "content": reply.text,
       "tool_calls": [{"id": c.id, "name": c.name, "input": dict(c.input)}
       for c in reply.tool_calls]}` to `turns`
    6. For each tool call, run `execute_tool(c.name, dict(c.input),
       user_id)` → `(content_json, is_error)`; append
       `{"role": "tool_result", "tool_call_id": c.id,
       "content": content_json, "is_error": is_error}` to `turns`; record
       `c.name` in `tools_used`
    7. Increment `rounds` and repeat from step 3
    8. If the loop stopped because the round cap was hit, the reply is "I
       couldn't finish that request. Please try a simpler instruction."
       Otherwise it is the last reply's `.text` (or "Done." if empty)
  - Return `{"reply": str, "tools_used": [str, ...]}`
- `ai/prompts.py` — append a "Tools" paragraph to `CHAT_SYSTEM_PROMPT`: use
  `list_expenses` to find an expense's id before editing or deleting; before
  deleting, restate the expense (date, description, amount) and wait for a
  yes; after any change, state exactly what changed including the amount in
  ₹; dates are ISO `YYYY-MM-DD`; resolve relative dates ("yesterday", "last
  Friday") from the "Today is" line in the context
- `app.py` — import `is_mutating` from `ai.tools`; `chat_send` computes
  `refresh = any(is_mutating(name) for name in result["tools_used"])` and
  includes it in the JSON response
- `static/js/chat.js` — reload on `refresh`

## Files to create
- `ai/tools/__init__.py`
  ```python
  from ai.tools.registry import register_tool, get_tool_definitions, execute_tool, is_mutating
  from ai.tools import expenses  # noqa: F401 — registers the expense tools
  ```
  Steps 13 and 14 each append exactly one more import line here.
- `ai/tools/registry.py`
  - `_TOOLS = {}` mapping tool name → `{"definition": dict,
    "handler": callable, "mutating": bool}`
  - `register_tool(definition, mutating=False)` — decorator; registering a
    name that already exists replaces it (safe under module reloads)
  - `get_tool_definitions()` — definitions in registration order (order is
    deterministic, which keeps behaviour reproducible across calls)
  - `is_mutating(name)` — `False` for unknown names
  - `execute_tool(name, tool_input, user_id)` → `(content_json_str,
    is_error)`; wraps the handler in `try/except Exception`; unknown tool or
    exception → `('{"error": "..."}', True)`; never raises
  - Handler contract: `handler(user_id, tool_input) -> dict`; the registry
    `json.dumps` the dict
- `ai/tools/expenses.py` — four tools, every `input_schema` sets
  `"additionalProperties": false` and lists every property in `required`
  (optional fields use `"type": ["string", "null"]` etc., so "not
  provided" is expressed as an explicit `null` rather than an absent key):
  - `list_expenses` — input `{date_from: string|null, date_to: string|null,
    category: enum(CATEGORIES)|null, limit: integer 1–50}` → output
    `{"expenses": [{id, date, description, category, amount}]}`. Wraps
    `get_recent_transactions(user_id, limit, date_from, date_to)`; because
    `_user_date_filter` only filters when both bounds are present, a missing
    bound is filled with `"0000-01-01"` / `"9999-12-31"`; category is
    filtered in Python. Description must say: "Search the user's expenses.
    Call this first to find the id before editing or deleting."
  - `add_expense` — input `{amount: number, category: enum(CATEGORIES),
    date: string, description: string|null}` → `{"ok": true,
    "expense": {...}}`. Mutating.
  - `update_expense` — input `{expense_id: integer, amount: number|null,
    category: enum|null, date: string|null, description: string|null}`;
    `null` means "keep the current value". Loads via
    `get_expense_by_id(expense_id, user_id)`, merges, validates, calls
    `update_expense(...)`. Not found → `{"error": "Expense not found."}`
    with `is_error`. Mutating.
  - `delete_expense` — input `{expense_id: integer}`. Description text is
    load-bearing and must read: "Permanently delete one expense. Only call
    this after the user has explicitly confirmed, in their most recent
    message, that they want this specific expense deleted. If they have not
    confirmed, describe the expense and ask first." Mutating.
  - `_validate_expense_fields(amount, category, date_str, description)` →
    error message or `None`, with the same rules as `app.py`: float > 0,
    category in `CATEGORIES`, `datetime.strptime(date_str, "%Y-%m-%d")`,
    description ≤ 200 characters, blank description → `None`. This duplicates
    the route validation because `ai/` cannot import `app.py`; note it as a
    candidate for a shared helper in a future step.

## New dependencies
No new dependencies (stdlib `json`, `datetime`).

## Rules for implementation
- `user_id` is never a tool parameter: handlers receive it from
  `execute_tool`, which receives it from the route's `session["user_id"]`.
  No `input_schema` may declare a `user_id` property, and
  `additionalProperties: false` means a model that tries to supply one gets
  rejected before the handler ever runs
- Every tool's `input_schema` sets `additionalProperties: false` and lists
  every property in `required`
- Tool results are JSON strings; failures return `is_error: True` and never
  raise out of `execute_tool`
- When a reply asks for more than one tool call, all of them are executed
  and all of their results are appended to `turns` before calling
  `create_message` again
- Only user text and the final assistant text are stored in
  `chat_messages`; the intermediate tool-call and tool-result entries that
  accumulate in `turns` during the loop live only for the duration of one
  `run_chat_turn` call and are never persisted or replayed across requests.
  Justification: the final text already summarises what happened, storing
  only it keeps `chat_messages` simple and human-readable, and the exact
  structure needed to resume a tool conversation is an internal concern of
  `ai/llm_client.py`, not something `chat_messages` should have to preserve.
  The cost is that the model must call `list_expenses` again in a later turn
  to recover ids, which is cheap
- Hard cap `MAX_TOOL_ROUNDS = 8`
- Delete confirmation is enforced at the prompt level: the `delete_expense`
  description and the system prompt both require restating the expense and
  waiting for a yes. Trade-off: a two-phase confirm-token protocol (the tool
  returns a token the second call must echo) is stricter and testable as a
  state machine, but doubles the tool surface for a single row the user can
  re-add; the prompt-level guard is proportionate here
- Handlers reuse `database/queries.py` helpers only — no SQL in `ai/`
- Validation rules are identical to the HTML forms; validation failures are
  tool errors, not exceptions
- Tool definition order is registration order and must not depend on dict
  or set iteration
- Parse tool call input as a dict (`dict(call.input)`); never string-match
  the serialised input
- `refresh` is computed in the route from `is_mutating`; read-only tools
  never trigger a reload
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Foreign keys PRAGMA must be enabled on every connection (already done in
  `get_db()`)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- Currency must always display as ₹ — never £ or $

## Tests to write
File: `tests/test_nl_crud_agent.py`

### Unit tests
| Function | Input | Expected output |
|---|---|---|
| `get_tool_definitions` | — | names are exactly `["list_expenses", "add_expense", "update_expense", "delete_expense"]` in that order; each `input_schema["additionalProperties"] is False` and lists every property in `required`; none has a `user_id` property |
| `is_mutating` | each of the four names | `False` for `list_expenses`, `True` for the other three; `False` for an unknown name |
| `execute_tool` | `"add_expense"`, valid input, `user_id=1` | returns `(json, False)`; a row exists in `expenses` with `user_id=1` |
| `execute_tool` | `"add_expense"`, `amount=-5` | `is_error True`; no row inserted |
| `execute_tool` | `"add_expense"`, `category="Rent"` | `is_error True` |
| `execute_tool` | `"add_expense"`, input also containing `user_id=2` | row created for `user_id=1`; the extra key is ignored |
| `execute_tool` | `"update_expense"` with only `amount` set | amount updated; category, date, description unchanged |
| `execute_tool` | `"update_expense"` on another user's id | `is_error True`; row unchanged |
| `execute_tool` | `"delete_expense"` on own id | row gone; `(json, False)` |
| `execute_tool` | `"delete_expense"` on another user's id | `is_error True`; row remains |
| `execute_tool` | `"list_expenses"` with `category="Food"` | only Food rows, all owned by the user |
| `execute_tool` | `"list_expenses"` with only `date_from` | rows on/after that date are returned (missing bound filled) |
| `execute_tool` | unknown name | `is_error True`, no exception |
| `run_chat_turn` (fake) | `tool_call_reply("add_expense", {...})` then `text_reply("Added ₹250")` | reply `"Added ₹250"`; `tools_used == ["add_expense"]`; expense exists; `fake.calls[1]["turns"]` contains a `{"role": "tool_result", ...}` entry; `fake.calls[1]["tools"]` is non-empty |
| `run_chat_turn` (fake) | one reply with two tool calls | the next call's `turns` contains two `tool_result` entries |
| `run_chat_turn` (fake) | 9 consecutive `tool_calls` replies | stops after 8 rounds with the "couldn't finish" reply |
| `run_chat_turn` (fake) | tool handler raises | the resulting `tool_result` entry has `is_error True`; loop continues to the fake's next response |

### Route tests
`POST /api/chat` — authenticated, fake runs `add_expense` then replies:
- Returns 200 with `refresh: true`
- New expense row belongs to the logged-in user
- Stored history has exactly one `user` row and one `assistant` row (no
  tool-call or tool-result rows)

`POST /api/chat` — authenticated, fake replies with text only:
- Returns 200 with `refresh: false`

`POST /api/chat` — authenticated as user B, fake calls `delete_expense` with
user A's expense id:
- Returns 200; user A's row still exists

`POST /api/chat` — authenticated, fake calls `list_expenses`:
- The `tool_result` entry in `fake.calls[1]["turns"]` contains only this
  user's expenses

`POST /api/chat` — authenticated, fake calls an unknown tool name:
- Returns 200; the resulting `tool_result` entry has `is_error: true`

## Definition of done
- [ ] "Add 250 for lunch today" creates a Food / ₹250 / today expense and the profile table refreshes to show it
- [ ] "Change that to 300" updates the same expense
- [ ] "Delete it" first gets a restatement and a confirmation question; "yes" then deletes it
- [ ] Asking to delete an id that belongs to another user results in a "not found" reply and no change
- [ ] Invalid inputs (negative amount, unknown category, bad date) produce a helpful reply, not a 5xx
- [ ] Stored chat history contains only readable text turns
- [ ] Read-only requests ("show my food expenses") do not reload the page
- [ ] All tests in `tests/test_nl_crud_agent.py` pass without `LLM_API_KEY`
