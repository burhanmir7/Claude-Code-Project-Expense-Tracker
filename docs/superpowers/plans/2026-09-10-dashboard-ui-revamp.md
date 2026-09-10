# Dashboard UI Revamp (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the `/profile` dashboard to match the approved "Style A" reference mockup (icon-badge KPI cards, icon+label sidebar, header search box, polished chart/table cards) using Tailwind CDN utility classes, while keeping every other page's appearance and the entire existing behavior/test suite unchanged.

**Architecture:** Tailwind loads site-wide via CDN in `base.html` with its base CSS reset disabled (so pages not yet using Tailwind utilities are visually unaffected), configured to read colors from Spendly's existing CSS custom properties so light/dark theming keeps working with zero new dark-mode-specific classes. `templates/profile.html` and `templates/_dashboard_sidebar.html` are rewritten in Tailwind utility classes; five structural class names those templates' own JS (`static/js/dashboard.js`) depends on via `querySelector` are kept as bare "hook" classes alongside the new utility classes. `static/css/profile.css` shrinks to just the category-color tokens once everything else converts to utilities.

**Tech Stack:** Flask + Jinja2 (existing), Tailwind CDN (`https://cdn.tailwindcss.com`, new), Chart.js (existing, unchanged), vanilla JS (existing, unchanged) — no npm, no build step, no new `requirements.txt` entry.

**Spec:** `.claude/specs/15-dashboard-ui-revamp.md`

## Global Constraints

- Tailwind CDN only — no npm, no build step, no other JS framework (per spec's "Decisions from brainstorming — Tech stack")
- Keep Spendly's existing green `--accent` as primary brand color; only add one new token pair (`--accent-3`/`--accent-3-light`, blue) for the Net Worth card (per spec's "Brand color" decision)
- Tailwind `darkMode` must be `['selector', '[data-theme="dark"]']` to match the existing toggle in `static/js/main.js` exactly — never the `media` strategy
- No fabricated data or columns: keep the transactions table's current columns (Date, Description, Category, Amount, Actions); no month-over-month trend text on any KPI card (no ledger/history exists to compute one)
- Currency stays Python-side `:,.2f}` comma-formatted; never reformatted in templates
- Parameterized SQL only, never string-formatted values
- Every `id`, `data-*` attribute, and literal string listed in the "Preserve list" below must appear verbatim in the rendered output of every task from Task 3 onward
- Phase 1 touches only: `templates/base.html`, `templates/profile.html`, `templates/_dashboard_sidebar.html`, `static/css/style.css`, `static/css/profile.css`, `database/queries.py`, `app.py`, `CLAUDE.md`, plus test files. No other template or CSS file changes.

### Preserve list (must appear verbatim in rendered `/profile` + sidebar output)

**IDs:** `monthly-chart`, `category-chart`, `profile-balance-select` / `profile-debt-select` / `profile-investment-select` (each present only when that card has accounts), `profile-chat-quickstart-form`, `profile-chat-quickstart-input`, `profile-chat-quickstart-attach-button`, `profile-chat-quickstart-attach`, `profile-dashboard-clock`, `theme-toggle` (exactly one such id on the page — the sidebar's toggle button, since `base.html`'s navbar is hidden via `hide_chrome=True` on this page)

**Structural classes JS finds via `querySelector` (`static/js/dashboard.js`'s `wireBalanceCard()`), keep as bare hook classes alongside new Tailwind utilities:** `profile-balance-card`, `profile-balance-value`, `profile-balance-select`, `profile-balance-menu-toggle`, `profile-balance-menu-dropdown`

**Literal `class="..."` strings a test checks directly:** `class="profile-sidebar"` (sidebar wrapper), `class="navbar"` (must NOT appear anywhere in `/profile`'s body since `hide_chrome=True`)

**Text/attributes:** "Dashboard", "Soon", "Account Balance", "Debt", "Total Investment", every expense category name, "No accounts yet.", "No debts yet.", "No investments yet.", `href="/accounts"`, `data-monthly`/`data-categories`/`data-accounts` attributes with their existing `tojson | forceescape` values, `src=".../js/chat.js"`, `src=".../js/dashboard.js"`

**Unchanged files:** `static/js/dashboard.js`, `static/js/chat.js`, `static/js/main.js`, `templates/_chat_drawer.html`, `static/css/chat.css` — none of these are modified in this plan.

---

## Task 1: Wire up Tailwind CDN and new design tokens

**Files:**
- Modify: `CLAUDE.md` (Tech constraints section)
- Modify: `static/css/style.css:1-49` (add one token pair to both `:root` and `[data-theme="dark"]`)
- Modify: `templates/base.html:1-15` (add Tailwind CDN script + config in `<head>`)
- Test: manual — no automated test file changes in this task

**Interfaces:**
- Produces: Tailwind utility classes become usable in any template extending `base.html`. New CSS variables `--accent-3` (light `#2f6690`, dark `#7fb3d9`) and `--accent-3-light` (light `#e6eef4`, dark `#1c2e3a`) become available for later tasks' KPI card icon badges. Tailwind color tokens `paper`, `paperWarm`, `paperCard`, `ink`, `inkSoft`, `inkMuted`, `inkFaint`, `accent`, `accentLight`, `accent2`, `accent2Light`, `accent3`, `accent3Light`, `danger`, `dangerLight`, `border`, `borderSoft` become available as Tailwind utility suffixes (e.g. `bg-paperCard`, `text-inkMuted`, `border-border`) for later tasks.
- Consumes: nothing (first task).

- [ ] **Step 1: Confirm the current baseline passes**

Run: `source myenv/bin/activate && pytest -q`
Expected: `245 passed` (or whatever the current count is — record it; this is the number every later task must not regress below)

- [ ] **Step 2: Add the new color tokens to `static/css/style.css`**

In the `:root` block (light theme), immediately after the `--danger-light: #fdecea;` line, add:
```css
    --accent-3: #2f6690;
    --accent-3-light: #e6eef4;
```

In the `[data-theme="dark"]` block, immediately after the `--danger-light: #3c211d;` line, add:
```css
    --accent-3: #7fb3d9;
    --accent-3-light: #1c2e3a;
```

- [ ] **Step 3: Add the Tailwind CDN script and config to `templates/base.html`**

In `templates/base.html`, replace:
```html
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    {% if session.get('user_id') %}
    <link rel="stylesheet" href="{{ url_for('static', filename='css/chat.css') }}">
    {% endif %}
    {% block head %}{% endblock %}
```
with:
```html
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    {% if session.get('user_id') %}
    <link rel="stylesheet" href="{{ url_for('static', filename='css/chat.css') }}">
    {% endif %}
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            darkMode: ['selector', '[data-theme="dark"]'],
            corePlugins: { preflight: false },
            theme: {
                extend: {
                    colors: {
                        paper: 'var(--paper)',
                        paperWarm: 'var(--paper-warm)',
                        paperCard: 'var(--paper-card)',
                        ink: 'var(--ink)',
                        inkSoft: 'var(--ink-soft)',
                        inkMuted: 'var(--ink-muted)',
                        inkFaint: 'var(--ink-faint)',
                        accent: 'var(--accent)',
                        accentLight: 'var(--accent-light)',
                        accent2: 'var(--accent-2)',
                        accent2Light: 'var(--accent-2-light)',
                        accent3: 'var(--accent-3)',
                        accent3Light: 'var(--accent-3-light)',
                        danger: 'var(--danger)',
                        dangerLight: 'var(--danger-light)',
                        border: 'var(--border)',
                        borderSoft: 'var(--border-soft)'
                    },
                    fontFamily: {
                        display: ['DM Serif Display', 'Georgia', 'serif'],
                        body: ['DM Sans', 'system-ui', 'sans-serif']
                    },
                    borderRadius: {
                        sm: 'var(--radius-sm)',
                        md: 'var(--radius-md)',
                        lg: 'var(--radius-lg)'
                    }
                }
            }
        }
    </script>
    {% block head %}{% endblock %}
```

`corePlugins: { preflight: false }` is essential here, not optional: Tailwind's base reset restyles bare `<h1>`/`<button>`/`<p>`/etc. site-wide the instant the script loads, which would visually break every page that doesn't use Tailwind utilities yet (login, landing, expense forms, accounts pages). Disabling it means Tailwind only affects elements that actually use its utility classes.

- [ ] **Step 4: Update `CLAUDE.md`'s Tech constraints section**

Find this line in `CLAUDE.md`:
```
- **Vanilla JS only** — no React, no jQuery, no npm packages
```
Replace it with:
```
- **Vanilla JS only** — no React, no jQuery, no npm packages. The one named exception is Tailwind CDN (`https://cdn.tailwindcss.com`, loaded in `base.html`) for CSS utility classes — it ships no build step and no interactive behavior of its own; all interactivity remains hand-written vanilla JS
```

- [ ] **Step 5: Verify nothing broke**

Run: `source myenv/bin/activate && pytest -q`
Expected: same count as Step 1 (still passing — this task adds no new visible markup, so no test should change behavior)

- [ ] **Step 6: Manual visual spot-check**

Start the dev server (`python app.py`) if not already running, open `/`, `/login`, and `/profile` in a browser. Confirm all three look **exactly as they did before this task** — Tailwind is loaded but nothing on the page uses its classes yet, and `preflight: false` means the reset doesn't touch unstyled elements either.

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md static/css/style.css templates/base.html
git commit -m "Wire up Tailwind CDN and new accent-3 color token

Preflight disabled so pages not yet using Tailwind utilities are
visually unaffected; darkMode keyed to the existing data-theme toggle."
```

---

## Task 2: Backend transaction search filter

**Files:**
- Modify: `database/queries.py:56-71` (`get_recent_transactions`)
- Modify: `app.py` (`profile()` route)
- Test: `tests/test_06-date-filter-profile-page.py`

**Interfaces:**
- Consumes: nothing new from Task 1.
- Produces: `get_recent_transactions(user_id, limit=10, date_from=None, date_to=None, search=None)` — new `search` param, case-insensitive substring match on `description` OR `category`, composes with `date_from`/`date_to`. `app.py`'s `profile()` route reads `request.args.get('q', '').strip()`, passes `search=q or None` to `get_recent_transactions`, and passes `search_query=q` into the template context (used by Task 4's search box markup).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_06-date-filter-profile-page.py` (place near the other `get_recent_transactions`-adjacent tests, using the file's existing `register_new_user`/`user_id_for`/`insert_expense` helpers already imported at the top of the file):

```python
# ------------------------------------------------------------------ #
# GET /profile — transaction search (?q=)                             #
# ------------------------------------------------------------------ #

def test_search_matches_description_case_insensitive(client):
    email = "search1@example.com"
    register_new_user(client, name="Search One", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40.00, "Food", date.today(), "Grocery run")
    insert_expense(uid, 10.00, "Transport", date.today(), "Cab ride")

    rows = get_recent_transactions(uid, search="grocery")

    assert len(rows) == 1
    assert rows[0]["description"] == "Grocery run"


def test_search_matches_category(client):
    email = "search2@example.com"
    register_new_user(client, name="Search Two", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40.00, "Food", date.today(), "Lunch")
    insert_expense(uid, 10.00, "Transport", date.today(), "Cab ride")

    rows = get_recent_transactions(uid, search="Food")

    assert len(rows) == 1
    assert rows[0]["category"] == "Food"


def test_search_composes_with_date_range(client):
    today = date.today()
    email = "search3@example.com"
    register_new_user(client, name="Search Three", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40.00, "Food", today - timedelta(days=40), "Old grocery run")
    insert_expense(uid, 10.00, "Food", today, "New grocery run")

    rows = get_recent_transactions(
        uid, search="grocery",
        date_from=(today - timedelta(days=5)).isoformat(),
        date_to=today.isoformat(),
    )

    assert len(rows) == 1
    assert rows[0]["description"] == "New grocery run"


def test_search_no_matches_returns_empty(client):
    email = "search4@example.com"
    register_new_user(client, name="Search Four", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40.00, "Food", date.today(), "Lunch")

    rows = get_recent_transactions(uid, search="zzzznomatch")

    assert rows == []


def test_search_absent_behaves_as_before(client):
    email = "search5@example.com"
    register_new_user(client, name="Search Five", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40.00, "Food", date.today(), "Lunch")

    rows = get_recent_transactions(uid)

    assert len(rows) == 1


def test_route_search_query_param_filters_table(client):
    login_demo(client)
    response = client.get("/profile?q=bills")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Electricity" in body
    assert "Groceries" not in body
```

`get_recent_transactions` is already imported at the top of this test file (per its existing `from database.queries import (get_category_breakdown, get_recent_transactions, get_summary_stats)` import block) — no new import needed. `timedelta` is already imported too.

- [ ] **Step 2: Run tests to verify they fail**

Run: `source myenv/bin/activate && pytest tests/test_06-date-filter-profile-page.py -k search -v`
Expected: `test_search_matches_description_case_insensitive`, `test_search_matches_category`, `test_search_composes_with_date_range`, `test_search_no_matches_returns_empty` FAIL with `TypeError: get_recent_transactions() got an unexpected keyword argument 'search'`; `test_search_absent_behaves_as_before` PASSES already (no new argument used); `test_route_search_query_param_filters_table` FAILS on the assertion (the route doesn't read `q` yet, so "Groceries" is still present)

- [ ] **Step 3: Implement `search` in `database/queries.py`**

Replace:
```python
def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    conn = get_db()
    where, params = _user_date_filter(user_id, date_from, date_to)
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
with:
```python
def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None, search=None):
    conn = get_db()
    where, params = _user_date_filter(user_id, date_from, date_to)

    if search:
        where += " AND (description LIKE ? OR category LIKE ?)"
        term = "%" + search + "%"
        params += [term, term]

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

- [ ] **Step 4: Wire `q` into `app.py`'s `profile()` route**

In `app.py`, `profile()` currently has:
```python
    transactions = [
        {
            "id": t["id"],
            "date": t["date"],
            "description": t["description"],
            "category": t["category"],
            "amount": f"₹{t['amount']:,.2f}",
        }
        for t in get_recent_transactions(user_id, date_from=date_from, date_to=date_to)
    ]
```
Replace with:
```python
    search_query = request.args.get("q", "").strip()

    transactions = [
        {
            "id": t["id"],
            "date": t["date"],
            "description": t["description"],
            "category": t["category"],
            "amount": f"₹{t['amount']:,.2f}",
        }
        for t in get_recent_transactions(user_id, date_from=date_from, date_to=date_to, search=search_query or None)
    ]
```

Then find the `return render_template(` call for `"profile.html"` and add `search_query=search_query,` to its keyword arguments (anywhere in the argument list — e.g. right after `selected_from=date_from, selected_to=date_to,`):
```python
    return render_template(
        "profile.html", user=user, stats=stats,
        transactions=transactions,
        selected_from=date_from, selected_to=date_to,
        search_query=search_query,
        active_preset=active_preset, preset_ranges=preset_ranges,
        monthly_totals=monthly_totals,
        category_breakdown=category_breakdown, hide_chrome=True,
        accounts=accounts, total_balance=total_balance,
        debt_accounts=debt_accounts, total_debt=total_debt,
        investment_accounts=investment_accounts, total_investment=total_investment,
        net_worth=net_worth, net_worth_is_negative=net_worth_is_negative,
        net_worth_account_count=net_worth_account_count,
    )
```

`search_query` is passed to the template even though no template references it yet — Jinja does not error on unused context variables, so this is safe ahead of Task 4 wiring it into the search box's `value=`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `source myenv/bin/activate && pytest tests/test_06-date-filter-profile-page.py -k search -v`
Expected: all 6 tests PASS

- [ ] **Step 6: Run the full suite to confirm no regression**

Run: `source myenv/bin/activate && pytest -q`
Expected: previous count + 5 new tests (the 6th, `test_search_absent_behaves_as_before`, was already passing before this task and still counts) — e.g. if Task 1 ended at 245, expect 250

- [ ] **Step 7: Commit**

```bash
git add database/queries.py app.py tests/test_06-date-filter-profile-page.py
git commit -m "Add transaction search filter to GET /profile

New ?q= query param filters recent transactions by description or
category (case-insensitive), composing with the existing date range."
```

---

## Task 3: Rewrite the dashboard sidebar with icon navigation

**Files:**
- Modify: `templates/_dashboard_sidebar.html` (full rewrite)
- Modify: `static/css/profile.css` (remove now-unused sidebar rules, once Task 3 confirms nothing else needs them — see Step 4)
- Test: existing tests only, no new test file

**Interfaces:**
- Consumes: Tailwind classes/tokens from Task 1.
- Produces: same sidebar structure (same nav sections, same links, same "Soon" stubs) with icon+label rows instead of plain text links. `id="theme-toggle"` stays on the theme toggle button. `class="profile-sidebar"` stays on the `<aside>` wrapper.

- [ ] **Step 1: Confirm the current baseline passes**

Run: `source myenv/bin/activate && pytest -q`
Expected: same count as the end of Task 2

- [ ] **Step 2: Replace `templates/_dashboard_sidebar.html`**

Replace the entire file with:
```html
<aside class="profile-sidebar w-56 shrink-0 border-r border-border bg-paperCard flex flex-col gap-6 p-4 min-h-screen">
    <div class="flex items-center gap-2 px-2">
        <span class="brand-icon">◈</span>
        <span class="font-display text-lg text-ink">Spendly</span>
    </div>

    <div class="flex flex-col gap-1">
        <p class="text-[0.7rem] uppercase tracking-wider text-inkFaint px-2 mb-1">General</p>
        <a href="{{ url_for('profile') }}" class="flex items-center gap-3 rounded-md px-3 py-2 text-sm bg-accentLight text-ink font-medium">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 shrink-0" aria-hidden="true"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
            Dashboard
        </a>
        <a href="{{ url_for('accounts') }}" class="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-inkSoft hover:bg-accentLight hover:text-ink">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 shrink-0" aria-hidden="true"><path d="M17 7H6a3 3 0 0 0 0 6h12a3 3 0 0 1 0 6H6"></path><polyline points="14 4 17 7 14 10"></polyline><polyline points="10 20 7 17 10 14"></polyline></svg>
            Accounts
        </a>
        <span class="flex items-center justify-between gap-3 rounded-md px-3 py-2 text-sm text-inkFaint cursor-not-allowed" aria-disabled="true">
            <span class="flex items-center gap-3">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 shrink-0" aria-hidden="true"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
                All Expenses
            </span>
            <span class="text-[0.65rem] uppercase border border-border rounded-sm px-1.5 py-0.5">Soon</span>
        </span>
        <span class="flex items-center justify-between gap-3 rounded-md px-3 py-2 text-sm text-inkFaint cursor-not-allowed" aria-disabled="true">
            <span class="flex items-center gap-3">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 shrink-0" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                Bills &amp; Subscriptions
            </span>
            <span class="text-[0.65rem] uppercase border border-border rounded-sm px-1.5 py-0.5">Soon</span>
        </span>
        <span class="flex items-center justify-between gap-3 rounded-md px-3 py-2 text-sm text-inkFaint cursor-not-allowed" aria-disabled="true">
            <span class="flex items-center gap-3">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 shrink-0" aria-hidden="true"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline><polyline points="17 6 23 6 23 12"></polyline></svg>
                Investment
            </span>
            <span class="text-[0.65rem] uppercase border border-border rounded-sm px-1.5 py-0.5">Soon</span>
        </span>
        <span class="flex items-center justify-between gap-3 rounded-md px-3 py-2 text-sm text-inkFaint cursor-not-allowed" aria-disabled="true">
            <span class="flex items-center gap-3">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 shrink-0" aria-hidden="true"><rect x="1" y="4" width="22" height="16" rx="2"></rect><line x1="1" y1="10" x2="23" y2="10"></line></svg>
                Cards
            </span>
            <span class="text-[0.65rem] uppercase border border-border rounded-sm px-1.5 py-0.5">Soon</span>
        </span>
        <span class="flex items-center justify-between gap-3 rounded-md px-3 py-2 text-sm text-inkFaint cursor-not-allowed" aria-disabled="true">
            <span class="flex items-center gap-3">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 shrink-0" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="6"></circle><circle cx="12" cy="12" r="2"></circle></svg>
                Goals
            </span>
            <span class="text-[0.65rem] uppercase border border-border rounded-sm px-1.5 py-0.5">Soon</span>
        </span>
    </div>

    <div class="flex flex-col gap-1">
        <p class="text-[0.7rem] uppercase tracking-wider text-inkFaint px-2 mb-1">Tools</p>
        <span class="flex items-center justify-between gap-3 rounded-md px-3 py-2 text-sm text-inkFaint cursor-not-allowed" aria-disabled="true">
            <span class="flex items-center gap-3">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 shrink-0" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                Insight
            </span>
            <span class="text-[0.65rem] uppercase border border-border rounded-sm px-1.5 py-0.5">Soon</span>
        </span>
        <span class="flex items-center justify-between gap-3 rounded-md px-3 py-2 text-sm text-inkFaint cursor-not-allowed" aria-disabled="true">
            <span class="flex items-center gap-3">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 shrink-0" aria-hidden="true"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>
                Analytics
            </span>
            <span class="text-[0.65rem] uppercase border border-border rounded-sm px-1.5 py-0.5">Soon</span>
        </span>
    </div>

    <div class="flex flex-col gap-1">
        <p class="text-[0.7rem] uppercase tracking-wider text-inkFaint px-2 mb-1">Other</p>
        <a href="{{ url_for('add_expense') }}" class="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-inkSoft hover:bg-accentLight hover:text-ink">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 shrink-0" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="16"></line><line x1="8" y1="12" x2="16" y2="12"></line></svg>
            Add Expense
        </a>
        <span class="flex items-center justify-between gap-3 rounded-md px-3 py-2 text-sm text-inkFaint cursor-not-allowed" aria-disabled="true">
            <span class="flex items-center gap-3">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 shrink-0" aria-hidden="true"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
                Settings
            </span>
            <span class="text-[0.65rem] uppercase border border-border rounded-sm px-1.5 py-0.5">Soon</span>
        </span>
        <span class="flex items-center justify-between gap-3 rounded-md px-3 py-2 text-sm text-inkFaint cursor-not-allowed" aria-disabled="true">
            <span class="flex items-center gap-3">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 shrink-0" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                Help Center
            </span>
            <span class="text-[0.65rem] uppercase border border-border rounded-sm px-1.5 py-0.5">Soon</span>
        </span>
        <span class="flex items-center justify-between gap-3 rounded-md px-3 py-2 text-sm text-inkFaint cursor-not-allowed" aria-disabled="true">
            <span class="flex items-center gap-3">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 shrink-0" aria-hidden="true"><path d="M3 18v-6a9 9 0 0 1 18 0v6"></path><path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"></path></svg>
                Support
            </span>
            <span class="text-[0.65rem] uppercase border border-border rounded-sm px-1.5 py-0.5">Soon</span>
        </span>
        <button id="theme-toggle" type="button" aria-label="Toggle dark mode" class="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-inkSoft hover:bg-accentLight hover:text-ink text-left w-full bg-transparent border-0 cursor-pointer font-body">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 shrink-0" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle><line x1="12" y1="2" x2="12" y2="4"></line><line x1="12" y1="20" x2="12" y2="22"></line><line x1="4.2" y1="4.2" x2="5.6" y2="5.6"></line><line x1="18.4" y1="18.4" x2="19.8" y2="19.8"></line><line x1="2" y1="12" x2="4" y2="12"></line><line x1="20" y1="12" x2="22" y2="12"></line><line x1="4.2" y1="19.8" x2="5.6" y2="18.4"></line><line x1="18.4" y1="5.6" x2="19.8" y2="4.2"></line></svg>
            Toggle theme
        </button>
        <a href="{{ url_for('logout') }}" class="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-inkSoft hover:bg-accentLight hover:text-ink">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 shrink-0" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
            Sign out
        </a>
    </div>

    <div class="mt-auto border border-dashed border-border rounded-md p-3 text-center text-inkFaint" aria-disabled="true">
        <p class="text-sm mb-1">Upgrade to PRO</p>
        <p class="text-[0.65rem] uppercase">Soon</p>
    </div>
</aside>
```

Every `href`/`url_for()` target, "Dashboard", "Soon" (×8), "Accounts", `id="theme-toggle"`, and `class="profile-sidebar"` are preserved from the original — only the visual styling and icon presence changed.

- [ ] **Step 3: Run the full suite**

Run: `source myenv/bin/activate && pytest -q`
Expected: same count as Task 2 — no test should reference sidebar CSS classes that were removed (only `class="profile-sidebar"` is checked, and it's preserved)

- [ ] **Step 4: Remove now-unused sidebar CSS rules from `static/css/profile.css`**

Delete the entire "Sidebar" section (from the `/* Sidebar */` comment through the end of `.profile-sidebar-upgrade-title`'s rule, i.e. lines covering `.profile-sidebar`, `.profile-sidebar-brand`, `.profile-sidebar-section`, `.profile-sidebar-heading`, `.profile-sidebar-link`, `.profile-sidebar-link-soon`, `.profile-sidebar-soon`, `.profile-sidebar-theme-toggle`, `.profile-sidebar-upgrade`, `.profile-sidebar-upgrade-title`) — none of these class names appear in the new sidebar markup. Also remove the `.profile-sidebar { ... }` and `.profile-sidebar-link-active` overrides referenced inside the `@media (max-width: 900px)` block at the bottom of the file, replacing that block's sidebar-related rules with nothing (keep the rest of the media query, which handles `.profile-kpi-row`/`.profile-chart-row`/`.profile-bottom-row` — those still exist until Tasks 5–6).

- [ ] **Step 5: Run the full suite again**

Run: `source myenv/bin/activate && pytest -q`
Expected: same count — CSS-only deletions never affect rendered HTML or test assertions

- [ ] **Step 6: Manual visual check**

Open `/profile` in a browser (both light and dark mode via the sidebar's theme toggle). Confirm: icon+label nav renders, active "Dashboard" item is highlighted, "Soon" badges still show on stub items, clicking "Accounts" navigates correctly, theme toggle still switches themes.

- [ ] **Step 7: Commit**

```bash
git add templates/_dashboard_sidebar.html static/css/profile.css
git commit -m "Restyle dashboard sidebar with icon navigation in Tailwind

Same nav structure and Soon stubs as before; only presentation changed."
```

---

## Task 4: Rewrite the dashboard header, search box, and chat quickstart bar

**Files:**
- Modify: `templates/profile.html:16-56` (header block through the filter bar)
- Test: existing tests only

**Interfaces:**
- Consumes: `search_query` from Task 2's `profile()` route; Tailwind tokens from Task 1.
- Produces: same header/filter-bar structure with a new functional search form; every id (`profile-dashboard-clock`, `profile-chat-quickstart-form`, `profile-chat-quickstart-input`, `profile-chat-quickstart-attach-button`, `profile-chat-quickstart-attach`) preserved exactly.

- [ ] **Step 1: Confirm the current baseline passes**

Run: `source myenv/bin/activate && pytest -q`
Expected: same count as the end of Task 3

- [ ] **Step 2: Replace the header-through-filterbar block in `templates/profile.html`**

Replace:
```html
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

        <form id="profile-chat-quickstart-form" class="profile-chat-quickstart">
            <input type="file" id="profile-chat-quickstart-attach" class="chat-attach-input" accept="image/png,image/jpeg,image/webp,image/gif">
            <button type="button" id="profile-chat-quickstart-attach-button" class="profile-chat-quickstart-attach" aria-label="Attach a receipt image">📎</button>
            <input type="text" id="profile-chat-quickstart-input" class="profile-chat-quickstart-input"
                   placeholder="Ask about your spending..." autocomplete="off">
            <button type="submit" class="profile-chat-quickstart-send">Send</button>
        </form>

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
```
with:
```html
    <div class="profile-dashboard-main flex-1 min-w-0 flex flex-col gap-5 py-6 px-6">
        <div class="flex items-center gap-4 flex-wrap">
            <div>
                <h1 class="font-display text-2xl text-ink">Hi, {{ user.name }} 👋</h1>
                <p class="text-inkMuted text-sm">Track your expenses and transactions</p>
            </div>
            <div class="flex-1"></div>
            <form action="{{ url_for('profile') }}" method="get" class="flex items-center">
                <input type="hidden" name="date_from" value="{{ selected_from or '' }}">
                <input type="hidden" name="date_to" value="{{ selected_to or '' }}">
                <input type="search" name="q" value="{{ search_query or '' }}"
                       placeholder="Search expenses..." aria-label="Search expenses"
                       class="w-48 md:w-64 rounded-lg border border-border bg-paperCard text-ink text-sm px-3 py-2 font-body">
            </form>
            <span class="text-inkFaint text-xs" id="profile-dashboard-clock"></span>
            <div class="w-9 h-9 rounded-full bg-accent text-paperCard flex items-center justify-center font-semibold">{{ user.initials }}</div>
        </div>

        <form id="profile-chat-quickstart-form" class="profile-balance-card flex items-center gap-3 rounded-2xl p-4 bg-paperCard shadow-sm">
            <input type="file" id="profile-chat-quickstart-attach" class="chat-attach-input" accept="image/png,image/jpeg,image/webp,image/gif">
            <button type="button" id="profile-chat-quickstart-attach-button" aria-label="Attach a receipt image"
                    class="border border-border rounded-lg bg-paperCard text-ink px-2.5 py-2 cursor-pointer">📎</button>
            <input type="text" id="profile-chat-quickstart-input"
                   placeholder="Ask about your spending..." autocomplete="off"
                   class="flex-1 rounded-lg border border-border bg-paper text-ink px-3 py-2 font-body">
            <button type="submit" class="rounded-lg border border-border bg-accent text-paperCard px-4 py-2 font-body cursor-pointer">Send</button>
        </form>

        <div class="flex flex-wrap items-center justify-between gap-3 rounded-2xl p-4 bg-paperCard shadow-sm">
            <div class="flex flex-wrap gap-2">
                <a href="{{ url_for('profile', date_from=preset_ranges.this_month[0], date_to=preset_ranges.this_month[1]) }}"
                   class="rounded-lg border px-3.5 py-1.5 text-sm font-body no-underline {% if active_preset == 'this_month' %}bg-accentLight border-accent text-ink{% else %}border-border text-inkMuted bg-paper{% endif %}">This Month</a>
                <a href="{{ url_for('profile', date_from=preset_ranges.last_3_months[0], date_to=preset_ranges.last_3_months[1]) }}"
                   class="rounded-lg border px-3.5 py-1.5 text-sm font-body no-underline {% if active_preset == 'last_3_months' %}bg-accentLight border-accent text-ink{% else %}border-border text-inkMuted bg-paper{% endif %}">Last 3 Months</a>
                <a href="{{ url_for('profile', date_from=preset_ranges.last_6_months[0], date_to=preset_ranges.last_6_months[1]) }}"
                   class="rounded-lg border px-3.5 py-1.5 text-sm font-body no-underline {% if active_preset == 'last_6_months' %}bg-accentLight border-accent text-ink{% else %}border-border text-inkMuted bg-paper{% endif %}">Last 6 Months</a>
                <a href="{{ url_for('profile') }}"
                   class="rounded-lg border px-3.5 py-1.5 text-sm font-body no-underline {% if active_preset == 'all_time' %}bg-accentLight border-accent text-ink{% else %}border-border text-inkMuted bg-paper{% endif %}">All Time</a>
            </div>
            <form action="{{ url_for('profile') }}" method="get" class="flex items-end gap-3">
                <label class="flex flex-col text-xs text-inkFaint gap-1" for="date_from">From
                    <input type="date" id="date_from" name="date_from" value="{{ selected_from or '' }}"
                           class="rounded-lg border border-border bg-paper text-ink px-2 py-1.5 font-body">
                </label>
                <label class="flex flex-col text-xs text-inkFaint gap-1" for="date_to">To
                    <input type="date" id="date_to" name="date_to" value="{{ selected_to or '' }}"
                           class="rounded-lg border border-border bg-paper text-ink px-2 py-1.5 font-body">
                </label>
                <button type="submit" class="rounded-lg border border-border bg-accent text-paperCard px-4 py-1.5 font-body cursor-pointer">Apply</button>
            </form>
        </div>
```

The chat quickstart form keeps the `profile-balance-card` hook class (matching Task 5's KPI cards) purely so it visually matches the new card style — `dashboard.js`'s `wireBalanceCard()` no-ops safely on it since it has no `.profile-balance-value`/`.profile-balance-select` children (the function's own `if (accounts && value && select)` and `if (menuToggle && menuDropdown)` guards both fail closed).

- [ ] **Step 3: Run the full suite**

Run: `source myenv/bin/activate && pytest -q`
Expected: same count — `profile-dashboard-clock`, all four quickstart ids, `date_from`/`date_to` input ids/names, and every `url_for()` target are unchanged

- [ ] **Step 4: Manual check**

Open `/profile`. Confirm: clock renders and updates, quickstart chat form still sends messages, date preset links still work, typing in the new search box and submitting filters the table (visually verify once Task 6 renders it — for now just confirm the page still loads with a 200 and the box is visible).

- [ ] **Step 5: Commit**

```bash
git add templates/profile.html
git commit -m "Restyle dashboard header and add functional search box

Search composes with the existing date-range filter via hidden inputs."
```

---

## Task 5: Rewrite the four KPI cards in Style A

**Files:**
- Modify: `templates/profile.html` (the `profile-kpi-row` block)
- Test: existing tests only

**Interfaces:**
- Consumes: `--accent-3`/`accent3`/`accent3Light` tokens from Task 1; `profile-balance-card`/`profile-balance-value`/`profile-balance-select`/`profile-balance-menu-toggle`/`profile-balance-menu-dropdown` hook classes (unchanged contract with `dashboard.js`).
- Produces: same four cards, same conditional rendering (`{% if accounts %}` etc.), same `data-accounts` attributes, restyled as icon-badge cards per the approved mockup. No trend/percentage text — Spendly has no balance history to compute one.

- [ ] **Step 1: Confirm the current baseline passes**

Run: `source myenv/bin/activate && pytest -q`
Expected: same count as the end of Task 4

- [ ] **Step 2: Replace the `profile-kpi-row` block in `templates/profile.html`**

Replace the entire `<div class="profile-kpi-row">...</div>` block (from `<div class="profile-kpi-row">` through its matching closing `</div>`, containing all four cards) with:
```html
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div class="profile-balance-card rounded-2xl p-4 bg-paperCard shadow-sm flex flex-col gap-2.5" data-accounts="{{ accounts | tojson | forceescape }}">
                <div class="flex items-center gap-2.5">
                    <span class="w-8 h-8 rounded-lg bg-accentLight text-accent flex items-center justify-center shrink-0" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4"><rect x="2" y="6" width="20" height="13" rx="2"></rect><path d="M2 10h20"></path><circle cx="16.5" cy="14.5" r="1.25" fill="currentColor" stroke="none"></circle></svg>
                    </span>
                    <span class="text-sm text-inkMuted flex-1">Account Balance</span>
                    <div class="relative">
                        <button type="button" class="profile-balance-menu-toggle bg-transparent border-0 text-inkMuted cursor-pointer px-1 leading-none" id="profile-balance-menu-toggle" aria-label="Account options" aria-haspopup="true" aria-expanded="false">⋮</button>
                        <div class="profile-balance-menu-dropdown flex absolute top-full right-0 z-10 bg-paperCard border border-border rounded-lg min-w-[140px] flex-col p-1.5" id="profile-balance-menu-dropdown" hidden>
                            <a href="{{ url_for('add_account') }}" class="block px-2 py-1.5 text-sm text-ink rounded-md hover:bg-paperWarm">Add account</a>
                            <a href="{{ url_for('accounts') }}" class="block px-2 py-1.5 text-sm text-ink rounded-md hover:bg-paperWarm">Manage accounts</a>
                        </div>
                    </div>
                </div>

                {% if accounts %}
                <span class="profile-balance-value text-2xl font-semibold text-ink" id="profile-balance-value">{{ total_balance }}</span>
                <select class="profile-balance-select self-start rounded-lg border border-border bg-paper text-ink text-xs px-2 py-1.5 font-body" id="profile-balance-select" aria-label="Select account">
                    <option value="all">All Accounts</option>
                    {% for a in accounts %}
                    <option value="{{ a.id }}">{{ a.name }}</option>
                    {% endfor %}
                </select>
                {% else %}
                <span class="profile-balance-value text-2xl font-semibold text-ink">₹0.00</span>
                <p class="text-xs text-inkFaint">No accounts yet. <a href="{{ url_for('add_account') }}" class="text-accent">Add one</a></p>
                {% endif %}
            </div>

            <div class="profile-balance-card rounded-2xl p-4 bg-paperCard shadow-sm flex flex-col gap-2.5" data-accounts="{{ debt_accounts | tojson | forceescape }}">
                <div class="flex items-center gap-2.5">
                    <span class="w-8 h-8 rounded-lg bg-dangerLight text-danger flex items-center justify-center shrink-0" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4"><rect x="3" y="7" width="18" height="12" rx="2"></rect><path d="M3 11h18"></path><path d="M7 15h4"></path></svg>
                    </span>
                    <span class="text-sm text-inkMuted flex-1">Debt</span>
                    <div class="relative">
                        <button type="button" class="profile-balance-menu-toggle bg-transparent border-0 text-inkMuted cursor-pointer px-1 leading-none" id="profile-debt-menu-toggle" aria-label="Debt options" aria-haspopup="true" aria-expanded="false">⋮</button>
                        <div class="profile-balance-menu-dropdown flex absolute top-full right-0 z-10 bg-paperCard border border-border rounded-lg min-w-[140px] flex-col p-1.5" id="profile-debt-menu-dropdown" hidden>
                            <a href="{{ url_for('add_account', type='debt') }}" class="block px-2 py-1.5 text-sm text-ink rounded-md hover:bg-paperWarm">Add account</a>
                            <a href="{{ url_for('accounts') }}" class="block px-2 py-1.5 text-sm text-ink rounded-md hover:bg-paperWarm">Manage accounts</a>
                        </div>
                    </div>
                </div>

                {% if debt_accounts %}
                <span class="profile-balance-value text-2xl font-semibold text-ink" id="profile-debt-value">{{ total_debt }}</span>
                <select class="profile-balance-select self-start rounded-lg border border-border bg-paper text-ink text-xs px-2 py-1.5 font-body" id="profile-debt-select" aria-label="Select debt account">
                    <option value="all">All Debts</option>
                    {% for a in debt_accounts %}
                    <option value="{{ a.id }}">{{ a.name }}</option>
                    {% endfor %}
                </select>
                {% else %}
                <span class="profile-balance-value text-2xl font-semibold text-ink">₹0.00</span>
                <p class="text-xs text-inkFaint">No debts yet. <a href="{{ url_for('add_account', type='debt') }}" class="text-accent">Add one</a></p>
                {% endif %}
            </div>

            <div class="profile-balance-card rounded-2xl p-4 bg-paperCard shadow-sm flex flex-col gap-2.5" data-accounts="{{ investment_accounts | tojson | forceescape }}">
                <div class="flex items-center gap-2.5">
                    <span class="w-8 h-8 rounded-lg bg-accent2Light text-accent2 flex items-center justify-center shrink-0" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4"><polyline points="3 17 9 11 13 15 21 7"></polyline><polyline points="14 7 21 7 21 14"></polyline></svg>
                    </span>
                    <span class="text-sm text-inkMuted flex-1">Total Investment</span>
                    <div class="relative">
                        <button type="button" class="profile-balance-menu-toggle bg-transparent border-0 text-inkMuted cursor-pointer px-1 leading-none" id="profile-investment-menu-toggle" aria-label="Investment options" aria-haspopup="true" aria-expanded="false">⋮</button>
                        <div class="profile-balance-menu-dropdown flex absolute top-full right-0 z-10 bg-paperCard border border-border rounded-lg min-w-[140px] flex-col p-1.5" id="profile-investment-menu-dropdown" hidden>
                            <a href="{{ url_for('add_account', type='investment') }}" class="block px-2 py-1.5 text-sm text-ink rounded-md hover:bg-paperWarm">Add account</a>
                            <a href="{{ url_for('accounts') }}" class="block px-2 py-1.5 text-sm text-ink rounded-md hover:bg-paperWarm">Manage accounts</a>
                        </div>
                    </div>
                </div>

                {% if investment_accounts %}
                <span class="profile-balance-value text-2xl font-semibold text-ink" id="profile-investment-value">{{ total_investment }}</span>
                <select class="profile-balance-select self-start rounded-lg border border-border bg-paper text-ink text-xs px-2 py-1.5 font-body" id="profile-investment-select" aria-label="Select investment">
                    <option value="all">All Investments</option>
                    {% for a in investment_accounts %}
                    <option value="{{ a.id }}">{{ a.name }}</option>
                    {% endfor %}
                </select>
                {% else %}
                <span class="profile-balance-value text-2xl font-semibold text-ink">₹0.00</span>
                <p class="text-xs text-inkFaint">No investments yet. <a href="{{ url_for('add_account', type='investment') }}" class="text-accent">Add one</a></p>
                {% endif %}
            </div>

            <div class="profile-balance-card rounded-2xl p-4 bg-paperCard shadow-sm flex flex-col gap-2.5">
                <div class="flex items-center gap-2.5">
                    <span class="w-8 h-8 rounded-lg bg-accent3Light text-accent3 flex items-center justify-center shrink-0" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4"><path d="M12 20V10"></path><path d="M18 20V4"></path><path d="M6 20v-4"></path></svg>
                    </span>
                    <span class="text-sm text-inkMuted flex-1">Net Worth</span>
                    <div class="relative">
                        <button type="button" class="profile-balance-menu-toggle bg-transparent border-0 text-inkMuted cursor-pointer px-1 leading-none" aria-label="Net worth options" aria-haspopup="true" aria-expanded="false">⋮</button>
                        <div class="profile-balance-menu-dropdown flex absolute top-full right-0 z-10 bg-paperCard border border-border rounded-lg min-w-[140px] flex-col p-1.5" hidden>
                            <a href="{{ url_for('accounts') }}" class="block px-2 py-1.5 text-sm text-ink rounded-md hover:bg-paperWarm">Manage accounts</a>
                        </div>
                    </div>
                </div>

                <span class="profile-balance-value text-2xl font-semibold {% if net_worth_is_negative %}text-danger{% else %}text-ink{% endif %}">{{ net_worth }}</span>
                <p class="text-xs text-inkFaint">{{ net_worth_account_count }} account{{ "s" if net_worth_account_count != 1 else "" }}</p>
            </div>
        </div>
```

Each dropdown `<div>` carries a Tailwind `flex` class (for its visible-state layout, since `flex-col` alone only sets `flex-direction` and does nothing without `display: flex` also present) plus the bare `hidden` HTML attribute that `dashboard.js` toggles via `menuDropdown.hidden = true/false` (the DOM property, not a class). Do **not** add a Tailwind `hidden` utility class alongside `flex` — both set the `display` property, and Tailwind's generated `.flex{display:flex}` rule is a same-specificity author-stylesheet rule that beats the browser's default `[hidden]{display:none}` UA rule, silently reopening the exact bug already fixed once in this codebase (the dropdown would render open by default). Task 7 keeps one small hand-written CSS rule, `.profile-balance-menu-dropdown[hidden] { display: none; }`, specifically to give the hidden state higher specificity than the `flex` utility — that rule is the fix, not a Tailwind class.

- [ ] **Step 3: Run the full suite**

Run: `source myenv/bin/activate && pytest -q`
Expected: same count — all four cards' ids, the `profile-balance-*` hook classes, `data-accounts` attributes, and conditional empty-state text are unchanged

- [ ] **Step 4: Manual check**

Open `/profile` with at least one account of each type (add via chat or the Accounts page if needed). Confirm: each card shows its colored icon badge (green/red/amber/blue), the three-dot menu opens and closes on click, the dropdown selector switches the displayed balance without a page reload, Net Worth shows red text when negative. Toggle dark mode and confirm all four cards still look correct.

- [ ] **Step 5: Commit**

```bash
git add templates/profile.html
git commit -m "Restyle the four KPI cards with icon badges (Style A)

Same dropdown/menu/refresh behavior; only visual treatment changed.
No trend indicator — Spendly has no balance history to compute one."
```

---

## Task 6: Rewrite the chart row, transactions table, and bills stub

**Files:**
- Modify: `templates/profile.html` (the `profile-chart-row` and `profile-bottom-row` blocks)
- Test: existing tests only

**Interfaces:**
- Consumes: Tailwind tokens from Task 1.
- Produces: same two chart canvases (`id="monthly-chart"`, `id="category-chart"`, same `data-monthly`/`data-categories` attributes), same table columns and category badges, same "Bills & Subscriptions" stub text.

- [ ] **Step 1: Confirm the current baseline passes**

Run: `source myenv/bin/activate && pytest -q`
Expected: same count as the end of Task 5

- [ ] **Step 2: Replace the chart-row and bottom-row blocks in `templates/profile.html`**

Replace:
```html
        <div class="profile-chart-row">
            <div class="profile-chart-card">
                <h2 class="profile-card-title">Monthly spending</h2>
                <p class="profile-chart-subtitle">{{ stats[1].value }} transactions this range</p>
                <canvas id="monthly-chart" data-monthly="{{ monthly_totals | tojson | forceescape }}"></canvas>
            </div>
            <div class="profile-chart-card">
                <h2 class="profile-card-title">Category breakdown</h2>
                <p class="profile-chart-subtitle">Top: {{ stats[2].value }}</p>
                <canvas id="category-chart" data-categories="{{ category_breakdown | tojson | forceescape }}"></canvas>
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
```
with:
```html
        <div class="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-4">
            <div class="rounded-2xl p-4 bg-paperCard shadow-sm">
                <h2 class="font-display text-lg text-ink mb-1">Monthly spending</h2>
                <p class="text-sm text-inkMuted mb-2">{{ stats[1].value }} transactions this range</p>
                <canvas id="monthly-chart" data-monthly="{{ monthly_totals | tojson | forceescape }}"></canvas>
            </div>
            <div class="rounded-2xl p-4 bg-paperCard shadow-sm">
                <h2 class="font-display text-lg text-ink mb-1">Category breakdown</h2>
                <p class="text-sm text-inkMuted mb-2">Top: {{ stats[2].value }}</p>
                <canvas id="category-chart" data-categories="{{ category_breakdown | tojson | forceescape }}"></canvas>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-[1.6fr_1fr] gap-4">
            <div class="rounded-2xl p-4 bg-paperCard shadow-sm">
                <h2 class="font-display text-lg text-ink mb-3">Recent transactions</h2>
                <div class="overflow-x-auto">
                    <table class="w-full border-collapse">
                        <thead>
                            <tr>
                                <th class="px-3 py-2 text-left text-xs uppercase tracking-wide text-inkMuted border-b border-borderSoft">Date</th>
                                <th class="px-3 py-2 text-left text-xs uppercase tracking-wide text-inkMuted border-b border-borderSoft">Description</th>
                                <th class="px-3 py-2 text-left text-xs uppercase tracking-wide text-inkMuted border-b border-borderSoft">Category</th>
                                <th class="px-3 py-2 text-right text-xs uppercase tracking-wide text-inkMuted border-b border-borderSoft">Amount</th>
                                <th class="px-3 py-2 text-right text-xs uppercase tracking-wide text-inkMuted border-b border-borderSoft">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for t in transactions %}
                            <tr class="hover:bg-paperWarm">
                                <td class="px-3 py-2.5 text-sm border-b border-borderSoft">{{ t.date }}</td>
                                <td class="px-3 py-2.5 text-sm border-b border-borderSoft">{{ t.description }}</td>
                                <td class="px-3 py-2.5 text-sm border-b border-borderSoft"><span class="category-badge category-badge-{{ t.category|lower }}">{{ t.category }}</span></td>
                                <td class="px-3 py-2.5 text-sm text-right font-semibold text-ink border-b border-borderSoft" style="font-variant-numeric: tabular-nums;">{{ t.amount }}</td>
                                <td class="px-3 py-2.5 text-right border-b border-borderSoft">
                                    <a href="{{ url_for('edit_expense', id=t.id) }}" aria-label="Edit expense" class="inline-flex w-4 h-4 text-inkMuted hover:text-accent">
                                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                            <path d="M12 20h9"></path>
                                            <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"></path>
                                        </svg>
                                    </a>
                                    <form method="POST" action="{{ url_for('delete_expense', id=t.id) }}" class="inline-flex ml-2" onsubmit="return confirm('Delete this expense?')">
                                        <button type="submit" aria-label="Delete expense" class="inline-flex w-4 h-4 text-inkMuted hover:text-danger bg-transparent border-0 p-0 cursor-pointer">
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
                                <td colspan="5" class="text-center text-inkFaint py-6">No transactions in this date range.</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="rounded-2xl p-4 bg-paperCard shadow-sm opacity-55" aria-disabled="true">
                <h2 class="font-display text-lg text-ink mb-3 flex items-center gap-2">Bills &amp; Subscriptions <span class="text-[0.65rem] uppercase border border-border rounded-sm px-1.5 py-0.5 font-body">Soon</span></h2>
                <p class="text-center text-inkFaint py-6">Coming in a future update.</p>
            </div>
        </div>
```

The `.category-badge*` classes are intentionally kept exactly as-is (not converted to Tailwind) — they already resolve to per-category CSS custom properties (`--cat-food`, `--cat-transport`, etc.) that `static/css/profile.css` defines and nothing about that per-category color system needs to change.

- [ ] **Step 3: Run the full suite**

Run: `source myenv/bin/activate && pytest -q`
Expected: same count — `id="monthly-chart"`/`id="category-chart"` with their `data-*` attributes, category badge classes, transaction amounts, "No transactions in this date range.", and "Bills & Subscriptions"/"Soon" are all unchanged

- [ ] **Step 4: Manual check**

Open `/profile`. Confirm both charts render (bar + donut), the transactions table shows real data with edit/delete icons working, deleting an expense still shows the native confirm dialog (expected — this is the existing `onsubmit="return confirm(...)"` pattern, unchanged), and the Bills & Subscriptions card still shows as a dimmed "Soon" stub. Check dark mode too.

- [ ] **Step 5: Commit**

```bash
git add templates/profile.html
git commit -m "Restyle chart row, transactions table, and Bills stub

Same columns, same category-badge color system, same chart canvases."
```

---

## Task 7: Clean up dead CSS and final regression pass

**Files:**
- Modify: `static/css/profile.css` (remove all rules for classes no longer used anywhere in `templates/profile.html` or `templates/_dashboard_sidebar.html`)
- Test: full existing suite + manual verification of the spec's Definition of Done

**Interfaces:**
- Consumes: nothing new.
- Produces: `static/css/profile.css` containing only the `:root { --cat-* }` token block (and the `@media` block's now-empty-of-sidebar-rules query, or removed entirely if nothing remains in it after Task 3's Step 4 changes) — verify with a final grep pass.

- [ ] **Step 1: Grep for now-dead classes**

Run:
```bash
for cls in profile-section profile-container profile-card profile-card-title section-icon profile-user-card profile-avatar profile-name profile-email profile-member-since profile-stats profile-stat profile-stat-head profile-stat-icon profile-stat-label profile-stat-value profile-stat-note profile-table profile-table-wrap col-amount col-actions table-action-link delete-form btn-delete profile-chat-quickstart profile-chat-quickstart-input profile-chat-quickstart-send profile-chat-quickstart-attach profile-filterbar profile-filter-presets profile-filter-btn profile-filter-btn-active profile-filter-custom profile-filter-custom-active profile-filter-label profile-filter-apply profile-table-empty profile-empty-note profile-dashboard-shell profile-dashboard-main profile-dashboard-header profile-dashboard-greeting profile-dashboard-subtitle profile-dashboard-header-actions profile-dashboard-clock profile-dashboard-avatar profile-kpi-row profile-kpi-card profile-kpi-card-soon profile-kpi-label profile-kpi-value profile-kpi-note profile-kpi-ring profile-chart-row profile-chart-card profile-chart-subtitle profile-bottom-row profile-col-main profile-col-side profile-card-soon; do
  if grep -qE "class=\"[^\"]*\b$cls\b" templates/profile.html templates/_dashboard_sidebar.html 2>/dev/null; then
    echo "STILL USED: $cls"
  fi
done
```
The pattern only matches inside `class="..."` attributes specifically (not `id="..."`), since some names in this list — `profile-dashboard-clock` — legitimately survive as an `id` in the new markup (per the Preserve list) while their old CSS *class* rule is genuinely dead; a naive substring match across any attribute would falsely flag those as still-needed.

Expected: no output (every listed class is fully replaced by Tailwind utilities in Tasks 3–6). If any class prints "STILL USED", check that reference — it likely means a spot in `templates/profile.html` was missed in an earlier task and needs the same Tailwind conversion before its CSS rule can be deleted.

- [ ] **Step 2: Delete the dead rules from `static/css/profile.css`**

Remove every rule block for a class confirmed dead in Step 1. Keep: the `:root { --cat-* }` block at the top of the file, the `.category-badge*` rules, the `@media` block only if anything inside it still applies (if Task 3's Step 4 already emptied it of sidebar rules and nothing else remains inside `@media (max-width: 900px) { ... }` or `@media (max-width: 768px) { ... }`, delete those empty media query blocks too), and — critically — the `.profile-balance-menu-dropdown[hidden] { display: none; }` rule. That rule is not dead: it's the fix that keeps Task 5's three-dot menus closed by default (see Task 5's note on the `flex`/`hidden`-attribute interaction) and must survive this cleanup even though `.profile-balance-menu-dropdown` alone (without `[hidden]`) otherwise carries no other rules after this task.

- [ ] **Step 3: Run the full suite**

Run: `source myenv/bin/activate && pytest -q`
Expected: same count as the end of Task 6 — pure CSS deletion never changes rendered HTML

- [ ] **Step 4: Full manual regression pass against the spec's Definition of Done**

With the dev server running, in a browser:
- [ ] `/profile` visually matches the approved Style-A mockup direction (icon-badge KPI cards, icon+label sidebar, header search box, restyled chart/table cards)
- [ ] Toggle dark mode from the sidebar — every element (cards, sidebar, table, charts, search box) switches correctly with no unstyled/white-on-white or black-on-black text
- [ ] Type a search term matching an existing expense's description, submit — table filters to matching rows only; clear the box and resubmit — full list returns
- [ ] Each of the four KPI cards: three-dot menu opens/closes, dropdown selector switches the shown balance instantly (no reload), "Add account" links go to the correctly-prefilled add-account form
- [ ] Visit `/login`, `/`, `/expenses/add`, `/accounts` — confirm none of them changed appearance (Task 1's `preflight: false` should mean zero visual drift on these pages)

- [ ] **Step 5: Run the full suite one final time**

Run: `source myenv/bin/activate && pytest -q`
Expected: full pass, count matching the running total from Task 6 (Task 1's baseline + 5 new search tests from Task 2)

- [ ] **Step 6: Commit**

```bash
git add static/css/profile.css
git commit -m "Remove dead CSS after the dashboard Tailwind rewrite

profile.css now holds only the --cat-* category color tokens."
```
