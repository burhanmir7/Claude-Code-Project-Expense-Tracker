# AI Chat Interface (Step 10) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent, per-user AI chat drawer (talk-only, no tools yet) backed by three JSON endpoints and a new `chat_messages` table, using Google Gemini as the LLM provider behind a provider-neutral seam.

**Architecture:** A new `ai/` package (`llm_client.py`, `prompts.py`, `chat.py`) isolates all LLM concerns from Flask and SQLite. `ai/llm_client.py` is the only file that imports the `google-genai` SDK; it exposes `create_message()`, a normalized function returning `.text` / `.tool_calls` / `.finish_reason`, and translates every SDK failure into an `AIError` subclass. `ai/chat.py` builds the turn history and calls the seam. `app.py` wires three new `/api/chat*` routes to `database/queries.py` helpers and `ai/chat.py`. A vanilla-JS drawer (`static/js/chat.js`) talks only to Spendly's own endpoints, never to Gemini directly.

**Tech Stack:** Flask, raw `sqlite3`, vanilla JS (ES5 IIFE), `google-genai` (Gemini SDK, free tier), pytest.

**Spec:** `.claude/specs/10-ai-chat-interface.md`

## Global Constraints

- The API key is read only via `os.environ.get("LLM_API_KEY")` inside `get_client()` — never hardcoded, never read at import time; `python app.py` must boot with the variable unset.
- The provider SDK (`google-genai`) is imported only in `ai/llm_client.py`. Every other file calls `llm_client.create_message(...)` after `from ai import llm_client` — never `from ai.llm_client import create_message` (that bypasses the test fake).
- Nothing outside `ai/llm_client.py` may assume Gemini's request/response shape — only `create_message()`'s plain arguments and its normalized reply (`.text`, `.tool_calls`, `.finish_reason`).
- Nothing in `ai/` imports Flask.
- No SQLAlchemy/ORM — raw `sqlite3` via `get_db()` only. Parameterised queries only — never string-format values into SQL.
- `PRAGMA foreign_keys = ON` is already set in `get_db()` for every connection.
- Tests must never require `LLM_API_KEY` and must never import `google.genai` — always use the `fake_llm` fixture, which patches `ai.llm_client.create_message`.
- JSON endpoints return `401 {"error": "Authentication required."}` when logged out; they never use `abort()` and never redirect.
- Never log message contents, prompts, tool inputs, images, or raw provider responses; on failure log only the exception class name.
- `chat.js` renders message text with `textContent`/DOM APIs only, never `innerHTML` with dynamic content.
- CSS uses tokens only (`--paper-card`, `--border`, `--accent`, `--accent-light`, `--paper-warm`, `--danger-light`, `--ink`, `--radius-lg`, `--font-body`) — no hardcoded hex values, no inline styles.
- Currency in any assistant-facing copy is always ₹, never $ or £.
- Follow existing repo conventions: `conn = get_db(); try: ... finally: conn.close()` in every query helper; each test file defines its own local `new_user_id_for(client)` helper (the repo does not share it via `conftest.py`).

---

### Task 1: `chat_messages` schema + query helpers

**Files:**
- Modify: `database/db.py` (add DDL inside `init_db()`, after the `expenses` table block)
- Modify: `database/queries.py` (add `get_chat_messages`, `insert_chat_message`, `delete_chat_messages`)
- Test: `tests/test_ai_chat_interface.py` (new file)

**Interfaces:**
- Produces: `get_chat_messages(user_id, limit=None) -> list[dict]` (each dict has `id`, `role`, `content`, `created_at`; oldest-first; when `limit` is given, returns the newest `limit` rows, still oldest-first). `insert_chat_message(user_id, role, content) -> int` (new row id). `delete_chat_messages(user_id) -> int` (rows deleted).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ai_chat_interface.py`:

```python
from database.queries import delete_chat_messages, get_chat_messages, insert_chat_message


# ------------------------------------------------------------------ #
# chat_messages query helpers                                        #
# ------------------------------------------------------------------ #

def test_insert_chat_message_creates_row(client):
    message_id = insert_chat_message(1, "user", "hi")

    assert isinstance(message_id, int)
    rows = get_chat_messages(1)
    assert rows[-1]["role"] == "user"
    assert rows[-1]["content"] == "hi"


def test_get_chat_messages_oldest_first(client):
    insert_chat_message(1, "user", "one")
    insert_chat_message(1, "assistant", "two")
    insert_chat_message(1, "user", "three")

    rows = get_chat_messages(1)

    assert len(rows) == 3
    assert [r["content"] for r in rows] == ["one", "two", "three"]
    for row in rows:
        assert set(row.keys()) == {"id", "role", "content", "created_at"}


def test_get_chat_messages_respects_limit(client):
    for i in range(5):
        insert_chat_message(1, "user", "msg%d" % i)

    rows = get_chat_messages(1, limit=2)

    assert [r["content"] for r in rows] == ["msg3", "msg4"]


def test_get_chat_messages_scoped_to_user(client):
    register_new_user(client)
    other_user_id = new_user_id_for(client)

    insert_chat_message(1, "user", "demo user message")
    insert_chat_message(other_user_id, "user", "other user message")

    rows = get_chat_messages(1)

    assert len(rows) == 1
    assert rows[0]["content"] == "demo user message"


def test_delete_chat_messages_scoped_to_user(client):
    register_new_user(client)
    other_user_id = new_user_id_for(client)

    insert_chat_message(1, "user", "a")
    insert_chat_message(1, "assistant", "b")
    insert_chat_message(other_user_id, "user", "c")

    deleted = delete_chat_messages(1)

    assert deleted == 2
    assert get_chat_messages(1) == []
    assert len(get_chat_messages(other_user_id)) == 1


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def register_new_user(client, name="New User", email="new@example.com", password="pass1234"):
    client.post(
        "/register",
        data={
            "name": name,
            "email": email,
            "password": password,
            "confirm_password": password,
        },
    )
    client.post("/login", data={"email": email, "password": password})


def new_user_id_for(client):
    from database.db import get_user_by_email

    return get_user_by_email("new@example.com")["id"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ai_chat_interface.py -v`
Expected: FAIL with `ImportError: cannot import name 'get_chat_messages'` (or similar) since none of these functions exist yet.

- [ ] **Step 3: Add the `chat_messages` table**

In `database/db.py`, inside `init_db()`, add immediately after the closing `""")` of the `expenses` table block:

```python
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
```

- [ ] **Step 4: Add the query helpers**

Append to `database/queries.py`:

```python
def get_chat_messages(user_id, limit=None):
    conn = get_db()
    try:
        query = "SELECT id, role, content, created_at FROM chat_messages WHERE user_id = ? ORDER BY id DESC"
        params = [user_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    rows = list(reversed(rows))
    return [
        {"id": row["id"], "role": row["role"], "content": row["content"], "created_at": row["created_at"]}
        for row in rows
    ]


def insert_chat_message(user_id, role, content):
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO chat_messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def delete_chat_messages(user_id):
    conn = get_db()
    try:
        cursor = conn.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_ai_chat_interface.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 6: Commit**

```bash
git add database/db.py database/queries.py tests/test_ai_chat_interface.py
git commit -m "feat: add chat_messages table and query helpers"
```

---

### Task 2: `ai/llm_client.py` — Gemini seam

**Files:**
- Create: `ai/__init__.py` (empty)
- Create: `ai/llm_client.py`
- Modify: `requirements.txt` (add `google-genai`)
- Test: `tests/test_ai_chat_interface.py` (append)

**Interfaces:**
- Produces: `MODEL`, `CHAT_MAX_TOKENS`, `EXTRACT_MAX_TOKENS`, `REQUEST_TIMEOUT_SECONDS` constants; `AIError` (base, `.status`, `.user_message`), `AIConfigError` (503), `AIRateLimitError` (429), `AIUnavailableError` (502); `get_client()`; `create_message(system_text, context_text="", turns=None, tools=None, response_schema=None, image=None)` returning an object with `.text`, `.tool_calls`, `.finish_reason`.

**Step 0 — verify the SDK's actual API surface before writing code against it.** The Gemini `google-genai` SDK evolves; introspect the installed version instead of trusting memorized signatures:

```bash
pip install google-genai
pip show google-genai | grep Version
python -c "from google import genai; help(genai.Client.__init__)"
python -c "from google.genai import types; help(types.HttpOptions)"
python -c "from google.genai import types; help(types.GenerateContentConfig)"
python -c "from google.genai import errors; help(errors.APIError)"
```

If any field name below (`http_options`, `system_instruction`, `response_json_schema`, `.code` on `APIError`) doesn't match what's introspected, adjust Step 3's code to match the real signature — don't silently keep a broken call.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ai_chat_interface.py`:

```python
import pytest

from ai import llm_client
from ai.llm_client import AIConfigError


# ------------------------------------------------------------------ #
# ai/llm_client.py                                                    #
# ------------------------------------------------------------------ #

def test_get_client_raises_when_key_unset(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    llm_client._client = None

    with pytest.raises(AIConfigError) as exc_info:
        llm_client.get_client()

    assert exc_info.value.status == 503
    assert "LLM_API_KEY" in exc_info.value.user_message


def test_create_message_raises_when_key_unset(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    llm_client._client = None

    with pytest.raises(AIConfigError):
        llm_client.create_message(system_text="You are a test assistant.", turns=[])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ai_chat_interface.py -v -k "client_raises or create_message_raises"`
Expected: FAIL with `ModuleNotFoundError: No module named 'ai'`

- [ ] **Step 3: Implement the seam**

Create `ai/__init__.py` (empty file).

Create `ai/llm_client.py`:

```python
import base64
import logging
import os

from google import genai
from google.genai import errors, types

MODEL = "gemini-2.0-flash"
CHAT_MAX_TOKENS = 4096
EXTRACT_MAX_TOKENS = 1024
REQUEST_TIMEOUT_SECONDS = 30.0

logger = logging.getLogger(__name__)

_client = None


class AIError(Exception):
    status = 502

    def __init__(self, user_message):
        super().__init__(user_message)
        self.user_message = user_message


class AIConfigError(AIError):
    status = 503


class AIRateLimitError(AIError):
    status = 429


class AIUnavailableError(AIError):
    status = 502


class _ToolCall:
    def __init__(self, id, name, input):
        self.id = id
        self.name = name
        self.input = input


class _Reply:
    def __init__(self, text, tool_calls, finish_reason):
        self.text = text
        self.tool_calls = tool_calls
        self.finish_reason = finish_reason


def get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            raise AIConfigError("The AI assistant is not configured. Set LLM_API_KEY to enable it.")
        _client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(REQUEST_TIMEOUT_SECONDS * 1000)),
        )
    return _client


def _build_contents(turns, image):
    contents = []
    for turn in turns:
        role = "model" if turn["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=turn["content"])]))

    if image is not None and contents:
        contents[-1].parts.append(
            types.Part.from_bytes(data=base64.b64decode(image["data"]), mime_type=image["media_type"])
        )

    return contents


def _build_tools(tools):
    if not tools:
        return None
    declarations = [
        types.FunctionDeclaration(
            name=tool["name"],
            description=tool["description"],
            parameters_json_schema=tool["input_schema"],
        )
        for tool in tools
    ]
    return [types.Tool(function_declarations=declarations)]


def _map_finish_reason(candidate, has_tool_calls):
    if has_tool_calls:
        return "tool_calls"
    reason = str(getattr(candidate, "finish_reason", "") or "")
    if reason == "MAX_TOKENS":
        return "length"
    if reason in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"):
        return "refused"
    return "stop"


def create_message(system_text, context_text="", turns=None, tools=None, response_schema=None, image=None):
    client = get_client()
    turns = turns or []

    system_instruction = system_text
    if context_text:
        system_instruction = system_text + "\n\n" + context_text

    config_kwargs = {
        "system_instruction": system_instruction,
        "max_output_tokens": CHAT_MAX_TOKENS,
    }

    tool_config = _build_tools(tools)
    if tool_config:
        config_kwargs["tools"] = tool_config

    if response_schema:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_json_schema"] = response_schema

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=_build_contents(turns, image),
            config=types.GenerateContentConfig(**config_kwargs),
        )
    except errors.APIError as exc:
        logger.warning("LLM request failed: %s", type(exc).__name__)
        if exc.code in (401, 403):
            raise AIConfigError("The AI assistant is not configured. Set LLM_API_KEY to enable it.") from exc
        if exc.code == 429:
            raise AIRateLimitError("The assistant is busy. Please try again in a moment.") from exc
        raise AIUnavailableError("The assistant is temporarily unavailable. Please try again.") from exc
    except Exception as exc:
        logger.warning("LLM request failed: %s", type(exc).__name__)
        raise AIUnavailableError("The assistant is temporarily unavailable. Please try again.") from exc

    raw_calls = response.function_calls or []
    tool_calls = [
        _ToolCall(id="call_%d" % i, name=call.name, input=dict(call.args or {}))
        for i, call in enumerate(raw_calls)
    ]

    candidate = response.candidates[0] if response.candidates else None
    finish_reason = _map_finish_reason(candidate, bool(tool_calls))

    try:
        text = response.text or ""
    except Exception:
        text = ""

    return _Reply(text=text, tool_calls=tool_calls, finish_reason=finish_reason)
```

Add to `requirements.txt` the exact line reported by `pip show google-genai | grep Version` from Step 0, e.g.:

```
google-genai==<version from pip show>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ai_chat_interface.py -v`
Expected: PASS (all tests so far)

Also verify the app still boots with no key set:

Run: `LLM_API_KEY= python -c "import app"`
Expected: no exception (import succeeds; `get_client()` is never called at import time)

- [ ] **Step 5: Commit**

```bash
git add ai/__init__.py ai/llm_client.py requirements.txt tests/test_ai_chat_interface.py
git commit -m "feat: add Gemini-backed ai/llm_client.py seam"
```

---

### Task 3: `ai/prompts.py` + `ai/chat.py` + `fake_llm` fixture

**Files:**
- Create: `ai/prompts.py`
- Create: `ai/chat.py`
- Modify: `tests/conftest.py` (append `text_reply`, `tool_call_reply`, `FakeLLM`, `fake_llm`)
- Test: `tests/test_ai_chat_interface.py` (append)

**Interfaces:**
- Consumes: `ai.llm_client.create_message(...)` from Task 2 (called only as `llm_client.create_message(...)`, never imported directly).
- Produces: `ai.prompts.CHAT_SYSTEM_PROMPT` (str). `ai.chat.HISTORY_LIMIT = 20`. `ai.chat.CONTEXT_PROVIDERS = []`. `build_messages(history, user_text) -> list[dict]`. `build_turn_context(user_id, user_name, today) -> str`. `run_chat_turn(user_id, history, user_text, user_name, today) -> {"reply": str, "tools_used": []}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/conftest.py`:

```python
from types import SimpleNamespace


def text_reply(text, finish_reason="stop"):
    return SimpleNamespace(text=text, tool_calls=[], finish_reason=finish_reason)


def tool_call_reply(name, tool_input, tool_id="call_01", text=None):
    call = SimpleNamespace(id=tool_id, name=name, input=tool_input)
    return SimpleNamespace(text=text or "", tool_calls=[call], finish_reason="tool_calls")


class FakeLLM:
    def __init__(self):
        self.responses = []
        self.calls = []

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

Append to `tests/test_ai_chat_interface.py`:

```python
from datetime import date

from ai.chat import build_messages, build_turn_context, run_chat_turn
from ai.prompts import CHAT_SYSTEM_PROMPT
from tests.conftest import text_reply


# ------------------------------------------------------------------ #
# ai/chat.py — build_messages                                        #
# ------------------------------------------------------------------ #

def test_build_messages_trims_to_history_limit():
    history = [
        {"role": "assistant" if i % 2 == 0 else "user", "content": "msg%d" % i}
        for i in range(25)
    ]

    turns = build_messages(history, "new question")

    assert len(turns) == 21
    assert turns[0]["role"] == "user"
    assert turns[-1] == {"role": "user", "content": "new question"}


def test_build_messages_drops_leading_assistant_row():
    history = [
        {"role": "assistant" if i % 2 == 0 else "user", "content": "msg%d" % i}
        for i in range(20)
    ]

    turns = build_messages(history, "new question")

    assert turns[0]["role"] == "user"


# ------------------------------------------------------------------ #
# ai/chat.py — build_turn_context                                    #
# ------------------------------------------------------------------ #

def test_build_turn_context_includes_date_and_name():
    context = build_turn_context(user_id=1, user_name="Demo User", today=date(2026, 9, 7))

    assert "Today is 2026-09-07." in context
    assert "Demo User" in context


# ------------------------------------------------------------------ #
# ai/chat.py — run_chat_turn                                         #
# ------------------------------------------------------------------ #

def test_run_chat_turn_returns_reply_text(fake_llm):
    fake_llm.responses.append(text_reply("Hello"))
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": "msg%d" % i}
        for i in range(30)
    ]

    result = run_chat_turn(1, history, "hi", "Demo User", date(2026, 9, 7))

    assert result == {"reply": "Hello", "tools_used": []}
    call = fake_llm.calls[0]
    assert call["system_text"] == CHAT_SYSTEM_PROMPT
    assert "Today is" in call["context_text"]
    assert len(call["turns"]) == 21


def test_run_chat_turn_refused_reply(fake_llm):
    fake_llm.responses.append(text_reply("", finish_reason="refused"))

    result = run_chat_turn(1, [], "hi", "Demo User", date(2026, 9, 7))

    assert result["reply"] == "I can't help with that request."


def test_run_chat_turn_length_reply(fake_llm):
    fake_llm.responses.append(text_reply("partial answer", finish_reason="length"))

    result = run_chat_turn(1, [], "hi", "Demo User", date(2026, 9, 7))

    assert result["reply"] == "partial answer …"


def test_run_chat_turn_empty_text_reply(fake_llm):
    fake_llm.responses.append(text_reply(""))

    result = run_chat_turn(1, [], "hi", "Demo User", date(2026, 9, 7))

    assert result["reply"] == "Done."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ai_chat_interface.py -v -k "build_messages or build_turn_context or run_chat_turn"`
Expected: FAIL with `ModuleNotFoundError: No module named 'ai.chat'`

- [ ] **Step 3: Implement prompts and chat orchestration**

Create `ai/prompts.py`:

```python
CHAT_SYSTEM_PROMPT = (
    "You are Spendly's assistant, a helpful guide for the Spendly personal "
    "expense tracker. Always display currency as ₹ (Indian rupees) — "
    "never $ or £. The only expense categories in this app are Food, "
    "Transport, Bills, Health, Entertainment, Shopping, and Other. Answer "
    "only questions about the user's finances within Spendly and about how "
    "to use the app. Reply in short, plain text — no markdown tables, no "
    "headers, no bullet lists with markdown syntax. Never invent figures; "
    "only state amounts you were actually given."
)
```

Create `ai/chat.py`:

```python
from ai import llm_client
from ai.prompts import CHAT_SYSTEM_PROMPT

HISTORY_LIMIT = 20

CONTEXT_PROVIDERS = []


def build_messages(history, user_text):
    trimmed = list(history[-HISTORY_LIMIT:])
    while trimmed and trimmed[0]["role"] == "assistant":
        trimmed = trimmed[1:]

    turns = [{"role": row["role"], "content": row["content"]} for row in trimmed]
    turns.append({"role": "user", "content": user_text})
    return turns


def build_turn_context(user_id, user_name, today):
    parts = ["Today is %s." % today.isoformat(), "The user's name is %s." % user_name]
    for provider in CONTEXT_PROVIDERS:
        result = provider(user_id)
        if result:
            parts.append(result)
    return " ".join(parts)


def run_chat_turn(user_id, history, user_text, user_name, today):
    reply = llm_client.create_message(
        system_text=CHAT_SYSTEM_PROMPT,
        context_text=build_turn_context(user_id, user_name, today),
        turns=build_messages(history, user_text),
    )

    if reply.finish_reason == "refused":
        text = "I can't help with that request."
    elif reply.finish_reason == "length":
        text = (reply.text or "") + " …"
    elif not reply.text:
        text = "Done."
    else:
        text = reply.text

    return {"reply": text, "tools_used": []}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ai_chat_interface.py -v`
Expected: PASS (all tests so far)

- [ ] **Step 5: Commit**

```bash
git add ai/prompts.py ai/chat.py tests/conftest.py tests/test_ai_chat_interface.py
git commit -m "feat: add chat prompt and turn orchestration"
```

---

### Task 4: `/api/chat*` routes

**Files:**
- Modify: `app.py` (imports, `_json_error`, three routes under a new `# AI routes` banner)
- Test: `tests/test_ai_chat_interface.py` (append)

**Interfaces:**
- Consumes: `get_chat_messages`, `insert_chat_message`, `delete_chat_messages` (Task 1); `run_chat_turn`, `HISTORY_LIMIT` from `ai.chat` (Task 3); `AIError` from `ai.llm_client` (Task 2).
- Produces: routes `GET /api/chat/history` (view fn `chat_history`), `POST /api/chat` (view fn `chat_send`), `DELETE /api/chat/history` (view fn `chat_clear`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ai_chat_interface.py`:

```python
from ai.llm_client import AIRateLimitError, AIUnavailableError
from tests.conftest import text_reply


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

def test_chat_history_requires_auth(client):
    response = client.get("/api/chat/history")

    assert response.status_code == 401
    assert "error" in response.get_json()


def test_chat_history_returns_stored_messages(client, monkeypatch):
    from database.queries import insert_chat_message

    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    insert_chat_message(1, "user", "hi")
    insert_chat_message(1, "assistant", "hello")

    response = client.get("/api/chat/history")
    body = response.get_json()

    assert response.status_code == 200
    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][1]["role"] == "assistant"


def test_chat_send_requires_auth(client):
    response = client.post("/api/chat", json={"message": "hi"})

    assert response.status_code == 401


def test_chat_send_success_stores_both_turns(client, fake_llm):
    from database.queries import get_chat_messages

    fake_llm.responses.append(text_reply("Sure"))
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/api/chat", json={"message": "hi"})

    assert response.status_code == 200
    assert response.get_json() == {"reply": "Sure"}

    rows = get_chat_messages(1)
    assert [r["role"] for r in rows] == ["user", "assistant"]
    assert rows[0]["content"] == "hi"
    assert rows[1]["content"] == "Sure"


def test_chat_send_blank_message(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/api/chat", json={"message": "   "})

    assert response.status_code == 400
    from database.queries import get_chat_messages
    assert get_chat_messages(1) == []


def test_chat_send_too_long_message(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/api/chat", json={"message": "x" * 2001})

    assert response.status_code == 400
    from database.queries import get_chat_messages
    assert get_chat_messages(1) == []


def test_chat_send_non_json_body(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/api/chat", data="not json", content_type="text/plain")

    assert response.status_code == 400


def test_chat_send_no_api_key_configured(client, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    from ai import llm_client
    llm_client._client = None
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/api/chat", json={"message": "hi"})

    assert response.status_code == 503
    from database.queries import get_chat_messages
    assert get_chat_messages(1) == []


def test_chat_send_unavailable_error(client, fake_llm):
    fake_llm.responses.append(AIUnavailableError("The assistant is temporarily unavailable. Please try again."))
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/api/chat", json={"message": "hi"})

    assert response.status_code == 502
    from database.queries import get_chat_messages
    assert get_chat_messages(1) == []


def test_chat_send_rate_limit_error(client, fake_llm):
    fake_llm.responses.append(AIRateLimitError("The assistant is busy. Please try again in a moment."))
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/api/chat", json={"message": "hi"})

    assert response.status_code == 429
    from database.queries import get_chat_messages
    assert get_chat_messages(1) == []


def test_chat_clear_requires_auth(client):
    response = client.delete("/api/chat/history")

    assert response.status_code == 401


def test_chat_clear_deletes_rows(client):
    from database.queries import insert_chat_message, get_chat_messages

    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    insert_chat_message(1, "user", "a")
    insert_chat_message(1, "assistant", "b")
    insert_chat_message(1, "user", "c")

    response = client.delete("/api/chat/history")

    assert response.status_code == 200
    assert response.get_json() == {"cleared": 3}
    assert get_chat_messages(1) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ai_chat_interface.py -v -k "chat_history or chat_send or chat_clear"`
Expected: FAIL with 404s (routes don't exist yet)

- [ ] **Step 3: Implement the routes**

In `app.py`, update the Flask import line to include `jsonify`:

```python
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for
```

Add new imports below the existing `database.queries` import block:

```python
from ai import llm_client
from ai.chat import HISTORY_LIMIT, run_chat_turn
from database.queries import (
    delete_chat_messages,
    get_chat_messages,
    insert_chat_message,
)
```

(Merge these into the existing `from database.queries import (...)` block rather than a second import statement — keep one alphabetized block per module.)

In the `# Helpers` section, add:

```python
def _json_error(message, status):
    return jsonify({"error": message}), status
```

Add a new banner and the three routes (after the expense routes, before `with app.app_context():`):

```python
# ------------------------------------------------------------------ #
# AI routes                                                           #
# ------------------------------------------------------------------ #

CHAT_HISTORY_LIMIT = 50
CHAT_MESSAGE_MAX_LENGTH = 2000


@app.route("/api/chat/history", methods=["GET"])
def chat_history():
    user_id = session.get("user_id")
    if not user_id:
        return _json_error("Authentication required.", 401)

    messages = get_chat_messages(user_id, limit=CHAT_HISTORY_LIMIT)
    return jsonify({"messages": messages})


@app.route("/api/chat", methods=["POST"])
def chat_send():
    user_id = session.get("user_id")
    if not user_id:
        return _json_error("Authentication required.", 401)

    body = request.get_json(silent=True)
    if not body:
        return _json_error("Message is required.", 400)

    text = (body.get("message") or "").strip()
    if not text:
        return _json_error("Message is required.", 400)
    if len(text) > CHAT_MESSAGE_MAX_LENGTH:
        return _json_error("Message must be 2000 characters or fewer.", 400)

    history = get_chat_messages(user_id, limit=HISTORY_LIMIT)
    user = get_user_by_id(user_id)

    try:
        result = run_chat_turn(user_id, history, text, user["name"], date.today())
    except llm_client.AIError as e:
        return _json_error(e.user_message, e.status)

    insert_chat_message(user_id, "user", text)
    insert_chat_message(user_id, "assistant", result["reply"])

    return jsonify({"reply": result["reply"]})


@app.route("/api/chat/history", methods=["DELETE"])
def chat_clear():
    user_id = session.get("user_id")
    if not user_id:
        return _json_error("Authentication required.", 401)

    cleared = delete_chat_messages(user_id)
    return jsonify({"cleared": cleared})
```

Note: `date` is already imported at the top of `app.py` (`from datetime import date, datetime`) — no new import needed there.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ai_chat_interface.py -v`
Expected: PASS (all tests so far)

Also run the full suite to confirm nothing else broke:

Run: `pytest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_ai_chat_interface.py
git commit -m "feat: add /api/chat routes"
```

---

### Task 5: Chat drawer UI

**Files:**
- Create: `templates/_chat_drawer.html`
- Create: `static/css/chat.css`
- Create: `static/js/chat.js`
- Modify: `templates/base.html`
- Test: `tests/test_ai_chat_interface.py` (append)

**Interfaces:**
- Consumes: `url_for('chat_history')`, `url_for('chat_send')` from Task 4; `session.get('user_id')` (existing).
- Produces: drawer markup with `id="chat-drawer"`, toggle `id="chat-toggle"`, messages container `id="chat-messages"`, form `id="chat-form"` / `id="chat-input"`, clear button `id="chat-clear"`, close button `id="chat-close"`, status `id="chat-status"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ai_chat_interface.py`:

```python
def test_profile_includes_chat_drawer_when_logged_in(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="chat-drawer"' in body
    assert "js/chat.js" in body


def test_landing_excludes_chat_drawer_when_logged_out(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "chat-drawer" not in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ai_chat_interface.py -v -k "chat_drawer"`
Expected: FAIL — `'id="chat-drawer"' in body` is `False`

- [ ] **Step 3: Build the drawer**

Create `templates/_chat_drawer.html`:

```html
<aside id="chat-drawer" class="chat-drawer chat-drawer-collapsed"
       data-history-url="{{ url_for('chat_history') }}"
       data-send-url="{{ url_for('chat_send') }}">
    <button id="chat-toggle" class="chat-toggle" type="button" aria-expanded="false">
        <span class="chat-toggle-icon">◈</span>
    </button>

    <div class="chat-panel">
        <div class="chat-header">
            <span class="chat-title">Spendly Assistant</span>
            <div class="chat-header-actions">
                <button id="chat-clear" class="chat-clear" type="button">Clear</button>
                <button id="chat-close" class="chat-close" type="button" aria-label="Close chat">&times;</button>
            </div>
        </div>

        <div id="chat-messages" class="chat-messages" aria-live="polite">
            <p class="chat-empty">Ask me about your spending.</p>
        </div>

        <p id="chat-status" class="chat-status" hidden></p>

        <form id="chat-form" class="chat-form">
            <textarea id="chat-input" class="chat-input" maxlength="2000" rows="1" placeholder="Ask about your spending..."></textarea>
            <button type="submit" class="chat-send">Send</button>
        </form>
    </div>
</aside>
```

Create `static/css/chat.css`:

```css
.chat-drawer {
    position: fixed;
    right: 24px;
    bottom: 24px;
    z-index: 1000;
    font-family: var(--font-body);
}

.chat-toggle {
    width: 56px;
    height: 56px;
    border-radius: 50%;
    border: 1px solid var(--border);
    background: var(--accent);
    color: var(--paper-card);
    font-size: 1.5rem;
    cursor: pointer;
}

.chat-panel {
    display: flex;
    flex-direction: column;
    width: 360px;
    max-width: 360px;
    max-height: 70vh;
    background: var(--paper-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    margin-bottom: 12px;
    overflow: hidden;
}

.chat-drawer-collapsed .chat-panel {
    display: none;
}

.chat-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    background: var(--paper-warm);
    border-bottom: 1px solid var(--border);
    color: var(--ink);
}

.chat-header-actions {
    display: flex;
    gap: 8px;
}

.chat-clear,
.chat-close {
    background: none;
    border: none;
    color: var(--ink);
    cursor: pointer;
}

.chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.chat-empty {
    color: var(--ink);
    opacity: 0.6;
}

.chat-bubble-user,
.chat-bubble-assistant,
.chat-bubble-error {
    padding: 10px 14px;
    border-radius: var(--radius-lg);
    max-width: 85%;
    white-space: pre-wrap;
}

.chat-bubble-user {
    align-self: flex-end;
    background: var(--accent-light);
    color: var(--ink);
}

.chat-bubble-assistant {
    align-self: flex-start;
    background: var(--paper-warm);
    color: var(--ink);
}

.chat-bubble-error {
    align-self: flex-start;
    background: var(--danger-light);
    color: var(--ink);
}

.chat-status {
    padding: 0 16px 8px;
    color: var(--ink);
    opacity: 0.7;
    font-size: 0.85rem;
}

.chat-form {
    display: flex;
    gap: 8px;
    padding: 12px 16px;
    border-top: 1px solid var(--border);
}

.chat-input {
    flex: 1;
    resize: none;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 8px 12px;
    font-family: var(--font-body);
    color: var(--ink);
    background: var(--paper-card);
}

.chat-send {
    border: none;
    border-radius: var(--radius-lg);
    background: var(--accent);
    color: var(--paper-card);
    padding: 8px 16px;
    cursor: pointer;
}

@media (max-width: 600px) {
    .chat-drawer {
        right: 12px;
        left: 12px;
        bottom: 12px;
    }

    .chat-panel {
        width: 100%;
        max-width: 100%;
    }
}
```

Create `static/js/chat.js`:

```js
(function () {
    var STORAGE_KEY = "spendly-chat-open";

    var drawer = document.getElementById("chat-drawer");
    if (!drawer) {
        return;
    }

    var toggleButton = document.getElementById("chat-toggle");
    var closeButton = document.getElementById("chat-close");
    var clearButton = document.getElementById("chat-clear");
    var messagesEl = document.getElementById("chat-messages");
    var statusEl = document.getElementById("chat-status");
    var formEl = document.getElementById("chat-form");
    var inputEl = document.getElementById("chat-input");

    var historyUrl = drawer.getAttribute("data-history-url");
    var sendUrl = drawer.getAttribute("data-send-url");

    function setOpen(isOpen) {
        if (isOpen) {
            drawer.classList.remove("chat-drawer-collapsed");
        } else {
            drawer.classList.add("chat-drawer-collapsed");
        }
        if (toggleButton) {
            toggleButton.setAttribute("aria-expanded", isOpen ? "true" : "false");
        }
        try {
            localStorage.setItem(STORAGE_KEY, isOpen ? "open" : "closed");
        } catch (e) {
            /* localStorage unavailable */
        }
    }

    function isOpenStored() {
        try {
            return localStorage.getItem(STORAGE_KEY) === "open";
        } catch (e) {
            return false;
        }
    }

    function scrollToBottom() {
        if (messagesEl) {
            messagesEl.scrollTop = messagesEl.scrollHeight;
        }
    }

    function clearEmptyState() {
        if (!messagesEl) {
            return;
        }
        var empty = messagesEl.querySelector(".chat-empty");
        if (empty) {
            empty.remove();
        }
    }

    function resetMessages() {
        if (!messagesEl) {
            return;
        }
        while (messagesEl.firstChild) {
            messagesEl.removeChild(messagesEl.firstChild);
        }
        var empty = document.createElement("p");
        empty.className = "chat-empty";
        empty.textContent = "Ask me about your spending.";
        messagesEl.appendChild(empty);
    }

    function appendBubble(role, text) {
        if (!messagesEl) {
            return;
        }
        clearEmptyState();
        var bubble = document.createElement("div");
        if (role === "user") {
            bubble.className = "chat-bubble-user";
        } else if (role === "error") {
            bubble.className = "chat-bubble-error";
        } else {
            bubble.className = "chat-bubble-assistant";
        }
        bubble.textContent = text;
        messagesEl.appendChild(bubble);
        scrollToBottom();
    }

    function setStatus(text) {
        if (!statusEl) {
            return;
        }
        if (text) {
            statusEl.textContent = text;
            statusEl.hidden = false;
        } else {
            statusEl.hidden = true;
            statusEl.textContent = "";
        }
    }

    function setInputDisabled(disabled) {
        if (inputEl) {
            inputEl.disabled = disabled;
        }
    }

    function loadHistory() {
        if (!historyUrl) {
            return;
        }
        fetch(historyUrl)
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                var messages = data && data.messages ? data.messages : [];
                if (messages.length === 0) {
                    return;
                }
                clearEmptyState();
                for (var i = 0; i < messages.length; i++) {
                    appendBubble(messages[i].role, messages[i].content);
                }
            })
            .catch(function () {
                /* history load failed; leave empty state as-is */
            });
    }

    function sendMessage(text) {
        appendBubble("user", text);
        setInputDisabled(true);
        setStatus("Thinking…");

        fetch(sendUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text })
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { ok: response.ok, data: data };
                });
            })
            .then(function (result) {
                setInputDisabled(false);
                setStatus("");
                if (result.ok) {
                    appendBubble("assistant", result.data.reply);
                } else {
                    appendBubble("error", result.data.error || "Something went wrong.");
                }
            })
            .catch(function () {
                setInputDisabled(false);
                setStatus("");
                appendBubble("error", "Something went wrong.");
            });
    }

    function trySend() {
        if (!inputEl) {
            return;
        }
        var text = inputEl.value.trim();
        if (!text) {
            return;
        }
        inputEl.value = "";
        sendMessage(text);
    }

    if (toggleButton) {
        toggleButton.addEventListener("click", function () {
            setOpen(drawer.classList.contains("chat-drawer-collapsed"));
        });
    }

    if (closeButton) {
        closeButton.addEventListener("click", function () {
            setOpen(false);
        });
    }

    if (clearButton) {
        clearButton.addEventListener("click", function () {
            if (!confirm("Clear this conversation?")) {
                return;
            }
            fetch(historyUrl, { method: "DELETE" })
                .then(function () {
                    resetMessages();
                })
                .catch(function () {
                    /* clear failed; leave existing messages visible */
                });
        });
    }

    if (formEl) {
        formEl.addEventListener("submit", function (event) {
            event.preventDefault();
            trySend();
        });
    }

    if (inputEl) {
        inputEl.addEventListener("keydown", function (event) {
            if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                trySend();
            }
        });
    }

    if (isOpenStored()) {
        setOpen(true);
    }

    loadHistory();
})();
```

Modify `templates/base.html`: add the conditional stylesheet link right after the `style.css` link and before `{% block head %}`:

```html
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    {% if session.get('user_id') %}
    <link rel="stylesheet" href="{{ url_for('static', filename='css/chat.css') }}">
    {% endif %}
    {% block head %}{% endblock %}
```

And add the conditional include + script right after `</footer>`, before the existing `main.js` script tag:

```html
    </footer>

    {% if session.get('user_id') %}
    {% include "_chat_drawer.html" %}
    <script src="{{ url_for('static', filename='js/chat.js') }}"></script>
    {% endif %}

    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
    {% block scripts %}{% endblock %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ai_chat_interface.py -v`
Expected: PASS (all tests so far)

Run the full suite to confirm no regressions on other pages:

Run: `pytest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add templates/_chat_drawer.html templates/base.html static/css/chat.css static/js/chat.js tests/test_ai_chat_interface.py
git commit -m "feat: add chat drawer UI"
```

---

### Task 6: Docs, dependency pin, and manual verification

**Files:**
- Modify: `requirements.txt` (confirm the pinned `google-genai` line from Task 2 is present and correct)
- Modify: `CLAUDE.md` (record the provider choice; flip the three `/api/chat*` route rows to Implemented)

**Interfaces:** None — this task only updates documentation and performs manual, non-automated verification. No code interfaces are produced or consumed.

- [ ] **Step 1: Update `CLAUDE.md`'s pip carve-out line**

In the `## Tech constraints` section, change:

```
- **No new pip packages** — work within `requirements.txt` as-is. The single sanctioned exception is one LLM SDK package for the AI layer (Step 10) — the provider is chosen at implementation time, not decided by these docs; pin its version and name it here once chosen. Anything else must be flagged and approved first
```

to:

```
- **No new pip packages** — work within `requirements.txt` as-is. The single sanctioned exception is `google-genai` (pinned in `requirements.txt`), used only by `ai/llm_client.py` for the Gemini free-tier API. Anything else must be flagged and approved first
```

- [ ] **Step 2: Flip the three `/api/chat*` rows in the route table**

In the `## Implemented vs stub routes` table, change:

```
| `GET /api/chat/history` | Stub — Step 10 |
| `POST /api/chat` | Stub — Step 10 |
| `DELETE /api/chat/history` | Stub — Step 10 |
```

to:

```
| `GET /api/chat/history` | Implemented — Step 10 |
| `POST /api/chat` | Implemented — Step 10 |
| `DELETE /api/chat/history` | Implemented — Step 10 |
```

- [ ] **Step 3: Run the full automated suite one more time**

Run: `pytest -v`
Expected: PASS, with `LLM_API_KEY` unset in the shell (confirms no test secretly depends on a real key or network access)

- [ ] **Step 4: Manual smoke test — no key configured**

```bash
unset LLM_API_KEY
python app.py
```

In a browser: log in as `demo@spendly.com` / `demo123`, open the chat drawer, send a message. Expected: an error bubble reading "The AI assistant is not configured. Set LLM_API_KEY to enable it." and no other page breakage.

- [ ] **Step 5: Manual smoke test — real key configured**

Get a free Gemini API key from Google AI Studio, then:

```bash
export LLM_API_KEY=<your-key>
python app.py
```

In the browser: send a message like "What have I spent on Food?". Expected: a plain-text reply, any amount shown as ₹, no markdown tables/headers. Reload the page — the conversation should still be there. Click Clear, confirm — the conversation should empty.

If the real call fails with an error that doesn't map to one of the three `AIError` subclasses correctly (e.g. a 401 rendering as "temporarily unavailable" instead of "not configured"), revisit the exception-code mapping in `ai/llm_client.py`'s `create_message()` from Task 2 and adjust it based on the actual error shape you observe.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md requirements.txt
git commit -m "docs: record Gemini as the Step 10 LLM provider"
```

---

## Definition of Done

- [ ] `pip install -r requirements.txt` installs `google-genai`; `python app.py` starts with no `LLM_API_KEY` set
- [ ] Logged-out pages show no chat drawer; logged-in pages show a floating toggle bottom-right
- [ ] Sending a message with a valid key returns a reply, and amounts in the reply use ₹
- [ ] Sending a message with no key shows the "not configured" error bubble and nothing else breaks
- [ ] Reloading the page restores the conversation from SQLite
- [ ] "Clear" empties the conversation after confirmation
- [ ] Drawer open/closed state persists across page navigation
- [ ] Drawer respects dark mode without any hardcoded colours
- [ ] All tests in `tests/test_ai_chat_interface.py` pass without `LLM_API_KEY` set and without importing `google.genai`
- [ ] `CLAUDE.md` route table shows the three `/api/chat*` rows as Implemented
