# Spec: Analytics and Advisor

## Overview
Step 13 gives the assistant real numbers to reason with and gives the profile
page a "Budget insights" card that needs no LLM at all. New aggregation
helpers in `database/queries.py` compute totals over a window, daily average,
month-over-month comparison, per-category month comparison and unusually
large transactions. `ai/insights.py` turns those into one to three
deterministic, rule-based insight lines rendered server-side on the profile.
The same helpers are exposed to the LLM as read-only tools in
`ai/tools/analytics.py`, and the system prompt gains advisor rules: fetch the
numbers before advising, cite them in ₹, recommend one to three concrete
cutbacks, never guess. The chat drawer can then answer "how am I doing this
month?" and "where should I cut back?" with grounded figures.

## Depends on
- Step 5: Backend routes for profile page (`get_summary_stats`,
  `get_category_breakdown`)
- Step 6: Date filter (`_user_date_filter`, `_months_ago` arithmetic)
- Step 10: AI Chat Interface (system prompt, `create_message` seam)
- Step 11: NL CRUD Agent (tool registry, tool loop, `refresh` flag)

## Routes
No new routes. The existing `GET /profile` route passes one additional
template variable, `insights`.

## Database changes
No database changes.

## Templates
- **Modify**: `templates/profile.html`
  - In `.profile-col-side`, above the "Category breakdown" card, add a
    `.profile-card.profile-insights` card with the title "Budget insights",
    `{% for i in insights %}<p class="profile-insight
    profile-insight-{{ i.level }}">{{ i.text }}</p>{% endfor %}`, and a
    small `.profile-insights-note` reading "Based on the last 30 days"
  - The card is independent of the date filter
- **Modify**: `static/css/profile.css`
  - `.profile-insights`, `.profile-insight`, `.profile-insights-note`
  - `.profile-insight-warn` — `--danger-light` background, `--danger` left
    border
  - `.profile-insight-good` — `--accent-2-light` background, `--accent-2`
    left border
  - `.profile-insight-info` — `--paper-warm` background, `--border` left
    border

## Files to change
- `database/queries.py` — add the five helpers below; every helper takes
  explicit ISO date strings or a `date` object so tests are deterministic
  - `get_window_total(user_id, date_from, date_to)` → float via
    `COALESCE(SUM(amount), 0)`
  - `get_daily_average(user_id, date_from, date_to)` → total divided by the
    inclusive day count; `0.0` when the window is empty or inverted
  - `get_month_comparison(user_id, today)` → `{"current_total",
    "previous_total", "change_pct", "current_from", "current_to",
    "previous_from", "previous_to"}`; current window is the 1st of the month
    to `today`, previous window is the full previous calendar month
    (`calendar.monthrange`); `change_pct` is an int rounded percentage and
    `None` when `previous_total` is 0
  - `get_category_month_comparison(user_id, today)` → list of `{"name",
    "current", "previous", "change_pct"}` for every category present in
    either month, sorted by `current` descending
  - `get_high_spend_transactions(user_id, date_from, date_to,
    multiplier=2.0, limit=5)` → transactions whose amount exceeds
    `multiplier` × the mean amount of the window, newest first; empty list
    when the window has fewer than 3 transactions; each item has `id`,
    `date`, `description`, `category`, `amount`, `window_mean`
- `ai/tools/__init__.py` — add `from ai.tools import analytics  # noqa: F401`
- `ai/prompts.py` — append `ADVISOR_RULES` to `CHAT_SYSTEM_PROMPT` (still a
  stable constant): when asked how the user is doing, for advice, or
  where to cut back, call an analytics tool first; quote the figures in ₹;
  give one to three specific, actionable suggestions tied to the largest or
  fastest-growing category; be encouraging, not judgmental; if there is not
  enough data, say so plainly
- `app.py` — import `build_budget_insights` from `ai.insights`; in
  `profile()` pass `insights=build_budget_insights(user_id, today)`
- `templates/profile.html`, `static/css/profile.css` — as above

## Files to create
- `ai/insights.py` (no LLM, no Flask)
  - `build_budget_insights(user_id, today)` → list of at most 3
    `{"level": "warn" | "good" | "info", "text": str}` built from the
    helpers above, checking rules in this priority order and stopping at 3:
    1. `change_pct >= 15` → warn "Spending is up {pct}% vs last month
       (₹{current} vs ₹{previous})."
    2. Top category is at least 40% of the last 30 days → warn
       "{Category} is {share}% of your spending in the last 30 days
       (₹{amount})."
    3. Any high-spend transactions in the last 30 days → info "{n} unusually
       large purchase(s), e.g. ₹{amount} on {description}."
    4. `change_pct <= -10` → good "Nice — spending is down {pct}% vs last
       month."
    5. No expenses in the last 30 days → info "No expenses logged in the
       last 30 days."
    6. Otherwise → good "Spending looks steady: ₹{daily_avg} a day on
       average."
  - All currency formatted with `f"₹{x:,.2f}"` inside this module
- `ai/tools/analytics.py` — read-only tools, every `input_schema` sets
  `additionalProperties: false`, registered with `mutating=False`
  - `PERIODS = ["last_7_days", "last_30_days", "this_month", "last_month"]`
  - `_today()` → `date.today()`, module-level so tests can monkeypatch
    `ai.tools.analytics._today`
  - `_period_bounds(period, today)` → `(date_from, date_to)` ISO strings
  - `get_spending_summary` — input `{period: enum(PERIODS)}` → `{period,
    date_from, date_to, total, transaction_count, daily_average,
    top_category, categories: [{name, amount, pct}]}` (wraps
    `get_summary_stats`, `get_daily_average`, `get_category_breakdown`)
  - `compare_months` — input `{}` → `get_month_comparison` merged with
    `{"categories": get_category_month_comparison(...)}`
  - `get_unusual_expenses` — input `{period: enum(PERIODS)}` →
    `{"transactions": get_high_spend_transactions(...)}`
  - `get_budget_insights` — input `{}` → `{"insights":
    build_budget_insights(...)}`

## New dependencies
No new dependencies (stdlib `calendar`, `datetime`, `json`).

## Rules for implementation
- All aggregation lives in SQL or Python inside `database/queries.py`;
  `ai/insights.py` and the tool handlers only call helpers
- The insights card is fully deterministic and renders with no API key
- Analytics tools are registered with `mutating=False`, so they never
  trigger a page refresh
- Every helper accepts `today` or the window explicitly; `date.today()` is
  called only in `app.py` and in `ai.tools.analytics._today()`
- `change_pct` is `None` (serialised as `null`) when the previous month is
  0 — never a division error, never infinity
- All ₹ text formatting happens in Python with `f"₹{x:,.2f}"`
- The system prompt remains free of dates and figures; numbers reach the
  model only through tool results
- An empty tool-schema input is `{"type": "object", "properties": {},
  "required": [], "additionalProperties": false}`
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Foreign keys PRAGMA must be enabled on every connection (already done in
  `get_db()`)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- Currency must always display as ₹ — never £ or $

## Tests to write
File: `tests/test_analytics_and_advisor.py`

Seed with `insert_expense` at fixed dates and pass a fixed
`today = date(2026, 9, 15)`; patch `ai.tools.analytics._today` for tool
tests.

### Unit tests
| Function | Input | Expected output |
|---|---|---|
| `get_window_total` | 3 rows inside the window, 1 outside | sum of the 3 |
| `get_window_total` | no rows | `0` |
| `get_daily_average` | ₹300 over a 3-day window | `100.0` |
| `get_daily_average` | `date_from > date_to` | `0.0` |
| `get_month_comparison` | ₹200 this month, ₹100 last month | `change_pct == 100`; bounds are `2026-09-01`–`2026-09-15` and `2026-08-01`–`2026-08-31` |
| `get_month_comparison` | nothing last month | `change_pct is None` |
| `get_month_comparison` | `today = date(2026, 1, 10)` | previous window is `2025-12-01`–`2025-12-31` |
| `get_category_month_comparison` | Food in both months, Bills only last month | two entries; Bills has `current == 0` |
| `get_high_spend_transactions` | amounts 10, 10, 10, 100 | returns only the 100 |
| `get_high_spend_transactions` | 2 rows | `[]` |
| `get_high_spend_transactions` | another user's large row in window | excluded |
| `build_budget_insights` | +50% month over month | first item is `warn`; text contains `%` and `₹` |
| `build_budget_insights` | no expenses | single `info` item |
| `build_budget_insights` | steady spending, no anomalies | a `good` item |
| `build_budget_insights` | many triggers at once | `len(result) <= 3` |
| `_period_bounds` | `"last_7_days"`, `today = 2026-09-15` | `("2026-09-09", "2026-09-15")` |
| `execute_tool` | `"get_spending_summary"`, `period="last_30_days"` | JSON with `total`, `daily_average`, `categories`, `date_from` |
| `execute_tool` | `"compare_months"` | JSON with `change_pct` (may be `null`) and `categories` |
| `execute_tool` | `"get_spending_summary"`, `period="yesterday"` | `is_error True` |
| `get_tool_definitions` | — | contains the four analytics names; `is_mutating` is `False` for each |

### Route tests
`GET /profile` — authenticated, seeded expenses:
- Returns 200; body contains "Budget insights" and at least one
  `profile-insight-` class
- Body contains `₹` inside the insights card

`GET /profile` — authenticated, brand-new user:
- Returns 200; body contains "No expenses logged"

`POST /api/chat` — authenticated, fake calls `get_spending_summary` then
replies:
- Returns 200 with `refresh: false`
- The `tool_result` JSON in `fake.calls[1]` contains `"total"`

`POST /api/chat` — authenticated, any message:
- `fake.calls[0]["system"][0]["text"]` contains the advisor wording (e.g.
  "cut back")

## Definition of done
- [ ] The profile shows a "Budget insights" card with one to three lines, with no API key required
- [ ] Adding a single very large expense makes a warn-level insight appear
- [ ] "How much did I spend this month?" gets a ₹ figure that matches the profile "This Month" stat
- [ ] "Where should I cut back?" gets one to three concrete suggestions tied to real categories
- [ ] A brand-new user asking for advice is told there isn't enough data yet
- [ ] Analytics questions never reload the page
- [ ] All tests in `tests/test_analytics_and_advisor.py` pass without `LLM_API_KEY`
