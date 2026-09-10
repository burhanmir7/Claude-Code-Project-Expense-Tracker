# Spec: Wealth Management

## Overview
Step 14 widens Spendly from expenses to net worth. A new `accounts` table
stores balances for a user's savings, debt and investment accounts — just the
current balance and when it was last updated, no per-account ledger. Users
manage accounts through conventional Flask pages (`/accounts`, add, edit,
delete) that follow the Add / Edit Expense form pattern exactly. Net worth
(savings + investments − debts) appears as a fourth stat tile on the profile
and as a summary on the Accounts page. The assistant gets read tools to list
accounts and report net worth, plus write tools to add an account or update a
balance ("my savings are now 1.2 lakh"), and every chat turn's context block
carries a one-line net-worth snapshot so simple questions need no tool call.

## Depends on
- Step 7: Add Expense (form template pattern, 400 re-render with retained
  values)
- Step 8: Edit Expense (pre-filled edit form, 404 on ownership failure)
- Step 9: Delete Expense (POST-only delete with `confirm()`)
- Step 10: AI Chat Interface (`CONTEXT_PROVIDERS` hook in `ai/chat.py`)
- Step 11: NL CRUD Agent (tool registry, `refresh` flag)

## Routes
- `GET /accounts` — list accounts grouped by type with a net-worth summary —
  logged-in only
- `GET /accounts/add` — render the add-account form — logged-in only
- `POST /accounts/add` — validate and create; 400 re-render on error, 302 to
  `/accounts` on success — logged-in only
- `GET /accounts/<int:id>/edit` — render the pre-filled form; 404 if not
  owned — logged-in only
- `POST /accounts/<int:id>/edit` — validate and update; 400 / 404 / 302 —
  logged-in only
- `POST /accounts/<int:id>/delete` — delete; 404 if not owned; 302 to
  `/accounts` — logged-in only

View function names: `accounts`, `add_account`, `edit_account`,
`delete_account`. `GET /profile` gains a "Net worth" stat tile (no new
route).

## Database changes
Add to `database/db.py`:

```python
ACCOUNT_TYPES = ["savings", "debt", "investment"]
```

and to `init_db()`, after `chat_messages`:

```sql
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('savings', 'debt', 'investment')),
    balance REAL NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
)
```

`balance` is always a non-negative magnitude; the debt sign is applied only
in the net-worth calculation. Trade-off: storing signed balances would
simplify the SUM but makes the form confusing ("enter −5000 for a loan"), so
it is rejected.

## Templates
- **Create**: `templates/accounts.html`
  - Extends `base.html`; `{% block head %}` links `css/accounts.css`
  - `.accounts-section > .accounts-container`
  - Summary card with three figures — Assets, Debts, Net worth — where a
    negative net worth carries `.accounts-networth-negative` (uses
    `--danger`)
  - Table with columns Name / Type / Balance / Updated / Actions; the type
    cell is a badge `.accounts-type .accounts-type-{{ a.type }}`; Actions
    holds an Edit link to `url_for('edit_account', id=a.id)` and a
    `<form method="POST" action="{{ url_for('delete_account', id=a.id) }}"
    class="delete-form" onsubmit="return confirm('Delete this account?')">`
  - `{% else %}` empty-state row "No accounts yet."
  - "Add account" link with `.btn-primary` to `url_for('add_account')`
- **Create**: `templates/add_account.html`
  - `.auth-section` form pattern; `action="{{ url_for('add_account') }}"`
  - `name` text input, `maxlength="60"`, `value="{{ name or '' }}"`
  - `type` `<select>` built from `account_types` with a disabled
    placeholder, `{% if type == t %}selected{% endif %}`
  - `balance` number input, `step="0.01"`, `min="0"`,
    `value="{{ balance or '' }}"`
  - `.btn-submit` "Add Account" and `.btn-cancel` to `url_for('accounts')`
- **Create**: `templates/edit_account.html`
  - Same fields pre-filled from `account`; `action="{{ url_for(
    'edit_account', id=account.id) }}"`; submit "Save Changes"
- **Modify**: `templates/profile.html`
  - A fourth stat tile with `icon == "bank"`; add an
    `{% elif stat.icon == "bank" %}` SVG branch; the tile's value links to
    `url_for('accounts')`
- **Modify**: `templates/base.html`
  - Add `<a href="{{ url_for('accounts') }}">Accounts</a>` inside the
    authenticated branch of the nav, before "Add Expense"
- **Modify**: `static/css/profile.css`
  - `.profile-stats` grid becomes `repeat(auto-fit, minmax(160px, 1fr))` so
    four tiles fit

## Files to change
- `database/db.py` — `ACCOUNT_TYPES` and the `accounts` DDL
- `database/queries.py`
  - `get_accounts(user_id)` → list of `{"id", "name", "type", "balance",
    "updated_at"}` ordered by `type, name`
  - `get_account_by_id(account_id, user_id)` → dict or `None`
  - `insert_account(user_id, name, account_type, balance)` → lastrowid
  - `update_account(account_id, user_id, name, account_type, balance)` →
    rowcount; sets `updated_at = datetime('now')`
  - `delete_account_by_id(account_id, user_id)` → rowcount
  - `get_net_worth(user_id)` → `{"assets", "debts", "net_worth",
    "account_count"}` using `SUM(CASE WHEN type = 'debt' THEN balance ELSE
    0 END)` and the complementary asset sum; all zeros when there are no
    accounts
- `app.py`
  - Import `ACCOUNT_TYPES` from `database.db` and the six helpers from
    `database.queries`
  - Four account routes under a new `# Account routes` banner, following
    the expense routes' shape (auth guard, `rerender` closure returning 400,
    `abort(404)` after `get_account_by_id` returns `None`)
  - Validation: `name` required and ≤ 60 characters; `type` in
    `ACCOUNT_TYPES`; `balance` parses as float and is ≥ 0
  - `profile()` appends the tile: `{"label": "Net worth",
    "value": f"₹{net['net_worth']:,.2f}", "note": f"{net['account_count']}
    accounts", "icon": "bank"}`
- `ai/tools/__init__.py` — add `from ai.tools import accounts  # noqa: F401`
- `ai/prompts.py` — append one paragraph: accounts hold current balances,
  not transactions; savings and investments are assets, debts reduce net
  worth; confirm which account the user means (by name) before updating a
  balance
- `templates/profile.html`, `templates/base.html`, `static/css/profile.css`
  — as above

## Files to create
- `templates/accounts.html`, `templates/add_account.html`,
  `templates/edit_account.html`
- `static/css/accounts.css` — class prefix `accounts-`; tokens only;
  `.accounts-type-savings` uses `--accent-light` / `--accent`,
  `.accounts-type-investment` uses `--accent-2-light` / `--accent-2`,
  `.accounts-type-debt` uses `--danger-light` / `--danger`
- `ai/tools/accounts.py`
  - `_validate_account_fields(name, account_type, balance)` → error message
    or `None`, same rules as the routes
  - `list_accounts` — input `{}` → `{"accounts": [...], "net_worth":
    {...}}`
  - `get_net_worth` — input `{}` → the `get_net_worth` dict
  - `add_account` — input `{name: string, type: enum(ACCOUNT_TYPES),
    balance: number}` — mutating
  - `update_account_balance` — input `{account_id: integer, balance:
    number}` — mutating; not found → `is_error`
  - No delete tool. Trade-off: keeps the destructive surface limited to
    expenses, where confirmation semantics were designed in Step 11;
    account removal is rare and stays UI-only
  - `net_worth_context(user_id) -> str | None` — returns "Net worth
    snapshot: assets ₹X, debts ₹Y, net worth ₹Z across N accounts." or
    `None` when the user has no accounts; the module appends it to
    `ai.chat.CONTEXT_PROVIDERS` at import time so this step never edits
    `ai/chat.py`

## New dependencies
No new dependencies.

## Rules for implementation
- Every account query is scoped by `user_id`; edit and delete return 404
  after `get_account_by_id` returns `None`
- Balance is stored as a non-negative magnitude; net worth is computed in
  SQL as assets minus debts
- Validation failures re-render with status 400 and retain the submitted
  values
- The net-worth tile and the Accounts page render with no API key
- `net_worth_context` is registered by appending to
  `ai.chat.CONTEXT_PROVIDERS` when `ai.tools.accounts` is imported; it must
  return `None` (not an empty string) when the user has no accounts so the
  line is omitted from the context block
- Mutating account tools set `refresh: true` exactly like expense tools
- Account type is stored lowercase and shown with the `|capitalize` filter
- The type badge and summary colours use tokens only
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Foreign keys PRAGMA must be enabled on every connection (already done in
  `get_db()`)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- Currency must always display as ₹ — never £ or $

## Amendment (post-dashboard-redesign)

Written after the profile-page dashboard redesign shipped, when this step was
actually implemented. Supersedes the affected parts of "Templates" and
"Files to change" above:

- No separate "Net worth" stat tile. Instead, the dashboard's existing
  `stats[0]` "Total Spent" KPI card is replaced by a richer
  `.profile-balance-card`: a bank icon, "Account Balance" title, a
  three-dot menu (Add account / Manage accounts), a balance figure, and a
  `<select>` of "All Accounts" plus each account by name. Selecting an
  account shows its raw balance; selecting "All" shows the raw sum of every
  account's balance (not assets-minus-debts — that net-worth figure still
  lives on the dedicated `/accounts` page's summary card via
  `get_net_worth`). No month-over-month trend indicator: the data model
  intentionally has no balance history/ledger (see "Database changes"
  above), so a real trend can't be computed; this stays out of scope.
- All accounts' `{id, name, balance}` are embedded on `/profile` as a
  `data-accounts` JSON attribute (the same pattern `dashboard.js` already
  uses for chart data), and a small vanilla-JS handler swaps the displayed
  number on `<select>` change with no new API endpoint or route.
- Nav link placement: the dashboard redesign split navigation into two
  surfaces that didn't exist when this spec was written. "Accounts" is
  added to both `templates/base.html`'s top nav (used by `/accounts` and
  its add/edit pages, which still follow the pre-redesign
  `base.html`-extending form pattern) and `templates/_dashboard_sidebar.html`
  (used by `/profile`), instead of only `base.html` as originally written.

## Amendment 2 (dashboard card split by type, and a delete tool)

Written after further dashboard iteration and an explicit follow-up request
to expose account deletion through chat:

- The single `.profile-balance-card` above was split into four cards, one
  per account type plus net worth: **Account Balance** (savings only),
  **Debt**, **Total Investment**, and **Net Worth** — replacing the KPI
  row's "Total Spent", "Monthly Expenses", "Total Investment", and "Goal"
  slots respectively. Each of the first three has the dropdown-selector
  behaviour described in Amendment 1, scoped to that one type; "All
  Accounts"/"All Debts"/"All Investments" is the raw sum within that type,
  never assets-minus-debts. Net Worth has no dropdown (it is a single
  aggregate figure, not a per-account one) and instead shows
  `get_net_worth`'s `net_worth` figure, styled red when negative, with an
  account-count note. `static/js/dashboard.js` wires all such cards
  generically by looping over every `.profile-balance-card` and resolving
  each one's value/select/menu elements via `card.querySelector(...)`
  rather than by hardcoded IDs or array indices, so adding another
  type-scoped card later needs no JS changes.
- **Supersedes the "No delete tool" decision above.** `ai/tools/accounts.py`
  now also registers `delete_account` (input `{account_id}`, mutating),
  following the exact same prompt-level confirm-before-delete pattern as
  Step 11's `delete_expense`: its description text requires the model to
  restate the account (name, type, balance) and get an explicit yes before
  calling it. `ai/tools/__init__.py`'s registration order is now
  `list_expenses, add_expense, update_expense, delete_expense,
  list_accounts, get_net_worth, add_account, update_account_balance,
  delete_account`.

## Tests to write
File: `tests/test_wealth_management.py`

### Unit tests
| Function | Input | Expected output |
|---|---|---|
| `insert_account` | `user_id=1, "HDFC Savings", "savings", 50000` | row exists; returns an int id |
| `get_accounts` | 2 accounts for user 1, 1 for user 2 | 2 dicts for user 1, ordered by type then name |
| `get_account_by_id` | own id | dict with `name`, `type`, `balance` |
| `get_account_by_id` | another user's id | `None` |
| `update_account` | own id, new balance | balance updated; `updated_at` is not earlier than `created_at` |
| `update_account` | another user's id | rowcount 0; row unchanged |
| `delete_account_by_id` | own id | rowcount 1; row gone |
| `get_net_worth` | savings 50000, investment 20000, debt 30000 | `assets == 70000`, `debts == 30000`, `net_worth == 40000`, `account_count == 3` |
| `get_net_worth` | no accounts | all zeros |
| `_validate_account_fields` | name of 61 characters | error message |
| `_validate_account_fields` | balance `-1` | error message |
| `execute_tool` | `"add_account"`, valid input | row for `user_id`; `(json, False)` |
| `execute_tool` | `"add_account"`, type `"crypto"` | `is_error True` |
| `execute_tool` | `"update_account_balance"`, another user's id | `is_error True`; balance unchanged |
| `execute_tool` | `"get_net_worth"` | JSON with `net_worth` |
| `net_worth_context` | user with accounts | string containing `Net worth snapshot` and `₹` |
| `net_worth_context` | user without accounts | `None` |
| `build_turn_context` | user with accounts | result contains "Net worth snapshot" |
| `get_tool_definitions` | — | contains `list_accounts`, `get_net_worth`, `add_account`, `update_account_balance`; no `delete_account` tool |

### Route tests
`GET /accounts` — unauthenticated:
- Redirects to `/login` (302)

`GET /accounts` — authenticated, seeded accounts (50000 / 20000 / 30000):
- Returns 200; body contains the account names, `₹40,000.00`, and Edit /
  Delete controls

`GET /accounts` — authenticated, no accounts:
- Returns 200; body contains the empty-state text

`POST /accounts/add` — authenticated, valid:
- Redirects to `/accounts` (302); row exists in `accounts`

`POST /accounts/add` — authenticated, missing name:
- Returns 400; body contains an error message

`POST /accounts/add` — authenticated, type `"crypto"`:
- Returns 400; submitted name is retained in the form

`POST /accounts/add` — authenticated, balance `-1`:
- Returns 400

`GET /accounts/<id>/edit` — authenticated, another user's account:
- Returns 404

`POST /accounts/<id>/edit` — authenticated, valid:
- Redirects (302); DB reflects the new values

`POST /accounts/<id>/delete` — authenticated, own account:
- Redirects (302); row gone

`POST /accounts/<id>/delete` — authenticated, another user's account:
- Returns 404; row remains

`GET /accounts/<id>/delete` — any user:
- Returns 405

`GET /profile` — authenticated, with accounts:
- Body contains "Net worth" and the ₹ figure; nav contains "Accounts"

`POST /api/chat` — authenticated, fake calls `update_account_balance` then
replies:
- Returns 200 with `refresh: true`; balance updated in DB
- `fake.calls[0]["context_text"]` contains "Net worth snapshot"

`POST /api/chat` — authenticated, user with no accounts:
- `fake.calls[0]["context_text"]` does not contain "Net worth snapshot"

## Definition of done
- [ ] `/accounts` lists accounts grouped by type with assets, debts and net worth in ₹
- [ ] Add / edit / delete account work with the same validation and 404 behaviour as expenses
- [ ] The profile shows a "Net worth" tile linking to `/accounts`; the nav has "Accounts"
- [ ] "What's my net worth?" is answered from the context snapshot; "list my accounts" uses the tool
- [ ] "Update my HDFC savings to 60000" changes the balance and the page refreshes
- [ ] A user cannot read or change another user's accounts via the UI or the chat
- [ ] All tests in `tests/test_wealth_management.py` pass without `LLM_API_KEY`
