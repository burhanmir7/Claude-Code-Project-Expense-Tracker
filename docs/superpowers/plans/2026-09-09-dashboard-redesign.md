# Profile Page as Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `/profile` into a sidebar-based dashboard (KPI cards, a monthly-spending bar chart, a category donut chart) using only data Spendly already has, and move receipt scanning from a full-page dropzone into the chat as an attach-and-confirm flow.

**Architecture:** `base.html` gains a `hide_chrome` flag that suppresses the navbar/footer for one page only. `profile.html` becomes a two-column layout (a new `_dashboard_sidebar.html` partial + the restyled main dashboard), fed by one new query (`get_monthly_totals`) plus the existing stats/category/transaction queries unchanged. Chart.js (CDN) renders the two charts from data passed via `data-*` JSON attributes on their canvases, read by a new `dashboard.js`. Receipt scanning gets two new JSON routes (`POST /api/chat/receipt`, `POST /api/expenses`) that reuse `ai/receipts.py` exactly as Step 12 built it; the old `POST /expenses/scan` route, its dropzone template, and its dedicated CSS/JS are deleted in the same pass that adds the replacement.

**Tech Stack:** Flask, raw `sqlite3`, vanilla JS (ES5 IIFE), Chart.js 4.4.4 via CDN (the one approved external-library exception), pytest.

**Spec:** `docs/superpowers/specs/2026-09-09-dashboard-redesign-design.md`

## Global Constraints

- Placeholder sidebar items and KPI cards are never `<a href="...">` and never carry a click handler — plain elements with `aria-disabled="true"` and a "Soon" label.
- No invented numbers anywhere: placeholders show `₹0.00`, `—`, or a static 0%-progress shell — never a plausible-looking fake figure.
- New JSON routes follow the existing `/api/*` convention exactly: `request.get_json(silent=True)` / `request.files.get(...)`, `401 {"error": "Authentication required."}` when logged out, never `abort()`, never a redirect.
- Image bytes never touch disk, DB, session, or logs — `POST /api/chat/receipt` reuses `ai/receipts.py` as-is, no new image-handling code.
- The new rich assistant chat bubble renders all model-derived text via `textContent`/DOM creation only, never `innerHTML`.
- `get_monthly_totals` uses parameterised queries only, scoped to `user_id`, zero-filled and contiguous — never skip a month for lack of data.
- Chart.js is the only external script this feature adds. CSS uses custom-property tokens only — no hardcoded hex values.
- `hide_chrome` defaults to falsy so no other page's rendering changes.
- Callers reference the AI seam only as `llm_client.AIError` / `run_chat_turn` / `extract_receipt` etc. — nothing new imports a provider SDK; only `ai/llm_client.py` may do that (unchanged from Steps 10/12).

---

### Task 1: `get_monthly_totals` query

**Files:**
- Modify: `database/queries.py`
- Test: `tests/test_backend_connection.py` (append)

**Interfaces:**
- Produces: `get_monthly_totals(user_id, months=6) -> list[dict]` — exactly `months` entries, oldest to newest, each `{"month": "YYYY-MM", "total": float}`; a month with no expenses appears with `total: 0`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_backend_connection.py`:

```python
from database.queries import get_monthly_totals


def test_get_monthly_totals_returns_six_contiguous_months(client):
    from database.db import get_db

    conn = get_db()
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (1, 100.0, "Food", "2026-07-15", "test"),
    )
    conn.commit()
    conn.close()

    result = get_monthly_totals(1, months=6)

    assert len(result) == 6
    months = [row["month"] for row in result]
    assert months == sorted(months)
    for row in result:
        assert set(row.keys()) == {"month", "total"}


def test_get_monthly_totals_zero_fills_months_with_no_expenses(client):
    result = get_monthly_totals(999999, months=6)

    assert len(result) == 6
    assert all(row["total"] == 0 for row in result)


def test_get_monthly_totals_scoped_to_user(client):
    from database.db import get_db

    conn = get_db()
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (1, 500.0, "Food", date.today().isoformat(), "mine"),
    )
    conn.commit()
    conn.close()

    mine = get_monthly_totals(1, months=1)
    other = get_monthly_totals(999999, months=1)

    assert mine[0]["total"] >= 500.0
    assert other[0]["total"] == 0
```

Add `from datetime import date` to the top of `tests/test_backend_connection.py` if it isn't already imported there (check first — several other tests in this file may already need it).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_backend_connection.py -v -k monthly_totals`
Expected: FAIL with `ImportError: cannot import name 'get_monthly_totals'`

- [ ] **Step 3: Implement**

In `database/queries.py`, change the top import line from:

```python
from datetime import datetime
```

to:

```python
from datetime import date, datetime
```

Then append the function:

```python
def get_monthly_totals(user_id, months=6):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT strftime('%Y-%m', date) AS ym, SUM(amount) AS total "
            "FROM expenses WHERE user_id = ? GROUP BY ym",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    totals_by_month = {row["ym"]: row["total"] for row in rows}

    today = date.today()
    year, month = today.year, today.month
    buckets = []
    for _ in range(months):
        buckets.append("%04d-%02d" % (year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    buckets.reverse()

    return [{"month": ym, "total": totals_by_month.get(ym, 0)} for ym in buckets]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backend_connection.py -v -k monthly_totals`
Expected: PASS (all 3 tests)

Run the full suite: `pytest -q`

- [ ] **Step 5: Commit**

```bash
git add database/queries.py tests/test_backend_connection.py
git commit -m "feat: add get_monthly_totals query for the dashboard bar chart"
```

---

### Task 2: New JSON routes — `POST /api/chat/receipt` and `POST /api/expenses`

**Files:**
- Modify: `app.py`
- Test: `tests/test_receipt_ocr_intake.py` (append; old route tests are removed in Task 3, not this task — this task only adds the new routes alongside the old one, so both exist briefly)

**Interfaces:**
- Consumes: `detect_image_type`, `extract_receipt`, `normalise_receipt`, `MAX_RECEIPT_BYTES` from `ai.receipts` (already imported in `app.py`); `llm_client.AIError` (already imported); `insert_chat_message`, `insert_expense`, `CATEGORIES` (already imported).
- Produces: routes `POST /api/chat/receipt` (view function `chat_scan_receipt`) and `POST /api/expenses` (view function `api_add_expense`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_receipt_ocr_intake.py`:

```python
def _upload_json(client, data, filename="receipt.png"):
    return client.post(
        "/api/chat/receipt",
        data={"receipt": (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )


def test_chat_scan_receipt_requires_auth(client):
    response = _upload_json(client, PNG_BYTES)

    assert response.status_code == 401


def test_chat_scan_receipt_success_returns_expense_and_stores_chat_history(client, fake_llm):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    payload = {"is_receipt": True, "amount": 249.5, "date": "2026-09-01", "description": "Lunch", "category": "Food"}
    fake_llm.responses.append(text_reply(json.dumps(payload)))

    response = _upload_json(client, PNG_BYTES, filename="lunch.png")
    body = response.get_json()

    assert response.status_code == 200
    assert body["expense"] == {"amount": "249.50", "date": "2026-09-01", "description": "Lunch", "category": "Food"}
    assert "reply" in body and isinstance(body["reply"], str)

    from database.queries import get_chat_messages
    rows = get_chat_messages(1)
    assert rows[-2]["role"] == "user"
    assert "lunch.png" in rows[-2]["content"]
    assert rows[-1]["role"] == "assistant"


def test_chat_scan_receipt_no_file_returns_400_json(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/api/chat/receipt", data={}, content_type="multipart/form-data")

    assert response.status_code == 400
    assert response.get_json()["error"] == "Please choose a receipt image."


def test_chat_scan_receipt_wrong_type_returns_400_json(client, fake_llm):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = _upload_json(client, PDF_BYTES)

    assert response.status_code == 400
    assert "PNG, JPEG, WebP or GIF" in response.get_json()["error"]
    assert fake_llm.calls == []


def test_chat_scan_receipt_not_a_receipt_returns_400_json(client, fake_llm):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    payload = {"is_receipt": False, "amount": None, "date": None, "description": None, "category": "Other"}
    fake_llm.responses.append(text_reply(json.dumps(payload)))

    response = _upload_json(client, PNG_BYTES)

    assert response.status_code == 400
    assert "doesn't look like a receipt" in response.get_json()["error"]


def test_chat_scan_receipt_no_api_key_returns_503_json(client, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    llm_client._client = None
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = _upload_json(client, PNG_BYTES)

    assert response.status_code == 503
    assert "not configured" in response.get_json()["error"]


def test_api_add_expense_requires_auth(client):
    response = client.post("/api/expenses", json={"amount": "10.00", "date": "2026-09-01", "description": "x", "category": "Food"})

    assert response.status_code == 401


def test_api_add_expense_success_creates_expense(client):
    from database.queries import get_summary_stats

    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    before_count = get_summary_stats(1)["transaction_count"]

    response = client.post("/api/expenses", json={"amount": "249.50", "date": "2026-09-01", "description": "Lunch", "category": "Food"})

    assert response.status_code == 200
    assert response.get_json() == {"success": True}
    assert get_summary_stats(1)["transaction_count"] == before_count + 1


def test_api_add_expense_invalid_amount_returns_400(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/api/expenses", json={"amount": "not a number", "date": "2026-09-01", "description": "x", "category": "Food"})

    assert response.status_code == 400


def test_api_add_expense_invalid_category_returns_400(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/api/expenses", json={"amount": "10.00", "date": "2026-09-01", "description": "x", "category": "Groceries"})

    assert response.status_code == 400


def test_api_add_expense_invalid_date_returns_400(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/api/expenses", json={"amount": "10.00", "date": "not-a-date", "description": "x", "category": "Food"})

    assert response.status_code == 400


def test_api_add_expense_description_too_long_returns_400(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/api/expenses", json={"amount": "10.00", "date": "2026-09-01", "description": "x" * 201, "category": "Food"})

    assert response.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_receipt_ocr_intake.py -v -k "chat_scan_receipt or api_add_expense"`
Expected: FAIL with 404s (routes don't exist yet)

- [ ] **Step 3: Implement the routes**

In `app.py`, add the `_json_error` helper's neighbor routes. If `_json_error(message, status)` doesn't already exist in `app.py` (it was added in Step 10 for the chat routes), reuse it; otherwise this task assumes it's already present under the `# Helpers` banner.

Add these two routes near the existing `# AI routes` banner (after `chat_clear`, or wherever the AI-related routes are grouped):

```python
@app.route("/api/chat/receipt", methods=["POST"])
def chat_scan_receipt():
    user_id = session.get("user_id")
    if not user_id:
        return _json_error("Authentication required.", 401)

    today = date.today()

    file = request.files.get("receipt")
    if not file or not file.filename:
        return _json_error("Please choose a receipt image.", 400)

    data = file.read()
    if len(data) > MAX_RECEIPT_BYTES:
        return _json_error("Receipt image must be 5 MB or smaller.", 400)

    media_type = detect_image_type(data)
    if media_type is None:
        return _json_error("Please upload a PNG, JPEG, WebP or GIF image.", 400)

    try:
        result = extract_receipt(data, media_type, today)
    except llm_client.AIError as e:
        return _json_error(e.user_message, e.status)

    if not result.get("is_receipt"):
        return _json_error("That image doesn't look like a receipt.", 400)

    fields = normalise_receipt(result, today)
    reply = "I found a %s expense of ₹%s from %s. Want me to save it?" % (
        fields["category"], fields["amount"], fields["date"],
    )

    insert_chat_message(user_id, "user", "📎 " + file.filename)
    insert_chat_message(user_id, "assistant", reply)

    return jsonify({"reply": reply, "expense": fields})


@app.route("/api/expenses", methods=["POST"])
def api_add_expense():
    user_id = session.get("user_id")
    if not user_id:
        return _json_error("Authentication required.", 401)

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _json_error("Amount, category, and date are required.", 400)

    amount = (body.get("amount") or "").strip() if isinstance(body.get("amount"), str) else ""
    category = (body.get("category") or "").strip() if isinstance(body.get("category"), str) else ""
    date_str = (body.get("date") or "").strip() if isinstance(body.get("date"), str) else ""
    description = (body.get("description") or "").strip() if isinstance(body.get("description"), str) else ""

    if not amount or not category or not date_str:
        return _json_error("Amount, category, and date are required.", 400)

    try:
        amount_value = float(amount)
    except ValueError:
        return _json_error("Amount must be a valid number.", 400)

    if amount_value <= 0:
        return _json_error("Amount must be greater than zero.", 400)

    if category not in CATEGORIES:
        return _json_error("Please select a valid category.", 400)

    parsed_date = _parse_date(date_str)
    if not parsed_date:
        return _json_error("Please enter a valid date.", 400)

    if len(description) > 200:
        return _json_error("Description must be 200 characters or fewer.", 400)

    insert_expense(user_id, amount_value, category, parsed_date.isoformat(), description or None)

    return jsonify({"success": True})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_receipt_ocr_intake.py -v`
Expected: PASS (all tests, including the still-present old `scan_receipt` tests — those are untouched by this task)

Run the full suite: `pytest -q`

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_receipt_ocr_intake.py
git commit -m "feat: add JSON receipt-scan and expense-create routes for the chat flow"
```

---

### Task 3: Remove the old dropzone, `POST /expenses/scan`, and its tests

**Files:**
- Modify: `app.py` (remove `scan_receipt`)
- Modify: `templates/add_expense.html` (remove the receipt card, `{% block head %}`, `{% block scripts %}`)
- Delete: `static/css/receipt.css`
- Delete: `static/js/receipt.js`
- Modify: `tests/test_receipt_ocr_intake.py` (remove the route/template tests tied to the deleted route and dropzone; keep the `ai/receipts.py` unit tests and the new Task 2 tests)
- Modify: `CLAUDE.md`

**Interfaces:** None new — this task only removes.

- [ ] **Step 1: Remove the dead route tests**

In `tests/test_receipt_ocr_intake.py`, delete these test functions entirely (they test the route and template this task removes):
`test_scan_receipt_requires_auth`, `test_scan_receipt_success`, `test_scan_receipt_no_file`, `test_scan_receipt_wrong_type`, `test_scan_receipt_too_large`, `test_scan_receipt_not_a_receipt`, `test_scan_receipt_no_api_key_configured`, `test_add_expense_page_includes_receipt_dropzone`.

Keep everything else in the file: the `detect_image_type`/`normalise_receipt`/`RECEIPT_SCHEMA` unit tests, the `extract_receipt` unit tests, and the new `chat_scan_receipt`/`api_add_expense` tests from Task 2. Also delete the now-unused `_upload` helper function and the `PNG_BYTES`/`PDF_BYTES` module constants **only if** nothing in the file still uses them — check first, since Task 2's `_upload_json` and tests reuse `PNG_BYTES`/`PDF_BYTES`, so those constants stay; only the old `_upload` helper (distinct from `_upload_json`) becomes dead code if nothing else calls it.

- [ ] **Step 2: Run the remaining tests to confirm nothing broke**

Run: `pytest tests/test_receipt_ocr_intake.py -v`
Expected: PASS (all remaining tests)

- [ ] **Step 3: Remove the route from app.py**

Delete the entire `scan_receipt` view function (the `@app.route("/expenses/scan", methods=["POST"])` block) from `app.py`.

- [ ] **Step 4: Revert add_expense.html**

In `templates/add_expense.html`, remove the `{% block head %}...{% endblock %}` block (the `receipt.css` link), remove the entire `<div class="auth-card receipt-card">...</div>` block, and remove the `{% block scripts %}...{% endblock %}` block (the `receipt.js` script tag). The file should return to exactly its Step 7 shape: `{% block title %}`, then `{% block content %}` containing only the header and the manual-entry form card.

- [ ] **Step 5: Delete the dead CSS/JS files**

```bash
rm static/css/receipt.css static/js/receipt.js
```

- [ ] **Step 6: Update CLAUDE.md**

In the route table, remove this row entirely:

```
| `POST /expenses/scan` | Implemented — Step 12 |
```

(It will be replaced by rows for the two new routes in Task 8, once they're stable — don't add those rows yet in this task, just remove the dead one.)

- [ ] **Step 7: Run the full suite**

Run: `pytest -q`
Expected: PASS — confirms nothing else referenced the removed route, template blocks, or files.

- [ ] **Step 8: Commit**

```bash
git add app.py templates/add_expense.html tests/test_receipt_ocr_intake.py CLAUDE.md
git rm static/css/receipt.css static/js/receipt.js
git commit -m "refactor: remove the old Add Expense dropzone, replaced by the chat-based scan flow"
```

---

### Task 4: `hide_chrome` layout flag + dashboard sidebar partial

**Files:**
- Modify: `templates/base.html`
- Create: `templates/_dashboard_sidebar.html`
- Test: `tests/test_backend_connection.py` (append)

**Interfaces:**
- Produces: `base.html` respects a `hide_chrome` template variable (falsy by default) to suppress the `<nav class="navbar">` and `<footer class="footer">` blocks. `_dashboard_sidebar.html` is a partial (does not extend `base.html`) that renders the brand mark, three nav sections (General/Tools/Other), the theme-toggle button, sign-out link, and an inert "Upgrade to PRO" card. It expects to be `{% include %}`d somewhere that already has `session` available (it always does, in Jinja).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_backend_connection.py`:

```python
def test_login_page_still_shows_navbar(client):
    response = client.get("/login")
    body = response.get_data(as_text=True)

    assert 'class="navbar"' in body


def test_profile_page_hides_top_navbar(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert 'class="navbar"' not in body
```

- [ ] **Step 2: Run tests to verify the second one fails**

Run: `pytest tests/test_backend_connection.py -v -k "hides_top_navbar or still_shows_navbar"`
Expected: `test_login_page_still_shows_navbar` PASSES already (no behavior change yet); `test_profile_page_hides_top_navbar` FAILS (navbar is still there — `hide_chrome` doesn't exist yet and `profile()` doesn't pass it)

- [ ] **Step 3: Add the `hide_chrome` conditional to base.html**

In `templates/base.html`, wrap the existing `<nav class="navbar">...</nav>` block:

```html
    {% if not hide_chrome %}
    <nav class="navbar">
        ...(unchanged contents)...
    </nav>
    {% endif %}
```

And wrap the existing `<footer class="footer">...</footer>` block the same way:

```html
    {% if not hide_chrome %}
    <footer class="footer">
        ...(unchanged contents)...
    </footer>
    {% endif %}
```

Do not change anything else in `base.html` in this task — `profile()` doesn't pass `hide_chrome=True` yet (that's Task 5), so this step alone doesn't change any page's rendering. The test from Step 1 will still fail until Task 5 wires it up — **that's expected**; note in your report that `test_profile_page_hides_top_navbar` remains red until Task 5, and don't try to make it pass here.

- [ ] **Step 4: Create the sidebar partial**

Create `templates/_dashboard_sidebar.html`:

```html
<aside class="profile-sidebar">
    <div class="profile-sidebar-brand">
        <span class="brand-icon">◈</span>
        <span class="brand-name">Spendly</span>
    </div>

    <div class="profile-sidebar-section">
        <p class="profile-sidebar-heading">General</p>
        <a href="{{ url_for('profile') }}" class="profile-sidebar-link profile-sidebar-link-active">Dashboard</a>
        <span class="profile-sidebar-link profile-sidebar-link-soon" aria-disabled="true">All Expenses <span class="profile-sidebar-soon">Soon</span></span>
        <span class="profile-sidebar-link profile-sidebar-link-soon" aria-disabled="true">Bills &amp; Subscriptions <span class="profile-sidebar-soon">Soon</span></span>
        <span class="profile-sidebar-link profile-sidebar-link-soon" aria-disabled="true">Investment <span class="profile-sidebar-soon">Soon</span></span>
        <span class="profile-sidebar-link profile-sidebar-link-soon" aria-disabled="true">Cards <span class="profile-sidebar-soon">Soon</span></span>
        <span class="profile-sidebar-link profile-sidebar-link-soon" aria-disabled="true">Goals <span class="profile-sidebar-soon">Soon</span></span>
    </div>

    <div class="profile-sidebar-section">
        <p class="profile-sidebar-heading">Tools</p>
        <span class="profile-sidebar-link profile-sidebar-link-soon" aria-disabled="true">Insight <span class="profile-sidebar-soon">Soon</span></span>
        <span class="profile-sidebar-link profile-sidebar-link-soon" aria-disabled="true">Analytics <span class="profile-sidebar-soon">Soon</span></span>
    </div>

    <div class="profile-sidebar-section">
        <p class="profile-sidebar-heading">Other</p>
        <a href="{{ url_for('add_expense') }}" class="profile-sidebar-link">Add Expense</a>
        <span class="profile-sidebar-link profile-sidebar-link-soon" aria-disabled="true">Settings <span class="profile-sidebar-soon">Soon</span></span>
        <span class="profile-sidebar-link profile-sidebar-link-soon" aria-disabled="true">Help Center <span class="profile-sidebar-soon">Soon</span></span>
        <span class="profile-sidebar-link profile-sidebar-link-soon" aria-disabled="true">Support <span class="profile-sidebar-soon">Soon</span></span>
        <button id="theme-toggle" class="profile-sidebar-link profile-sidebar-theme-toggle" type="button" aria-label="Toggle dark mode">Toggle theme</button>
        <a href="{{ url_for('logout') }}" class="profile-sidebar-link">Sign out</a>
    </div>

    <div class="profile-sidebar-upgrade" aria-disabled="true">
        <p class="profile-sidebar-upgrade-title">Upgrade to PRO</p>
        <p class="profile-sidebar-soon">Soon</p>
    </div>
</aside>
```

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: PASS except `test_profile_page_hides_top_navbar`, which stays red until Task 5 — confirm this is the ONLY failure, then proceed.

- [ ] **Step 6: Commit**

```bash
git add templates/base.html templates/_dashboard_sidebar.html tests/test_backend_connection.py
git commit -m "feat: add hide_chrome layout flag and the dashboard sidebar partial"
```

---

### Task 5: Restructure `profile.html` into the dashboard layout

**Files:**
- Modify: `templates/profile.html`
- Modify: `app.py` (`profile()` route)
- Modify: `static/css/profile.css`
- Test: `tests/test_backend_connection.py` (existing profile tests + append)

**Interfaces:**
- Consumes: `get_monthly_totals` (Task 1), `hide_chrome` (Task 4), `_dashboard_sidebar.html` (Task 4).
- Produces: `profile()` passes `hide_chrome=True`, `monthly_expenses` (string, ₹-formatted), `monthly_totals` (list from Task 1), `category_breakdown` (raw list from `get_category_breakdown`, unrounded) to the template, in addition to everything it already passes.

- [ ] **Step 1: Write the failing test**

This task changes what `test_profile_authenticated_seed_user` (in `tests/test_backend_connection.py`) already asserts. Update that existing test to also check the new elements, rather than adding a whole new test — this is the test the plan's earlier assumption about content ("₹318.24", category names) must keep matching. Find `test_profile_authenticated_seed_user` and add these lines at the end of it:

```python
    assert 'class="profile-sidebar"' in body
    assert "Dashboard" in body
    assert "Soon" in body
    assert 'id="monthly-chart"' in body
    assert 'id="category-chart"' in body
```

Also append this new test right after it:

```python
def test_profile_hides_top_navbar_now_wired(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="navbar"' not in body
```

(This second test covers the same assertion `test_profile_page_hides_top_navbar` from Task 4 already made — Task 4's test should now pass too once this task wires `hide_chrome=True` through. Don't delete Task 4's test; this one is just an explicit double-check at this task's own gate.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_backend_connection.py -v -k profile`
Expected: FAIL — `'class="profile-sidebar"' in body` etc. are `False`, and `test_profile_page_hides_top_navbar` from Task 4 is still red

- [ ] **Step 3: Update the `profile()` route**

In `app.py`, add `get_monthly_totals` to the `from database.queries import (...)` block (alphabetized with the rest).

Immediately after the existing `categories = [...]` block in `profile()`, add:

```python
    month_start = today.replace(day=1).isoformat()
    monthly_expenses_total = get_summary_stats(user_id, date_from=month_start, date_to=today.isoformat())["total_spent"]
    monthly_expenses = f"₹{monthly_expenses_total:,.2f}"
    monthly_totals = get_monthly_totals(user_id)
    category_breakdown = get_category_breakdown(user_id, date_from=date_from, date_to=date_to)
```

Then change the `return render_template(...)` call to:

```python
    return render_template(
        "profile.html", user=user, stats=stats,
        transactions=transactions, categories=categories,
        selected_from=date_from, selected_to=date_to,
        active_preset=active_preset, preset_ranges=preset_ranges,
        monthly_expenses=monthly_expenses, monthly_totals=monthly_totals,
        category_breakdown=category_breakdown, hide_chrome=True,
    )
```

(The old `categories` list — used by the horizontal-bar UI this task removes from the template — is no longer referenced by any template markup after Step 4 below. Leave the Python variable and its computation in place for now rather than removing it; Task 8's cleanup pass is a reasonable place to remove genuinely dead server-side code once the whole feature is stable, but removing it here isn't required for this task's tests to pass and isn't worth the extra diff risk in the middle of a bigger template rewrite.)

- [ ] **Step 4: Restructure profile.html**

Replace the entire contents of `templates/profile.html` with:

```html
{% extends "base.html" %}

{% block title %}Your Profile — Spendly{% endblock %}

{% block head %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/profile.css') }}">
{% endblock %}

{% block content %}

<div class="profile-dashboard-shell">
    {% include "_dashboard_sidebar.html" %}

    <div class="profile-dashboard-main">
        <div class="profile-dashboard-header">
            <div>
                <h1 class="profile-dashboard-greeting">Hi, {{ user.name }} 👋</h1>
                <p class="profile-dashboard-subtitle">Track your expenses and transactions</p>
            </div>
            <div class="profile-dashboard-header-actions">
                <span class="profile-dashboard-clock" id="profile-dashboard-clock"></span>
                <div class="profile-dashboard-avatar">{{ user.initials }}</div>
            </div>
        </div>

        <div class="profile-filterbar">
            <div class="profile-filter-presets">
                <a href="{{ url_for('profile', date_from=preset_ranges.this_month[0], date_to=preset_ranges.this_month[1]) }}"
                   class="profile-filter-btn{% if active_preset == 'this_month' %} profile-filter-btn-active{% endif %}">This Month</a>
                <a href="{{ url_for('profile', date_from=preset_ranges.last_3_months[0], date_to=preset_ranges.last_3_months[1]) }}"
                   class="profile-filter-btn{% if active_preset == 'last_3_months' %} profile-filter-btn-active{% endif %}">Last 3 Months</a>
                <a href="{{ url_for('profile', date_from=preset_ranges.last_6_months[0], date_to=preset_ranges.last_6_months[1]) }}"
                   class="profile-filter-btn{% if active_preset == 'last_6_months' %} profile-filter-btn-active{% endif %}">Last 6 Months</a>
                <a href="{{ url_for('profile') }}"
                   class="profile-filter-btn{% if active_preset == 'all_time' %} profile-filter-btn-active{% endif %}">All Time</a>
            </div>
            <form class="profile-filter-custom{% if active_preset is none and selected_from %} profile-filter-custom-active{% endif %}"
                  action="{{ url_for('profile') }}" method="get">
                <label class="profile-filter-label" for="date_from">From
                    <input type="date" id="date_from" name="date_from" value="{{ selected_from or '' }}">
                </label>
                <label class="profile-filter-label" for="date_to">To
                    <input type="date" id="date_to" name="date_to" value="{{ selected_to or '' }}">
                </label>
                <button type="submit" class="profile-filter-apply">Apply</button>
            </form>
        </div>

        <div class="profile-kpi-row">
            <div class="profile-kpi-card">
                <span class="profile-kpi-label">Total Spent</span>
                <span class="profile-kpi-value">{{ stats[0].value }}</span>
                <span class="profile-kpi-note">{{ stats[0].note }}</span>
            </div>
            <div class="profile-kpi-card">
                <span class="profile-kpi-label">Monthly Expenses</span>
                <span class="profile-kpi-value">{{ monthly_expenses }}</span>
                <span class="profile-kpi-note">This calendar month</span>
            </div>
            <div class="profile-kpi-card profile-kpi-card-soon" aria-disabled="true">
                <span class="profile-kpi-label">Total Investment <span class="profile-sidebar-soon">Soon</span></span>
                <span class="profile-kpi-value">₹0.00</span>
            </div>
            <div class="profile-kpi-card profile-kpi-card-soon" aria-disabled="true">
                <span class="profile-kpi-label">Goal <span class="profile-sidebar-soon">Soon</span></span>
                <span class="profile-kpi-ring" aria-hidden="true"></span>
            </div>
        </div>

        <div class="profile-chart-row">
            <div class="profile-chart-card">
                <h2 class="profile-card-title">Monthly spending</h2>
                <p class="profile-chart-subtitle">{{ stats[1].value }} transactions this range</p>
                <canvas id="monthly-chart" data-monthly="{{ monthly_totals | tojson }}"></canvas>
            </div>
            <div class="profile-chart-card">
                <h2 class="profile-card-title">Category breakdown</h2>
                <p class="profile-chart-subtitle">Top: {{ stats[2].value }}</p>
                <canvas id="category-chart" data-categories="{{ category_breakdown | tojson }}"></canvas>
            </div>
        </div>

        <div class="profile-bottom-row">
            <div class="profile-card profile-col-main">
                <h2 class="profile-card-title">Recent transactions</h2>
                <div class="profile-table-wrap">
                    <table class="profile-table">
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Description</th>
                                <th>Category</th>
                                <th class="col-amount">Amount</th>
                                <th class="col-actions">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for t in transactions %}
                            <tr>
                                <td>{{ t.date }}</td>
                                <td>{{ t.description }}</td>
                                <td><span class="category-badge category-badge-{{ t.category|lower }}">{{ t.category }}</span></td>
                                <td class="col-amount">{{ t.amount }}</td>
                                <td class="col-actions">
                                    <a href="{{ url_for('edit_expense', id=t.id) }}" class="table-action-link" aria-label="Edit expense">
                                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                            <path d="M12 20h9"></path>
                                            <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"></path>
                                        </svg>
                                    </a>
                                    <form method="POST" action="{{ url_for('delete_expense', id=t.id) }}" class="delete-form" onsubmit="return confirm('Delete this expense?')">
                                        <button type="submit" class="table-action-link btn-delete" aria-label="Delete expense">
                                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                                <polyline points="3 6 5 6 21 6"></polyline>
                                                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path>
                                                <path d="M10 11v6"></path>
                                                <path d="M14 11v6"></path>
                                                <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"></path>
                                            </svg>
                                        </button>
                                    </form>
                                </td>
                            </tr>
                            {% else %}
                            <tr class="profile-table-empty">
                                <td colspan="5">No transactions in this date range.</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="profile-card profile-col-side profile-card-soon" aria-disabled="true">
                <h2 class="profile-card-title">Bills &amp; Subscriptions <span class="profile-sidebar-soon">Soon</span></h2>
                <p class="profile-empty-note">Coming in a future update.</p>
            </div>
        </div>

        <form id="profile-chat-quickstart-form" class="profile-chat-quickstart">
            <input type="file" id="profile-chat-quickstart-attach" class="chat-attach-input" accept="image/png,image/jpeg,image/webp,image/gif">
            <button type="button" id="profile-chat-quickstart-attach-button" class="profile-chat-quickstart-attach" aria-label="Attach a receipt image">📎</button>
            <input type="text" id="profile-chat-quickstart-input" class="profile-chat-quickstart-input"
                   placeholder="Ask about your spending..." autocomplete="off">
            <button type="submit" class="profile-chat-quickstart-send">Send</button>
        </form>
    </div>
</div>

{% endblock %}
```

Note: `stats[0]`/`stats[1]`/`stats[2]` are the existing Total-spent/Transactions/Top-category entries `profile()` already builds — this template reuses their already-formatted `.value` strings rather than recomputing anything, so no new Python formatting logic is needed beyond what Step 3 added.

- [ ] **Step 5: Remove the now-dead horizontal-bar CSS**

In `static/css/profile.css`, delete these rule blocks (their only markup usage — the old `.profile-columns`/`.profile-col-side` bar-chart card — no longer exists after Step 4 above): `.profile-bar-row`, `.profile-bar-row:last-child`, `.profile-bar-cat`, `.profile-bar-total`, `.profile-bar-cat` (duplicate selector block if present), `.profile-bar-track`, `.profile-bar-fill`, every `.category-fill-*` rule, and every `.width-N` rule (`.width-10` through `.width-100`). Also delete `.profile-columns`, `.profile-col-main`, `.profile-col-side` **only if** you're about to redefine them below with new dashboard-appropriate rules (you are — see Step 6) — otherwise leave them as-is and let Step 6 override by cascade; either is fine, but don't leave two contradictory definitions of the same selector with no comment explaining why. Prefer deleting the old ones cleanly.

Do not delete `.category-badge-*` — the recent-transactions table still uses those.

- [ ] **Step 6: Add the new dashboard CSS**

Append to `static/css/profile.css`:

```css
/* ------------------------------------------------------------------ */
/* Dashboard shell                                                      */
/* ------------------------------------------------------------------ */

.profile-dashboard-shell {
    display: flex;
    gap: 1.5rem;
    align-items: flex-start;
    min-height: calc(100vh - 3rem);
}

.profile-dashboard-main {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    padding: 1.5rem 0;
}

/* ------------------------------------------------------------------ */
/* Sidebar                                                              */
/* ------------------------------------------------------------------ */

.profile-sidebar {
    flex: 0 0 220px;
    padding: 1.5rem 1rem;
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    min-height: 100vh;
}

.profile-sidebar-brand {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-family: var(--font-display);
    font-size: 1.1rem;
    color: var(--ink);
    padding: 0 0.5rem;
}

.profile-sidebar-section {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
}

.profile-sidebar-heading {
    font-size: 0.7rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--ink-faint);
    padding: 0 0.5rem;
    margin-bottom: 0.25rem;
}

.profile-sidebar-link {
    display: block;
    padding: 0.5rem 0.5rem;
    border-radius: var(--radius-sm);
    color: var(--ink-soft);
    text-decoration: none;
    font-size: 0.9rem;
    border: none;
    background: none;
    text-align: left;
    width: 100%;
    cursor: pointer;
    font-family: var(--font-body);
}

.profile-sidebar-link:not(.profile-sidebar-link-soon):hover,
.profile-sidebar-link-active {
    background: var(--accent-light);
    color: var(--ink);
}

.profile-sidebar-link-soon {
    color: var(--ink-faint);
    cursor: not-allowed;
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.profile-sidebar-soon {
    font-size: 0.65rem;
    text-transform: uppercase;
    color: var(--ink-faint);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 0.1rem 0.35rem;
}

.profile-sidebar-theme-toggle {
    display: block;
}

.profile-sidebar-upgrade {
    margin-top: auto;
    border: 1px dashed var(--border);
    border-radius: var(--radius-md);
    padding: 0.75rem;
    text-align: center;
    color: var(--ink-faint);
}

.profile-sidebar-upgrade-title {
    font-size: 0.85rem;
    margin-bottom: 0.25rem;
}

/* ------------------------------------------------------------------ */
/* Header                                                               */
/* ------------------------------------------------------------------ */

.profile-dashboard-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.profile-dashboard-greeting {
    font-family: var(--font-display);
    font-size: 1.4rem;
    color: var(--ink);
}

.profile-dashboard-subtitle {
    color: var(--ink-muted);
    font-size: 0.85rem;
}

.profile-dashboard-header-actions {
    display: flex;
    align-items: center;
    gap: 1rem;
}

.profile-dashboard-clock {
    color: var(--ink-faint);
    font-size: 0.8rem;
}

.profile-dashboard-avatar {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: var(--accent);
    color: var(--paper-card);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
}

/* ------------------------------------------------------------------ */
/* KPI cards                                                            */
/* ------------------------------------------------------------------ */

.profile-kpi-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
}

.profile-kpi-card {
    background: var(--paper-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
}

.profile-kpi-card-soon {
    opacity: 0.55;
}

.profile-kpi-label {
    font-size: 0.8rem;
    color: var(--ink-muted);
    display: flex;
    align-items: center;
    gap: 0.35rem;
}

.profile-kpi-value {
    font-size: 1.4rem;
    font-weight: 600;
    color: var(--ink);
}

.profile-kpi-note {
    font-size: 0.75rem;
    color: var(--ink-faint);
}

.profile-kpi-ring {
    display: block;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    border: 4px solid var(--border);
}

/* ------------------------------------------------------------------ */
/* Charts                                                               */
/* ------------------------------------------------------------------ */

.profile-chart-row {
    display: grid;
    grid-template-columns: 1.4fr 1fr;
    gap: 1rem;
}

.profile-chart-card {
    background: var(--paper-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 1rem;
}

.profile-chart-subtitle {
    font-size: 0.8rem;
    color: var(--ink-muted);
    margin-bottom: 0.5rem;
}

/* ------------------------------------------------------------------ */
/* Bottom row                                                           */
/* ------------------------------------------------------------------ */

.profile-bottom-row {
    display: grid;
    grid-template-columns: 1.6fr 1fr;
    gap: 1rem;
}

.profile-card-soon {
    opacity: 0.55;
}

@media (max-width: 900px) {
    .profile-dashboard-shell {
        flex-direction: column;
    }

    .profile-sidebar {
        flex: none;
        min-height: auto;
        border-right: none;
        border-bottom: 1px solid var(--border);
    }

    .profile-kpi-row,
    .profile-chart-row,
    .profile-bottom-row {
        grid-template-columns: 1fr;
    }
}
```

- [ ] **Step 7: Add the live clock**

Append to `static/js/main.js` (the site-wide script, since the clock element only exists on the dashboard page but `main.js` already null-guards every lookup the same way):

```javascript
(function () {
    var clockEl = document.getElementById("profile-dashboard-clock");
    if (!clockEl) {
        return;
    }

    var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

    function render() {
        var now = new Date();
        var hours = now.getHours();
        var period = hours >= 12 ? "PM" : "AM";
        var displayHours = hours % 12 || 12;
        var minutes = now.getMinutes();
        var minuteStr = minutes < 10 ? "0" + minutes : String(minutes);
        clockEl.textContent = displayHours + ":" + minuteStr + " " + period + " | " + now.getDate() + " " + MONTHS[now.getMonth()] + " " + now.getFullYear();
    }

    render();
    setInterval(render, 30000);
})();
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_backend_connection.py -v -k profile`
Expected: PASS (all profile tests, including `test_profile_hides_top_navbar_now_wired` and Task 4's `test_profile_page_hides_top_navbar`)

Run the full suite: `pytest -q`

- [ ] **Step 9: Commit**

```bash
git add app.py templates/profile.html static/css/profile.css static/js/main.js tests/test_backend_connection.py
git commit -m "feat: restructure profile page into the sidebar dashboard layout"
```

---

### Task 6: Chart.js bar + donut charts

**Files:**
- Modify: `templates/profile.html` (add the Chart.js `<script>` tag and `dashboard.js` script tag)
- Create: `static/js/dashboard.js`

**Interfaces:**
- Consumes: `#monthly-chart`'s `data-monthly` attribute (JSON list of `{"month": "YYYY-MM", "total": float}`, from Task 1/5) and `#category-chart`'s `data-categories` attribute (JSON list of `{"name": str, "amount": float, "pct": int}`, from Task 5's `category_breakdown`).
- Produces: two rendered Chart.js charts. No other file consumes anything from this task.

This task has no meaningful automated test — Chart.js rendering happens entirely in the browser via `<canvas>`, and this project's test suite only exercises server-rendered HTML via the Flask test client (no headless browser in the test stack). Verify this task manually as described in Step 3.

- [ ] **Step 1: Add Chart.js and dashboard.js to profile.html**

In `templates/profile.html`, change the `{% block head %}` to:

```html
{% block head %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/profile.css') }}">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
{% endblock %}
```

Add a `{% block scripts %}` at the end of the file, after the closing `{% endblock %}` of `content`:

```html
{% block scripts %}
<script src="{{ url_for('static', filename='js/dashboard.js') }}"></script>
{% endblock %}
```

- [ ] **Step 2: Create dashboard.js**

Create `static/js/dashboard.js`:

```javascript
(function () {
    var CATEGORY_ORDER = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"];
    var MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

    function readJSON(el, attr) {
        if (!el) {
            return null;
        }
        var raw = el.getAttribute(attr);
        if (!raw) {
            return null;
        }
        try {
            return JSON.parse(raw);
        } catch (e) {
            return null;
        }
    }

    function monthLabel(ym) {
        var parts = ym.split("-");
        var monthIndex = parseInt(parts[1], 10) - 1;
        return MONTH_LABELS[monthIndex] + " '" + parts[0].slice(2);
    }

    function categoryColor(name) {
        var root = document.documentElement;
        var varName = "--cat-" + name.toLowerCase();
        var value = getComputedStyle(root).getPropertyValue(varName);
        return value ? value.trim() : "#999999";
    }

    if (typeof Chart === "undefined") {
        return;
    }

    var monthlyCanvas = document.getElementById("monthly-chart");
    var monthlyData = readJSON(monthlyCanvas, "data-monthly");
    if (monthlyCanvas && monthlyData) {
        new Chart(monthlyCanvas, {
            type: "bar",
            data: {
                labels: monthlyData.map(function (row) { return monthLabel(row.month); }),
                datasets: [{
                    label: "Spending",
                    data: monthlyData.map(function (row) { return row.total; }),
                    backgroundColor: categoryColor("Food")
                }]
            },
            options: {
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true } }
            }
        });
    }

    var categoryCanvas = document.getElementById("category-chart");
    var categoryData = readJSON(categoryCanvas, "data-categories");
    if (categoryCanvas && categoryData && categoryData.length > 0) {
        var ordered = CATEGORY_ORDER.filter(function (name) {
            return categoryData.some(function (row) { return row.name === name; });
        });
        var amounts = ordered.map(function (name) {
            var match = categoryData.filter(function (row) { return row.name === name; })[0];
            return match ? match.amount : 0;
        });

        new Chart(categoryCanvas, {
            type: "doughnut",
            data: {
                labels: ordered,
                datasets: [{
                    data: amounts,
                    backgroundColor: ordered.map(categoryColor)
                }]
            },
            options: {
                plugins: { legend: { position: "bottom" } }
            }
        });
    }
})();
```

- [ ] **Step 3: Manual verification**

Run: `python app.py`, log in, visit `/profile`. Expected: a bar chart showing 6 months of spending (zero-height bars for months with no data) and a doughnut chart showing the category breakdown in the same colors the category badges already use elsewhere on the page. Toggle dark mode and reload — chart colors should still look correct (they're read from the theme's CSS variables at page-load time).

- [ ] **Step 4: Run the full automated suite**

Run: `pytest -q`
Expected: PASS (this task didn't touch any server-side code, so nothing should have changed)

- [ ] **Step 5: Commit**

```bash
git add templates/profile.html static/js/dashboard.js
git commit -m "feat: render monthly spending and category breakdown with Chart.js"
```

---

### Task 7: Chat attach button and rich receipt-result bubble

**Files:**
- Modify: `templates/_chat_drawer.html` (add attach button + hidden file input to `#chat-form`)
- Modify: `templates/profile.html` (already has the quickstart attach button from Task 5 — this task wires its behavior)
- Modify: `static/js/chat.js`
- Modify: `static/css/chat.css`
- Test: manual only (see Step 5) — this is pure client-side JS/CSS behavior; the server-side routes it calls are already tested in Task 2

**Interfaces:**
- Consumes: `POST /api/chat/receipt` and `POST /api/expenses` (Task 2), returning/accepting the JSON shapes documented there.

- [ ] **Step 1: Add the attach control to the drawer form**

In `templates/_chat_drawer.html`, change the `#chat-form` block from:

```html
        <form id="chat-form" class="chat-form">
            <textarea id="chat-input" class="chat-input" maxlength="2000" rows="1" placeholder="Ask about your spending..."></textarea>
            <button type="submit" class="chat-send">Send</button>
        </form>
```

to:

```html
        <form id="chat-form" class="chat-form">
            <input type="file" id="chat-attach-input" class="chat-attach-input" accept="image/png,image/jpeg,image/webp,image/gif">
            <button type="button" id="chat-attach-button" class="chat-attach" aria-label="Attach a receipt image">📎</button>
            <textarea id="chat-input" class="chat-input" maxlength="2000" rows="1" placeholder="Ask about your spending..."></textarea>
            <button type="submit" class="chat-send">Send</button>
        </form>
```

- [ ] **Step 2: Add the CSS**

Append to `static/css/chat.css`:

```css
.chat-attach-input {
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

.chat-attach {
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: var(--paper-card);
    color: var(--ink);
    padding: 8px 10px;
    cursor: pointer;
}

.chat-receipt-card {
    align-self: flex-start;
    background: var(--paper-warm);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 10px 14px;
    max-width: 85%;
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.chat-receipt-save {
    align-self: flex-start;
    border: none;
    border-radius: var(--radius-sm);
    background: var(--accent);
    color: var(--paper-card);
    padding: 6px 12px;
    cursor: pointer;
    font-family: var(--font-body);
    font-size: 0.85rem;
}

.chat-receipt-save:disabled {
    opacity: 0.6;
    cursor: default;
}
```

- [ ] **Step 3: Wire up the attach button and rich bubble in chat.js**

In `static/js/chat.js`, add these new element lookups near the top, alongside the existing ones (right after the `quickstartInput` line):

```javascript
    var attachButton = document.getElementById("chat-attach-button");
    var attachInput = document.getElementById("chat-attach-input");
    var quickstartAttachButton = document.getElementById("profile-chat-quickstart-attach-button");
    var quickstartAttachInput = document.getElementById("profile-chat-quickstart-attach");
```

Add a new function, placed after the existing `appendBubble` function:

```javascript
    function appendReceiptCard(replyText, expense, saveUrl) {
        if (!messagesEl) {
            return;
        }
        clearEmptyState();

        appendBubble("assistant", replyText);

        var card = document.createElement("div");
        card.className = "chat-receipt-card";

        var summary = document.createElement("div");
        summary.textContent = expense.category + " · ₹" + expense.amount + " · " + expense.date +
            (expense.description ? " · " + expense.description : "");
        card.appendChild(summary);

        var saveButton = document.createElement("button");
        saveButton.type = "button";
        saveButton.className = "chat-receipt-save";
        saveButton.textContent = "Save as expense";
        saveButton.addEventListener("click", function () {
            saveButton.disabled = true;
            saveButton.textContent = "Saving…";

            fetch("/api/expenses", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(expense)
            })
                .then(function (response) {
                    return response.json().then(function (data) {
                        return { ok: response.ok, data: data };
                    });
                })
                .then(function (result) {
                    if (result.ok) {
                        appendBubble("assistant", "Saved — reloading to update your totals…");
                        window.location.reload();
                    } else {
                        saveButton.disabled = false;
                        saveButton.textContent = "Save as expense";
                        appendBubble("error", result.data.error || "Something went wrong.");
                    }
                })
                .catch(function () {
                    saveButton.disabled = false;
                    saveButton.textContent = "Save as expense";
                    appendBubble("error", "Something went wrong.");
                });
        });
        card.appendChild(saveButton);

        messagesEl.appendChild(card);
        scrollToBottom();
    }

    function scanReceipt(file) {
        appendBubble("user", "📎 " + file.name);
        setInputDisabled(true);
        setStatus("Reading receipt…");

        var formData = new FormData();
        formData.append("receipt", file);

        fetch("/api/chat/receipt", {
            method: "POST",
            body: formData
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
                    appendReceiptCard(result.data.reply, result.data.expense);
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
```

Add the event wiring near the other listeners, right before `if (isOpenStored())`:

```javascript
    if (attachButton && attachInput) {
        attachButton.addEventListener("click", function () {
            attachInput.click();
        });
        attachInput.addEventListener("change", function () {
            if (attachInput.files.length) {
                var file = attachInput.files[0];
                attachInput.value = "";
                setOpen(true);
                scanReceipt(file);
            }
        });
    }

    if (quickstartAttachButton && quickstartAttachInput) {
        quickstartAttachButton.addEventListener("click", function () {
            quickstartAttachInput.click();
        });
        quickstartAttachInput.addEventListener("change", function () {
            if (quickstartAttachInput.files.length) {
                var file = quickstartAttachInput.files[0];
                quickstartAttachInput.value = "";
                setOpen(true);
                scanReceipt(file);
            }
        });
    }
```

- [ ] **Step 4: Run the full automated suite**

Run: `pytest -q`
Expected: PASS (this task is pure template/JS/CSS — no Python changed)

- [ ] **Step 5: Manual verification**

With `LLM_API_KEY` unset: `python app.py`, log in, click the 📎 button in the drawer (or the dashboard's quickstart 📎 button), pick any image. Expected: a user bubble with the filename, "Reading receipt…", then an error bubble reading "The AI assistant is not configured. Set LLM_API_KEY to enable it." — no crash, nothing saved.

With a real `LLM_API_KEY` and an actual receipt image: expected a "Save as expense" card with the extracted amount/date/category/description; clicking it should save the expense and reload the page, after which the new expense appears in Recent Transactions and the KPI totals update.

- [ ] **Step 6: Commit**

```bash
git add templates/_chat_drawer.html static/js/chat.js static/css/chat.css
git commit -m "feat: attach and confirm receipts from the chat drawer"
```

---

### Task 8: Docs and final verification

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:** None — documentation and verification only.

- [ ] **Step 1: Update the route table**

In `CLAUDE.md`'s route table, add these two rows (in the appropriate alphabetical/logical position near the other `/api/` rows):

```
| `POST /api/chat/receipt` | Implemented — dashboard redesign |
| `POST /api/expenses` | Implemented — dashboard redesign |
```

- [ ] **Step 2: Update the architecture tree comment**

In `CLAUDE.md`'s file-tree comment block, change:

```
│       └── <feature>.js    # chat.js (drawer), receipt.js (dropzone)
```

to:

```
│       └── <feature>.js    # chat.js (drawer + receipt attach), dashboard.js (charts)
```

And change:

```
│   │   └── <page>.css      # One file per page/feature (profile, chat, receipt, accounts)
```

to:

```
│   │   └── <page>.css      # One file per page/feature (profile, chat, accounts)
```

- [ ] **Step 3: Run the full suite one more time**

Run: `pytest -q`
Expected: PASS, full suite, with `LLM_API_KEY` unset.

- [ ] **Step 4: Manual smoke test — every other page's chrome is unaffected**

With the app running, visit `/`, `/login`, `/register`, `/expenses/add`, and (after logging in) `/expenses/<id>/edit` for an existing expense. Expected: every one of these still shows the normal top navbar and footer — only `/profile` looks like the new dashboard.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: record the new receipt/expense JSON routes and dashboard file layout"
```

---

## Definition of Done

- [ ] `/profile` renders as a sidebar + dashboard layout; every other page is visually unchanged (top navbar still present)
- [ ] Only Dashboard, Add Expense, theme toggle, and Sign out are clickable in the sidebar; everything else is visibly inert with a "Soon" tag
- [ ] The 4 KPI cards show real Total Spent and real Monthly Expenses; Total Investment and Goal are static placeholders
- [ ] The bar chart shows 6 consecutive months of real spending, zero-filled where there's no data; the donut chart shows the real category breakdown in the app's existing category colors
- [ ] Attaching a receipt via the chat's 📎 button shows the scan result as a chat message with a working "Save as expense" button; nothing is saved until that button is clicked
- [ ] The old dropzone is gone from Add Expense; `POST /expenses/scan` no longer exists
- [ ] All new/changed tests pass without `LLM_API_KEY` and without importing a provider SDK
