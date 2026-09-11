# Spec: Dashboard Redesign Nocturne Phase C

## Overview

This is Sub-project C — the last of the three-part Nocturne dashboard redesign described in
`design_handoff_dashboard_redesign/README.md` and decomposed in
`.claude/specs/16-dashboard-redesign-nocturne-phase-a.md`. Phases A and B shipped the full visual
system and interactivity for `/profile` (sidebar, shell, charts, command palette, chat drawer) while
deliberately leaving the Net worth sparkline, Insight cards, Budgets panel, and Goals panel as
flat/empty placeholders — `app.py`'s `profile()` route currently hardcodes `budgets=[], goals=[],
insights=[]` (`app.py:257`) and the net-worth tile's sparkline is a static flat `<polyline>`
(`templates/profile.html:113-114`). This phase adds the real backend behind all four: a `budgets`
table, a `goals` table (with a working "contribute" action), a `net_worth_snapshots` table feeding
`net_worth_series()`, and `ai/insights.py`'s two rule-based insights — then wires each into the
already-built markup so the empty states only show when a user genuinely has no data yet, never as
a permanent placeholder.

## Depends on

- `16-dashboard-redesign-nocturne-phase-a.md` — the dashboard shell, tiles grid, insights row,
  budgets/goals row markup, and `dashboard.css`/`dashboard.js` conventions this phase builds on.
- `14-wealth-management.md` — the `accounts` table and `get_net_worth`/`get_accounts` this phase's
  net-worth snapshotting sits alongside.
- `07-add-expense.md` — the `expenses` table this phase's budget/insight calculations read from.

## Scoping decisions (read before implementing)

1. **"Upcoming renewals" stays out of scope.** It requires recurring-expense detection, a concept
   the schema has no notion of. Phase A already shipped its permanent empty-state copy
   ("Recurring-expense tracking is coming in a future update.") — this phase does not touch it or
   invent a fake heuristic for it.
2. **Insights row markup must change from a single `{% for %}...{% else %}` loop to three
   independently-conditional cards.** Today ALL THREE cards share one Jinja `{% else %}` — the
   instant `insights` is non-empty, all three empty states vanish at once. That can't express "Top
   category has data, Budget headroom doesn't" simultaneously, which is exactly the state most users
   will be in. `ai/insights.py` returns a dict (`{"top_category": ..., "budget_headroom": ...}`,
   each `None` or a data dict) instead of a list, and the template gets one `{% if %}/{% else %}`
   block per card, each preserving the exact existing empty-state copy/classes byte-for-byte when
   its own key is `None`.
3. **Budgets are query-level CRUD, no new HTTP route.** The dashboard's budget rings
   (`design_handoff_dashboard_redesign/README.md`, "Budgets + Goals row") are read-only — no
   add/edit affordance is in the shipped design, and the sidebar's "Budgets" nav item is still a
   disabled stub reserved for a future dedicated page. Per `CLAUDE.md`'s "do not implement a stub
   route unless the active task explicitly targets that step," this phase adds `get_budgets` +
   `upsert_budget` + `delete_budget` in `queries.py` (so a future `/budgets` page has them ready)
   and seeds real rows via `seed_db()`, but adds no `/api/budgets` route.
4. **Goals get a real HTTP route.** The design's "＋ contribute" button is an interactive dashboard
   element that must actually persist progress, so `POST /api/goals/<int:goal_id>/contribute` is in
   scope (`design_handoff_dashboard_redesign/README.md` calls this out explicitly under "Backend
   work this design implies": "a goals table + a contribute endpoint for the goals panel").
5. **`net_worth_series()` is backed by a new `net_worth_snapshots` table, not fabricated trend
   data.** The `accounts` table only stores current balances, not history, so there is no way to
   reconstruct past net worth. Every account mutation (`insert_account`, `update_account`,
   `delete_account_by_id`) upserts a snapshot row for the current calendar month; querying the
   series forward-fills any month with no snapshot from the most recent earlier one (or `0` if the
   user has no snapshot at or before that month yet — e.g. before they ever added an account). This
   means a brand-new user's sparkline is a flat `₹0` line until they add their first account, then
   steps up — real data, never a fake upward trend.
6. **Only the Net worth tile's large sparkline is wired to real data.** The five small
   per-tile/per-account sparklines (Balance/Debt/Investment tiles and their dropdown rows) stay flat
   placeholders — the backend work list only calls for one series ("`net_worth_series(user_id)` ...
   for the sparkline"), and per-account historical tracking isn't in this schema at all.

## Routes

- `POST /api/goals/<int:goal_id>/contribute` — logged-in JSON endpoint. Adds ₹5,000 to the goal's
  `saved` amount, capped at `target`. Returns `401 {"error": ...}` if logged out, `404
  {"error": ...}` if the goal doesn't belong to the current user, else
  `200 {"saved": <float>, "target": <float>}`.

No other new routes. `GET /profile` is modified (not newly created) to pass real `budgets`, `goals`,
`insights`, and `net_worth_series` data instead of the current hardcoded empty values.

## Database changes

Three new tables in `database/db.py`'s `init_db()`:

```sql
CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    category TEXT NOT NULL CHECK (category IN
        ('Food', 'Transport', 'Bills', 'Health', 'Entertainment', 'Shopping', 'Other')),
    monthly_ceiling REAL NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, category),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
)

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    target REAL NOT NULL,
    saved REAL NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
)

CREATE TABLE IF NOT EXISTS net_worth_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    month TEXT NOT NULL,
    net_worth REAL NOT NULL,
    recorded_at TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, month),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
)
```

`category`'s `CHECK` list mirrors `CATEGORIES` in the same file, exactly as `accounts.type`'s
`CHECK` already mirrors `ACCOUNT_TYPES` — kept in sync by hand, matching that existing precedent.

`seed_db()` gains, for the demo user only, after the existing expense inserts: four budget rows
matching the README's mock ceilings (`Food` 8000, `Transport` 6000, `Bills` 7000, `Shopping` 5000)
and one goal row (`"Kyoto trip"`, target 150000, saved 45000) — the same trip name already referenced
by the assistant-bar suggestion chip shipped in Phase A ("Am I on track for the Kyoto trip?"), so the
seeded data matches copy that's already on the page.

## Templates

- **Modify:** `templates/profile.html` —
  - Net worth tile (`templates/profile.html:113-114`): add `data-series="{{ net_worth_series |
    tojson | forceescape }}"` to the sparkline `<svg>`, and `id="tile-networth-note"` to the
    `<p class="tile-note">` beneath the figure (so hovering the sparkline can swap its text and
    restore it on mouseleave, mirroring the existing monthly-chart hover pattern in
    `dashboard.js`).
  - Insights row (`templates/profile.html:223-244`): replace the single `{% for insight in insights
    %}...{% else %}` block with three independently-conditional cards keyed off
    `insights.top_category` and `insights.budget_headroom` (see Scoping decision 2); "Upcoming
    renewals" keeps its exact current empty-state markup, always.
  - Budgets panel (`templates/profile.html:246-260`): each `{% for b in budgets %}` row renders a
    ring (`<svg class="budget-ring-svg" viewBox="0 0 76 76">` with a track circle + an arc circle
    whose `stroke-dasharray`/`stroke-dashoffset` Jinja computes directly from `b.pct_used` — no JS
    needed for the static value, only a CSS transition for the mount animation), the category name,
    and `₹{{ b.spent }} / ₹{{ b.monthly_ceiling }}`.
  - Goals panel (`templates/profile.html:261-274`): each `{% for g in goals %}` row renders the
    name, `₹{{ g.saved }} of ₹{{ g.target }}`, a `data-goal-id="{{ g.id }}"` "＋" contribute button,
    and a progress bar (`<div class="goal-bar"><div class="goal-bar-fill" style="width: {{ g.pct
    }}%"></div></div>`).

## Files to change

- `database/db.py` — three new tables in `init_db()`; seed budgets/goal in `seed_db()`.
- `database/queries.py` — `get_budgets`, `upsert_budget`, `delete_budget`, `get_goals`,
  `insert_goal`, `contribute_to_goal`, `net_worth_series`, and a `_record_net_worth_snapshot`
  helper called from `insert_account`/`update_account`/`delete_account_by_id`.
- `app.py` — `profile()` passes real `budgets`, `goals`, `insights`, `net_worth_series`; new
  `POST /api/goals/<int:goal_id>/contribute` route.
- `templates/profile.html` — sections listed above.
- `static/css/dashboard.css` — ring/progress-bar styles, insight-card per-card empty state classes
  (reusing the existing `.insight-card-empty` styling, just applied per-card now), sparkline
  gradient/dot/hover styles for the net-worth tile.
- `static/js/dashboard.js` — net-worth sparkline rendering + hover (mirrors the existing
  `renderMonthlyChart` hover pattern), goal contribute button wiring (`fetch` +
  `showToast` + bar-width update, reusing the existing `showToast` helper).

## Files to create

- `ai/insights.py` — `get_insights(user_id, date_from, date_to)` returning
  `{"top_category": dict|None, "budget_headroom": dict|None}`. No LLM calls, no Flask imports;
  reads via `database.queries` functions only (mirrors `ai/tools/accounts.py`'s import style).
  - `top_category`: `None` unless the category breakdown for the given range has 2+ categories
    (matching the existing empty-state copy's own condition, "computed once you have spending in
    more than one category"); otherwise a dict with the top category's name, amount, and share.
  - `budget_headroom`: `None` unless the user has at least one budget row; otherwise the sum of all
    `monthly_ceiling`s minus this month's spend in those same categories, plus a same-pace
    projected month-end total (`spent_so_far / days_elapsed_this_month * days_in_month`).
- `tests/test_dashboard_redesign_nocturne_phase_c.py`

## New dependencies

No new dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs.
- Parameterised queries only — every new query in `queries.py` uses `?` placeholders.
- Passwords hashed with werkzeug — not applicable, no auth code is touched.
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html` (unchanged — only `profile.html`'s content block changes).
- `category` CHECK constraint values must match `CATEGORIES` in `database/db.py` exactly, in the
  same file, following the `accounts.type`/`ACCOUNT_TYPES` precedent.
- `ai/insights.py` must not import Flask or any LLM provider SDK — it may import
  `database.queries` and `database.db` directly, exactly like `ai/tools/accounts.py` does today.
- `POST /api/goals/<int:goal_id>/contribute`: `user_id` comes only from `session["user_id"]`,
  never from the request body; verify the goal belongs to that user (404 if not, mirroring
  `get_expense_by_id`'s / `get_account_by_id`'s `user_id`-scoped lookup pattern) before mutating it.
- `_record_net_worth_snapshot` must run inside the same `queries.py` functions that already mutate
  `accounts` (`insert_account`, `update_account`, `delete_account_by_id`), after their existing
  `commit()`, not as new logic in `app.py` or `ai/tools/accounts.py` — those callers must keep
  working unmodified.
- Every new SVG element follows the existing Phosphor-style convention already used across the
  dashboard: `stroke-width` 1.7–2, `stroke="currentColor"`, 24×24 viewBox for icons (rings and the
  sparkline have their own viewBoxes per the README's exact pixel specs: 76×76 rings, 320×64
  sparkline).
- Money in new markup keeps the app-wide `₹` + `toLocaleString('en-IN')` (JS) /
  `f"₹{value:,.2f}"` (Python) convention already used everywhere else on this page.

## Tests to write

File: `tests/test_dashboard_redesign_nocturne_phase_c.py`

### Unit tests

| Function | Input | Expected output |
|---|---|---|
| `get_budgets(user_id)` | one budget row, `monthly_ceiling=100`, and one expense of `40` this month in that category | one dict with `category`, `monthly_ceiling=100`, `spent=40` |
| `upsert_budget(user_id, category, monthly_ceiling)` | called twice for the same `(user_id, "Food")` with `100` then `150` | `get_budgets` shows exactly one `Food` row with `monthly_ceiling=150` |
| `get_goals(user_id)` | one inserted goal `("Trip", target=1000, saved=200)` | one dict with `name="Trip"`, `target=1000`, `saved=200` |
| `contribute_to_goal(goal_id, user_id, amount=5000)` | goal with `target=1000, saved=200` | `saved` becomes `1000` (capped), not `5200` |
| `net_worth_series(user_id, months=3)` | no accounts ever created for this user | 3 buckets, each `net_worth == 0` |
| `net_worth_series(user_id, months=3)` | one account inserted this month with `balance=500` | the current month's bucket is `500`; earlier buckets are `0` |
| `ai.insights.get_insights(user_id, date_from, date_to)` | only one category of spending in range | `result["top_category"] is None` |
| `ai.insights.get_insights(user_id, date_from, date_to)` | two categories of spending, no budgets | `result["top_category"]` is a dict; `result["budget_headroom"] is None` |
| `ai.insights.get_insights(user_id, date_from, date_to)` | one budget row, some spend this month in that category | `result["budget_headroom"]` is a dict whose headroom equals `monthly_ceiling - spent` |

### Route tests

`POST /api/goals/<id>/contribute` — unauthenticated:
- `401 {"error": ...}`.

`POST /api/goals/<id>/contribute` — authenticated, goal belongs to a different user:
- `404`.

`POST /api/goals/<id>/contribute` — authenticated, own goal, `saved` well below `target`:
- `200`; JSON `saved` increased by exactly `5000`; re-fetching via `get_goals` confirms the DB row
  changed.

`POST /api/goals/<id>/contribute` — authenticated, own goal, `saved` within `5000` of `target`:
- `200`; JSON `saved` equals `target` exactly (capped, not overshot).

`GET /profile` — authenticated, demo user (has seeded budgets + goal from `seed_db()`):
- `200`; response body contains the seeded goal's name (`"Kyoto trip"`) and does **not** contain the
  budgets panel's empty-state copy (`"No budgets set yet"`).

## Definition of done

- [ ] `pytest` passes, including every test above.
- [ ] A fresh demo login shows real budget rings (not "No budgets set yet") and a real goal row (not
      "No goals yet") on `/profile`, matching the seeded data.
- [ ] Clicking a goal's "＋" button adds ₹5,000 to its progress bar (capped at the target), shows a
      toast, and persists across a page reload.
- [ ] The Net worth tile's large sparkline reflects real `net_worth_series` data: flat at ₹0 for a
      brand-new user with no accounts, stepping up in the month an account is added, and hovering it
      updates the note line to that month's value before reverting on mouseleave.
- [ ] The "Top category" and "Budget headroom" insight cards show real computed values once their
      respective data exists (2+ categories in range; at least one budget row), and still show their
      original empty-state copy when it doesn't — independently of each other.
- [ ] "Upcoming renewals" is untouched and still shows its original empty-state copy.
- [ ] No other page's visuals or behavior changed.
