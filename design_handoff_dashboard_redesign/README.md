# Handoff: Spendly dashboard redesign (`GET /profile`)

## Overview

A full UX and visual redesign of Spendly's dashboard — the page rendered by `templates/profile.html`
plus `templates/_dashboard_sidebar.html` and the chat drawer in `templates/_chat_drawer.html`.

The redesign keeps every capability the current page has (date presets and custom range, search,
account/debt/investment/net-worth summaries, monthly and category charts, the transaction table, the
AI drawer, receipt scan) and adds: a prominent assistant bar, a command palette, budget rings, goal
tracking, computed insight cards, category drill-down, a net-worth sparkline, inline expense entry,
per-account dropdowns on the summary tiles, and real empty states.

## About the design files

The files in `prototypes/` are **design references written in HTML** — prototypes that show intended
look and behaviour. They are **not production code to paste in**. They are authored as "Design
Components": a single HTML file with a template and a small React-flavoured logic class, rendered by
`support.js`. Your job is to **recreate the design inside Spendly's existing environment**, which per
`CLAUDE.md` is:

- Flask + Jinja2 templates extending `base.html` — no other web framework
- **Vanilla JS only** — no React, no jQuery, no npm. Tailwind CDN is the one sanctioned exception
- Page-specific CSS goes in a new `static/css/<page>.css` with a matching class prefix
- Page-specific JS goes in a new `static/js/<feature>.js`, loaded via `{% block scripts %}`
- All SQL lives in `database/queries.py`; routes in `app.py` only fetch and render

So: read the prototype for layout, tokens and behaviour; implement it as Jinja markup +
`static/css/dashboard.css` + `static/js/dashboard.js`. Do **not** port the React-style logic class —
rewrite the behaviour as vanilla event handlers.

## Fidelity

**High fidelity.** Colors, type sizes, spacing, radii, shadows and copy in the prototype are final.
Recreate them exactly. Every value comes from the Nocturne token sheet in `tokens/nocturne.css`.

## Files in this bundle

| Path | What it is |
|---|---|
| `prototypes/Spendly Dashboard - Redesign.dc.html` | **The target design.** All markup, tokens and behaviour. |
| `prototypes/Spendly Dashboard - Current.dc.html` | A faithful recreation of today's `/profile`, for before/after comparison. |
| `prototypes/support.js` | Runtime the two prototypes need to render locally. Not for production. |
| `tokens/nocturne.css` | The Nocturne stylesheet — token `:root` block plus `.btn`, `.tag`, `.input`, `.card`, `.table`, `.dialog` classes. |

To view a prototype: open the `.dc.html` file in a browser with `support.js` and `tokens/nocturne.css`
alongside it (adjust the stylesheet `<link>` path in the file's `<helmet>` block).

---

## Design tokens

Copy `tokens/nocturne.css` into `static/css/nocturne.css` and link it from `base.html`. It replaces the
`:root` block currently at the top of `static/css/style.css`. Every value below is already in it.

### Color

| Token | Value | Use |
|---|---|---|
| `--color-bg` | `#161826` | Page ground |
| `--color-surface` | `#232532` | Every card |
| `--color-text` | `#e9e9ed` | Body text |
| `--color-accent` | `#9184d9` | Lines, marks, outlines, focus ring. **Never a large fill.** |
| `--color-divider` | `color-mix(in srgb, #e9e9ed 16%, transparent)` | Rules, borders, table row lines |
| `--color-neutral-100…900` | `#f3f5fe` … `#292b31` | Surfaces, muted text (`-400`/`-500`), borders |
| `--color-accent-100…900` | `#f5f4ff` … `#2b2741` | Tints and tinted text |

Rules that matter:

- On this dark ground, **light ramp steps (100–300) carry text; dark steps (700–900) are fills and
  borders.** Getting this backwards fails contrast — it was a real defect during review.
- Muted text is `--color-neutral-400` / `--color-neutral-500`, never an alpha of the body color.
- Accent at paragraph size must be `--color-accent-300`, not `--color-accent`.

**Category colors** (used for the donut, legend swatches and the ledger tag borders):

| Category | Fill / swatch / border | Tag text |
|---|---|---|
| Food | `--color-accent-300` | `--color-accent-200` |
| Transport | `--color-accent-400` | `--color-accent-200` |
| Bills | `--color-accent-500` | `--color-accent-300` |
| Health | `--color-accent-600` | `--color-accent-300` |
| Entertainment | `--color-accent-700` | `--color-accent-300` |
| Shopping | `--color-neutral-500` | `--color-neutral-300` |
| Other | `--color-neutral-700` | `--color-neutral-300` |

The seven categories match `database/db.py → CATEGORIES` exactly.

### Type

Inter throughout, `--font-heading` and `--font-body` both `"Inter", system-ui, sans-serif`.
Headings are weight **500** — never bolder; hierarchy is size and space.

| Role | Size | Weight | Notes |
|---|---|---|---|
| Page title (`Good evening, Aditya`) | 26px | 500 | `letter-spacing: -0.02em` |
| Net worth figure | 34px | 600 | `-0.025em`, `tabular-nums` |
| Tile figure | 21px | 600 | `-0.02em`, `tabular-nums` |
| Card heading (`h2`) | 15px | 500 | |
| Body / table cell | 13.5px | 400 | |
| Secondary / meta | 12–12.5px | 400 | `--color-neutral-500` |
| Section eyebrow | 10.5–11px | 500 | uppercase, `letter-spacing: .08–.09em` |

All money uses `font-variant-numeric: tabular-nums` and `toLocaleString('en-IN')` grouping
(`₹1,78,700`). Amounts in the ledger keep two decimals; headline figures round.

### Spacing, radius, elevation

- Spacing scale is 0.7× dense: `--space-1` 2.8px through `--space-8` 22.4px.
- Radii: `--radius-sm` 4px (chips inside menus), `--radius-md` 8px (controls), `--radius-lg` 14px (cards).
  Pills use `999px`.
- Elevation: `--shadow-sm` (hairline edge only), `--shadow-md` (cards), `--shadow-lg` (drawer, palette,
  dropdowns). Never stack them.
- Card padding: `16px 18px` for large cards, `14px 15px` for the small tiles, `13px 15px` for insight cards.
- Grid gap between cards: `14px`. Vertical gap between page sections: `18px`.
- Main content padding: `22px 28px 64px`, `max-width: 1320px`.

### Interaction states

- `:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }` on everything.
- Hover tint on interactive rows and nav items:
  `background: color-mix(in srgb, var(--color-accent) 9–14%, transparent)`.
- Buttons are **outlined, not filled**: `.btn.btn-primary` is a 1px accent border on transparent.

---

## Layout

Two columns: `grid-template-columns: 196px minmax(0, 1fr)`.

### Sidebar (replaces `_dashboard_sidebar.html`)

`196px`, `padding: 20px 12px`, `border-right: 1px solid var(--color-divider)`, sticky full-height,
`display: flex; flex-direction: column; gap: 26px`.

1. Brand: 22px rounded square with a 1px accent border containing `◈`, then "Spendly" at 16px/500.
2. Group **Money** — eyebrow at 10px uppercase `--color-neutral-500`, then Dashboard (active),
   Accounts, Ledger, Budgets, Goals. Items are 13.5px, `padding: 7px 8px`, `--radius-md`, 15px icon,
   10px gap. Active item: `background: color-mix(in srgb, var(--color-accent) 14%, transparent)` with
   `--color-text`. Inactive: transparent with `--color-neutral-400`.
3. Group **Workspace** — Insights, Cards, Reports.
4. Bottom: theme toggle (icon swaps sun/moon with the label), then a user chip — 26px avatar circle on
   `--color-accent-800` with `--color-accent-200` initials, name at 12.5px, plan at 10.5px.

**Deliberate change from the current build:** the seven "Soon" pills are gone. Ship only what exists
and add nav entries as routes land — the current sidebar is 70% disabled items.

### Main column, top to bottom

**1. Header row** — flex, wrap, 16px gap.
- Left: `h1` greeting, then a 13px `--color-neutral-500` subline reading
  `"{n} transactions · ₹{total} out · selected range"` (live, recomputed on every filter change).
- Right: a search-shaped button (min-width 210px, 1px divider border, `--radius-md`) with a magnifier
  icon, "Search or jump to…", and a `⌘K` kbd chip — it **opens the command palette**, it is not an
  input. Then a `.btn.btn-primary` "＋ Add expense".

**2. Assistant bar** — full-width card, `--radius-lg`, `--color-surface`, `--shadow-sm` rising to
`--shadow-md` on focus (180ms).
- Row: 26px accent-outlined circle with `◈`; a borderless 14.5px input with placeholder
  `Ask Spendly anything — "how much did I spend on food in August?"`; a `.btn.btn-ghost`
  "Scan receipt" with a 15px scan icon; a `.btn.btn-primary` "Ask".
- Below: four suggestion chips (999px radius, 1px divider border, 12px):
  "What did I overspend on this month?", "Compare August to September",
  "Show every Bills transaction", "Am I on track for the Kyoto trip?".
- Enter or Ask opens the chat drawer and posts the question into it.

**3. Filter row** — four preset pills (This month / Last 3 months / Last 6 months / All time), a 1px
18px vertical divider, two `<input type="date">` separated by `→`, then a right-aligned 12px range
note. Active pill: 1px accent border, `color-mix(accent 16%)` background, `--color-text`. Changing
either date sets the preset to `custom` (no pill lit).

**4. Inline add-expense row** — hidden until "＋ Add expense" or the palette opens it. A card that
animates in (`translateY(6px)` → none, 220ms). Fields: Description (flex 2, min 150px), Amount ₹
(120px), Category `<select>` (150px, options from `CATEGORIES`), Date (150px), then Save and Cancel.
Labels are 10.5px uppercase eyebrows above each field. Save validates description + numeric amount,
prepends the row to the ledger with a highlight tint, and shows a toast.

**5. Summary tiles** — `grid-template-columns: repeat(auto-fit, minmax(168px, 1fr))`, 14px gap. The
net-worth card spans 2 tracks.

*Net worth card* — `--shadow-md`, `padding: 16px 18px`:
- Eyebrow "NET WORTH" + a 11.5px `--color-accent-300` delta ("▲ 5.4% this month")
- 34px figure
- A 12px note line that becomes `"{Month} 2026 · ₹{value}"` while hovering the sparkline
- A 320×64 SVG sparkline: gradient area fill (accent at 34% → 0% opacity), 1.8px accent polyline,
  a dot per point (r 2, growing to 4 on hover; unhovered dots drop to 0.3 opacity), and one invisible
  52px-wide hit rect per point driving the hover.

*Balance / Debt / Invested tiles* — `--shadow-sm`, `padding: 14px 15px`:
- Row: 24px icon square (1px `--color-accent-800` border, accent glyph), 12px label, a caret button
- 21px figure
- 56×16 mini sparkline + a 11.5px note
- **Caret opens an account dropdown** — absolutely positioned, `top: 42px`, inset 12px left/right,
  `--shadow-lg`, `--radius-md`, 4px padding, `sp-pop` 140ms. First option is "All balance / All debt /
  All invested" with the total; then one row per account showing name and its own amount. Selecting an
  account swaps the figure, the sparkline and the note; the caret rotates 180°. Outside click or
  Escape closes it. This is the modern equivalent of the current `profile-balance-select`.

  Data source: `get_accounts(user_id)` grouped by `type` (`savings` / `debt` / `investment`), same as
  the current route. Net worth from `get_net_worth(user_id)`.

**6. Insight cards** — `repeat(auto-fit, minmax(240px, 1fr))`, `--shadow-sm`. Each: a 26px circle on
`--color-accent-900` with an `--color-accent-300` icon, a 13px/500 title, a 12px body at
`--color-neutral-500`, line-height 1.45. The three are computed, not hardcoded:
- Top category — name, amount, share of total, transaction count
- Budget headroom — `₹{30000 − spent}` under ceiling, with the projected close
- Upcoming renewals — count and the three names/amounts

These belong in `ai/insights.py` (the rule-based, no-LLM module `CLAUDE.md` already reserves), fed to
the template by the route. No LLM call.

**7. Charts row** — `minmax(340px, 1.5fr) minmax(280px, 1fr)`.

*Monthly spending* (`--shadow-md`): header row with the `h2`, then a right-aligned 12px month label and
a 15px/600 amount that both track the hovered bar (defaulting to "Six months" and the total). A 620×190
SVG: four horizontal `--color-divider` grid lines; one bar group per month with `rx="4"`, max width
62px. Bar fill is `--color-accent-700` inside the selected range, `--color-neutral-800` outside, and
`--color-accent` on hover. Bars animate up from zero on mount — transition `y` and `height` over 550ms
`cubic-bezier(.2,.8,.2,1)`. Month label at y=184, 11px, `--color-neutral-500`.

*Where it goes* (`--shadow-md`): `h2` plus an 11.5px hint "Click a slice to filter the ledger". A
116px donut (outer r 52, inner r 34, drawn as arc paths starting at −90°) beside a legend column
(min-width 132px). Center text shows the focused category's amount and name, or the total and
"Total out". Hovering a slice or legend row dims the others to 0.28 opacity; clicking either sets the
ledger drill-down filter (clicking again clears it). Legend rows: 8px swatch, name, right-aligned
percentage in `--color-neutral-500`; non-focused rows drop to `--color-neutral-600`.

> **Do not let drill-down shrink the other panels.** The donut, budget rings and insights compute from a
> **date-range-only** subset of the transactions. Only the ledger table applies `drillCat` and the
> search query. Getting this wrong makes every other budget read ₹0 the moment you click a slice.

**8. Budgets + Goals row** — same column split.

*Budgets*: `repeat(auto-fit, minmax(96px, 1fr))` of rings. Each is a 76px SVG rotated −90°: a
`--color-divider` track and an accent arc, both r 30, `stroke-width 7`, `stroke-linecap round`,
driven by `stroke-dasharray` and transitioned over 800ms on mount. Arc turns `--color-accent-300`
above 90% usage. Under each: category name at 12.5px/500 and `₹used / ₹ceiling` at 11px.
Ceilings in the mock: Food 8,000 · Transport 6,000 · Bills 7,000 · Shopping 5,000 — these need a real
`budgets` table (`user_id`, `category`, `monthly_ceiling`).

*Goals*: per goal, a 13px name, a right-aligned `₹saved of ₹target`, a `＋` contribute button, and a
6px `999px` progress bar (`--color-divider` track, accent fill, 600ms width transition). Needs a
`goals` table (`user_id`, `name`, `target`, `saved`).

**9. Ledger** — `--shadow-md`, `padding: 16px 18px 8px`.
- Header: `h2` "Ledger"; a removable `.tag.tag-accent` chip showing the active drill-down category with
  a `✕`; a 220px filter input; a right-aligned `"{shown} of {total}"` count.
- Table: 10.5px uppercase `--color-neutral-500` headers, `1px solid var(--color-divider)` under every
  row, cells `padding: 9px 10px`. Columns: Date (12.5px, `--color-neutral-400`, `dd MMM`), Description
  (13.5px), Category (a pill button — 1px border in the category's fill color, text in the category's
  *text* color, `padding: 1.5px 9px`, 11.5px — clicking it sets the drill-down), Amount (right, 13.5px,
  500, tabular), and a 36px delete column with a 15px trash icon at `--color-neutral-600` that turns
  accent on hover. Row hover: `color-mix(accent 9%)`. Newly added rows carry a persistent
  `color-mix(accent 12%)` tint.
- **Empty state** (replaces the current bare "No transactions in this date range."): a 40px outlined
  circle with a magnifier, a 14px title, a 12.5px body, and a "Clear filters" primary button.
  Copy branches — with a query: `Nothing matches "{q}"` / "Try a shorter word, or widen the date range
  — the ledger holds {n} transactions in total."; without: "No expenses in this range" / "Widen the
  range or add the first expense for these dates."

**10. Chat drawer** (replaces `_chat_drawer.html`) — `position: fixed; right: 18px; bottom: 18px`,
352px wide, `max-height: 74vh`, `--radius-lg`, `--shadow-lg`, slides in over 200ms.
- Header: 7px accent status dot, "Spendly Assistant" at 13.5px/500, "Clear", "✕".
- Message list: user bubbles right-aligned on `--color-accent-800` with `--color-accent-100` text and
  a `10px 10px 3px 10px` radius; assistant bubbles left-aligned, transparent with `--shadow-sm` and a
  `10px 10px 10px 3px` radius. 13px, line-height 1.5, `white-space: pre-wrap`.
- Typing indicator: three 5px accent dots blinking at 0 / 200 / 400ms offsets.
- Receipt card: an eyebrow stage label, a 3px accent progress bar, then the extracted Merchant /
  Amount / Category rows with "Add to ledger" and "Discard".
- Footer: three quick chips, a 32px scan-receipt icon button, the input, and Send.
- A 46px accent-outlined FAB (`◈`) sits in the same corner when the drawer is closed.

**11. Command palette** — `⌘K` / `Ctrl+K` anywhere, or the header search button. Full-screen scrim
`rgba(10,11,18,0.62)` with a 2px blur, panel `min(560px, 92vw)` at 13vh from the top, `--shadow-lg`,
`sp-pop` 160ms. A 15px borderless input with a bottom divider, then a scrollable list (max 52vh).
Rows: 15px accent icon, label, right-aligned hint key. Selected row:
`color-mix(accent 16%)`. Arrow keys move the selection, Enter runs it, Escape or a scrim click closes.
Commands: Add an expense · Scan a receipt · Ask the assistant · Range → this month / last 3 / all time ·
Toggle theme · Clear all filters · Filter → each of the seven categories. Filtering is a plain
substring match on the label; "No command matches that." when empty.

**12. Toast** — bottom-center pill, `--shadow-lg`, `padding: 9px 18px`, 13px, auto-dismiss after 2.2s.
Fires on: expense added, expense deleted, receipt filed, goal contribution, and validation failure.

---

## Interactions & behaviour

| Trigger | Behaviour |
|---|---|
| Preset pill | Sets `date_from` / `date_to`; everything recomputes |
| Date input change | Sets a custom range, clears the active pill |
| Ledger filter input | Case-insensitive substring on description + category. **Ledger only.** |
| Donut slice / legend row / ledger category pill | Sets the drill-down category; clicking the active one clears it. **Ledger only.** |
| Drill-down chip `✕` / "Clear filters" | Clears query and drill-down (Clear filters also resets the range to all time) |
| Bar hover | Bar turns `--color-accent`; the card header shows that month and total |
| Sparkline hover | Dot grows, others dim; the note line shows that month's net worth |
| Tile caret | Opens the account dropdown; outside click or Escape closes |
| Account option | Swaps the tile's figure, sparkline and note |
| ＋ Add expense | Toggles the inline row |
| Save | Validates, prepends the row with a highlight, toasts |
| Row trash | Removes the row, toasts |
| Goal ＋ | Adds ₹5,000 (capped at target), animates the bar, toasts |
| Assistant bar Enter / Ask / chip | Opens the drawer, posts the question |
| Assistant reply | 850ms typing indicator, then the answer |
| "Show every X transaction" | Also sets the drill-down to that category |
| Scan receipt | Three stages at 0 / 800 / 1700ms → extracted card → "Add to ledger" prepends the expense and posts a confirmation |
| Theme toggle | Flips `data-om-theme` on `<html>`; the icon swaps with the label |
| ⌘K / Ctrl+K | Toggles the palette |

### Animations

| Name | Definition |
|---|---|
| `sp-rise` | `opacity 0 → 1`, `translateY(6px) → none`, 180–220ms ease — cards, drawer, messages, toast |
| `sp-pop` | `opacity 0 → 1`, `scale(.97) → 1`, 140–220ms ease — palette, dropdowns, empty state |
| `sp-blink` | `opacity .25 → 1 → .25`, 1s infinite — typing dots |
| Bars | `y` + `height`, 550ms `cubic-bezier(.2,.8,.2,1)`, on mount |
| Rings | `stroke-dasharray`, 800ms, same easing |
| Goal bars | `width`, 600ms, same easing |
| Hover tints | 150ms |

### Light mode

The theme toggle sets `data-om-theme="light"` on `<html>` and overrides seven variables. Because every
rule reads from tokens, nothing else changes:

```css
[data-om-theme="light"] {
  --color-bg: #f3f5fe;
  --color-surface: #ffffff;
  --color-text: #292b31;
  --color-divider: color-mix(in srgb, #292b31 14%, transparent);
  --shadow-sm: 0 0 0 1px #e4e7f5;
  --shadow-md: 0 0 0 1px #cfd3e5, 0 6px 18px rgba(41,43,49,0.10);
  --shadow-lg: 0 0 0 1px #b2b6ca, 0 16px 40px rgba(41,43,49,0.18);
  --color-accent: #5d5294;
}
```

Persist the choice the way `static/js/main.js` already does for the current toggle, and set
`color-scheme` on the date inputs so their native pickers follow.

---

## State

The prototype is client-side; the real page splits between server render and JS.

**Server-rendered per request** (`GET /profile`) — extend the existing route, keep all SQL in
`database/queries.py`:

`date_from`, `date_to`, `active_preset`, `preset_ranges`, `q`, `drill_category` (new query param),
`user`, `transactions`, `monthly_totals`, `category_breakdown`, `accounts` / `debt_accounts` /
`investment_accounts` (each with per-account balances for the dropdowns), `total_balance`,
`total_debt`, `total_investment`, `net_worth`, `net_worth_series` (new — six monthly snapshots for the
sparkline), `budgets` (new), `goals` (new), `insights` (new, from `ai/insights.py`).

**Client-side only** (`static/js/dashboard.js`): which tile dropdown is open and what it has selected,
palette open/query/selected index, chat drawer open state and messages, receipt-scan stage, inline
add-expense open state, hovered bar / slice / sparkline point, toast, theme.

Search and drill-down can be either — server round-trip via `url_for('profile', q=…, category=…)` keeps
it consistent with the existing preset links; filtering the already-rendered rows in JS feels faster.
Pick one and be consistent.

## Backend work this design implies

1. `net_worth_series(user_id)` in `queries.py` — six monthly net-worth snapshots for the sparkline.
2. A `budgets` table + CRUD for the rings (`user_id`, `category`, `monthly_ceiling`).
3. A `goals` table + a contribute endpoint for the goals panel (`user_id`, `name`, `target`, `saved`).
4. `ai/insights.py` — the three rule-based insight strings (already reserved in `CLAUDE.md`; no LLM).
5. `get_accounts` already returns per-account rows; expose them to the template for the dropdowns.
6. A `category` query param on `GET /profile` if drill-down is server-side.

Everything else — presets, search, charts, the transaction table, `POST /api/chat`,
`POST /api/chat/receipt`, `POST /api/expenses` — already exists.

## Assets

No images. Every icon is inline SVG on `currentColor`, `stroke-width` 1.7–2, 24×24 viewBox, drawn in
the Phosphor style Nocturne specifies. They are all in the redesign prototype's `I` map — copy them
from there rather than redrawing. Inter loads from Google Fonts; the current `DM Serif Display` /
`DM Sans` pair is dropped.

## Suggested order

1. Token sheet + Inter, in `base.html`. Confirm the current page still renders.
2. Sidebar rewrite.
3. Static shell: header, assistant bar, filter row, tiles, cards — server data, no JS yet.
4. Charts as inline SVG generated in the template or by `dashboard.js` from the existing
   `monthly_totals` / `category_breakdown` JSON. **Chart.js can go** — the design's charts are simpler
   as hand-drawn SVG and are the only reason that CDN script is loaded.
5. Interactions in `dashboard.js`: tile dropdowns, hovers, drill-down, inline add, toast.
6. Command palette.
7. Chat drawer restyle on the existing `chat.js` endpoints.
8. New backend: budgets, goals, net-worth series, insights.
