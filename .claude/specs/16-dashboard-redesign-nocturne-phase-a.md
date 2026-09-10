# Spec: Dashboard Redesign — Nocturne (Phase A: Visual System + Shell + Charts + Interactions)

## Overview

Replaces the Tailwind-based `/profile` dashboard shipped in
[15-dashboard-ui-revamp.md](15-dashboard-ui-revamp.md) with the "Nocturne"
dark design system handed off in
`design_handoff_dashboard_redesign/` (`README.md` is the authoritative
source for exact pixel values, copy text, and animation timings — this spec
resolves scope, ambiguity, and the concrete route/data/test contract; it
does not restate every measurement).

This is **Sub-project A** of a three-part decomposition the user approved:

- **A (this spec)** — visual system, sidebar, static shell, SVG charts,
  `dashboard.js` interactions. No schema changes.
- **B (future)** — command palette, chat drawer restyle.
- **C (future)** — new backend: `budgets` table, `goals` table,
  `net_worth_series` query, `ai/insights.py`.

Only `/profile` and its two partials change. Every other page (login,
register, landing, accounts, expense forms, terms/privacy) keeps its
current DM Serif/DM Sans + green-accent look — this is a scoped page
rewrite, not a site-wide reskin, matching the precedent set by spec 15.

## Depends on
- Spec 15 (Dashboard UI Revamp) — this spec supersedes its visual approach
  for `/profile` and `_dashboard_sidebar.html` outright; the account-type
  KPI data (`accounts`, `debt_accounts`, `investment_accounts`,
  `total_balance`, `total_debt`, `total_investment`, `net_worth`) and the
  `q` search parameter it introduced are kept and re-skinned, not rebuilt
  from scratch
- Step 14 (Wealth Management) — `get_accounts`, `get_net_worth`
- `ai/tools`, `ai/chat.py`, `static/js/chat.js`, `templates/_chat_drawer.html`
  — read but not modified; the assistant bar wires into the existing chat
  flow without restyling it (restyle is Sub-project B)

## Decisions from brainstorming (resolved ambiguities)

1. **Tokens are page-scoped, not global.** The README's step 1 says "Token
   sheet + Inter, in `base.html`," which would reskin the entire site.
   Since Tailwind usage today is confined to `templates/profile.html` and
   `templates/_dashboard_sidebar.html` (verified via grep — no other
   template uses Tailwind utility classes), this spec instead:
   - Copies `design_handoff_dashboard_redesign/tokens/nocturne.css` to
     `static/css/nocturne.css` unmodified (its own `:root` block, new
     `--color-*` names — it does not touch or rename `style.css`'s
     `--paper`/`--ink`/etc. tokens, so there is no collision)
   - Links `nocturne.css` and the Inter font only from `profile.html`'s own
     `{% block head %}`, exactly like `profile.css` is linked today
   - Removes the Tailwind CDN `<script>` and its `tailwind.config` block
     from `base.html` entirely (nothing else depends on it once
     `profile.html`/`_dashboard_sidebar.html` are rewritten as hand-written
     CSS), per the design handoff's own guidance to implement as CSS +
     vanilla JS, not Tailwind utilities
   - `base.html`'s existing DM Serif Display/DM Sans font link and
     `style.css` link are untouched — they still serve every other page
2. **Assistant bar scope.** The assistant bar's own markup/CSS (input,
   scan-receipt button, Ask button, suggestion chips) is built in A. Its
   Enter/Ask/chip behavior opens the **existing, unrestyled** chat drawer
   and submits the typed text through the existing `/api/chat` flow driven
   by `static/js/chat.js` — reusing chat.js's existing open/submit
   mechanism (add the smallest possible hook to chat.js if one doesn't
   already exist — e.g. an exported function or a custom DOM event —
   rather than duplicating its POST logic in `dashboard.js`). Restyling the
   drawer itself (`_chat_drawer.html`, `chat.css`) is Sub-project B; it will
   look visually inconsistent with the new dashboard until then, an
   accepted trade-off matching spec 15's own precedent for out-of-scope
   pages.
3. **Command palette is entirely out of scope for A** (Sub-project B). The
   header's "Search or jump to…" button renders visually per the README
   but has no click/⌘K handler wired in A — it is inert. This is an
   intentional, documented gap, not a bug.
4. **Search and drill-down are server round-trips**, consistent with the
   existing preset-link mechanism (already decided in prior brainstorming).
   `q` (existing) and a new `category` query param both apply **only** to
   the ledger table. The donut, budget-ring placeholders, and insight
   placeholders compute from a **date-range-only** subset — never from `q`
   or `category` — per the README's explicit warning against drill-down
   shrinking the other panels.
5. **Budgets, Goals, and Insight cards render as empty states in A** (no
   `budgets`/`goals` tables and no `ai/insights.py` module exist yet — both
   are Sub-project C). The section markup, grid layout, and card shells are
   built now so C only has to swap placeholder content for real data; no
   fabricated numbers are shown.
6. **Sparklines render as non-interactive placeholders in A.** The net-worth
   card's 320×64 sparkline and each tile's 56×16 mini-sparkline need
   historical time-series data (`net_worth_series`, Sub-project C) that
   doesn't exist yet — Spendly's schema stores only current balances, never
   snapshots. Rather than fabricate a fake trend (misleading) or skip the
   markup (extra rework for C), A renders a flat, muted, non-interactive
   placeholder line (no dots, no hover, no delta badge) in the same SVG
   structure the README describes. Sub-project C swaps the data source and
   turns on the hover/dot/delta behavior — no markup changes needed then.
7. **"Soon" sidebar pills are removed**, per the README's explicit
   "deliberate change." Ledger, Budgets, Goals, Insights, Cards, and
   Reports nav items appear as inactive/disabled entries (styled per the
   README's inactive-item token, `--color-neutral-400` on transparent) with
   no "Soon" badge — they simply have no working link until their routes
   land. This intentionally breaks the existing `assert "Soon" in body`
   test (see Tests to write).
8. **Chart.js is removed** from `profile.html`. Both charts become
   hand-drawn inline SVG built by `dashboard.js` from the existing
   `monthly_totals` / `category_breakdown` JSON (no new data needed) — the
   only reason Chart.js was loaded on this page.
9. **The sidebar user chip's "plan" label is static decorative text**, not
   fabricated financial data — Spendly has no subscription/plan concept in
   its schema. Hardcode `"Free plan"` (matching the existing disabled
   "Upgrade to PRO" stub's implication that everyone is currently on a free
   tier). This differs from the sparkline/insights placeholders, which are
   computed figures that could mislead if faked — a plan label is chrome.

## Routes

`GET /profile` — no new route, extends the existing one:
- Adds one new optional query parameter, `category` (string, one of the
  seven `CATEGORIES` values) — the ledger drill-down filter. Composes with
  `q`, `date_from`, `date_to` on the ledger only, exactly as `q` composes
  with the date range today. Selecting the currently-active category again
  (client-side, via the drill-down chip's `✕` or clicking the same pill)
  clears it — a plain toggle, not new server logic beyond "param present or
  absent."
- Passes `drill_category` (the resolved value, or `None`) to the template,
  alongside a `budgets = []`, `goals = []`, `insights = []` set of
  placeholder context variables so the template can render the Sub-project-C
  sections generically (empty list → empty state) without special-casing
  "feature doesn't exist yet."

No other routes change. `POST /api/expenses` (inline add-expense row),
`POST /api/chat` and `POST /api/chat/receipt` (assistant bar → existing chat
drawer) are consumed as-is, unmodified.

## Database changes

None. `budgets`, `goals`, and `net_worth_series` remain Sub-project C.

`database/queries.py`:
- `get_recent_transactions(user_id, limit=10, date_from=None, date_to=None,
  search=None, category=None)` gains a `category` parameter. When provided,
  adds a parameterized `AND category = ?` clause. Composes with existing
  `search` and date-range clauses (all provided filters apply together,
  same pattern as the existing `search` parameter added in spec 15).
- No other query signatures change. `get_summary_stats`,
  `get_category_breakdown`, `get_monthly_totals`, `get_accounts`,
  `get_net_worth` are called exactly as today (date-range only, never
  `category` or `search`) — this is what keeps the donut/insights/budget
  placeholders immune to ledger drill-down, per resolved decision 4.

## Templates

### `templates/profile.html` — full rewrite
Head block: Inter font link, `nocturne.css`, `dashboard.css` (new — see
below). No Chart.js `<script>`.

Body, top to bottom (see README §"Layout" for exact markup/measurements):
1. `{% include "_dashboard_sidebar.html" %}` (rewritten, see below)
2. Header row: greeting `h1` + live subline, inert search-shaped button,
   "+ Add expense" button
3. Assistant bar: input, "Scan receipt", "Ask", four suggestion chips
4. Filter row: four preset pills + custom date range (existing behavior,
   restyled)
5. Inline add-expense row (hidden by default, toggled by "+ Add expense")
6. Summary tiles: Net worth (2-column span, placeholder sparkline, from
   `get_net_worth`) + Balance/Debt/Invested tiles (caret dropdown replacing
   today's `<select>`, placeholder mini-sparkline, from `get_accounts`
   grouped by type — same data plumbing as spec 15, new markup)
7. Insight cards row: three empty-state cards (from the `insights=[]`
   placeholder)
8. Charts row: monthly bar chart + category donut, both inline SVG built by
   `dashboard.js` from `monthly_totals` / `category_breakdown`
9. Budgets + Goals row: two empty-state cards (from `budgets=[]`/`goals=[]`)
10. Ledger: table with pill category badges (clickable → sets `category`
    drill-down), search input (`q`), removable drill-down chip, branching
    empty-state copy per README §"Ledger"

Scripts block loads `dashboard.js` only.

### `templates/_dashboard_sidebar.html` — full rewrite
Per README §"Sidebar": brand mark, **Money** group (Dashboard active →
`url_for('profile')`, Accounts → `url_for('accounts')`, Ledger/Budgets/Goals
inactive — no route yet), **Workspace** group (Insights/Cards/Reports,
inactive), bottom theme toggle + user chip (initials, name, plan label) +
sign-out. No "Soon" badges (resolved decision 7). Wrapper keeps
`class="profile-sidebar"` for continuity with anything outside this page
that might reference it (nothing currently does, but it costs nothing to
keep the hook).

### `templates/_chat_drawer.html`
Not modified in this sub-project.

## Files to change
- `app.py` — `profile()`: read `request.args.get('category')`, validate
  against `CATEGORIES` (invalid/unknown value treated as absent, same
  fallback style as invalid dates), pass `category=drill_category or None`
  to `get_recent_transactions`, and pass `drill_category`, `budgets=[]`,
  `goals=[]`, `insights=[]` to the template
- `database/queries.py` — `get_recent_transactions` gains the `category`
  parameter as described above
- `templates/profile.html` — full rewrite (see above)
- `templates/_dashboard_sidebar.html` — full rewrite (see above)
- `templates/base.html` — remove the Tailwind CDN `<script>` and
  `tailwind.config` block; no other change
- `static/js/chat.js` — add the minimal hook needed for the assistant bar to
  open the drawer and submit text (exact shape decided at plan/implementation
  time — read the current file first); no visual/behavioral change to the
  drawer itself
- `static/js/dashboard.js` — full rewrite: drop `wireBalanceCard()`'s
  `<select>`-based wiring and Chart.js calls; add tile caret-dropdown
  wiring, inline SVG bar/donut chart rendering from the existing JSON
  data attributes, drill-down click handling (sets `category` via
  `url_for`-style link navigation, consistent with how preset pills already
  navigate), inline add-expense toggle + client validation + `POST
  /api/expenses`, toast, and assistant-bar → chat-drawer wiring
- `CLAUDE.md` — the "Tailwind CDN" exception line added by spec 15 is
  removed (Tailwind is no longer used anywhere in the app once this ships);
  restate "Vanilla JS only" for CSS authoring too, without a Tailwind
  exception

## Files to create
- `static/css/nocturne.css` — the Nocturne token sheet, copied from
  `design_handoff_dashboard_redesign/tokens/nocturne.css` verbatim (fix only
  the internal comment's `readme.md` cross-reference, which refers to files
  outside this repo)
- `static/css/dashboard.css` — replaces `static/css/profile.css` (deleted).
  Component styles for the sidebar, header, assistant bar, filter row,
  tiles, insight/budget/goal cards, charts, and ledger — hand-written CSS
  built on `nocturne.css`'s tokens, per README measurements. Keeps the
  `--cat-<name>` and adds `--cat-<name>-text` custom properties (read by
  `dashboard.js`'s `categoryColor()`, unchanged lookup mechanism) mapped to
  the README's category-color table:
  `Food→--color-accent-300/--color-accent-200`,
  `Transport→--color-accent-400/--color-accent-200`,
  `Bills→--color-accent-500/--color-accent-300`,
  `Health→--color-accent-600/--color-accent-300`,
  `Entertainment→--color-accent-700/--color-accent-300`,
  `Shopping→--color-neutral-500/--color-neutral-300`,
  `Other→--color-neutral-700/--color-neutral-300`

## Files to delete
- `static/css/profile.css` (superseded by `static/css/dashboard.css`)

## New dependencies
None added. Tailwind CDN and Chart.js CDN are both **removed** — this spec
is a net reduction in external dependencies. `requirements.txt` is
unaffected (both were `<script>` tags, never pip packages).

## Rules for implementation
- Every rendered value that already has a Python-side format
  (`₹{value:,.2f}`, date formatting) keeps that formatting — no
  template-side reformatting
- Parameterized queries only — the new `category` clause in
  `get_recent_transactions` never string-formats the value into SQL
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()`, unchanged
- All templates extend `base.html`
- No inline `<style>` blocks — everything in `nocturne.css` / `dashboard.css`
- Category names/colors must exactly match `database/db.py → CATEGORIES`
  (seven categories, same spelling/casing)
- `static/js/dashboard.js` and `static/js/chat.js` stay vanilla JS — no
  frameworks, no npm
- Currency must always display as ₹, never £ or $
- The donut, budget/goal/insight placeholders, and net-worth/tile figures
  must be computed from date-range-only queries — never from `q` or
  `category` (resolved decision 4); only `get_recent_transactions` for the
  ledger table takes those two params
- Placeholder sections (Budgets, Goals, Insights, sparklines) must render
  real empty-state markup (matching the visual card/SVG shell), not be
  omitted from the page — Sub-project C should only need to swap data, not
  add markup

## Tests to write / update

The following existing assertions are **intentionally invalidated** by this
redesign and must be updated, not preserved — the design explicitly changes
this copy/markup:

| File | Assertion | Why it changes |
|---|---|---|
| `tests/test_backend_connection.py` | `assert "Soon" in body` | Sidebar "Soon" pills are removed (resolved decision 7) — update to assert the new inactive-item markup instead |
| `tests/test_backend_connection.py` | `assert 'class="profile-sidebar ' in body` (trailing space, a Tailwind-utility-list artifact) | `dashboard.css` uses a single plain class with no trailing space — update to `assert 'class="profile-sidebar"' in body` |
| `tests/test_backend_connection.py` | `assert 'id="monthly-chart"'` / `'id="category-chart"'` (on `<canvas>`) | Charts become inline SVG, not Chart.js canvases — update to assert the new SVG containers' ids/classes instead |
| `tests/test_wealth_management.py` | `assert 'id="profile-balance-select"'` / `-debt-select` / `-investment-select` | The `<select>` KPI pattern is replaced by the caret-dropdown pattern — update to assert the new dropdown trigger/panel ids |
| `tests/test_06-date-filter-profile-page.py` | body text like `"Account Balance"` (still true — tile label unchanged) | Verify still passes with new markup; only fails if tile copy changes, which it shouldn't |

Before implementation, the plan must grep `templates/profile.html` and
`templates/_dashboard_sidebar.html` for every literal string/id/class the
test suite currently checks (`tests/test_backend_connection.py`,
`tests/test_06-date-filter-profile-page.py`, `tests/test_wealth_management.py`,
and any incidental profile-page assertions in `tests/test_add_expense.py`,
`tests/test_delete_expense.py`, `tests/test_edit_expense.py`,
`tests/test_ai_chat_interface.py`) and update each one to match the new
markup deliberately, rather than trying to preserve strings the design
intentionally changes.

New tests to add (new file `tests/test_16_dashboard_drill_down.py` or an
extension of `test_06-date-filter-profile-page.py`):

| Test | Input | Expected |
|---|---|---|
| Drill-down filters ledger only | seed 2 categories, `?category=Food` | `get_recent_transactions(..., category="Food")` returns only Food rows |
| Drill-down composes with search | `?category=Food&q=lunch` | only rows matching both |
| Drill-down does not affect summary/category-breakdown | `?category=Food` | `get_category_breakdown`/`get_summary_stats` totals unchanged vs. no `category` param (called without `category` in the route) |
| Invalid category falls back | `?category=NotARealCategory` | treated as absent, no crash, 200 |
| No `category` param | — | behaves exactly as before this step |

Plus: run the **full existing suite** and fix every failure caused by the
intentional markup/copy changes above (the "Preserve list" discipline from
spec 15 is replaced here by an explicit "this changed on purpose, update
the test" discipline, since Sub-project A is a deliberate copy/behavior
replacement, not a preserve-everything rewrite).

## Definition of done
- [ ] `/profile` visually matches the Nocturne design system: dark theme by
      default, Inter typography, the token values in
      `design_handoff_dashboard_redesign/tokens/nocturne.css`
- [ ] Sidebar matches README §"Sidebar" with no "Soon" pills
- [ ] Header, assistant bar, filter row, tiles, insight/budget/goal
      placeholders, charts, and ledger all render per README §"Layout"
- [ ] Monthly and category charts are hand-drawn inline SVG; Chart.js is
      fully removed from the page and its CDN script tag deleted
- [ ] Tile caret dropdowns, inline add-expense, ledger drill-down (server
      round-trip), search, toast, and light/dark theme toggle all work
- [ ] Assistant bar opens the existing chat drawer and submits typed text
      into the existing `/api/chat` flow, unmodified in appearance
- [ ] Command palette button is present but inert (Sub-project B)
- [ ] Budgets/Goals/Insights sections render real empty states, no
      fabricated data
- [ ] Sparklines render as non-interactive placeholders, no fabricated
      trend data
- [ ] No other page's appearance changed
- [ ] `CLAUDE.md` no longer mentions Tailwind as a sanctioned exception
- [ ] Full test suite passes with `LLM_API_KEY` unset, including the
      updated assertions and new drill-down tests listed above
