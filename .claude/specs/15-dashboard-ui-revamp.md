# Spec: Dashboard UI Revamp (Phase 1)

## Overview
Restyles the `/profile` dashboard to match a reference "Expensify"-style
design — polished KPI cards with colored icon badges, a lighter/airier
sidebar and header, sharper chart and table cards, and a new working search
box — using Tailwind CDN utility classes instead of hand-written CSS for
this page. Every other page (accounts, expense forms, auth, landing, the
chat drawer) keeps its current look; this is a scoped first phase, not a
site-wide rewrite. No backend feature changes beyond a new transaction
search filter. All four existing account-type KPI cards (Account Balance,
Debt, Total Investment, Net Worth) keep their exact current behavior
(dropdown selectors, three-dot menus, `refresh` semantics) — only their
visual styling changes.

## Depends on
- Step 14: Wealth Management (the four account-type KPI cards and their
  `data-accounts` / `wireBalanceCard()` JS wiring, which this step must not
  functionally change)
- The existing dark/light theme toggle (`static/js/main.js`, which sets
  `data-theme` on `<html>`) — Tailwind's dark variant must key off the same
  attribute, not `prefers-color-scheme`, so the existing toggle keeps
  working unchanged

## Decisions from brainstorming
- **Tech stack**: Tailwind CDN (`<script src="https://cdn.tailwindcss.com">`)
  + Chart.js (already in use). No npm, no build step, no new pip packages.
  This is a deliberate, explicit exception to `CLAUDE.md`'s current
  "Vanilla JS only" line for CSS *authoring* — Tailwind is a utility CSS
  framework, not a JS framework, and ships no interactive behavior of its
  own; all interactivity remains hand-written vanilla JS. `CLAUDE.md`'s
  tech-constraints section must be updated to say so explicitly as part of
  this step, so the exception isn't just implicit in this spec.
- **Phasing**: dashboard (`/profile`) only in this step. Other pages are
  visually inconsistent with the new look until a future Phase 2 spec
  propagates it — an accepted, explicit trade-off.
- **Theming**: keep the dark/light toggle. Tailwind's `darkMode` strategy is
  configured as `['selector', '[data-theme="dark"]']` to match the existing
  toggle exactly (see `static/js/main.js`), not the `media` strategy.
- **Brand color**: keep Spendly's existing green accent (`--accent`) as the
  primary brand color — do not adopt the reference image's blue/indigo
  palette. The four KPI cards each get a distinct existing-or-new accent
  color for their icon badge (see "New color tokens" below), the way the
  reference uses a different hue per card, without rebranding the app.
- **Search**: the header gains a real (not decorative) search box that
  filters the "Recent transactions" table by description or category,
  composing with the existing date-range filter — implemented as a plain
  GET form (no new JS), consistent with the existing custom date-range
  filter form's pattern.
- **No fabricated data**: the reference's "Sub Category" and "Mode" (payment
  method) transaction-table columns don't exist in Spendly's data model.
  They are not added; the table keeps its current columns (Date,
  Description, Category, Amount, Actions), restyled only.

## Routes
No new routes. `GET /profile` gains one new optional query parameter:
- `q` (string, optional) — filters recent transactions by description or
  category (case-insensitive substring match); composes with `date_from`/
  `date_to` exactly like they compose with each other today (all provided
  filters apply together; `q` alone with no dates means "all time,
  matching q")

## Database changes
None. No schema changes.

## New color tokens
Add to `static/css/style.css`'s `:root` (light) and `[data-theme="dark"]`
(dark) blocks, alongside the existing `--accent`/`--accent-2`/`--danger`
tokens — one new pair, for the Net Worth card's icon badge (the other three
cards reuse existing tokens: Account Balance → `--accent`, Debt →
`--danger`, Total Investment → `--accent-2`):
```css
/* light */
--accent-3: #2f6690;
--accent-3-light: #e6eef4;
/* dark */
--accent-3: #7fb3d9;
--accent-3-light: #1c2e3a;
```

## Files to change
- `CLAUDE.md` — amend the "Tech constraints" section to explicitly allow
  Tailwind CDN (CSS-only utility framework, no build step, no npm) as a
  named exception to "Vanilla JS only", and note that all interactivity
  stays hand-written vanilla JS
- `static/css/style.css` — add the `--accent-3`/`--accent-3-light` token
  pair (light and dark blocks)
- `templates/base.html` — add the Tailwind CDN `<script>` tag and an inline
  `tailwind.config` in `{% block head %}`'s shared parent markup (or a new
  always-loaded block), configuring:
  - `darkMode: ['selector', '[data-theme="dark"]']`
  - `theme.extend.colors` mapping semantic names to the existing CSS
    variables (e.g. `paper: 'var(--paper)'`, `paperCard: 'var(--paper-card)'`,
    `ink: 'var(--ink)'`, `inkMuted: 'var(--ink-muted)'`,
    `inkFaint: 'var(--ink-faint)'`, `border: 'var(--border)'`,
    `borderSoft: 'var(--border-soft)'`, `accent: 'var(--accent)'`,
    `accentLight: 'var(--accent-light)'`, `accent2: 'var(--accent-2)'`,
    `accent2Light: 'var(--accent-2-light)'`, `accent3: 'var(--accent-3)'`,
    `accent3Light: 'var(--accent-3-light)'`, `danger: 'var(--danger)'`,
    `dangerLight: 'var(--danger-light)'`) so Tailwind utilities
    (`bg-paperCard`, `text-ink`, `border-border`, etc.) automatically
    respect the existing light/dark tokens with no new dark-mode-specific
    classes needed for base colors
- `templates/profile.html` — full markup rewrite using Tailwind utility
  classes for layout, spacing, shadows, rounded corners, and typography.
  Every `id`, `data-*` attribute, `url_for()` call, Jinja variable
  reference, and every literal string checked by existing tests (see
  "Rules for implementation" — Preserve list) stays exactly as-is; only
  the presentation classes change. Adds the new search `<input name="q">`
  inside a `GET` form to `url_for('profile')` with hidden `date_from`/
  `date_to` inputs (pre-filled from `selected_from`/`selected_to`) so
  search composes with the date filter, following the same pattern as the
  existing custom-range filter form
- `templates/_dashboard_sidebar.html` — rewrite with icon+label nav items
  (inline SVGs matching the app's existing outline-icon style) styled with
  Tailwind utilities; every `href`/`url_for()` target and the literal
  `class="profile-sidebar"` on the wrapper element stay unchanged; "Soon"
  stub items keep the literal text "Soon"
- `static/css/profile.css` — remove the hand-written classes that
  `templates/profile.html` and `templates/_dashboard_sidebar.html` no
  longer use once replaced by Tailwind utilities (`.profile-kpi-*`,
  `.profile-balance-*`, `.profile-table*`, `.profile-chart*`,
  `.profile-filterbar*`, `.profile-chat-quickstart*`,
  `.profile-sidebar-*` link/section styles, etc.). The `--cat-*` category
  color custom properties at the top of the file are kept as-is —
  `static/js/dashboard.js`'s `categoryColor()` reads them directly via
  `getComputedStyle` and nothing about that changes
- `database/queries.py` — `get_recent_transactions(user_id, limit=10,
  date_from=None, date_to=None, search=None)` gains the `search` parameter;
  when provided, adds a parameterized `AND (description LIKE ? OR category
  LIKE ?)` clause with `%search%` on both sides, case-insensitive (SQLite's
  default `LIKE` behavior for ASCII)
- `app.py` — `profile()` reads `request.args.get('q', '').strip()`, passes
  it as `search=q or None` to `get_recent_transactions`, and passes
  `search_query=q` to the template so the box stays populated after
  submission (mirrors how `selected_from`/`selected_to` are already
  retained)

## Files to create
None.

## New dependencies
Tailwind CDN (`https://cdn.tailwindcss.com`), loaded via `<script>` tag —
no npm, no build step, no new `requirements.txt` entry. This is the one
named exception to `CLAUDE.md`'s pip/JS-framework constraints described
above.

## Rules for implementation
- **Preserve list** — the rewritten `templates/profile.html` and
  `templates/_dashboard_sidebar.html` must still produce, verbatim, every
  string the existing test suite checks for in the rendered body:
  - Literal `class="profile-sidebar"` on the sidebar wrapper, literal
    `class="navbar"` presence/absence tied to `hide_chrome`
  - `id="monthly-chart"`, `id="category-chart"` on the two chart canvases,
    with their existing `data-monthly`/`data-categories` attributes
    untouched
  - `id="profile-balance-select"`, `id="profile-debt-select"`,
    `id="profile-investment-select"` (each present only when that card has
    accounts, exactly as today), and the empty-state text "No accounts
    yet.", "No debts yet.", "No investments yet."
  - `id="profile-chat-quickstart-form"`, `id="profile-chat-quickstart-input"`
  - The text "Dashboard", "Soon", "Account Balance", "Debt", "Total
    Investment", every category name, and `href="/accounts"`
  - `src=".../js/chat.js"` and `src=".../js/dashboard.js"` script tags
  - All currency values keep Python-side `:,.2f}` comma formatting (no
    template-side reformatting)
- `static/js/dashboard.js` is not modified for the visual rewrite — its
  `wireBalanceCard()` scoped-`querySelector` wiring and chart rendering
  keep working unchanged as long as the ids/data-attributes above survive
- No inline `<style>` blocks — Tailwind utility classes in markup, plus
  `static/css/profile.css` for anything Tailwind utilities can't express
  (if anything remains after the rewrite)
- Currency must always display as ₹ — never £ or $
- Parameterized queries only — the new `search` clause in
  `get_recent_transactions` never string-formats the search term into SQL
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- All templates extend `base.html`

## Tests to write
No new test file — extend `tests/test_06-date-filter-profile-page.py`
(it already covers query-param-driven filtering of this exact page):

| Test | Input | Expected |
|---|---|---|
| Search matches description | seed an expense "Grocery run", `?q=grocery` | row appears in `get_recent_transactions(..., search="grocery")`; case-insensitive |
| Search matches category | `?q=Food` | rows with category Food returned; non-Food rows excluded |
| Search composes with date range | `?q=` + `date_from`/`date_to` both set | only rows matching both the term and the range are returned |
| Empty/absent `q` | no `q` param | behaves exactly as before this step (no regression) |
| No matches | `?q=zzzznomatch` | empty result, page still renders 200 with the existing zero-match empty state |

Plus: run the **full existing suite unmodified** and confirm all ~245
tests still pass against the rewritten templates — this is the primary
regression signal for the visual rewrite, since the tests check rendered
strings/ids, not CSS classes.

## Definition of done
- [ ] `/profile` visually matches the approved mockup direction: Style-A
      KPI cards (icon badge, value, trend/selector row), icon+label
      sidebar, header search box, restyled chart and table cards
- [ ] Dark mode still works via the existing toggle, with Tailwind
      utilities resolving to the correct dark tokens
- [ ] Searching the header box filters "Recent transactions" by
      description or category and composes with the date-range filter
- [ ] All four KPI cards' dropdown selectors, three-dot menus, and
      `refresh`-on-mutation behavior work exactly as before
- [ ] `CLAUDE.md` explicitly documents the Tailwind CDN exception
- [ ] Full existing test suite (~245 tests, plus the new search tests)
      passes with `LLM_API_KEY` unset
- [ ] No other page's appearance changed in this step
