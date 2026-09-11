# Spec: Dashboard Redesign Nocturne Phase B

## Overview

This is Sub-project B of the three-part Nocturne dashboard redesign described in
`design_handoff_dashboard_redesign/README.md` and decomposed in
`.claude/specs/16-dashboard-redesign-nocturne-phase-a.md`. Phase A shipped the static Nocturne
visual system, sidebar, header/assistant bar/filter row, summary tiles, and hand-drawn SVG charts,
all scoped to `/profile`. This phase adds the two pieces of dashboard interactivity Phase A
deliberately deferred: a `⌘K`/`Ctrl+K` command palette for the dashboard, and a full Nocturne
restyle of the chat drawer and its floating toggle, which render on every logged-in page via
`base.html`. No new routes and no schema changes — every action the palette exposes, and every
endpoint the drawer talks to, already exists and is unchanged by this phase.

## Depends on

- `16-dashboard-redesign-nocturne-phase-a.md` — Nocturne tokens (`static/css/nocturne.css`),
  `dashboard.css`/`dashboard.js` conventions, sidebar, and the `wireTile` outside-click/Escape
  dropdown pattern (`static/js/dashboard.js:37-70`) this phase's palette mirrors.
- `10-ai-chat-interface.md` — the existing chat routes and `_chat_drawer.html` markup being restyled.
- `12-receipt-ocr-intake.md` — the receipt-scan endpoint the drawer already calls.

## Routes

No new routes. Every command-palette action and every chat-drawer interaction calls a route that
already exists: `GET /profile` (with existing query params), `POST /api/chat`,
`POST /api/chat/receipt`, `POST /api/expenses`, `GET /api/chat/history`,
`DELETE /api/chat/history`.

## Database changes

No database changes.

## Templates

- **Modify:** `templates/profile.html` — add the command-palette markup (scrim + panel + row list)
  near the end of the dashboard shell; remove `disabled` from `.dashboard-search-button` and wire it
  (via `dashboard.js`) to open the palette. No other structural change to the page.
- **Modify:** `templates/_chat_drawer.html` — restyle markup to match the 352px / `--radius-lg`
  design (message list, typing indicator, receipt card, footer quick chips), keeping every existing
  element `id` and `data-*` attribute `chat.js` depends on (`chat-toggle`, `chat-drawer`,
  `chat-panel`, `chat-header`, `chat-clear`, `chat-close`, `chat-messages`, `chat-status`,
  `chat-form`, `chat-attach-input`, `chat-attach-button`, `chat-input`, `chat-send`, and the
  `data-history-url` / `data-send-url` / `data-receipt-url` / `data-expenses-url` attributes on
  `#chat-drawer`). Add new markup only for elements the current drawer lacks (footer quick chips).

## Files to change

- `templates/profile.html`
- `templates/_chat_drawer.html`
- `static/css/dashboard.css` — command palette styles (scrim, panel, row states, filtering empty
  state) and the shared `sp-pop` / `sp-rise` keyframes.
- `static/css/chat.css` — full restyle onto a self-contained Nocturne palette (see Rules).
- `static/js/dashboard.js` — command palette open/close, substring filtering, keyboard navigation,
  and command execution.
- `static/js/chat.js` — only if the new footer quick chips need a small wiring addition; reuse
  `appendBubble`, `sendMessage`, `scanReceipt`, `loadHistory` etc. unchanged. No protocol change.

## Files to create

None.

## New dependencies

No new dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs.
- Parameterised queries only — not applicable, no queries are touched in this phase.
- Passwords hashed with werkzeug — not applicable, no auth code is touched.
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html` (both modified templates already do, via `profile.html` /
  inclusion).
- **Command palette is dashboard-only.** It lives only in `dashboard.css` / `dashboard.js` /
  `profile.html`, never in `base.html`. Every one of its commands (add expense, scan receipt, ask
  the assistant, range presets, category filters, clear filters, theme toggle) acts on dashboard-only
  state or elements that only exist on `/profile`. It must not appear on other pages.
- **Chat drawer restyle must not depend on `nocturne.css` being loaded.** `_chat_drawer.html` and
  `chat.css` render on every logged-in page via `base.html`, and Phase A deliberately kept
  `nocturne.css` scoped to `/profile` only (spec 16: "tokens are page-scoped, not global") so other
  pages keep their current `style.css` look. Define the Nocturne values the drawer needs as a
  **self-contained set of CSS custom properties scoped to `.chat-drawer`**
  (e.g. `.chat-drawer { --color-bg: #161826; --color-surface: #232532; --color-text: #e9e9ed;
  --color-accent: #9184d9; ... }`, copied from `design_handoff_dashboard_redesign/tokens/nocturne.css`),
  and build every drawer rule off those local variables. Do **not** add a global `<link>` to
  `nocturne.css` in `base.html`.
- Reuse `chat.js`'s existing functions untouched — only markup/classes change, not the JS-to-DOM
  contract. If an element `id` genuinely must change, update `chat.js` in the same task, not later.
- Command palette keyboard/outside-click handling follows the existing `wireTile` pattern in
  `static/js/dashboard.js:37-70`: a single `document` click/keydown listener, the `hidden` attribute
  for visibility, `aria-expanded` on the trigger.
- Every icon is inline SVG, `stroke-width` 1.7–2, 24×24 viewBox, `stroke="currentColor"` — copy from
  `design_handoff_dashboard_redesign/prototypes/Spendly Dashboard - Redesign.dc.html`'s icon map
  rather than redrawing.
- `:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }` on every new
  interactive element (palette rows, drawer buttons) — using each context's own `--color-accent`
  (the dashboard's global one, or the drawer's local scoped one).
- Money in the drawer's receipt card keeps the existing `₹` + `toLocaleString('en-IN')` convention
  already used elsewhere in the app.

## Tests to write

File: `tests/test_dashboard_redesign_nocturne_phase_b.py`

### Unit tests

No new Python functions are introduced in this phase (pure template/CSS/JS change), so no unit
tests apply.

### Route tests

`GET /profile` — authenticated, valid session:
- Status 200.
- Response body contains the command-palette container markup (e.g. an element with
  `id="command-palette"`).
- Response body's `.dashboard-search-button` no longer has the `disabled` attribute.

`GET /profile` — unauthenticated:
- Redirects to `/login` (unchanged regression check).

`GET /accounts` — authenticated, valid session:
- Status 200.
- Response body still includes the chat drawer markup (e.g. `class="chat-drawer"` and
  `id="chat-toggle"`), confirming the restyled drawer still renders site-wide after the change.

## Definition of done

- [ ] `/profile`'s header search button is enabled and opens the command palette on click, and
      `⌘K` / `Ctrl+K` opens it from anywhere on the page.
- [ ] Command palette supports: Add an expense, Scan a receipt, Ask the assistant, Range → this
      month / last 3 months / last 6 months / all time, Clear all filters, Toggle theme, and
      Filter → each of the seven categories.
- [ ] In the palette: arrow keys move the selection, Enter runs the selected row, Escape or a scrim
      click closes it, typing filters the list by substring match on the label, and an empty result
      shows "No command matches that."
- [ ] The command palette is visually absent from every page other than `/profile`.
- [ ] `_chat_drawer.html` renders with the new 352px Nocturne-styled layout (message bubbles,
      receipt card, footer quick chips), consistently dark-themed on every logged-in page regardless
      of that page's own current theme.
- [ ] Chat drawer functionality in `chat.js` is unchanged: sending a message, clearing history,
      attaching/scanning a receipt, and the `/profile` quickstart form all still work exactly as
      before.
- [ ] No global `<link>` to `nocturne.css` was added to `base.html`; every other page's visuals
      (navbar, footer, `/expenses/add`, `/accounts`, etc.) are unchanged except for the chat
      drawer/toggle.
- [ ] `pytest` passes, including the new route-level regression tests in
      `tests/test_dashboard_redesign_nocturne_phase_b.py`.
- [ ] Manually verified in a browser: palette open/close/filter/keyboard navigation, every palette
      command actually performs its action, and the drawer restyle on both `/profile` and at least
      one non-dashboard page (e.g. `/accounts`).
