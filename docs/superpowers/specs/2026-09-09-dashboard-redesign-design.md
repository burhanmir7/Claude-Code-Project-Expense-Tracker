# Spec: Profile Page as Dashboard

## Overview

Redesigns the existing `/profile` page from a single centered column into an
Expensify-style dashboard: a left sidebar (replacing the top navbar on this
page only) plus a main area with KPI cards, a monthly-spending bar chart, a
category-breakdown donut chart, the existing recent-transactions table, and
the existing chat quickstart input. This is a **visual and structural
restyle of data Spendly already has** — no new features (Investments,
Goals, Bills & Subscriptions, Cards, Analytics, Settings, Help Center,
Support) are built. Every sidebar link and KPI card for something that
doesn't exist yet is rendered as a clearly-labelled, non-interactive
placeholder (greyed out, tagged "Soon") rather than hidden or faked with
invented numbers.

Separately, receipt scanning moves from a full-page dropzone-and-reload
flow (Step 12) into the chat: the chat input gets an attach button, and the
whole scan → extract → confirm → save interaction happens as messages in
the chat conversation via two new JSON endpoints. The old `POST
/expenses/scan` route, its dropzone template card, and its dedicated
CSS/JS are removed — replaced, not duplicated.

Chart rendering uses Chart.js, loaded via a CDN `<script>` tag (no npm, no
build step) — the one explicitly-approved exception to this project's
"vanilla JS only" rule, scoped to chart rendering only.

## Depends on

- Step 4-6: Profile page (`profile.html`, `get_summary_stats`,
  `get_category_breakdown`, `get_recent_transactions`, date-filter presets)
- Step 10: AI Chat Interface (`ai.chat.run_chat_turn`, `_chat_drawer.html`,
  `chat.js`, `chat_messages` table, `insert_chat_message`/`get_chat_messages`)
- Step 12: Receipt OCR Intake (`ai.receipts.detect_image_type` /
  `extract_receipt` / `normalise_receipt` / `MAX_RECEIPT_BYTES`,
  `ai.llm_client.AIError` hierarchy) — this step's route and dropzone UI are
  removed and replaced; the `ai/receipts.py` helpers are reused as-is

## Decisions made during brainstorming (binding, not open questions)

- Chat stays a toggleable drawer (not a permanent third column).
- The dashboard layout (sidebar + no top navbar/footer) applies to
  `/profile` only. Every other page keeps the current top navbar unchanged.
- The sidebar shows the **full** nav structure from the reference design
  (General: Dashboard, All Expenses, Bills & Subscriptions, Investment,
  Cards, Goals; Tools: Insight, Analytics; Other: Add Expense, Settings,
  Help Center, Support, theme toggle, Sign out; an "Upgrade to PRO" card at
  the bottom) — but only **Dashboard**, **Add Expense**, the **theme
  toggle**, and **Sign out** are real, clickable links. Everything else
  renders as inert text (not an `<a>`, no `href`, `aria-disabled="true"`)
  with a small "Soon" tag.
- The 4 top KPI cards map onto real data where Spendly has it, honestly
  labelled, not renamed to match the reference's wording where that would
  be misleading:
  - **Total Spent** — the existing filtered total (`get_summary_stats`
    respecting the page's date-range preset), replacing the reference's
    "Account Balance" slot. Spendly has no bank-account concept, so this
    is relabelled rather than faked.
  - **Monthly Expenses** — a new, always-current-calendar-month total,
    independent of the page's date-filter selection (same month boundary
    the existing `this_month` preset already uses: `today.replace(day=1)`
    through `today`).
  - **Total Investment** — placeholder, static "₹0.00", "Soon" tag.
  - **Goal** — placeholder, a static progress-ring shell, "Soon" tag.
  - The existing "Transactions" and "Top category" tiles are not dropped:
    they move into the two chart cards as subtitles (transaction count on
    the bar-chart card, top category name on the donut-chart card, which
    already visually shows this as its largest slice).
- Chart.js (CDN) renders both charts.
- The old Add-Expense-page dropzone, `POST /expenses/scan`,
  `static/css/receipt.css`, and `static/js/receipt.js` are deleted — the
  chat-based flow is the only way to scan a receipt going forward.

## Routes

### Changed layout, same route
- `GET /profile` (existing `profile` view) — now also computes the
  current-month total and the last-6-months series, and renders
  `today.isoformat()`/`session.get('user_id')` truthiness so the template
  can render the sidebar's active state. Still gated the same way
  (`redirect(url_for('login'))` if logged out).

### New JSON routes (both under `/api/`, both logged-in only, JSON 401
otherwise — no `abort()`, no redirect, matching the existing `/api/chat/*`
convention)

- `POST /api/chat/receipt` — accepts `multipart/form-data` field `receipt`.
  View function: `chat_scan_receipt`. Runs the exact same validation and
  extraction `ai/receipts.py` already provides (no-file → 400, size →
  400, type → 400, `AIError` → its mapped status, `is_receipt: false` →
  400), but returns JSON instead of re-rendering a template:
  - `200 {"reply": "<human-readable summary>", "expense": {"amount": str,
    "date": str, "description": str, "category": str}}` on success. The
    `expense` values are the same two-decimal-string / ISO-date /
    `CATEGORIES`-validated shapes `normalise_receipt` already produces.
  - `400 {"error": "..."}` for the same four validation messages Step 12
    already defines (missing file, unsupported type, too large, not a
    receipt).
  - `503`/`429`/`502` `{"error": e.user_message}` for `AIError` subclasses,
    same mapping as `chat_send`.
  - On success, persists two `chat_messages` rows (user: `"📎 " +
    filename`; assistant: the human-readable summary text) so conversation
    history reads sensibly on reload — same "store text turns only, never
    images" rule as before. **Accepted limitation:** the structured
    `expense` fields backing the "Save as expense" button are not
    persisted anywhere; if the page is reloaded before the button is
    clicked, the button is gone and the user must re-scan or use manual
    entry. This matches Step 12's "review before saving, nothing is
    silently kept around" spirit rather than adding a pending-action table.

- `POST /api/expenses` — accepts JSON body `{"amount": str, "date": str,
  "description": str, "category": str}` (exactly what the chat message's
  embedded button already holds from the scan response — no re-parsing of
  ambiguous input, no free-form re-entry). View function: `api_add_expense`.
  Runs the same validation `add_expense` already runs (amount parses as
  float > 0, category in `CATEGORIES`, date parses, description ≤ 200
  chars), then calls the existing `insert_expense`.
  - `200 {"success": true}` on success.
  - `400 {"error": "..."}` reusing the same messages `add_expense` already
    uses, on the same conditions.
  - This route never touches the AI layer at all — it is a plain,
    synchronous DB write, structurally identical to `add_expense`'s
    success path minus the HTML redirect.

### Removed
- `POST /expenses/scan` (`scan_receipt` view function) is deleted.

## Database changes

No new tables, no schema changes. One new read-only query:

- `database/queries.py`: `get_monthly_totals(user_id, months=6) ->
  list[dict]` — returns exactly `months` entries, oldest to newest, one
  per calendar month ending at the current month, each `{"month":
  "YYYY-MM", "total": float}`. Months with no expenses appear with
  `total: 0` — the series must be zero-filled and contiguous, never
  skip a month just because it has no rows (a real user's chart would
  otherwise show misleadingly compressed history).

## Templates

- **Modify**: `templates/profile.html` — restructured into two blocks
  inside `{% block content %}`: the sidebar (via a new include, see
  below) and the dashboard main area (greeting header with the live
  clock, 4 KPI cards, the two chart cards, the recent-transactions table,
  the existing chat quickstart form with the new attach button). The
  route passes `hide_chrome=True` so `base.html` suppresses the navbar
  and footer for this render only.
- **Create**: `templates/_dashboard_sidebar.html` — a partial (does not
  extend `base.html`, included only by `profile.html`), holding the brand
  mark, the three nav sections, the theme-toggle button, sign-out link,
  and the "Upgrade to PRO" placeholder card. Split out because
  `profile.html` was already large before this and the sidebar is a
  self-contained, single-purpose unit.
- **Modify**: `templates/base.html` — wrap the `<nav class="navbar">` and
  `<footer class="footer">` blocks in `{% if not hide_chrome %}`; default
  `hide_chrome` is falsy (via Jinja's `{% if not hide_chrome %}` treating
  an undefined var as falsy) so every other page is completely unaffected.
- **Modify**: `templates/add_expense.html` — remove the `{% block head
  %}` (receipt.css link), the `.receipt-card` form block, and the `{%
  block scripts %}` (receipt.js) added in Step 12. The page returns to
  exactly its Step 7 shape: title, subtitle, the manual-entry form.
- **Modify**: `templates/_chat_drawer.html` — add a hidden file input and
  an attach (📎) button inside `#chat-form`, next to the existing
  textarea and send button.

## Files to change

- `app.py`
  - `profile()`: compute `monthly_expenses = get_summary_stats(user_id,
    date_from=today.replace(day=1).isoformat(), date_to=today.isoformat())`
    (reusing the existing function, not a new one) and `monthly_totals =
    get_monthly_totals(user_id)`; pass both plus `hide_chrome=True` to
    `render_template`.
  - Add `chat_scan_receipt` and `api_add_expense` under a new `# Receipt
    and expense JSON routes` banner (or alongside the existing `# AI
    routes` banner — group with whichever reads more clearly once the
    imports are in place).
  - Remove `scan_receipt` and its now-unused imports (`MAX_RECEIPT_BYTES`,
    `detect_image_type` stay — still used by `chat_scan_receipt`;
    `extract_receipt`, `normalise_receipt` stay too).
  - Import `get_monthly_totals` from `database.queries`.
- `database/queries.py` — add `get_monthly_totals`.
- `templates/profile.html`, `templates/base.html`, `templates/add_expense.html`,
  `templates/_chat_drawer.html` — as above.
- `static/css/profile.css` — add the dashboard/sidebar/KPI-card/chart-card
  styles, continuing the file's existing `profile-` class prefix
  (`.profile-dashboard-shell`, `.profile-sidebar`, `.profile-kpi-card`,
  `.profile-chart-card`, etc.). Category donut colors reuse the existing
  `--cat-*` custom properties already defined at the top of this file.
- `static/css/chat.css` — add styles for the attach button and for the
  new rich "receipt result" assistant bubble (text + an embedded "Save as
  expense" button), using existing tokens only.
- `static/js/chat.js` — add the attach-button wiring (file picked → user
  bubble with the filename → "Reading receipt…" status → `fetch` to
  `/api/chat/receipt` → render the result bubble with a "Save as expense"
  button whose click handler `fetch`es `/api/expenses` with the
  `expense` fields already in hand from the scan response, then either
  shows a success bubble and reloads the page, or shows an error bubble on
  failure).

## Files to create

- `templates/_dashboard_sidebar.html` — as above.
- `static/js/dashboard.js` — ES5 IIFE, null-guarded. Reads the monthly
  totals and category breakdown from `data-*` JSON attributes on their
  respective `<canvas>` elements (matching this codebase's existing
  `data-history-url`-style convention — no inline `<script>` data
  blobs), and initializes two Chart.js charts: a bar chart (monthly
  totals) and a doughnut chart (category breakdown, colored from the
  same `--cat-*` CSS variables the old horizontal-bar UI used, read via
  `getComputedStyle` at init time).

## Files to delete

- `templates/add_expense.html`'s receipt-card markup (edit, not a file
  deletion — see Templates above)
- `static/css/receipt.css`
- `static/js/receipt.js`

## New dependencies

- Chart.js, loaded via `<script src="https://cdn.jsdelivr.net/npm/chart.js">`
  (or a pinned version path) in `profile.html`'s `{% block head %}` or
  `{% block scripts %}` — no other page loads it. This is the
  user-approved exception to "vanilla JS only / no external libraries"
  for this feature, scoped to chart rendering.

## Rules for implementation

- Placeholder sidebar items and KPI cards are never `<a href="...">` and
  never carry a click handler — plain text/`<span>`/`<div>` with
  `aria-disabled="true"` and a "Soon" label, so nothing looks clickable
  that silently does nothing.
- No invented numbers: every placeholder shows `₹0.00`, `—`, or a static
  0%-progress shell — never a plausible-looking fake figure.
- `chat_scan_receipt` and `api_add_expense` follow the same JSON-endpoint
  rules already established: `request.get_json(silent=True)` /
  `request.files.get(...)`, `401 {"error": "Authentication required."}`
  when logged out, never `abort()`, never a redirect.
- Image bytes still never touch disk, DB, session, or logs — same rule
  as Step 12, unchanged; `chat_scan_receipt` reuses `ai/receipts.py`
  as-is, no new image-handling code.
- `chat.js`'s new rich assistant bubble still renders all model-derived
  text via `textContent`/DOM creation — the "Save as expense" button's
  amount/date/category/description come from the already-normalised,
  already-validated response fields, never raw model output re-inserted
  as HTML.
- `get_monthly_totals` uses parameterised queries only, scoped to
  `user_id`, and is zero-filled/contiguous as specified above.
- Chart.js is the only external script this feature adds; nothing else
  in the project's JS gains a framework or a build step.
- CSS still uses only custom-property tokens — no hardcoded hex values,
  including in the new sidebar/KPI/chart-card styles.
- `hide_chrome` defaults to unset/falsy so no other page's rendering
  changes.

## Tests to write

- `database/queries.py`: `get_monthly_totals` — returns exactly `months`
  entries; oldest-to-newest; a month with zero expenses still appears
  with `total: 0`; scoped to the requesting user only.
- `POST /api/chat/receipt`: unauthenticated → 401 JSON; the four existing
  Step-12 validation failures (no file, wrong type, too large, not a
  receipt) still produce the same 400 messages and still call the fake
  zero times on the type/size failures; a successful fake response
  returns the normalised `expense` fields and a `reply` string, and
  stores exactly one user row and one assistant row in `chat_messages`
  (text only, never the image).
- `POST /api/expenses`: unauthenticated → 401 JSON; valid body creates
  exactly one expense row and returns `{"success": true}`; the same
  invalid-amount/invalid-category/invalid-date/too-long-description
  cases `add_expense` already rejects return 400 here too, and insert
  exactly zero rows.
- `GET /profile`: body no longer contains `id="receipt-form"` (dropzone
  gone); contains the sidebar's real links (`Add Expense`, `Sign out`)
  and does **not** render the placeholder items as `<a>` tags; body does
  not contain the top navbar markup (`hide_chrome` suppressed it) while
  every other existing page's test (login, add_expense, landing) still
  finds the navbar present, confirming `hide_chrome` didn't leak.
- `GET /expenses/add`: body no longer contains `id="receipt-form"` or
  `js/receipt.js`.

## Definition of done

- [ ] `/profile` renders as a sidebar + dashboard layout; every other page
      is visually unchanged (top navbar still present)
- [ ] Only Dashboard, Add Expense, theme toggle, and Sign out are
      clickable in the sidebar; everything else is visibly inert with a
      "Soon" tag
- [ ] The 4 KPI cards show real Total Spent and real Monthly Expenses;
      Total Investment and Goal are static placeholders
- [ ] The bar chart shows 6 consecutive months of real spending, zero-
      filled where there's no data; the donut chart shows the real
      category breakdown in the app's existing category colors
- [ ] Attaching a receipt via the chat's 📎 button shows the scan result
      as a chat message with a working "Save as expense" button; nothing
      is saved until that button is clicked
- [ ] The old dropzone is gone from Add Expense; `POST /expenses/scan` no
      longer exists
- [ ] All new/changed tests pass without `LLM_API_KEY` and without
      importing a provider SDK
