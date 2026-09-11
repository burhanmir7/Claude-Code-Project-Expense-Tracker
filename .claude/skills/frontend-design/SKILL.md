---
name: frontend-design
description: Designs and generates modern, production-ready UI for WISEX (formerly Spendly), a personal expense tracker built on Flask + Jinja2 + vanilla CSS, styled with the dark "Nocturne" design system. Produces clean fintech-style pages and components - cards, forms, tables, dashboards, modals - with consistent spacing, soft shadows, rounded corners, and inline SVG icons. Use this skill whenever the user asks to design, build, create, redesign, improve, or style any WISEX page, screen, section, or component - including phrasings like "design the X page", "create UI for X", "build a component for X", "make the X look better", "redesign X", or any request about WISEX's frontend, layout, CSS, or visual polish - even when WISEX isn't named explicitly if the conversation context is clearly about it.
disable-model-invocation: true
---

# WISEX UI Designer

You are designing frontend UI for **WISEX**, a personal expense tracker (rebranded from Spendly). WISEX is a Flask app with server-rendered Jinja2 templates, vanilla CSS, and a sprinkle of vanilla JS, styled with the "Nocturne" design system - a dark-first fintech aesthetic with a light-mode toggle. The goal of this skill is to help you generate UI that feels like it belongs in this polished, modern fintech product - not generic bootstrap-era output, and not React/Tailwind output that doesn't match the stack.

## What WISEX's stack looks like

- **Backend:** Flask (`app.py`), SQLite (`database/`)
- **Templates:** Jinja2 in `templates/` (e.g. `base.html`, `profile.html` - the main dashboard, `accounts.html`, `add_expense.html`)
- **Styles:** vanilla CSS in `static/css/` - `style.css` (global + brand primitives), `nocturne.css` (dark/light design tokens), `dashboard.css`, `chat.css`, `accounts.css`, `profile.css`. No Tailwind, no CSS-in-JS, no preprocessors.
- **Scripts:** small amounts of vanilla JS in `static/js/` for interactions (theme toggle in `main.js`, chart init in `dashboard.js`, chat drawer in `chat.js`)
- **Icons:** hand-inlined SVGs directly in templates (`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" ...>`), not an icon font or CDN library. Match the existing stroke style (round caps/joins, 1.75 stroke-width) when adding a new icon.

Generate output that fits this stack. Do not introduce React, Vue, Tailwind, shadcn, Bootstrap, styled-components, or an icon library/CDN (Lucide, Font Awesome, etc.) unless the user explicitly asks for one.

## Before you design: check what already exists

If the user's project files are available (e.g. they've shared the repo, uploaded files, or you're inside the codebase), open `base.html`, the main CSS file, and one or two existing templates before generating anything new. The goal is *consistency* - WISEX should feel like one coherent product, not a collage.

Specifically, look for and reuse:

- **Color tokens** - the real ones live in `static/css/nocturne.css` (`--color-bg`, `--color-surface`, `--color-text`, `--color-accent`, `--color-accent-2`, `--color-divider`, plus `--color-neutral-100..900` and `--color-accent-100..900`/`--color-accent-2-100..900` scales). Both a dark block and a light-mode override block exist - respect whichever the token is meant for, don't hardcode a hex that only works in one mode.
- **Spacing scale** (if there's a `--space-1`, `--space-2` pattern, use it)
- **Font family and type scale**
- **Existing component classes** - `.card`, `.btn`, `.input`, `.badge`, `.table`, etc.
- **The base layout** - `_dashboard_sidebar.html` partial for the sidebar nav, topbar, container width - follow it.

If you can't see the existing files and the request is non-trivial, ask the user to share a screenshot or paste a relevant template before you generate. One screenshot of the existing dashboard saves three rounds of revision.

## The Nocturne design language

When you have no existing reference to follow, default to this. It's a dark, fintech-leaning aesthetic close in spirit to modern banking/trading apps, with a supported light-mode toggle (site-wide, driven by `static/js/main.js`).

**Palette (defaults, override to match `static/css/nocturne.css`):**
- Background (dark): near-black slate (`#161826`); light mode swaps to a near-white ground - always define both, never hardcode one mode's hex outside its block
- Surface (cards): one step lighter than background (`#232532` dark) with a soft divider border, not a heavy shadow
- Text: light neutral on dark (`#e9e9ed`), inverted for light mode
- Primary accent: violet/indigo (`--color-accent`, `--color-accent-2`) - use the existing accent scale steps (100-900) rather than inventing new accent hexes
- Semantic: green for income/positive, red for expense/negative, amber for warnings - reuse whatever semantic tokens already exist before adding new ones

**Spacing:** 8px grid. Use multiples of 4px or 8px for padding, gap, margin. Don't use arbitrary values like 13px or 27px.

**Radius:** `8px` for inputs and small elements, `12px` for cards, `16px` for modals. Pills/badges can be fully rounded.

**Shadows:** subtle only. A card shadow like `0 1px 2px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.06)` is the ceiling. No glows, no heavy drop shadows.

**Typography:** system font stack is fine (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`) or Inter if the project uses it. Type scale: 12 / 14 / 16 / 20 / 24 / 32. Font weights: 400 body, 500 medium, 600 semibold for headings. Numbers (amounts) should use tabular figures: `font-variant-numeric: tabular-nums`.

**Layout patterns:**
- Card-based composition - group related info in surfaces, don't sprawl
- Generous whitespace - tight layouts read as cluttered in finance apps
- Left-aligned content with clear hierarchy; centered layouts only for empty states and auth
- Tables: zebra stripes optional, but always have row hover, right-align numeric columns
- Forms: label above input, helper text below, error state in red with icon

## Icons: inline SVG

WISEX does not use an icon font or CDN icon library. Icons are hand-inlined `<svg>` markup directly in the template, matching this stroke style:

```html
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"
     stroke-linecap="round" stroke-linejoin="round" class="sidebar-icon" aria-hidden="true">
  <circle cx="12" cy="12" r="9"></circle>
  <path d="M12 7v10M8 10h5.5a2.5 2.5 0 0 1 0 5H8"></path>
</svg>
```

Find a matching glyph's path data from any 24x24 outline icon set (Feather/Lucide-style paths work - the existing icons in `_dashboard_sidebar.html` and `profile.html` were sourced this way) and inline the `<path>`/`<circle>`/etc. directly - don't add a script tag or CDN dependency to fetch them at runtime. Size via CSS on the `<svg>` (`width`/`height`), not inline attributes. Prefer 16px inline with text, 20px for buttons, 24px for section headers.

Pick icons that carry meaning. A few WISEX-appropriate defaults:
- Expense/spend: `arrow-down-right`, `shopping-bag`, `credit-card`
- Income: `arrow-up-right`, `wallet`, `trending-up`
- Budget: `target`, `pie-chart`
- Category: `tag`, `folder`
- Add/new: `plus`, `plus-circle`
- Settings: `settings`, `sliders-horizontal`
- Date/time: `calendar`, `clock`
- Search: `search`, Filter: `filter`

Don't sprinkle icons everywhere. One icon per button, one per section heading, one per table row action - that's usually the right density.

## Output structure

When fulfilling a design request, structure your response like this:

### 1. Short UI plan (2-5 bullets)
Name the key sections of the page/component and any notable UX decisions. Keep it tight - this is orientation, not a spec document. Example: "Dashboard has 4 summary cards on top (balance, income, expenses, savings), a 'recent transactions' table, and a category breakdown donut. Summary cards show trend vs last month as a small delta pill."

### 2. The code
- **Template file(s)** - full Jinja2 with `{% extends "base.html" %}` and a `{% block content %}` unless building `base.html` itself. Use Jinja control flow (`{% for %}`, `{% if %}`) with sensible placeholder variable names the user can wire to their Flask route.
- **CSS** - either a new file (e.g. `static/css/dashboard.css`) or additions to an existing stylesheet. Scope with a page/component class prefix (`.dashboard-...`, `.tx-table-...`) so styles don't leak.
- **JS** (only if needed) - vanilla, no frameworks. Small and readable.

Put each file in its own fenced code block with a clear header comment or path annotation like `{# templates/profile.html #}` or `/* static/css/dashboard.css */`.

### 3. Integration note (1-3 lines)
How to wire it up - which Flask route renders it, what variables the template expects, any new dependency (almost always none). If the user needs to add a link in the sidebar or a route in `app.py`, call that out.

## What to avoid

- **Generic/dated looks** - no `<h1>Welcome to My App</h1>` with default browser styles, no sharp-cornered bordered boxes, no 2012-era bootstrap cards.
- **Code dumps without structure** - always separate template, CSS, and JS into labeled blocks.
- **Over-styling** - if something can be solid color instead of a gradient, use solid. If it can be a border instead of a shadow, use border. Restraint reads as quality.
- **Inconsistent spacing** - if you used 16px for card padding in one place, use 16px in the next place too. No 14px here, 18px there.
- **Random color accents** - one primary accent, semantic colors for meaning, everything else neutral.
- **Clever-but-unclear UX** - a clearly-labeled button beats a mystery icon. In finance, trust matters more than cuteness.
- **Mobile afterthought** - use CSS that works at narrow widths. At minimum, stack cards vertically and make tables horizontally scrollable below ~768px.

## Handling ambiguity

If the user asks for something under-specified ("design the reports page"), make reasonable assumptions and *state them up front* in the UI plan - one line each, no long preamble. For example: "Assuming reports page shows: monthly spend trend, top categories, and a downloadable CSV. Let me know if you want different widgets."

Don't pepper the user with clarifying questions for things you can reasonably decide. Do ask when the answer genuinely changes the output - e.g. "Is this a standalone page or a modal on top of the dashboard?"

## A worked example of the right vibe

**Request:** "Design the add expense form"

**UI plan:**
- Modal dialog (not a full page) - users add expenses inline from the dashboard
- Fields: amount (large, prominent), category (pill selector), date (defaults to today), note (optional)
- Primary action "Add expense" anchors bottom-right; cancel is a subtle text button
- Amount field gets a currency symbol prefix and tabular-nums

**Template:** `templates/partials/add_expense_modal.html` - extends nothing, included via `{% include %}`. Uses a `.modal` overlay pattern already in `base.css` if present.

**CSS:** additions to `static/css/components.css` for the new pill selector; reuses existing `.input`, `.btn-primary`, `.modal` classes.

**JS:** small module-free script to open/close the modal and reset the form on close.

That's the shape - concrete, consistent with the stack, visually restrained, and immediately usable.