# Dashboard Redesign — Nocturne (Phase A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Tailwind-based `/profile` dashboard with the Nocturne dark design system — new sidebar, header, assistant bar, filter row, summary tiles, insight/budget/goal placeholder sections, inline-SVG charts, and ledger — with a server-side `category` drill-down, no schema changes, and Tailwind fully removed from the app.

**Architecture:** `templates/profile.html` and `templates/_dashboard_sidebar.html` are fully rewritten as hand-written Jinja + CSS (no Tailwind). `static/css/nocturne.css` (new) holds the design-token sheet; `static/css/dashboard.css` (new, replaces `static/css/profile.css`) holds every component style for this page only — both are linked from `profile.html`'s own head block, never from `base.html`, so no other page's appearance changes. `static/js/dashboard.js` is rewritten to build both charts as inline SVG and to wire the new tile dropdowns, ledger drill-down navigation, inline add-expense row, and toasts — all vanilla JS, no new libraries. The existing chat-quickstart ids (`profile-chat-quickstart-form`/`-input`/`-attach-button`/`-attach`) are reused verbatim for the new assistant bar, so `static/js/chat.js` needs no changes at all.

**Tech Stack:** Flask + Jinja2, raw `sqlite3` via `database/queries.py`, vanilla JS, hand-written CSS (no Tailwind, no Chart.js).

**Spec:** `.claude/specs/16-dashboard-redesign-nocturne-phase-a.md`

## Global Constraints

- Currency always renders as `₹`, comma-grouped (`{:,.2f}` server-side, `toLocaleString('en-IN')` client-side per the design's own requirement — this is a change from the current `'en-US'` grouping in `dashboard.js`)
- Category names/order must exactly match `database/db.py`'s `CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]`
- All SQL stays parameterized (`?` placeholders) in `database/queries.py`; no SQL in `app.py` or templates
- No new pip packages, no npm, no JS frameworks — vanilla JS only
- All templates extend `base.html`; page CSS/JS load only from `profile.html`'s own `{% block head %}` / `{% block scripts %}`, never added to `base.html`
- The donut, budget/goal/insight placeholders, and the two summary-tile totals must be computed from **date-range-only** queries — `category` (drill-down) and `q` (search) apply **only** to `get_recent_transactions` for the ledger table
- Budgets, Goals, Insights, and both sparkline types render as genuine empty/placeholder states in this phase — no fabricated financial data. The sidebar's "plan" label (`"Free plan"`) is static decorative chrome, not financial data, and may be hardcoded
- Every step below must leave `pytest` fully green with `LLM_API_KEY` unset before moving to the next task

---

## Pre-flight: test-impact findings from codebase research

Verified against the exact current file contents before writing this plan —
these override the spec's more speculative "may need updating" hedges:

- `tests/test_backend_connection.py:120` — `assert 'class="profile-sidebar ' in body` (trailing space, a Tailwind-multi-class artifact) → becomes `assert 'class="profile-sidebar"' in body` (Task 3)
- `tests/test_backend_connection.py:122` — `assert "Soon" in body` → **delete this line** (no replacement; "Soon" text no longer exists anywhere in the redesigned page) (Task 3)
- `tests/test_backend_connection.py:123-124` — `assert 'id="monthly-chart"'` / `'id="category-chart"'` — **no change needed**. These are plain substring checks on the rendered HTML; they pass whether the id sits on a `<canvas>` or a `<div>`. Confirmed by reading the assertions directly.
- `tests/test_wealth_management.py` — six assertions reference `id="profile-balance-select"` / `-debt-select` / `-investment-select` (lines 614, 633, 645, 657, 675, 687). Each becomes the `-toggle` id (e.g. `profile-balance-toggle`) — see Task 5.
- `tests/test_06-date-filter-profile-page.py` — **no changes needed**. Every assertion in this file checks response body text (`"₹..."`, category names, flash text) or calls `get_summary_stats`/`get_recent_transactions`/`get_category_breakdown` directly — none of it depends on Tailwind classes, chart tag types, or the header search box's location.
- `tests/test_ai_chat_interface.py:397-398,409-410` — `id="chat-drawer"`, `"js/chat.js"`, `id="profile-chat-quickstart-form"`, `id="profile-chat-quickstart-input"` — **no changes needed**. `_chat_drawer.html`/`chat.js` are untouched, and the new assistant bar reuses these two ids verbatim (Task 4).
- `tests/test_add_expense.py`, `tests/test_delete_expense.py`, `tests/test_edit_expense.py` — only assert `response.headers["Location"].endswith("/profile")`; unaffected by this redesign.

New tests are added in Task 1 (backend `category` drill-down) and Task 3 (sidebar copy/id changes) using the exact edits above.

---

## Task 1: Backend — `category` drill-down parameter

**Files:**
- Modify: `database/queries.py:56-77` (`get_recent_transactions`)
- Modify: `app.py:161-247` (`profile()` route)
- Create: `tests/test_16_dashboard_drill_down.py`

**Interfaces:**
- Produces: `get_recent_transactions(user_id, limit=10, date_from=None, date_to=None, search=None, category=None)` — new `category` kwarg, parameterized `AND category = ?` clause, composes with existing `search`/date-range clauses
- Produces: `GET /profile` accepts an optional `category` query string param; the route passes `category=drill_category or None` to `get_recent_transactions` only (never to `get_summary_stats`/`get_category_breakdown`); the route passes new template variables `drill_category` (string or `None`), `budgets` (`[]`), `goals` (`[]`), `insights` (`[]`)

This task is independent of every template/CSS/JS task below — it's pure backend and fully testable against the *current* (pre-rewrite) `profile.html`, since none of its new tests depend on new markup, only on `get_recent_transactions`'s return value and on transaction description text appearing/not-appearing in the rendered body.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_16_dashboard_drill_down.py`:

```python
from datetime import date

from database.db import get_db, get_user_by_email
from database.queries import get_category_breakdown, get_recent_transactions, get_summary_stats
from tests.conftest import register_new_user

DEMO_USER_ID = 1


def user_id_for(email):
    return get_user_by_email(email)["id"]


def insert_expense(user_id, amount, category, expense_date, description="Test expense"):
    if hasattr(expense_date, "isoformat"):
        expense_date = expense_date.isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, expense_date, description),
    )
    conn.commit()
    conn.close()


def login_demo(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})


# ------------------------------------------------------------------ #
# database/queries.py — get_recent_transactions(category=...)         #
# ------------------------------------------------------------------ #

def test_get_recent_transactions_category_filters_to_that_category(client):
    email = "drill1@example.com"
    register_new_user(client, name="Drill One", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40.00, "Food", date.today(), "Lunch")
    insert_expense(uid, 10.00, "Transport", date.today(), "Cab ride")

    rows = get_recent_transactions(uid, category="Food")

    assert len(rows) == 1
    assert rows[0]["category"] == "Food"


def test_get_recent_transactions_category_composes_with_search(client):
    email = "drill2@example.com"
    register_new_user(client, name="Drill Two", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40.00, "Food", date.today(), "Grocery run")
    insert_expense(uid, 12.00, "Food", date.today(), "Cab ride")

    rows = get_recent_transactions(uid, category="Food", search="grocery")

    assert len(rows) == 1
    assert rows[0]["description"] == "Grocery run"


def test_get_recent_transactions_category_none_behaves_as_unfiltered(client):
    email = "drill3@example.com"
    register_new_user(client, name="Drill Three", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40.00, "Food", date.today(), "Lunch")
    insert_expense(uid, 10.00, "Transport", date.today(), "Cab ride")

    rows = get_recent_transactions(uid)

    assert len(rows) == 2


def test_get_recent_transactions_category_no_matches_returns_empty(client):
    email = "drill4@example.com"
    register_new_user(client, name="Drill Four", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40.00, "Food", date.today(), "Lunch")

    rows = get_recent_transactions(uid, category="Bills")

    assert rows == []


# ------------------------------------------------------------------ #
# GET /profile?category=...                                           #
# ------------------------------------------------------------------ #

def test_route_category_param_filters_ledger_rows(client):
    login_demo(client)
    response = client.get("/profile?category=Bills")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Electricity" in body
    assert "Groceries" not in body


def test_route_category_param_does_not_affect_summary_or_breakdown(client):
    """Resolved decision: category drill-down applies to the ledger only —
    the donut/insight/budget placeholders read date-range-only data."""
    login_demo(client)
    unfiltered_stats = get_summary_stats(DEMO_USER_ID)
    unfiltered_breakdown = get_category_breakdown(DEMO_USER_ID)

    response = client.get("/profile?category=Bills")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert f"₹{unfiltered_stats['total_spent']:,.2f}" in body, (
        "The route must not have passed category into get_summary_stats"
    )
    for row in unfiltered_breakdown:
        assert row["name"] in body, (
            "The route must not have passed category into get_category_breakdown"
        )


def test_route_invalid_category_falls_back_to_unfiltered(client):
    login_demo(client)
    response = client.get("/profile?category=NotARealCategory")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Electricity" in body
    assert "Groceries" in body


def test_route_no_category_param_behaves_as_before(client):
    login_demo(client)
    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Electricity" in body
    assert "Groceries" in body
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_16_dashboard_drill_down.py -v`
Expected: `FAIL` — `get_recent_transactions() got an unexpected keyword argument 'category'` and/or `TypeError` from `app.py` not yet accepting `category`.

- [ ] **Step 3: Implement `get_recent_transactions`'s `category` parameter**

In `database/queries.py`, replace the current `get_recent_transactions` (lines 56-77):

```python
def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None, search=None, category=None):
    conn = get_db()
    where, params = _user_date_filter(user_id, date_from, date_to)

    if search:
        where += " AND (description LIKE ? OR category LIKE ?)"
        term = "%" + search + "%"
        params += [term, term]

    if category:
        where += " AND category = ?"
        params.append(category)

    params.append(limit)

    rows = conn.execute(
        "SELECT id, date, description, category, amount FROM expenses "
        f"{where} ORDER BY date DESC, id DESC LIMIT ?",
        params,
    ).fetchall()
    conn.close()

    return [
        {"id": r["id"], "date": r["date"], "description": r["description"], "category": r["category"], "amount": r["amount"]}
        for r in rows
    ]
```

- [ ] **Step 4: Wire `category` into the `profile()` route**

In `app.py`, inside `profile()` (currently lines 161-247), make these two changes:

1. After the existing `search_query = request.args.get("q", "").strip()` line, add:

```python
    raw_category = request.args.get("category", "").strip()
    drill_category = raw_category if raw_category in CATEGORIES else None
```

2. Change the `transactions = [...]` comprehension's `get_recent_transactions(...)` call to add `category=drill_category`:

```python
    transactions = [
        {
            "id": t["id"],
            "date": t["date"],
            "description": t["description"],
            "category": t["category"],
            "amount": f"₹{t['amount']:,.2f}",
        }
        for t in get_recent_transactions(
            user_id, date_from=date_from, date_to=date_to,
            search=search_query or None, category=drill_category,
        )
    ]
```

3. In the final `render_template("profile.html", ...)` call, add three new keyword arguments:

```python
        drill_category=drill_category,
        budgets=[], goals=[], insights=[],
```

`CATEGORIES` is already imported at the top of `app.py` (line 13: `from database.db import ACCOUNT_TYPES, CATEGORIES, create_user, get_user_by_email, init_db, seed_db`) — no import change needed.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_16_dashboard_drill_down.py -v`
Expected: `PASS` — all 8 tests green.

- [ ] **Step 6: Run the full suite**

Run: `pytest`
Expected: all existing tests still pass (this task touches no markup or ids).

- [ ] **Step 7: Commit**

```bash
git add database/queries.py app.py tests/test_16_dashboard_drill_down.py
git commit -m "feat: add category drill-down parameter to GET /profile"
```

---

## Task 2: Design tokens + CSS/JS scaffolding swap

**Files:**
- Create: `static/css/nocturne.css`
- Create: `static/css/dashboard.css` (category-color tokens only for now — component styles land in later tasks)
- Delete: `static/css/profile.css`
- Modify: `templates/base.html` (remove Tailwind CDN script + config)
- Modify: `templates/profile.html:5-8` (head block: swap `profile.css` for `nocturne.css`/`dashboard.css`, add Inter font link, remove the Chart.js CDN `<script>`)
- Modify: `CLAUDE.md` (remove the Tailwind CDN exception line)

**Interfaces:**
- Produces: `static/css/nocturne.css` — the Nocturne `:root` token block (`--color-bg`, `--color-surface`, `--color-text`, `--color-accent`, `--color-accent-100…900`, `--color-neutral-100…900`, `--color-divider`, `--space-1…8`, `--radius-sm/md/lg`, `--shadow-sm/md/lg`) plus its `.btn`/`.tag`/`.input`/`.card`/`.table`/`.dialog` component classes
- Produces: `static/css/dashboard.css` — `--cat-<name>` and `--cat-<name>-text` custom properties (consumed by `dashboard.js`'s existing `categoryColor()` lookup, unchanged mechanism), mapped per the design's category table

This task deliberately leaves `templates/profile.html`'s body markup and `templates/_dashboard_sidebar.html` untouched (they still contain Tailwind utility classes with no Tailwind loaded) — this is a transitional, visually-broken-in-a-browser state that the next two tasks fix. `pytest` stays green throughout because no test fetches static assets or checks CSS classes/computed styles, only rendered HTML text/ids.

- [ ] **Step 1: Create `static/css/nocturne.css`**

Copy `design_handoff_dashboard_redesign/tokens/nocturne.css` verbatim to `static/css/nocturne.css`, with one edit: the file's opening comment reads `/* Nocturne — design-system tokens and component classes. This file is the source of truth for the system's look; retune it here and see readme.md. */` — change `readme.md` (a file that doesn't exist in this repo) to reference the spec instead:

```css
/* Nocturne — design-system tokens and component classes. This file is the source of truth for the system's look; retune it here and see .claude/specs/16-dashboard-redesign-nocturne-phase-a.md. */
```

Every other line is copied unmodified — the full `:root` block, the `body`/`h1`-`h6`/`.btn`/`.field`/`.input`/`.radio`/`.seg`/`.card`/`.tag`/`.nav`/`.table`/`.dialog` rules from `design_handoff_dashboard_redesign/tokens/nocturne.css`.

- [ ] **Step 2: Create `static/css/dashboard.css` (category tokens only)**

```css
/* ------------------------------------------------------------------ */
/* Category color tokens (scoped to the dashboard page)                */
/* Matches database/db.py CATEGORIES exactly.                          */
/* ------------------------------------------------------------------ */

:root {
    --cat-food: var(--color-accent-300);
    --cat-food-text: var(--color-accent-200);
    --cat-transport: var(--color-accent-400);
    --cat-transport-text: var(--color-accent-200);
    --cat-bills: var(--color-accent-500);
    --cat-bills-text: var(--color-accent-300);
    --cat-health: var(--color-accent-600);
    --cat-health-text: var(--color-accent-300);
    --cat-entertainment: var(--color-accent-700);
    --cat-entertainment-text: var(--color-accent-300);
    --cat-shopping: var(--color-neutral-500);
    --cat-shopping-text: var(--color-neutral-300);
    --cat-other: var(--color-neutral-700);
    --cat-other-text: var(--color-neutral-300);
}
```

- [ ] **Step 3: Delete `static/css/profile.css`**

```bash
git rm static/css/profile.css
```

- [ ] **Step 4: Update `templates/profile.html`'s head block**

Replace lines 5-8:

```html
{% block head %}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{{ url_for('static', filename='css/nocturne.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/dashboard.css') }}">
{% endblock %}
```

(The Chart.js `<script>` line is removed — Task 6 replaces canvas-based charts with inline SVG.)

- [ ] **Step 5: Remove Tailwind from `templates/base.html`**

Delete lines 14-52 (the `<script src="https://cdn.tailwindcss.com/3.4.17"></script>` tag and the entire `<script> tailwind.config = {...} </script>` block that follows it). `base.html`'s existing DM Serif Display/DM Sans font link (lines 7-9) and `style.css` link (line 10) stay — every other page still uses them.

- [ ] **Step 6: Update `CLAUDE.md`**

In the "Tech constraints" section, change:

```markdown
- **Vanilla JS only** — no React, no jQuery, no npm packages. The one named exception is Tailwind CDN (`https://cdn.tailwindcss.com`, loaded in `base.html`) for CSS utility classes — it ships no build step and no interactive behavior of its own; all interactivity remains hand-written vanilla JS
```

to:

```markdown
- **Vanilla JS only** — no React, no jQuery, no npm packages. CSS is hand-written per page (see `static/css/<page>.css`) — no CSS framework
```

- [ ] **Step 7: Run the full suite**

Run: `pytest`
Expected: all existing tests still pass (no rendered text/id changed by this task).

- [ ] **Step 8: Commit**

```bash
git add static/css/nocturne.css static/css/dashboard.css templates/profile.html templates/base.html CLAUDE.md
git rm static/css/profile.css
git commit -m "chore: swap Tailwind for Nocturne design tokens on the dashboard page"
```

---

## Task 3: Sidebar rewrite

**Files:**
- Modify: `templates/_dashboard_sidebar.html` (full rewrite)
- Modify: `static/css/dashboard.css` (append sidebar styles)
- Modify: `tests/test_backend_connection.py:120,122` (two assertion edits from the Pre-flight table)

**Interfaces:**
- Consumes: `nocturne.css`/`dashboard.css` tokens from Task 2; `url_for('profile')`, `url_for('accounts')`, `url_for('add_expense')`, `url_for('logout')` (all pre-existing endpoints)
- Produces: sidebar root stays `class="profile-sidebar"` (single class, no trailing space); `id="theme-toggle"` stays present (consumed unchanged by `static/js/main.js`, which only needs an element with that id — see Pre-flight research)

- [ ] **Step 1: Update the two `tests/test_backend_connection.py` assertions first (TDD: make them fail against the current sidebar)**

Line 120: change
```python
    assert 'class="profile-sidebar ' in body
```
to
```python
    assert 'class="profile-sidebar"' in body
```

Line 122: delete the line
```python
    assert "Soon" in body
```
entirely (no replacement).

- [ ] **Step 2: Run the test to verify the first assertion now fails**

Run: `pytest tests/test_backend_connection.py::test_profile_authenticated_seed_user -v`
Expected: `FAIL` on `assert 'class="profile-sidebar"' in body` — the current sidebar's root still has multiple Tailwind classes.

- [ ] **Step 3: Rewrite `templates/_dashboard_sidebar.html`**

```html
<aside class="profile-sidebar">
    <div class="sidebar-brand">
        <span class="sidebar-brand-mark" aria-hidden="true">◈</span>
        <span class="sidebar-brand-name">Spendly</span>
    </div>

    <div class="sidebar-group">
        <p class="sidebar-eyebrow">Money</p>
        <a href="{{ url_for('profile') }}" class="sidebar-item sidebar-item-active">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="sidebar-icon" aria-hidden="true"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
            Dashboard
        </a>
        <a href="{{ url_for('accounts') }}" class="sidebar-item">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="sidebar-icon" aria-hidden="true"><path d="M17 7H6a3 3 0 0 0 0 6h12a3 3 0 0 1 0 6H6"></path><polyline points="14 4 17 7 14 10"></polyline><polyline points="10 20 7 17 10 14"></polyline></svg>
            Accounts
        </a>
        <span class="sidebar-item sidebar-item-inactive" aria-disabled="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="sidebar-icon" aria-hidden="true"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
            Ledger
        </span>
        <span class="sidebar-item sidebar-item-inactive" aria-disabled="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="sidebar-icon" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><path d="M12 7v10M8 10h5.5a2.5 2.5 0 0 1 0 5H8"></path></svg>
            Budgets
        </span>
        <span class="sidebar-item sidebar-item-inactive" aria-disabled="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="sidebar-icon" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="6"></circle><circle cx="12" cy="12" r="2"></circle></svg>
            Goals
        </span>
    </div>

    <div class="sidebar-group">
        <p class="sidebar-eyebrow">Workspace</p>
        <span class="sidebar-item sidebar-item-inactive" aria-disabled="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="sidebar-icon" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
            Insights
        </span>
        <span class="sidebar-item sidebar-item-inactive" aria-disabled="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="sidebar-icon" aria-hidden="true"><rect x="1" y="4" width="22" height="16" rx="2"></rect><line x1="1" y1="10" x2="23" y2="10"></line></svg>
            Cards
        </span>
        <span class="sidebar-item sidebar-item-inactive" aria-disabled="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="sidebar-icon" aria-hidden="true"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>
            Reports
        </span>
    </div>

    <div class="sidebar-bottom">
        <button id="theme-toggle" type="button" aria-label="Toggle dark mode" class="sidebar-item sidebar-theme-toggle">
            <svg class="sidebar-icon theme-icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle><line x1="12" y1="2" x2="12" y2="4"></line><line x1="12" y1="20" x2="12" y2="22"></line><line x1="4.2" y1="4.2" x2="5.6" y2="5.6"></line><line x1="18.4" y1="18.4" x2="19.8" y2="19.8"></line><line x1="2" y1="12" x2="4" y2="12"></line><line x1="20" y1="12" x2="22" y2="12"></line><line x1="4.2" y1="19.8" x2="5.6" y2="18.4"></line><line x1="18.4" y1="5.6" x2="19.8" y2="4.2"></line></svg>
            <svg class="sidebar-icon theme-icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5Z"></path></svg>
            Toggle theme
        </button>
        <div class="sidebar-user-chip">
            <span class="sidebar-user-avatar">{{ user.initials }}</span>
            <span class="sidebar-user-info">
                <span class="sidebar-user-name">{{ user.name }}</span>
                <span class="sidebar-user-plan">Free plan</span>
            </span>
        </div>
        <a href="{{ url_for('logout') }}" class="sidebar-item">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="sidebar-icon" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
            Sign out
        </a>
    </div>
</aside>
```

- [ ] **Step 4: Append sidebar styles to `static/css/dashboard.css`**

```css
/* ------------------------------------------------------------------ */
/* Sidebar                                                              */
/* ------------------------------------------------------------------ */

.profile-sidebar {
    width: 196px;
    flex-shrink: 0;
    padding: 20px 12px;
    border-right: 1px solid var(--color-divider);
    display: flex;
    flex-direction: column;
    gap: 26px;
    position: sticky;
    top: 0;
    min-height: 100vh;
}

.sidebar-brand {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 8px;
}

.sidebar-brand-mark {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    border: 1px solid var(--color-accent);
    border-radius: var(--radius-sm);
    color: var(--color-accent);
    font-size: 13px;
}

.sidebar-brand-name {
    font-family: var(--font-heading);
    font-weight: var(--font-heading-weight);
    font-size: 16px;
    color: var(--color-text);
}

.sidebar-group {
    display: flex;
    flex-direction: column;
    gap: 1px;
}

.sidebar-eyebrow {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--color-neutral-500);
    padding: 0 8px;
    margin: 0 0 4px;
}

.sidebar-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 7px 8px;
    border-radius: var(--radius-md);
    font-size: 13.5px;
    color: var(--color-neutral-400);
    text-decoration: none;
    background: transparent;
    border: 0;
    font-family: var(--font-body);
    cursor: pointer;
    width: 100%;
    text-align: left;
}

.sidebar-item:hover {
    background: color-mix(in srgb, var(--color-accent) 9%, transparent);
    color: var(--color-text);
}

.sidebar-item-active {
    background: color-mix(in srgb, var(--color-accent) 14%, transparent);
    color: var(--color-text);
}

.sidebar-item-inactive {
    color: var(--color-neutral-600);
    cursor: not-allowed;
}

.sidebar-item-inactive:hover {
    background: transparent;
    color: var(--color-neutral-600);
}

.sidebar-icon {
    width: 15px;
    height: 15px;
    flex-shrink: 0;
}

.sidebar-bottom {
    margin-top: auto;
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.sidebar-theme-toggle {
    margin-bottom: 8px;
}

.sidebar-user-chip {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
}

.sidebar-user-avatar {
    width: 26px;
    height: 26px;
    border-radius: 50%;
    background: var(--color-accent-800);
    color: var(--color-accent-200);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 600;
    flex-shrink: 0;
}

.sidebar-user-info {
    display: flex;
    flex-direction: column;
    min-width: 0;
}

.sidebar-user-name {
    font-size: 12.5px;
    color: var(--color-text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.sidebar-user-plan {
    font-size: 10.5px;
    color: var(--color-neutral-500);
}
```

- [ ] **Step 5: Run the test to verify the sidebar-class assertion now passes**

Run: `pytest tests/test_backend_connection.py -v`
Expected: `PASS` — all tests in this file green (the "Soon" line is already deleted, and the sidebar class assertion now matches).

- [ ] **Step 6: Run the full suite**

Run: `pytest`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add templates/_dashboard_sidebar.html static/css/dashboard.css tests/test_backend_connection.py
git commit -m "feat: rewrite dashboard sidebar in the Nocturne design system"
```

---

## Task 4: Header, assistant bar, filter row

**Files:**
- Modify: `templates/profile.html` (replace lines 10-66 of the current file — the header row, chat-quickstart form, and filter bar — with the new markup below; the account tiles/charts/ledger sections below them are handled in Tasks 5-7 and still contain their *old* Tailwind markup until then, which is fine — pytest doesn't check CSS classes)
- Modify: `static/css/dashboard.css` (append header/assistant-bar/filter-row styles)

**Interfaces:**
- Consumes: `user.name`, `stats`, `search_query`, `selected_from`, `selected_to`, `active_preset`, `preset_ranges`, `drill_category` (from Task 1's route) — all already passed by `profile()`
- Produces: `id="profile-add-expense-toggle"` (button that Task 8's JS shows/hides the inline add-expense row), reuses `id="profile-chat-quickstart-form"` / `-input` / `-attach-button` / `-attach` verbatim (Task 8 adds the suggestion-chip JS)

This task removes the old header's live search box (`<input name="q">`) and the old header avatar/clock — search moves into the Ledger card (Task 7); the avatar/name/plan now live in the sidebar's user chip (Task 3). Per the spec's resolved decision 3, the new header's search-shaped button is visually present but inert (no click handler) — the command palette is Sub-project B.

- [ ] **Step 1: Replace `templates/profile.html` lines 10-66**

Replace everything from `{% block content %}` through the closing `</div>` of the old filter-bar form (current lines 10-66) with:

```html
{% block content %}

<div class="dashboard-shell">
    {% include "_dashboard_sidebar.html" %}

    <div class="dashboard-main">
        <header class="dashboard-header">
            <div>
                <h1 class="dashboard-greeting">Hi, {{ user.name }} 👋</h1>
                <p class="dashboard-subline">{{ stats[1].value }} transactions · {{ stats[0].value }} out · {{ "All time" if active_preset == "all_time" else "selected range" }}</p>
            </div>
            <div class="dashboard-header-actions">
                <button type="button" class="dashboard-search-button" aria-label="Search or jump to..." disabled>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="dashboard-search-icon" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                    <span>Search or jump to…</span>
                    <kbd class="dashboard-kbd">⌘K</kbd>
                </button>
                <button type="button" id="profile-add-expense-toggle" class="btn btn-primary">＋ Add expense</button>
            </div>
        </header>

        <div class="assistant-bar">
            <form id="profile-chat-quickstart-form" class="assistant-bar-row">
                <span class="assistant-bar-mark" aria-hidden="true">◈</span>
                <input type="file" id="profile-chat-quickstart-attach" class="chat-attach-input" accept="image/png,image/jpeg,image/webp,image/gif">
                <input type="text" id="profile-chat-quickstart-input" class="assistant-bar-input"
                       placeholder='Ask Spendly anything — "how much did I spend on food in August?"' autocomplete="off">
                <button type="button" id="profile-chat-quickstart-attach-button" class="btn btn-ghost" aria-label="Attach a receipt image">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="assistant-bar-icon" aria-hidden="true"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path></svg>
                    Scan receipt
                </button>
                <button type="submit" class="btn btn-primary">Ask</button>
            </form>
            <div class="assistant-bar-chips">
                <button type="button" class="assistant-chip" data-question="What did I overspend on this month?">What did I overspend on this month?</button>
                <button type="button" class="assistant-chip" data-question="Compare August to September">Compare August to September</button>
                <button type="button" class="assistant-chip" data-question="Show every Bills transaction">Show every Bills transaction</button>
                <button type="button" class="assistant-chip" data-question="Am I on track for the Kyoto trip?">Am I on track for the Kyoto trip?</button>
            </div>
        </div>

        <div class="filter-row">
            <div class="filter-pills">
                <a href="{{ url_for('profile', date_from=preset_ranges.this_month[0], date_to=preset_ranges.this_month[1], q=search_query, category=drill_category) }}"
                   class="filter-pill {% if active_preset == 'this_month' %}filter-pill-active{% endif %}">This month</a>
                <a href="{{ url_for('profile', date_from=preset_ranges.last_3_months[0], date_to=preset_ranges.last_3_months[1], q=search_query, category=drill_category) }}"
                   class="filter-pill {% if active_preset == 'last_3_months' %}filter-pill-active{% endif %}">Last 3 months</a>
                <a href="{{ url_for('profile', date_from=preset_ranges.last_6_months[0], date_to=preset_ranges.last_6_months[1], q=search_query, category=drill_category) }}"
                   class="filter-pill {% if active_preset == 'last_6_months' %}filter-pill-active{% endif %}">Last 6 months</a>
                <a href="{{ url_for('profile', q=search_query, category=drill_category) }}"
                   class="filter-pill {% if active_preset == 'all_time' %}filter-pill-active{% endif %}">All time</a>
            </div>
            <div class="filter-divider"></div>
            <form action="{{ url_for('profile') }}" method="get" class="filter-range-form">
                <input type="hidden" name="q" value="{{ search_query or '' }}">
                <input type="hidden" name="category" value="{{ drill_category or '' }}">
                <input type="date" id="date_from" name="date_from" value="{{ selected_from or '' }}" class="input">
                <span class="filter-range-arrow">→</span>
                <input type="date" id="date_to" name="date_to" value="{{ selected_to or '' }}" class="input">
                <button type="submit" class="btn btn-secondary">Apply</button>
            </form>
        </div>

        <div id="profile-add-expense-row" class="add-expense-row" hidden>
            <label class="add-expense-field add-expense-field-description">
                <span class="add-expense-label">Description</span>
                <input type="text" id="profile-add-expense-description" class="input" placeholder="Description">
            </label>
            <label class="add-expense-field add-expense-field-amount">
                <span class="add-expense-label">Amount ₹</span>
                <input type="number" id="profile-add-expense-amount" class="input" step="0.01" min="0" placeholder="0.00">
            </label>
            <label class="add-expense-field add-expense-field-category">
                <span class="add-expense-label">Category</span>
                <select id="profile-add-expense-category" class="input">
                    {% for c in ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"] %}
                    <option value="{{ c }}">{{ c }}</option>
                    {% endfor %}
                </select>
            </label>
            <label class="add-expense-field add-expense-field-date">
                <span class="add-expense-label">Date</span>
                <input type="date" id="profile-add-expense-date" class="input">
            </label>
            <div class="add-expense-actions">
                <button type="button" id="profile-add-expense-save" class="btn btn-primary">Save</button>
                <button type="button" id="profile-add-expense-cancel" class="btn btn-secondary">Cancel</button>
            </div>
        </div>
```

Leave everything from the old summary-tiles grid (`<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">`, currently starting at old line 68) through the end of the file **unchanged for now** — Tasks 5-7 replace those sections in place.

The seven categories in the `<select>` above are written out literally (not `{% for c in CATEGORIES %}`) because `CATEGORIES` is not currently passed into the template context; this matches the existing project convention of category lists appearing literally in templates that need them (checked: no template currently receives a `categories` template variable).

- [ ] **Step 2: Append header/assistant-bar/filter-row/add-expense-row styles to `static/css/dashboard.css`**

```css
/* ------------------------------------------------------------------ */
/* Shell layout                                                        */
/* ------------------------------------------------------------------ */

.dashboard-shell {
    display: flex;
    align-items: flex-start;
    min-height: 100vh;
}

.dashboard-main {
    flex: 1;
    min-width: 0;
    padding: 22px 28px 64px;
    max-width: 1320px;
    display: flex;
    flex-direction: column;
    gap: 18px;
}

/* ------------------------------------------------------------------ */
/* Header                                                               */
/* ------------------------------------------------------------------ */

.dashboard-header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
}

.dashboard-greeting {
    font-size: 26px;
    font-weight: 500;
    letter-spacing: -0.02em;
    margin: 0;
}

.dashboard-subline {
    font-size: 13px;
    color: var(--color-neutral-500);
    margin: 4px 0 0;
}

.dashboard-header-actions {
    display: flex;
    align-items: center;
    gap: 10px;
}

.dashboard-search-button {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 210px;
    padding: 8px 12px;
    border: 1px solid var(--color-divider);
    border-radius: var(--radius-md);
    background: var(--color-surface);
    color: var(--color-neutral-500);
    font-family: var(--font-body);
    font-size: 13px;
    cursor: not-allowed;
}

.dashboard-search-icon {
    width: 15px;
    height: 15px;
    flex-shrink: 0;
}

.dashboard-search-button span {
    flex: 1;
    text-align: left;
}

.dashboard-kbd {
    font-size: 10.5px;
    padding: 1px 5px;
    border: 1px solid var(--color-divider);
    border-radius: var(--radius-sm);
    color: var(--color-neutral-500);
}

/* ------------------------------------------------------------------ */
/* Assistant bar                                                        */
/* ------------------------------------------------------------------ */

.assistant-bar {
    background: var(--color-surface);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    transition: box-shadow 180ms;
}

.assistant-bar:focus-within {
    box-shadow: var(--shadow-md);
}

.assistant-bar-row {
    display: flex;
    align-items: center;
    gap: 10px;
}

.assistant-bar-mark {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    border: 1px solid var(--color-accent);
    border-radius: 50%;
    color: var(--color-accent);
    flex-shrink: 0;
    font-size: 13px;
}

.assistant-bar-input {
    flex: 1;
    min-width: 0;
    border: 0;
    background: transparent;
    color: var(--color-text);
    font-family: var(--font-body);
    font-size: 14.5px;
    padding: 6px 0;
}

.assistant-bar-input:focus-visible {
    outline: none;
}

.assistant-bar-icon {
    width: 15px;
    height: 15px;
}

.assistant-bar-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}

.assistant-chip {
    border: 1px solid var(--color-divider);
    border-radius: 999px;
    background: transparent;
    color: var(--color-neutral-400);
    font-family: var(--font-body);
    font-size: 12px;
    padding: 5px 12px;
    cursor: pointer;
}

.assistant-chip:hover {
    background: color-mix(in srgb, var(--color-accent) 9%, transparent);
    color: var(--color-text);
}

/* ------------------------------------------------------------------ */
/* Filter row                                                           */
/* ------------------------------------------------------------------ */

.filter-row {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
}

.filter-pills {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}

.filter-pill {
    display: inline-block;
    padding: 6px 14px;
    border-radius: 999px;
    border: 1px solid var(--color-divider);
    color: var(--color-neutral-400);
    font-size: 13px;
    text-decoration: none;
}

.filter-pill-active {
    border-color: var(--color-accent);
    background: color-mix(in srgb, var(--color-accent) 16%, transparent);
    color: var(--color-text);
}

.filter-divider {
    width: 1px;
    height: 18px;
    background: var(--color-divider);
}

.filter-range-form {
    display: flex;
    align-items: center;
    gap: 8px;
}

.filter-range-arrow {
    color: var(--color-neutral-500);
    font-size: 12px;
}

/* ------------------------------------------------------------------ */
/* Inline add-expense row                                               */
/* ------------------------------------------------------------------ */

.add-expense-row {
    display: flex;
    align-items: flex-end;
    gap: 12px;
    flex-wrap: wrap;
    background: var(--color-surface);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
    padding: 14px 16px;
}

.add-expense-field {
    display: flex;
    flex-direction: column;
    gap: 5px;
}

.add-expense-label {
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--color-neutral-500);
}

.add-expense-field-description { flex: 2; min-width: 150px; }
.add-expense-field-amount { width: 120px; }
.add-expense-field-category { width: 150px; }
.add-expense-field-date { width: 150px; }

.add-expense-actions {
    display: flex;
    gap: 8px;
}
```

- [ ] **Step 3: Run the full suite**

Run: `pytest`
Expected: all tests pass — the two chat-quickstart ids and the `q`/date-range param mechanics are unchanged, only visually restyled and repositioned.

- [ ] **Step 4: Commit**

```bash
git add templates/profile.html static/css/dashboard.css
git commit -m "feat: rewrite dashboard header, assistant bar, and filter row"
```

---

## Task 5: Summary tiles (Net worth, Balance, Debt, Invested)

**Files:**
- Modify: `templates/profile.html` (replace the old KPI-card grid section with the new tile markup)
- Modify: `static/css/dashboard.css` (append tile styles)
- Modify: `static/js/dashboard.js` (rewrite: drop `wireBalanceCard()`'s `<select>` wiring, add generic tile-dropdown wiring)
- Modify: `tests/test_wealth_management.py` (six id-string edits from the Pre-flight table)

**Interfaces:**
- Consumes: `accounts`, `debt_accounts`, `investment_accounts`, `total_balance`, `total_debt`, `total_investment`, `net_worth`, `net_worth_is_negative`, `net_worth_account_count` — all already passed by `profile()`, unchanged
- Produces: `static/js/dashboard.js` exposes `readJSON(el, attr)`, `formatRupees(amount)` (now `en-IN` locale), `categoryColor(name)`, and a `wireTile(tile)` function looping generically over `document.querySelectorAll(".tile[data-accounts]")` — Task 6 and Task 8 append to this same file without needing to change these

This task drops the old three-dot "options" menu (`profile-balance-menu-toggle` / `-menu-dropdown`, with its "Add account"/"Manage accounts" links) — the README's tile spec has no equivalent element, and no existing test asserts on it (verified in Pre-flight research). Account management is one click away via the sidebar's "Accounts" link.

- [ ] **Step 1: Update the six `tests/test_wealth_management.py` assertions first (TDD)**

Line 614: `assert 'id="profile-balance-select"' in body` → `assert 'id="profile-balance-toggle"' in body`
Line 633: `assert 'id="profile-debt-select"' in body` → `assert 'id="profile-debt-toggle"' in body`
Line 645: `assert 'id="profile-debt-select"' not in body` → `assert 'id="profile-debt-toggle"' not in body`
Line 657: `assert 'id="profile-balance-select"' not in body` → `assert 'id="profile-balance-toggle"' not in body`
Line 675: `assert 'id="profile-investment-select"' in body` → `assert 'id="profile-investment-toggle"' in body`
Line 687: `assert 'id="profile-investment-select"' not in body` → `assert 'id="profile-investment-toggle"' not in body`

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_wealth_management.py -v`
Expected: `FAIL` on the six edited assertions — the current markup still uses `-select` ids.

- [ ] **Step 3: Replace the KPI-card grid in `templates/profile.html`**

Replace the entire `<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">...</div>` block (the four account cards) with:

```html
        <div class="tiles-grid">
            <div class="tile tile-networth">
                <div class="tile-row">
                    <span class="tile-icon tile-icon-networth" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20V10"></path><path d="M18 20V4"></path><path d="M6 20v-4"></path></svg>
                    </span>
                    <span class="tile-eyebrow">Net worth</span>
                </div>
                <span class="tile-figure tile-figure-large {% if net_worth_is_negative %}tile-figure-negative{% endif %}">{{ net_worth }}</span>
                <p class="tile-note">{{ net_worth_account_count }} account{{ "s" if net_worth_account_count != 1 else "" }}</p>
                <svg class="tile-sparkline tile-sparkline-large" viewBox="0 0 320 64" aria-hidden="true">
                    <polyline class="tile-sparkline-placeholder-line" points="0,32 320,32"></polyline>
                </svg>
            </div>

            <div class="tile" data-accounts="{{ accounts | tojson | forceescape }}">
                <div class="tile-row">
                    <span class="tile-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="6" width="20" height="13" rx="2"></rect><path d="M2 10h20"></path><circle cx="16.5" cy="14.5" r="1.25" fill="currentColor" stroke="none"></circle></svg>
                    </span>
                    <span class="tile-label">Account Balance</span>
                    {% if accounts %}
                    <button type="button" class="tile-caret" id="profile-balance-toggle" aria-haspopup="true" aria-expanded="false" aria-label="Select account">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
                    </button>
                    {% endif %}
                </div>
                {% if accounts %}
                <span class="tile-figure" id="profile-balance-value">{{ total_balance }}</span>
                <svg class="tile-sparkline" viewBox="0 0 56 16" aria-hidden="true"><polyline class="tile-sparkline-placeholder-line" points="0,8 56,8"></polyline></svg>
                <p class="tile-note">{{ accounts|length }} account{{ "s" if accounts|length != 1 else "" }}</p>
                <div class="tile-dropdown" id="profile-balance-dropdown" hidden>
                    <button type="button" class="tile-dropdown-option" data-account-id="all"><span>All balance</span><span class="tile-dropdown-amount">{{ total_balance }}</span></button>
                    {% for a in accounts %}
                    <button type="button" class="tile-dropdown-option" data-account-id="{{ a.id }}"><span>{{ a.name }}</span><span class="tile-dropdown-amount">₹{{ "{:,.2f}".format(a.balance) }}</span></button>
                    {% endfor %}
                </div>
                {% else %}
                <span class="tile-figure">₹0.00</span>
                <svg class="tile-sparkline" viewBox="0 0 56 16" aria-hidden="true"><polyline class="tile-sparkline-placeholder-line" points="0,8 56,8"></polyline></svg>
                <p class="tile-note">No accounts yet. <a href="{{ url_for('add_account') }}">Add one</a></p>
                {% endif %}
            </div>

            <div class="tile" data-accounts="{{ debt_accounts | tojson | forceescape }}">
                <div class="tile-row">
                    <span class="tile-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="7" width="18" height="12" rx="2"></rect><path d="M3 11h18"></path><path d="M7 15h4"></path></svg>
                    </span>
                    <span class="tile-label">Debt</span>
                    {% if debt_accounts %}
                    <button type="button" class="tile-caret" id="profile-debt-toggle" aria-haspopup="true" aria-expanded="false" aria-label="Select debt account">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
                    </button>
                    {% endif %}
                </div>
                {% if debt_accounts %}
                <span class="tile-figure" id="profile-debt-value">{{ total_debt }}</span>
                <svg class="tile-sparkline" viewBox="0 0 56 16" aria-hidden="true"><polyline class="tile-sparkline-placeholder-line" points="0,8 56,8"></polyline></svg>
                <p class="tile-note">{{ debt_accounts|length }} account{{ "s" if debt_accounts|length != 1 else "" }}</p>
                <div class="tile-dropdown" id="profile-debt-dropdown" hidden>
                    <button type="button" class="tile-dropdown-option" data-account-id="all"><span>All debt</span><span class="tile-dropdown-amount">{{ total_debt }}</span></button>
                    {% for a in debt_accounts %}
                    <button type="button" class="tile-dropdown-option" data-account-id="{{ a.id }}"><span>{{ a.name }}</span><span class="tile-dropdown-amount">₹{{ "{:,.2f}".format(a.balance) }}</span></button>
                    {% endfor %}
                </div>
                {% else %}
                <span class="tile-figure">₹0.00</span>
                <svg class="tile-sparkline" viewBox="0 0 56 16" aria-hidden="true"><polyline class="tile-sparkline-placeholder-line" points="0,8 56,8"></polyline></svg>
                <p class="tile-note">No debts yet. <a href="{{ url_for('add_account', type='debt') }}">Add one</a></p>
                {% endif %}
            </div>

            <div class="tile" data-accounts="{{ investment_accounts | tojson | forceescape }}">
                <div class="tile-row">
                    <span class="tile-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 17 9 11 13 15 21 7"></polyline><polyline points="14 7 21 7 21 14"></polyline></svg>
                    </span>
                    <span class="tile-label">Total Investment</span>
                    {% if investment_accounts %}
                    <button type="button" class="tile-caret" id="profile-investment-toggle" aria-haspopup="true" aria-expanded="false" aria-label="Select investment">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
                    </button>
                    {% endif %}
                </div>
                {% if investment_accounts %}
                <span class="tile-figure" id="profile-investment-value">{{ total_investment }}</span>
                <svg class="tile-sparkline" viewBox="0 0 56 16" aria-hidden="true"><polyline class="tile-sparkline-placeholder-line" points="0,8 56,8"></polyline></svg>
                <p class="tile-note">{{ investment_accounts|length }} account{{ "s" if investment_accounts|length != 1 else "" }}</p>
                <div class="tile-dropdown" id="profile-investment-dropdown" hidden>
                    <button type="button" class="tile-dropdown-option" data-account-id="all"><span>All investments</span><span class="tile-dropdown-amount">{{ total_investment }}</span></button>
                    {% for a in investment_accounts %}
                    <button type="button" class="tile-dropdown-option" data-account-id="{{ a.id }}"><span>{{ a.name }}</span><span class="tile-dropdown-amount">₹{{ "{:,.2f}".format(a.balance) }}</span></button>
                    {% endfor %}
                </div>
                {% else %}
                <span class="tile-figure">₹0.00</span>
                <svg class="tile-sparkline" viewBox="0 0 56 16" aria-hidden="true"><polyline class="tile-sparkline-placeholder-line" points="0,8 56,8"></polyline></svg>
                <p class="tile-note">No investments yet. <a href="{{ url_for('add_account', type='investment') }}">Add one</a></p>
                {% endif %}
            </div>
        </div>
```

- [ ] **Step 4: Append tile styles to `static/css/dashboard.css`**

```css
/* ------------------------------------------------------------------ */
/* Summary tiles                                                        */
/* ------------------------------------------------------------------ */

.tiles-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(168px, 1fr));
    gap: 14px;
}

.tile {
    position: relative;
    background: var(--color-surface);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
    padding: 14px 15px;
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.tile-networth {
    grid-column: span 2;
    box-shadow: var(--shadow-md);
    padding: 16px 18px;
}

.tile-row {
    display: flex;
    align-items: center;
    gap: 8px;
}

.tile-icon {
    width: 24px;
    height: 24px;
    border: 1px solid var(--color-accent-800);
    border-radius: var(--radius-sm);
    color: var(--color-accent);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}

.tile-icon svg, .tile-caret svg { width: 14px; height: 14px; }

.tile-icon-networth { border: none; width: auto; height: auto; color: var(--color-accent-300); }

.tile-label {
    font-size: 12px;
    color: var(--color-neutral-400);
    flex: 1;
}

.tile-eyebrow {
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    color: var(--color-neutral-500);
}

.tile-caret {
    background: transparent;
    border: 0;
    color: var(--color-neutral-500);
    cursor: pointer;
    padding: 2px;
    transition: transform 150ms;
}

.tile-caret[aria-expanded="true"] {
    transform: rotate(180deg);
}

.tile-figure {
    font-size: 21px;
    font-weight: 600;
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
    color: var(--color-text);
}

.tile-figure-large {
    font-size: 34px;
    letter-spacing: -0.025em;
}

.tile-figure-negative {
    color: var(--color-accent-300);
}

.tile-note {
    font-size: 11.5px;
    color: var(--color-neutral-500);
    margin: 0;
}

.tile-note a {
    color: var(--color-accent-300);
}

.tile-sparkline {
    width: 56px;
    height: 16px;
}

.tile-sparkline-large {
    width: 100%;
    max-width: 320px;
    height: 64px;
}

.tile-sparkline-placeholder-line {
    fill: none;
    stroke: var(--color-neutral-700);
    stroke-width: 1.5;
}

.tile-dropdown {
    position: absolute;
    top: 42px;
    left: 12px;
    right: 12px;
    background: var(--color-surface);
    box-shadow: var(--shadow-lg);
    border-radius: var(--radius-md);
    padding: 4px;
    z-index: 10;
    display: flex;
    flex-direction: column;
}

.tile-dropdown-option {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    padding: 7px 8px;
    border-radius: var(--radius-sm);
    background: transparent;
    border: 0;
    color: var(--color-text);
    font-family: var(--font-body);
    font-size: 12.5px;
    cursor: pointer;
    text-align: left;
}

.tile-dropdown-option:hover {
    background: color-mix(in srgb, var(--color-accent) 9%, transparent);
}

.tile-dropdown-amount {
    color: var(--color-neutral-500);
    font-variant-numeric: tabular-nums;
}
```

- [ ] **Step 5: Rewrite `static/js/dashboard.js`**

```js
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

    function formatRupees(amount) {
        return "₹" + amount.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function closeDropdown(toggle, dropdown) {
        dropdown.hidden = true;
        toggle.setAttribute("aria-expanded", "false");
    }

    function wireTile(tile) {
        var accounts = readJSON(tile, "data-accounts");
        var toggle = tile.querySelector(".tile-caret");
        var dropdown = tile.querySelector(".tile-dropdown");
        var figure = tile.querySelector(".tile-figure");
        if (!accounts || !toggle || !dropdown || !figure) {
            return;
        }

        toggle.addEventListener("click", function (event) {
            event.stopPropagation();
            var isOpen = !dropdown.hidden;
            if (isOpen) {
                closeDropdown(toggle, dropdown);
            } else {
                dropdown.hidden = false;
                toggle.setAttribute("aria-expanded", "true");
            }
        });

        document.addEventListener("click", function () {
            closeDropdown(toggle, dropdown);
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                closeDropdown(toggle, dropdown);
            }
        });

        var options = dropdown.querySelectorAll(".tile-dropdown-option");
        for (var i = 0; i < options.length; i++) {
            options[i].addEventListener("click", function (event) {
                event.stopPropagation();
                var id = event.currentTarget.getAttribute("data-account-id");
                if (id === "all") {
                    var total = accounts.reduce(function (sum, a) { return sum + a.balance; }, 0);
                    figure.textContent = formatRupees(total);
                } else {
                    var selected = accounts.filter(function (a) { return String(a.id) === id; })[0];
                    figure.textContent = formatRupees(selected ? selected.balance : 0);
                }
                closeDropdown(toggle, dropdown);
            });
        }
    }

    var tiles = document.querySelectorAll(".tile[data-accounts]");
    for (var i = 0; i < tiles.length; i++) {
        wireTile(tiles[i]);
    }
})();
```

(This replaces the entire previous file contents — the old `wireBalanceCard()` function and its Chart.js block are both gone. Task 6 appends chart-rendering code to this same IIFE-per-concern pattern as a second top-level `(function () { ... })();` block; Task 8 appends a third for the inline add-expense row, toasts, and assistant-bar suggestion chips.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/test_wealth_management.py -v`
Expected: `PASS` — all tests green, including the six edited id assertions.

- [ ] **Step 7: Run the full suite**

Run: `pytest`
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add templates/profile.html static/css/dashboard.css static/js/dashboard.js tests/test_wealth_management.py
git commit -m "feat: rewrite summary tiles with caret-dropdown pattern"
```

---

## Task 6: Charts as inline SVG

**Files:**
- Modify: `templates/profile.html` (replace the `<canvas>` chart row with `<div>` containers)
- Modify: `static/css/dashboard.css` (append chart styles)
- Modify: `static/js/dashboard.js` (append chart-rendering code)

**Interfaces:**
- Consumes: `monthly_totals` (list of `{month, total}`), `category_breakdown` (list of `{name, amount, pct}`) — both already passed by `profile()`, unchanged; `readJSON`, `monthLabel`, `categoryColor`, `formatRupees` from Task 5
- Produces: two new top-level functions in `dashboard.js`, `renderMonthlyChart(container, data)` and `renderCategoryChart(container, data)`, invoked once on load; no interfaces are consumed by later tasks

`id="monthly-chart"` / `id="category-chart"` and their `data-monthly` / `data-categories` attributes are kept verbatim on the new `<div>` containers — confirmed in Pre-flight research that the existing test assertions are plain substring checks, tag-agnostic.

- [ ] **Step 1: Replace the chart row in `templates/profile.html`**

Replace the `<div class="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-4">...</div>` chart block with:

```html
        <div class="charts-row">
            <div class="chart-card">
                <div class="chart-card-header">
                    <h2>Monthly spending</h2>
                    <span class="chart-card-meta" id="monthly-chart-meta">Six months · {{ stats[0].value }}</span>
                </div>
                <div id="monthly-chart" class="chart-svg-container" data-monthly="{{ monthly_totals | tojson | forceescape }}"></div>
            </div>
            <div class="chart-card">
                <div class="chart-card-header">
                    <h2>Where it goes</h2>
                    <span class="chart-card-hint">Click a slice to filter the ledger</span>
                </div>
                <div id="category-chart" class="chart-svg-container" data-categories="{{ category_breakdown | tojson | forceescape }}"></div>
            </div>
        </div>
```

- [ ] **Step 2: Append chart styles to `static/css/dashboard.css`**

```css
/* ------------------------------------------------------------------ */
/* Charts                                                               */
/* ------------------------------------------------------------------ */

.charts-row {
    display: grid;
    grid-template-columns: minmax(340px, 1.5fr) minmax(280px, 1fr);
    gap: 14px;
}

.chart-card {
    background: var(--color-surface);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-md);
    padding: 16px 18px;
}

.chart-card-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 8px;
}

.chart-card-header h2 {
    font-size: 15px;
    margin: 0;
}

.chart-card-meta {
    font-size: 12px;
    color: var(--color-neutral-500);
}

.chart-card-hint {
    font-size: 11.5px;
    color: var(--color-neutral-500);
}

.chart-svg-container svg {
    width: 100%;
    height: auto;
    display: block;
}

.chart-bar {
    fill: var(--color-accent-700);
    transition: fill 150ms;
}

.chart-bar-outside-range {
    fill: var(--color-neutral-800);
}

.chart-bar:hover {
    fill: var(--color-accent);
}

.chart-grid-line {
    stroke: var(--color-divider);
    stroke-width: 1;
}

.chart-bar-label {
    font-size: 11px;
    fill: var(--color-neutral-500);
}

.donut-wrap {
    display: flex;
    align-items: center;
    gap: 18px;
}

.donut-slice {
    transition: opacity 150ms;
    cursor: pointer;
}

.donut-slice-dimmed {
    opacity: 0.28;
}

.donut-center-text {
    font-size: 15px;
    font-weight: 600;
    fill: var(--color-text);
}

.donut-center-label {
    font-size: 10px;
    fill: var(--color-neutral-500);
}

.donut-legend {
    min-width: 132px;
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.donut-legend-row {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--color-neutral-500);
    cursor: pointer;
    background: transparent;
    border: 0;
    font-family: var(--font-body);
    padding: 0;
}

.donut-legend-row-dimmed {
    color: var(--color-neutral-600);
}

.donut-legend-swatch {
    width: 8px;
    height: 8px;
    border-radius: 2px;
    flex-shrink: 0;
}

.donut-legend-name {
    flex: 1;
    text-align: left;
    color: var(--color-text);
}

.donut-legend-pct {
    color: var(--color-neutral-500);
}
```

- [ ] **Step 3: Append chart-rendering code to `static/js/dashboard.js`**

Add this as a new top-level IIFE at the end of the file (after the tile-wiring block from Task 5):

```js
(function () {
    var SVG_NS = "http://www.w3.org/2000/svg";
    var CATEGORY_ORDER = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"];

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
        var MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        var parts = ym.split("-");
        var monthIndex = parseInt(parts[1], 10) - 1;
        return MONTH_LABELS[monthIndex] + " '" + parts[0].slice(2);
    }

    function categoryColor(name) {
        var root = document.documentElement;
        var value = getComputedStyle(root).getPropertyValue("--cat-" + name.toLowerCase());
        return value ? value.trim() : "#999999";
    }

    function formatRupees(amount) {
        return "₹" + amount.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function svgEl(tag, attrs) {
        var el = document.createElementNS(SVG_NS, tag);
        for (var key in attrs) {
            if (Object.prototype.hasOwnProperty.call(attrs, key)) {
                el.setAttribute(key, attrs[key]);
            }
        }
        return el;
    }

    function renderMonthlyChart(container, data) {
        if (!data || data.length === 0) {
            return;
        }
        var width = 620;
        var height = 190;
        var maxTotal = Math.max.apply(null, data.map(function (row) { return row.total; })) || 1;
        var barWidth = Math.min(62, (width / data.length) * 0.6);
        var gap = width / data.length;

        var svg = svgEl("svg", { viewBox: "0 0 " + width + " " + height, role: "img", "aria-label": "Monthly spending" });

        for (var g = 1; g <= 4; g++) {
            var y = 160 - (g * 160 / 4);
            svg.appendChild(svgEl("line", { x1: 0, x2: width, y1: y, y2: y, class: "chart-grid-line" }));
        }

        data.forEach(function (row, i) {
            var barHeight = (row.total / maxTotal) * 150;
            var x = i * gap + (gap - barWidth) / 2;
            var y = 160 - barHeight;
            var rect = svgEl("rect", {
                x: x, y: y, width: barWidth, height: barHeight, rx: 4,
                class: "chart-bar",
            });
            rect.addEventListener("mouseenter", function () {
                var meta = document.getElementById("monthly-chart-meta");
                if (meta) {
                    meta.textContent = monthLabel(row.month) + " · " + formatRupees(row.total);
                }
            });
            svg.appendChild(rect);
            svg.appendChild(svgEl("text", { x: x + barWidth / 2, y: 184, "text-anchor": "middle", class: "chart-bar-label" })).textContent = monthLabel(row.month);
        });

        container.appendChild(svg);
    }

    function renderCategoryChart(container, data) {
        if (!data || data.length === 0) {
            return;
        }
        var ordered = CATEGORY_ORDER.filter(function (name) {
            return data.some(function (row) { return row.name === name; });
        }).map(function (name) {
            return data.filter(function (row) { return row.name === name; })[0];
        });

        var wrap = document.createElement("div");
        wrap.className = "donut-wrap";

        var size = 116;
        var outerR = 52;
        var innerR = 34;
        var cx = size / 2;
        var cy = size / 2;
        var svg = svgEl("svg", { viewBox: "0 0 " + size + " " + size, role: "img", "aria-label": "Category breakdown" });

        var total = ordered.reduce(function (sum, row) { return sum + row.amount; }, 0);
        var angle = -90;
        var slices = [];

        ordered.forEach(function (row) {
            var sweep = (row.amount / total) * 360;
            var startAngle = angle;
            var endAngle = angle + sweep;
            angle = endAngle;

            var path = svgEl("path", {
                d: donutArcPath(cx, cy, outerR, innerR, startAngle, endAngle),
                fill: categoryColor(row.name),
                class: "donut-slice",
            });
            svg.appendChild(path);
            slices.push({ path: path, row: row });
        });

        var centerLabel = svgEl("text", { x: cx, y: cy - 3, "text-anchor": "middle", class: "donut-center-text" });
        centerLabel.textContent = formatRupees(total);
        var centerSub = svgEl("text", { x: cx, y: cy + 11, "text-anchor": "middle", class: "donut-center-label" });
        centerSub.textContent = "Total out";
        svg.appendChild(centerLabel);
        svg.appendChild(centerSub);

        var legend = document.createElement("div");
        legend.className = "donut-legend";

        function setFocus(focusedRow) {
            slices.forEach(function (slice) {
                slice.path.classList.toggle("donut-slice-dimmed", focusedRow && slice.row.name !== focusedRow.name);
            });
            legend.querySelectorAll(".donut-legend-row").forEach(function (rowEl) {
                rowEl.classList.toggle("donut-legend-row-dimmed", focusedRow && rowEl.getAttribute("data-category") !== focusedRow.name);
            });
            if (focusedRow) {
                centerLabel.textContent = formatRupees(focusedRow.amount);
                centerSub.textContent = focusedRow.name;
            } else {
                centerLabel.textContent = formatRupees(total);
                centerSub.textContent = "Total out";
            }
        }

        function navigateToCategory(name) {
            var url = new URL(window.location.href);
            var current = url.searchParams.get("category");
            if (current === name) {
                url.searchParams.delete("category");
            } else {
                url.searchParams.set("category", name);
            }
            window.location.href = url.toString();
        }

        ordered.forEach(function (row, i) {
            var rowEl = document.createElement("button");
            rowEl.type = "button";
            rowEl.className = "donut-legend-row";
            rowEl.setAttribute("data-category", row.name);

            var swatch = document.createElement("span");
            swatch.className = "donut-legend-swatch";
            swatch.style.background = categoryColor(row.name);

            var name = document.createElement("span");
            name.className = "donut-legend-name";
            name.textContent = row.name;

            var pct = document.createElement("span");
            pct.className = "donut-legend-pct";
            pct.textContent = row.pct + "%";

            rowEl.appendChild(swatch);
            rowEl.appendChild(name);
            rowEl.appendChild(pct);
            rowEl.addEventListener("mouseenter", function () { setFocus(row); });
            rowEl.addEventListener("mouseleave", function () { setFocus(null); });
            rowEl.addEventListener("click", function () { navigateToCategory(row.name); });
            legend.appendChild(rowEl);

            slices[i].path.addEventListener("mouseenter", function () { setFocus(row); });
            slices[i].path.addEventListener("mouseleave", function () { setFocus(null); });
            slices[i].path.addEventListener("click", function () { navigateToCategory(row.name); });
        });

        wrap.appendChild(svg);
        wrap.appendChild(legend);
        container.appendChild(wrap);
    }

    function donutArcPath(cx, cy, outerR, innerR, startAngle, endAngle) {
        function point(radius, angleDeg) {
            var rad = (angleDeg * Math.PI) / 180;
            return { x: cx + radius * Math.cos(rad), y: cy + radius * Math.sin(rad) };
        }
        var largeArc = endAngle - startAngle > 180 ? 1 : 0;
        var outerStart = point(outerR, startAngle);
        var outerEnd = point(outerR, endAngle);
        var innerStart = point(innerR, endAngle);
        var innerEnd = point(innerR, startAngle);
        return [
            "M", outerStart.x, outerStart.y,
            "A", outerR, outerR, 0, largeArc, 1, outerEnd.x, outerEnd.y,
            "L", innerStart.x, innerStart.y,
            "A", innerR, innerR, 0, largeArc, 0, innerEnd.x, innerEnd.y,
            "Z",
        ].join(" ");
    }

    var monthlyContainer = document.getElementById("monthly-chart");
    renderMonthlyChart(monthlyContainer, readJSON(monthlyContainer, "data-monthly"));

    var categoryContainer = document.getElementById("category-chart");
    renderCategoryChart(categoryContainer, readJSON(categoryContainer, "data-categories"));
})();
```

- [ ] **Step 4: Run the full suite**

Run: `pytest`
Expected: all tests pass — `id="monthly-chart"`/`id="category-chart"` are unchanged strings, just now on `<div>` elements.

- [ ] **Step 5: Commit**

```bash
git add templates/profile.html static/css/dashboard.css static/js/dashboard.js
git commit -m "feat: replace Chart.js with hand-drawn inline SVG charts"
```

---

## Task 7: Insight cards, Budgets/Goals placeholders, and Ledger

**Files:**
- Modify: `templates/profile.html` (replace the old transactions-table + "Bills & Subscriptions" block with insight cards, budgets/goals placeholders, and the new ledger — this is the last content section of the file)
- Modify: `static/css/dashboard.css` (append styles)

**Interfaces:**
- Consumes: `insights`, `budgets`, `goals` (all `[]`, from Task 1's route), `transactions`, `drill_category`, `search_query` — all already passed by `profile()`

The working `q` search input moves here from the header (dropped in Task 4) per the README's layout — it composes with the existing date-range/preset mechanism exactly as it did in the header. The old disabled "Bills & Subscriptions ... Soon" stub card is removed entirely (no test depends on it — confirmed in Pre-flight research).

- [ ] **Step 1: Replace the remaining old content in `templates/profile.html`**

Replace everything from `<div class="grid grid-cols-1 lg:grid-cols-[1.6fr_1fr] gap-4">` (the old transactions table + "Bills & Subscriptions" stub) through the matching closing `</div>` with:

```html
        <div class="insights-row">
            {% for insight in insights %}
            <div class="insight-card">
                <span class="insight-icon" aria-hidden="true">{{ insight.icon | safe }}</span>
                <p class="insight-title">{{ insight.title }}</p>
                <p class="insight-body">{{ insight.body }}</p>
            </div>
            {% else %}
            <div class="insight-card insight-card-empty">
                <p class="insight-title">Top category</p>
                <p class="insight-body">Insights are computed once you have spending in more than one category.</p>
            </div>
            <div class="insight-card insight-card-empty">
                <p class="insight-title">Budget headroom</p>
                <p class="insight-body">Set up a budget to see how much headroom you have left this month.</p>
            </div>
            <div class="insight-card insight-card-empty">
                <p class="insight-title">Upcoming renewals</p>
                <p class="insight-body">Recurring-expense tracking is coming in a future update.</p>
            </div>
            {% endfor %}
        </div>

        <div class="budgets-goals-row">
            <div class="panel-card">
                <h2>Budgets</h2>
                {% if budgets %}
                <div class="budgets-grid">
                    {% for b in budgets %}
                    <div class="budget-ring">
                        <span class="budget-ring-name">{{ b.category }}</span>
                    </div>
                    {% endfor %}
                </div>
                {% else %}
                <p class="panel-empty">No budgets set yet — coming soon.</p>
                {% endif %}
            </div>
            <div class="panel-card">
                <h2>Goals</h2>
                {% if goals %}
                <div class="goals-list">
                    {% for g in goals %}
                    <div class="goal-row">
                        <span class="goal-name">{{ g.name }}</span>
                    </div>
                    {% endfor %}
                </div>
                {% else %}
                <p class="panel-empty">No goals yet — coming soon.</p>
                {% endif %}
            </div>
        </div>

        <div class="ledger-card">
            <div class="ledger-header">
                <h2>Ledger</h2>
                {% if drill_category %}
                <a href="{{ url_for('profile', date_from=selected_from, date_to=selected_to, q=search_query) }}" class="tag tag-accent ledger-drill-chip">
                    {{ drill_category }} <span aria-hidden="true">✕</span>
                </a>
                {% endif %}
                <form action="{{ url_for('profile') }}" method="get" class="ledger-search-form">
                    <input type="hidden" name="date_from" value="{{ selected_from or '' }}">
                    <input type="hidden" name="date_to" value="{{ selected_to or '' }}">
                    <input type="hidden" name="category" value="{{ drill_category or '' }}">
                    <input type="search" name="q" id="profile-ledger-search-input" value="{{ search_query or '' }}"
                           placeholder="Filter the ledger..." aria-label="Filter the ledger" class="input ledger-search-input">
                </form>
                <span class="ledger-count">{{ transactions|length }} shown</span>
            </div>
            <div class="ledger-table-wrap">
                <table class="table ledger-table">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Description</th>
                            <th>Category</th>
                            <th class="ledger-col-amount">Amount</th>
                            <th class="ledger-col-actions"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for t in transactions %}
                        {% set next_category = None if drill_category == t.category else t.category %}
                        <tr>
                            <td class="ledger-col-date">{{ t.date }}</td>
                            <td>{{ t.description }}</td>
                            <td>
                                <a href="{{ url_for('profile', date_from=selected_from, date_to=selected_to, q=search_query, category=next_category) }}"
                                   class="ledger-category-pill"
                                   style="border-color: var(--cat-{{ t.category|lower }}); color: var(--cat-{{ t.category|lower }}-text);">{{ t.category }}</a>
                            </td>
                            <td class="ledger-col-amount">{{ t.amount }}</td>
                            <td class="ledger-col-actions">
                                <a href="{{ url_for('edit_expense', id=t.id) }}" aria-label="Edit expense" class="ledger-action-icon">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                        <path d="M12 20h9"></path>
                                        <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"></path>
                                    </svg>
                                </a>
                                <form method="POST" action="{{ url_for('delete_expense', id=t.id) }}" class="ledger-delete-form" onsubmit="return confirm('Delete this expense?')">
                                    <button type="submit" aria-label="Delete expense" class="ledger-action-icon ledger-delete-button">
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
                        <tr>
                            <td colspan="5">
                                <div class="ledger-empty">
                                    {% if search_query %}
                                    <p class="ledger-empty-title">Nothing matches "{{ search_query }}"</p>
                                    <p class="ledger-empty-body">Try a shorter word, or widen the date range — the ledger holds transactions in total.</p>
                                    {% else %}
                                    <p class="ledger-empty-title">No expenses in this range</p>
                                    <p class="ledger-empty-body">Widen the range or add the first expense for these dates.</p>
                                    {% endif %}
                                    <a href="{{ url_for('profile') }}" class="btn btn-secondary">Clear filters</a>
                                </div>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
```

- [ ] **Step 2: Append styles to `static/css/dashboard.css`**

```css
/* ------------------------------------------------------------------ */
/* Insight cards                                                       */
/* ------------------------------------------------------------------ */

.insights-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 14px;
}

.insight-card {
    background: var(--color-surface);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
    padding: 13px 15px;
}

.insight-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    border-radius: 50%;
    background: var(--color-accent-900);
    color: var(--color-accent-300);
    margin-bottom: 8px;
}

.insight-title {
    font-size: 13px;
    font-weight: 500;
    margin: 0 0 4px;
}

.insight-body {
    font-size: 12px;
    color: var(--color-neutral-500);
    line-height: 1.45;
    margin: 0;
}

/* ------------------------------------------------------------------ */
/* Budgets / Goals                                                      */
/* ------------------------------------------------------------------ */

.budgets-goals-row {
    display: grid;
    grid-template-columns: minmax(340px, 1.5fr) minmax(280px, 1fr);
    gap: 14px;
}

.panel-card {
    background: var(--color-surface);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-md);
    padding: 16px 18px;
}

.panel-card h2 {
    font-size: 15px;
    margin: 0 0 8px;
}

.panel-empty {
    font-size: 12.5px;
    color: var(--color-neutral-500);
    margin: 0;
}

/* ------------------------------------------------------------------ */
/* Ledger                                                               */
/* ------------------------------------------------------------------ */

.ledger-card {
    background: var(--color-surface);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-md);
    padding: 16px 18px 8px;
}

.ledger-header {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 10px;
}

.ledger-header h2 {
    font-size: 15px;
    margin: 0;
}

.ledger-drill-chip {
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 4px;
}

.ledger-search-input {
    width: 220px;
}

.ledger-count {
    margin-left: auto;
    font-size: 12px;
    color: var(--color-neutral-500);
}

.ledger-table-wrap {
    overflow-x: auto;
}

.ledger-col-amount {
    text-align: right;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
}

.ledger-col-date {
    color: var(--color-neutral-400);
}

.ledger-col-actions {
    width: 36px;
}

.ledger-category-pill {
    display: inline-block;
    border: 1px solid;
    border-radius: calc(var(--radius-md) * 0.75);
    padding: 1.5px 9px;
    font-size: 11.5px;
    text-decoration: none;
}

.ledger-action-icon {
    display: inline-flex;
    width: 15px;
    height: 15px;
    color: var(--color-neutral-600);
    background: transparent;
    border: 0;
    padding: 0;
    cursor: pointer;
}

.ledger-action-icon:hover {
    color: var(--color-accent);
}

.ledger-delete-form {
    display: inline-flex;
    margin-left: 8px;
}

.ledger-empty {
    text-align: center;
    padding: 32px 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
}

.ledger-empty-title {
    font-size: 14px;
    margin: 0;
}

.ledger-empty-body {
    font-size: 12.5px;
    color: var(--color-neutral-500);
    margin: 0 0 8px;
}
```

- [ ] **Step 3: Run the full suite**

Run: `pytest`
Expected: all tests pass, including `test_route_search_query_param_filters_table` (search still works via the same `q` route param, just relocated in the DOM) and the new drill-down tests from Task 1.

- [ ] **Step 4: Commit**

```bash
git add templates/profile.html static/css/dashboard.css
git commit -m "feat: rewrite insight/budget/goal placeholders and ledger with drill-down"
```

---

## Task 8: Inline add-expense, toast, and assistant-bar suggestion chips

**Files:**
- Modify: `static/js/dashboard.js` (append inline-add-expense, toast, and suggestion-chip wiring)
- Modify: `static/css/dashboard.css` (append toast styles)

**Interfaces:**
- Consumes: `id="profile-add-expense-toggle"`, `id="profile-add-expense-row"`, `id="profile-add-expense-description"`, `-amount`, `-category`, `-date`, `id="profile-add-expense-save"`, `id="profile-add-expense-cancel"` (Task 4); `id="profile-chat-quickstart-input"`, `id="profile-chat-quickstart-form"` (Task 4, pre-existing); `POST /api/expenses` (pre-existing endpoint, unmodified)
- Produces: nothing consumed by a later task — this is the final `dashboard.js` addition

- [ ] **Step 1: Append toast styles to `static/css/dashboard.css`**

```css
/* ------------------------------------------------------------------ */
/* Toast                                                                */
/* ------------------------------------------------------------------ */

.dashboard-toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    background: var(--color-surface);
    box-shadow: var(--shadow-lg);
    border-radius: 999px;
    padding: 9px 18px;
    font-size: 13px;
    color: var(--color-text);
    z-index: 1000;
}
```

- [ ] **Step 2: Append the final IIFE to `static/js/dashboard.js`**

```js
(function () {
    function showToast(message) {
        var existing = document.querySelector(".dashboard-toast");
        if (existing) {
            existing.remove();
        }
        var toast = document.createElement("div");
        toast.className = "dashboard-toast";
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(function () {
            toast.remove();
        }, 2200);
    }

    var addToggle = document.getElementById("profile-add-expense-toggle");
    var addRow = document.getElementById("profile-add-expense-row");
    if (addToggle && addRow) {
        addToggle.addEventListener("click", function () {
            addRow.hidden = !addRow.hidden;
        });
    }

    var cancelButton = document.getElementById("profile-add-expense-cancel");
    if (cancelButton && addRow) {
        cancelButton.addEventListener("click", function () {
            addRow.hidden = true;
        });
    }

    var saveButton = document.getElementById("profile-add-expense-save");
    if (saveButton) {
        saveButton.addEventListener("click", function () {
            var descriptionEl = document.getElementById("profile-add-expense-description");
            var amountEl = document.getElementById("profile-add-expense-amount");
            var categoryEl = document.getElementById("profile-add-expense-category");
            var dateEl = document.getElementById("profile-add-expense-date");

            var description = descriptionEl.value.trim();
            var amount = parseFloat(amountEl.value);

            if (!description || isNaN(amount) || amount <= 0) {
                showToast("Enter a description and a valid amount.");
                return;
            }

            fetch("/api/expenses", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    description: description,
                    amount: amount,
                    category: categoryEl.value,
                    date: dateEl.value || new Date().toISOString().slice(0, 10),
                }),
            })
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error("save failed");
                    }
                    showToast("Expense added.");
                    window.location.reload();
                })
                .catch(function () {
                    showToast("Could not save the expense.");
                });
        });
    }

    var chips = document.querySelectorAll(".assistant-chip");
    var chatInput = document.getElementById("profile-chat-quickstart-input");
    var chatForm = document.getElementById("profile-chat-quickstart-form");
    for (var i = 0; i < chips.length; i++) {
        chips[i].addEventListener("click", function (event) {
            if (!chatInput || !chatForm) {
                return;
            }
            chatInput.value = event.currentTarget.getAttribute("data-question");
            if (chatForm.requestSubmit) {
                chatForm.requestSubmit();
            } else {
                chatForm.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
            }
        });
    }
})();
```

`POST /api/expenses` is the existing endpoint from spec 15 (`Implemented — dashboard redesign` per `CLAUDE.md`'s route table) — its request/response shape is unchanged, so no backend work is needed here. `chatForm.requestSubmit()` fires the existing native `submit` event that `chat.js`'s own listener already handles (open the drawer, POST to `/api/chat`) — no `chat.js` change needed.

- [ ] **Step 3: Manually verify in a browser**

Run: `python app.py`, log in as `demo@spendly.com` / `demo123`, open `/profile`. Confirm: "+ Add expense" toggles the inline row and saving one reloads the page with the new row present and a toast; each assistant-bar suggestion chip opens the chat drawer with that question sent; the tile carets open/close their dropdowns and swap the figure; clicking a ledger category pill or a donut slice/legend row navigates with `?category=...` and clicking the active one again clears it; the sidebar theme toggle still flips light/dark.

- [ ] **Step 4: Run the full suite**

Run: `pytest`
Expected: all tests pass — this task adds no new pytest-visible surface (client-only behavior on an already-tested endpoint), so the full-suite run is this task's regression gate.

- [ ] **Step 5: Commit**

```bash
git add static/js/dashboard.js static/css/dashboard.css
git commit -m "feat: wire inline add-expense, toast, and assistant-bar suggestion chips"
```

---

## Self-review notes (fixed inline above, recorded for the record)

- **Spec coverage:** every "Files to change/create/delete" entry in the spec maps to a task above (`app.py`/`database/queries.py` → Task 1; `nocturne.css`/`dashboard.css`/`profile.css` deletion/`base.html`/`CLAUDE.md` → Task 2; `_dashboard_sidebar.html` → Task 3; `profile.html` → Tasks 4/5/6/7; `dashboard.js` → Tasks 5/6/8). `static/js/chat.js` needed no changes at all once research confirmed the existing `profile-chat-quickstart-*` ids already do exactly what the assistant bar needs — this is a scope reduction from the spec's "add a hook if needed" hedge, not a gap.
- **Placeholder scan:** no TBD/TODO; every step has literal code. The one deliberately-open item (browser-verification checklist in Task 8 Step 3) is a manual QA step, not a coding placeholder.
- **Type/id consistency:** `profile-balance-toggle`/`profile-debt-toggle`/`profile-investment-toggle` (Task 5 markup) match the ids the Task 5 test edits expect and the ids `dashboard.js`'s `wireTile()` queries via `.tile-caret`/`.tile-dropdown` classes (not by id, so the three tiles share one generic function — consistent with the original `wireBalanceCard()` pattern). `readJSON`/`categoryColor`/`formatRupees` are defined identically (same body) in both the Task 5 and Task 6 IIFEs since each top-level IIFE is self-contained — this is intentional duplication scoped to each closure, matching the file's existing per-concern-IIFE structure, not a naming drift.
