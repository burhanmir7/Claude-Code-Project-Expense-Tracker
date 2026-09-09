# Receipt OCR Intake (Step 12) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user photograph or drag-and-drop a receipt on the Add Expense page and have the AI assistant read it, pre-filling the expense form for the user to review before saving — no new provider decision, no persistence of images.

**Architecture:** A new `ai/receipts.py` module holds pure, testable helpers (magic-byte type detection, a JSON schema, and post-processing) plus one LLM-calling function that reuses the Step 10 `ai.llm_client.create_message()` seam with an `image` and a `response_schema`. `app.py` gets one new route, `POST /expenses/scan`, that validates the upload, calls the extractor, and re-renders `add_expense.html` pre-filled — it never inserts an expense itself. A dropzone card and its JS are added to the existing Add Expense page as a progressive enhancement over a plain HTML file upload.

**Tech Stack:** Flask, stdlib `base64`/`json`/`datetime` only, vanilla JS (ES5 IIFE), pytest. No new pip packages.

**Spec:** `.claude/specs/12-receipt-ocr-intake.md`

## Global Constraints

- Image bytes live only in the request object and local variables — never written to disk, never stored in the DB or session, never logged.
- The media type is decided by `detect_image_type` alone; `file.mimetype` and the filename extension are never trusted.
- Size is checked with `len(data)` after `file.read()`; anything over `MAX_RECEIPT_BYTES` (5 MB) is rejected with 400 before any API call.
- `response_schema=RECEIPT_SCHEMA` is passed to `create_message`; the category enum inside it is built from `CATEGORIES` (imported from `database.db`), never retyped.
- The base64 image string contains no newlines (`base64.standard_b64encode(...).decode("ascii")`).
- `RECEIPT_PROMPT` is a stable constant passed as `system_text`; "today" travels inside the one `turns` entry, never baked into the prompt.
- `max_tokens = EXTRACT_MAX_TOKENS` for the extraction call — this is an internal decision inside `ai/llm_client.py` (see Task 2), invisible to every caller.
- The route never inserts an expense — it only renders the form; saving still goes through the existing `POST /expenses/add` and its own validation.
- The prefilled amount is passed as a two-decimal string so `<input type="number">` renders it.
- Unauthenticated requests to `/expenses/scan` redirect to `/login` (this is an HTML flow, not a JSON endpoint — no `abort()`, no 401).
- No SQLAlchemy/ORM — raw `sqlite3` via `get_db()` only. Parameterised queries only.
- Use CSS variables — never hardcode hex values. No inline styles. All templates extend `base.html`.
- Currency in any assistant-facing copy is always ₹, never $ or £.
- Callers reference the seam as `llm_client.create_message(...)` / `llm_client.AIError` / `llm_client.AIUnavailableError` after `from ai import llm_client` — never `from ai.llm_client import create_message`, which bypasses the `fake_llm` test fixture.
- `ai/receipts.py` has no Flask imports.
- Tests must never require `LLM_API_KEY` and must never import a provider SDK (`google.genai`) — use the existing `fake_llm` fixture from `tests/conftest.py`.

---

### Task 1: `ai/receipts.py` — pure helpers

**Files:**
- Create: `ai/receipts.py`
- Test: `tests/test_receipt_ocr_intake.py` (new file)

**Interfaces:**
- Produces: `ALLOWED_MEDIA_TYPES` (set of 4 strings), `MAX_RECEIPT_BYTES = 5 * 1024 * 1024`, `RECEIPT_SCHEMA` (dict), `detect_image_type(data: bytes) -> str | None`, `normalise_receipt(fields: dict, today: date) -> dict` with keys `amount`, `category`, `date`, `description` (all strings).

This task only covers the pure, non-LLM helpers — `extract_receipt` and `RECEIPT_PROMPT` come in Task 2, since they need the `ai/llm_client.py` change from that task.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_receipt_ocr_intake.py`:

```python
from datetime import date

from ai.receipts import RECEIPT_SCHEMA, detect_image_type, normalise_receipt


# ------------------------------------------------------------------ #
# detect_image_type                                                   #
# ------------------------------------------------------------------ #

def test_detect_image_type_png():
    assert detect_image_type(b"\x89PNG\r\n\x1a\n" + b"rest of file") == "image/png"


def test_detect_image_type_jpeg():
    assert detect_image_type(b"\xff\xd8\xff" + b"rest of file") == "image/jpeg"


def test_detect_image_type_webp():
    assert detect_image_type(b"RIFF" + b"1234" + b"WEBP" + b"rest of file") == "image/webp"


def test_detect_image_type_gif():
    assert detect_image_type(b"GIF89a" + b"rest of file") == "image/gif"


def test_detect_image_type_unsupported():
    assert detect_image_type(b"%PDF-1.4" + b"rest of file") is None


# ------------------------------------------------------------------ #
# normalise_receipt                                                    #
# ------------------------------------------------------------------ #

def test_normalise_receipt_valid_fields():
    fields = {"is_receipt": True, "amount": 249.5, "date": "2026-09-01", "description": "Lunch", "category": "Food"}

    result = normalise_receipt(fields, date(2026, 9, 1))

    assert result == {"amount": "249.50", "date": "2026-09-01", "description": "Lunch", "category": "Food"}


def test_normalise_receipt_missing_amount_and_unparseable_date():
    fields = {"is_receipt": True, "amount": None, "date": "31/12/2026", "description": "x", "category": "Food"}

    result = normalise_receipt(fields, date(2026, 9, 1))

    assert result["amount"] == ""
    assert result["date"] == "2026-09-01"


def test_normalise_receipt_truncates_long_description():
    fields = {"is_receipt": True, "amount": 10, "date": "2026-09-01", "description": "x" * 300, "category": "Food"}

    result = normalise_receipt(fields, date(2026, 9, 1))

    assert len(result["description"]) == 200


def test_normalise_receipt_unknown_category_falls_back_to_other():
    fields = {"is_receipt": True, "amount": 10, "date": "2026-09-01", "description": "x", "category": "Groceries"}

    result = normalise_receipt(fields, date(2026, 9, 1))

    assert result["category"] == "Other"


def test_normalise_receipt_non_positive_amount_becomes_blank():
    fields = {"is_receipt": True, "amount": 0, "date": "2026-09-01", "description": "x", "category": "Food"}

    result = normalise_receipt(fields, date(2026, 9, 1))

    assert result["amount"] == ""


# ------------------------------------------------------------------ #
# RECEIPT_SCHEMA                                                       #
# ------------------------------------------------------------------ #

def test_receipt_schema_category_enum_matches_categories():
    from database.db import CATEGORIES

    assert RECEIPT_SCHEMA["properties"]["category"]["enum"] == CATEGORIES
    assert RECEIPT_SCHEMA["additionalProperties"] is False
    assert set(RECEIPT_SCHEMA["required"]) == {"is_receipt", "amount", "date", "description", "category"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_receipt_ocr_intake.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ai.receipts'`

- [ ] **Step 3: Implement the pure helpers**

Create `ai/receipts.py`:

```python
from datetime import datetime

from database.db import CATEGORIES

ALLOWED_MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_RECEIPT_BYTES = 5 * 1024 * 1024

RECEIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "is_receipt": {"type": "boolean"},
        "amount": {"type": ["number", "null"]},
        "date": {"type": ["string", "null"]},
        "description": {"type": ["string", "null"]},
        "category": {"type": "string", "enum": CATEGORIES},
    },
    "required": ["is_receipt", "amount", "date", "description", "category"],
    "additionalProperties": False,
}


def detect_image_type(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def normalise_receipt(fields, today):
    amount = fields.get("amount")
    if amount is None or amount <= 0:
        amount_str = ""
    else:
        amount_str = "%.2f" % amount

    date_str = fields.get("date")
    try:
        if date_str is None:
            raise ValueError("no date")
        datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        date_str = today.isoformat()

    description = fields.get("description")
    if description is None:
        description = ""
    description = description.strip()[:200]

    category = fields.get("category")
    if category not in CATEGORIES:
        category = "Other"

    return {
        "amount": amount_str,
        "category": category,
        "date": date_str,
        "description": description,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_receipt_ocr_intake.py -v`
Expected: PASS (all 10 tests)

Run the full suite to confirm no regressions: `pytest -q`

- [ ] **Step 5: Commit**

```bash
git add ai/receipts.py tests/test_receipt_ocr_intake.py
git commit -m "feat: add pure receipt image-type detection and normalisation helpers"
```

---

### Task 2: `ai/prompts.py` RECEIPT_PROMPT + `ai/llm_client.py` extraction token budget + `extract_receipt`

**Files:**
- Modify: `ai/prompts.py` (add `RECEIPT_PROMPT`)
- Modify: `ai/llm_client.py` (extraction calls use `EXTRACT_MAX_TOKENS`, not `CHAT_MAX_TOKENS`)
- Modify: `ai/receipts.py` (add `extract_receipt`)
- Test: `tests/test_receipt_ocr_intake.py` (append)

**Interfaces:**
- Consumes: `ai.llm_client.create_message(system_text, context_text="", turns=None, tools=None, response_schema=None, image=None)` and `llm_client.AIUnavailableError` (both from Step 10, called only as `llm_client.create_message(...)` / `llm_client.AIUnavailableError` via `from ai import llm_client`).
- Produces: `ai.prompts.RECEIPT_PROMPT` (str). `ai.receipts.extract_receipt(image_bytes: bytes, media_type: str, today: date) -> dict` — the parsed JSON dict from the model (keys `is_receipt`, `amount`, `date`, `description`, `category`), or raises `llm_client.AIUnavailableError`.

**Why `ai/llm_client.py` needs a change even though the spec's own file list omits it:** Step 10 left `create_message()` hardcoding `max_output_tokens=CHAT_MAX_TOKENS` on every call, since chat was the only caller at the time (this was flagged as a known gap in Step 10's final review). This spec's own "Rules for implementation" section requires `max_tokens = EXTRACT_MAX_TOKENS` for the extraction call, and callers never pass a `max_tokens` argument to `create_message()` — so the seam itself must pick the right budget internally. The chat path never passes `response_schema`; the extraction path always does. So: pick `EXTRACT_MAX_TOKENS` when `response_schema` is given, `CHAT_MAX_TOKENS` otherwise. This one-line change is in scope for this task.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_receipt_ocr_intake.py`:

```python
import json

import pytest

from ai import llm_client
from ai.prompts import RECEIPT_PROMPT
from ai.receipts import RECEIPT_SCHEMA, extract_receipt
from tests.conftest import text_reply


# ------------------------------------------------------------------ #
# extract_receipt                                                     #
# ------------------------------------------------------------------ #

def test_extract_receipt_returns_parsed_json(fake_llm):
    payload = {"is_receipt": True, "amount": 249.5, "date": "2026-09-01", "description": "Lunch", "category": "Food"}
    fake_llm.responses.append(text_reply(json.dumps(payload)))

    result = extract_receipt(b"\x89PNG\r\n\x1a\n" + b"rest", "image/png", date(2026, 9, 1))

    assert result == payload
    call = fake_llm.calls[0]
    assert call["response_schema"] is RECEIPT_SCHEMA
    assert call["image"]["media_type"] == "image/png"
    assert call["system_text"] == RECEIPT_PROMPT
    assert "2026-09-01" in call["turns"][0]["content"]


def test_extract_receipt_raises_on_non_json_text(fake_llm):
    fake_llm.responses.append(text_reply("this is not json"))

    with pytest.raises(llm_client.AIUnavailableError):
        extract_receipt(b"\x89PNG\r\n\x1a\n", "image/png", date(2026, 9, 1))


def test_extract_receipt_raises_on_refused(fake_llm):
    fake_llm.responses.append(text_reply("", finish_reason="refused"))

    with pytest.raises(llm_client.AIUnavailableError):
        extract_receipt(b"\x89PNG\r\n\x1a\n", "image/png", date(2026, 9, 1))
```

Add `from datetime import date` to the top of `tests/test_receipt_ocr_intake.py` if not already present from Task 1 (Task 1's tests already import it — just confirm the single top-level import covers both).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_receipt_ocr_intake.py -v -k extract_receipt`
Expected: FAIL with `ImportError: cannot import name 'extract_receipt'`

- [ ] **Step 3: Implement**

Append to `ai/prompts.py`:

```python
RECEIPT_PROMPT = (
    "You are extracting structured data from an image of a purchase receipt "
    "or bill for the Spendly expense tracker. amount is the grand total "
    "actually paid (not a subtotal or tax line alone), as a plain number. "
    "date must be ISO format YYYY-MM-DD, or null if it cannot be read. "
    "description is a short label of at most 200 characters, such as "
    "'Grocery run at Big Bazaar'. category is the best fit among Food, "
    "Transport, Bills, Health, Entertainment, Shopping, and Other. Set "
    "is_receipt to false when the image is not a purchase receipt or bill."
)
```

In `ai/llm_client.py`, find this block (around line 113):

```python
    config_kwargs = {
        "system_instruction": system_instruction,
        "max_output_tokens": CHAT_MAX_TOKENS,
    }
```

Replace it with:

```python
    config_kwargs = {
        "system_instruction": system_instruction,
        "max_output_tokens": EXTRACT_MAX_TOKENS if response_schema else CHAT_MAX_TOKENS,
    }
```

`ai/receipts.py` currently starts with (from Task 1):

```python
from datetime import datetime

from database.db import CATEGORIES
```

Replace those two lines with the following complete import block (stdlib first, then first-party, matching the convention already used in `app.py` and `ai/chat.py`):

```python
import base64
import json
from datetime import datetime

from ai import llm_client
from ai.prompts import RECEIPT_PROMPT
from database.db import CATEGORIES
```

Then append the function itself at the end of `ai/receipts.py`:

```python
def extract_receipt(image_bytes, media_type, today):
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")

    reply = llm_client.create_message(
        system_text=RECEIPT_PROMPT,
        turns=[{"role": "user", "content": "Today is %s. Extract the receipt fields." % today.isoformat()}],
        image={"media_type": media_type, "data": b64},
        response_schema=RECEIPT_SCHEMA,
    )

    if reply.finish_reason == "refused":
        raise llm_client.AIUnavailableError("The assistant is temporarily unavailable. Please try again.")

    try:
        return json.loads(reply.text)
    except (ValueError, TypeError):
        raise llm_client.AIUnavailableError("The assistant is temporarily unavailable. Please try again.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_receipt_ocr_intake.py -v`
Expected: PASS (all tests so far)

Run the full suite: `pytest -q` — this exercises the `ai/llm_client.py` change against every existing chat test too (none of which pass `response_schema`, so they must still get `CHAT_MAX_TOKENS`; nothing in the existing test suite asserts on `max_output_tokens` directly, so a pass here means no regression, not proof of the new branch — that's confirmed by reading the code, and the real-provider behavior is verified manually in Task 5).

- [ ] **Step 5: Commit**

```bash
git add ai/prompts.py ai/llm_client.py ai/receipts.py tests/test_receipt_ocr_intake.py
git commit -m "feat: add receipt extraction prompt and LLM call, budget extraction calls separately"
```

---

### Task 3: `POST /expenses/scan` route

**Files:**
- Modify: `app.py`
- Test: `tests/test_receipt_ocr_intake.py` (append)

**Interfaces:**
- Consumes: `detect_image_type`, `extract_receipt`, `normalise_receipt`, `MAX_RECEIPT_BYTES` from `ai.receipts` (Tasks 1-2); `llm_client.AIError` (Step 10, already used elsewhere in `app.py` as `llm_client.AIError`); `CATEGORIES` (already imported).
- Produces: route `POST /expenses/scan`, view function `scan_receipt`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_receipt_ocr_intake.py`:

```python
import io

from database.queries import get_summary_stats

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 32
PDF_BYTES = b"%PDF-1.4" + b"0" * 32


def _upload(client, data, filename="receipt.png"):
    return client.post(
        "/expenses/scan",
        data={"receipt": (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )


# ------------------------------------------------------------------ #
# POST /expenses/scan                                                  #
# ------------------------------------------------------------------ #

def test_scan_receipt_requires_auth(client):
    response = _upload(client, PNG_BYTES)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_scan_receipt_success(client, fake_llm):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    before_count = get_summary_stats(1)["transaction_count"]
    payload = {"is_receipt": True, "amount": 249.5, "date": "2026-09-01", "description": "Lunch", "category": "Food"}
    fake_llm.responses.append(text_reply(json.dumps(payload)))

    response = _upload(client, PNG_BYTES)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'value="249.50"' in body
    assert 'value="2026-09-01"' in body
    assert "Lunch" in body
    assert 'value="Food" selected>' in body
    assert "Receipt read" in body
    assert get_summary_stats(1)["transaction_count"] == before_count


def test_scan_receipt_no_file(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/expenses/scan", data={}, content_type="multipart/form-data")

    assert response.status_code == 400
    assert "Please choose a receipt image." in response.get_data(as_text=True)


def test_scan_receipt_wrong_type(client, fake_llm):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = _upload(client, PDF_BYTES, filename="receipt.png")

    assert response.status_code == 400
    assert "PNG, JPEG, WebP or GIF" in response.get_data(as_text=True)
    assert fake_llm.calls == []


def test_scan_receipt_too_large(client, fake_llm):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    oversized = b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024 + 1)

    response = _upload(client, oversized)

    assert response.status_code == 400
    assert "5 MB or smaller" in response.get_data(as_text=True)
    assert fake_llm.calls == []


def test_scan_receipt_not_a_receipt(client, fake_llm):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    payload = {"is_receipt": False, "amount": None, "date": None, "description": None, "category": "Other"}
    fake_llm.responses.append(text_reply(json.dumps(payload)))

    response = _upload(client, PNG_BYTES)

    assert response.status_code == 400
    assert "doesn't look like a receipt" in response.get_data(as_text=True)


def test_scan_receipt_no_api_key_configured(client, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    llm_client._client = None
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = _upload(client, PNG_BYTES)

    assert response.status_code == 503
    assert "not configured" in response.get_data(as_text=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_receipt_ocr_intake.py -v -k scan_receipt`
Expected: FAIL with 404s (route doesn't exist yet)

- [ ] **Step 3: Implement the route**

In `app.py`, add to the `from ai.receipts import ...` — this is a new import line; add it directly below the existing `from ai.chat import HISTORY_LIMIT, run_chat_turn` line:

```python
from ai.receipts import MAX_RECEIPT_BYTES, detect_image_type, extract_receipt, normalise_receipt
```

Add the route right after `add_expense` (before `edit_expense`):

```python
@app.route("/expenses/scan", methods=["POST"])
def scan_receipt():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    today = date.today()

    def rerender(message, status):
        flash(message, "error")
        return render_template("add_expense.html", categories=CATEGORIES, today=today.isoformat()), status

    file = request.files.get("receipt")
    if not file or not file.filename:
        return rerender("Please choose a receipt image.", 400)

    data = file.read()
    if len(data) > MAX_RECEIPT_BYTES:
        return rerender("Receipt image must be 5 MB or smaller.", 400)

    media_type = detect_image_type(data)
    if media_type is None:
        return rerender("Please upload a PNG, JPEG, WebP or GIF image.", 400)

    try:
        result = extract_receipt(data, media_type, today)
    except llm_client.AIError as e:
        return rerender(e.user_message, e.status)

    if not result.get("is_receipt"):
        return rerender("That image doesn't look like a receipt.", 400)

    fields = normalise_receipt(result, today)
    flash("Receipt read — please check the details before saving.", "success")
    return render_template("add_expense.html", categories=CATEGORIES, today=today.isoformat(), **fields)
```

Also add, right after `app.secret_key = "dev-secret-key-change-in-production"`, the safety-net body-size cap:

```python
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_receipt_ocr_intake.py -v`
Expected: PASS (all tests so far)

Run the full suite: `pytest -q`
Expected: PASS — pay particular attention to the existing `add_expense`/`edit_expense` tests, since `MAX_CONTENT_LENGTH` is new global Flask config that now applies to every route, not just this one.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_receipt_ocr_intake.py
git commit -m "feat: add POST /expenses/scan route"
```

---

### Task 4: Dropzone UI on the Add Expense page

**Files:**
- Modify: `templates/add_expense.html`
- Create: `static/css/receipt.css`
- Create: `static/js/receipt.js`
- Test: `tests/test_receipt_ocr_intake.py` (append)

**Interfaces:**
- Consumes: `url_for('scan_receipt')` from Task 3.
- Produces: markup with `id="receipt-form"`, `id="receipt-dropzone"`, `id="receipt"` (file input), `id="receipt-filename"`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_receipt_ocr_intake.py`:

```python
def test_add_expense_page_includes_receipt_dropzone(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.get("/expenses/add")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="receipt-form"' in body
    assert 'id="receipt-dropzone"' in body
    assert "js/receipt.js" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_receipt_ocr_intake.py -v -k receipt_dropzone`
Expected: FAIL — `'id="receipt-form"' in body` is `False`

- [ ] **Step 3: Build the dropzone**

Modify `templates/add_expense.html` — add a `{% block head %}` right after `{% block title %}`:

```html
{% block head %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/receipt.css') }}">
{% endblock %}
```

Add the receipt card above the existing `<div class="auth-card">`, inside `.auth-container`:

```html
        <div class="auth-card receipt-card">
            <form id="receipt-form" method="POST" action="{{ url_for('scan_receipt') }}" enctype="multipart/form-data">
                <label class="receipt-dropzone" id="receipt-dropzone" for="receipt">Drop a receipt image here or click to choose</label>
                <input type="file" id="receipt" name="receipt"
                       accept="image/png,image/jpeg,image/webp,image/gif"
                       class="receipt-input" required>
                <span id="receipt-filename" class="receipt-filename"></span>
                <button type="submit" class="btn-submit receipt-submit">Scan receipt</button>
            </form>
        </div>

```

Add `{% block scripts %}` at the end of the file, after `{% endblock %}` that closes `content`:

```html
{% block scripts %}
<script src="{{ url_for('static', filename='js/receipt.js') }}"></script>
{% endblock %}
```

Create `static/css/receipt.css`:

```css
.receipt-card {
    margin-bottom: 1.5rem;
}

.receipt-dropzone {
    display: block;
    text-align: center;
    padding: 2rem 1rem;
    border: 2px dashed var(--border);
    border-radius: var(--radius-md);
    color: var(--ink-muted);
    font-family: var(--font-body);
    cursor: pointer;
}

.receipt-dropzone-active {
    border-color: var(--accent);
    background: var(--accent-light);
    color: var(--ink);
}

.receipt-input {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
}

.receipt-filename {
    display: block;
    margin-top: 0.5rem;
    font-size: 0.85rem;
    color: var(--ink-muted);
    text-align: center;
}

.receipt-submit {
    margin-top: 1rem;
}
```

Create `static/js/receipt.js`:

```js
(function () {
    var form = document.getElementById("receipt-form");
    var dropzone = document.getElementById("receipt-dropzone");
    var input = document.getElementById("receipt");
    var filenameEl = document.getElementById("receipt-filename");

    if (!form || !dropzone || !input) {
        return;
    }

    var submitButton = form.querySelector(".receipt-submit");

    function showFilename(file) {
        if (filenameEl && file) {
            filenameEl.textContent = file.name;
        }
    }

    dropzone.addEventListener("dragover", function (event) {
        event.preventDefault();
        dropzone.classList.add("receipt-dropzone-active");
    });

    dropzone.addEventListener("dragleave", function () {
        dropzone.classList.remove("receipt-dropzone-active");
    });

    dropzone.addEventListener("drop", function (event) {
        event.preventDefault();
        dropzone.classList.remove("receipt-dropzone-active");
        if (event.dataTransfer && event.dataTransfer.files.length) {
            input.files = event.dataTransfer.files;
            showFilename(input.files[0]);
            form.submit();
        }
    });

    input.addEventListener("change", function () {
        if (input.files.length) {
            showFilename(input.files[0]);
            form.submit();
        }
    });

    form.addEventListener("submit", function () {
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.textContent = "Reading receipt…";
        }
    });
})();
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_receipt_ocr_intake.py -v`
Expected: PASS (all tests so far)

Run the full suite: `pytest -q`
Expected: PASS — this modifies `add_expense.html`, so re-check the existing add/edit-expense tests aren't checking for the OLD absence of a `{% block head %}`/`{% block scripts %}` (they shouldn't be, but confirm).

- [ ] **Step 5: Commit**

```bash
git add templates/add_expense.html static/css/receipt.css static/js/receipt.js tests/test_receipt_ocr_intake.py
git commit -m "feat: add receipt dropzone UI to Add Expense page"
```

---

### Task 5: Docs and manual verification

**Files:**
- Modify: `CLAUDE.md` (flip `POST /expenses/scan` to Implemented)

**Interfaces:** None — documentation and manual, non-automated verification only.

- [ ] **Step 1: Flip the route table row**

In `CLAUDE.md`'s `## Implemented vs stub routes` table, change:

```
| `POST /expenses/scan` | Stub — Step 12 |
```

to:

```
| `POST /expenses/scan` | Implemented — Step 12 |
```

- [ ] **Step 2: Run the full automated suite**

Run: `pytest -v` with `LLM_API_KEY` unset in the shell.
Expected: PASS, confirming no test in `tests/test_receipt_ocr_intake.py` needs a real key or imports `google.genai`.

Verify: `grep -rn "google.genai\|from google import genai" tests/test_receipt_ocr_intake.py` returns nothing.

- [ ] **Step 3: Manual smoke test — no key configured**

```bash
unset LLM_API_KEY
python app.py
```

Log in, go to `/expenses/add`, choose or drop any image file. Expected: an error flash reading "The AI assistant is not configured. Set LLM_API_KEY to enable it.", and manual entry in the form below still works normally.

- [ ] **Step 4: Manual smoke test — real key, real receipt image**

```bash
export LLM_API_KEY=<a working Gemini key>
python app.py
```

Find or create a real receipt-like image (a photo of a bill, or any picture with a total/date on it) and drop it on the dropzone. Expected: the page reloads with the form pre-filled (amount, date, description, category) and the "Receipt read" success flash. Confirm nothing was saved yet (no row appears on `/profile` until you click "Add Expense" yourself).

Also test with a non-receipt image (e.g. a random photo). Expected: 400 "That image doesn't look like a receipt."

While this is running, this is also the point to verify the `ai/llm_client.py` `EXTRACT_MAX_TOKENS` branch from Task 2 actually takes effect against the real API — there's no automated test for it (the fake bypasses `create_message`'s internals entirely). If the extraction reply looks truncated or malformed, check that `max_output_tokens` is really resolving to `EXTRACT_MAX_TOKENS` (1024) and not something wrong.

- [ ] **Step 5: Verify no file is written anywhere**

After the manual tests above (both key-configured and not), run:

```bash
git status --porcelain
```

Expected: no untracked files appear anywhere in the repo as a result of scanning (aside from `expense_tracker.db`'s normal journal churn, which is already gitignored). This confirms the image was never written to disk.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: mark POST /expenses/scan as implemented"
```

---

## Definition of Done

- [ ] The Add Expense page shows a "Scan receipt" dropzone above the form
- [ ] Dropping or choosing an image submits it and the form comes back pre-filled with amount, date, description and category
- [ ] Nothing is saved until the user clicks "Add Expense"
- [ ] A non-image file or an image over 5 MB produces a clear error and no API call
- [ ] Without `LLM_API_KEY` the scan shows the "not configured" message and manual entry still works
- [ ] No file is written anywhere in the project during a scan (`git status` stays clean)
- [ ] All tests in `tests/test_receipt_ocr_intake.py` pass without `LLM_API_KEY` and without importing any provider SDK
- [ ] `CLAUDE.md` route table shows `POST /expenses/scan` as Implemented
