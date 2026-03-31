# Explore Page + Theme/Nav Unification Design

**Date:** 2026-03-31

## 1. Goals

1. Add an **Explore page** — card list with date range filter, for catching up after days away
2. **Unify navigation** across all three pages (Daily / Explore / Weekly)
3. **Unify theme** — all three pages support dark + light mode; light theme uses Weekly's Morandi palette, dark theme uses Daily's existing palette

## 2. Explore Page

### 2.1 URL & Entry

- Route: `/explore` (served by FastAPI, same as `/weekly`)
- Nav tab: `Daily | Explore | 周报` in all three pages

### 2.2 Layout

Same sidebar + main content layout as Daily page. Reuses `style.css`.

### 2.3 Sidebar Filters

**Date Range section:**
- Quick-select chips: `3d | 7d | 14d | 30d | All` — default `7d` selected
- Two `<input type="date">` fields (From / To) always visible below chips
- Clicking a quick chip fills both date inputs; manually editing a date input deselects all chips
- "All" chip clears both date inputs (no date filter)

**Source section:** Dynamic chips from `/api/stats` (same as Daily)

**Category section:** Dynamic chips from `/api/stats` (same as Daily)

**Min Score section:** Range slider (same as Daily)

**Stats section:** Total count + source count for current filters

### 2.4 Main Content

- Top bar with search input + theme toggle
- Card grid identical to Daily (score badge, title link, summary, source/category/author/time)
- Sorted by `ai_score DESC, collected_at DESC`
- Pagination

### 2.5 Backend Changes

**`storage/database.py`** — `search_items()` and `get_stats()`:
- Add optional `date_from: str | None` and `date_to: str | None` params
- When set, filter `collected_at >= {date_from}T00:00:00 AND collected_at <= {date_to}T23:59:59`
- Original `date` param unchanged (backward compatible)

**`web/app.py`**:
- `/api/news` — add `date_from`, `date_to` query params
- `/api/stats` — add `date_from`, `date_to` query params
- `/explore` route — serve `web/static/explore.html`

### 2.6 New Files

- `web/static/explore.html`
- `web/static/explore.js`

### 2.7 Files NOT Changed (logic)

- `web/static/app.js` — Daily page JS untouched
- `web/static/index.html` — only nav links added

## 3. Navigation Unification

### 3.1 Structure

All three pages get the same nav bar structure:

```
[AI News]   [Daily] [Explore] [周报]   [...right side controls...]
```

- Active tab highlighted
- Links: Daily → `/`, Explore → `/explore`, 周报 → `/weekly`

### 3.2 Implementation

- **Daily** (`web/static/index.html`): Replace current `topbar-left` with unified nav tabs, keep search + theme toggle on right
- **Explore** (`web/static/explore.html`): Built from scratch with same nav
- **Weekly** (`docs/weekly.html`): Replace current topbar HTML with same nav structure, add theme toggle button, keep week selector on right

## 4. Theme Unification

### 4.1 Approach

- **Daily + Explore**: Already use `style.css` with `[data-theme="dark"]` / `[data-theme="light"]` variables. Update light theme variables to match Weekly's Morandi palette.
- **Weekly**: Currently Morandi-only with inline CSS. Add `[data-theme="dark"]` variant using Daily's dark palette. Add theme toggle button + JS.

### 4.2 Light Theme Update (style.css)

Replace current `[data-theme="light"]` values with Morandi-derived values:

```
--bg-base: #e8e0d8       (Weekly --bg)
--bg-surface: #f5f0eb    (Weekly --card)
--bg-surface-hover: #ede6de
--bg-elevated: #f5f0eb
--border: #d5cdc3
--border-light: #ddd5cb
--text-primary: #4a4039  (Weekly --text-primary)
--text-secondary: #6b5f54 (Weekly --text-secondary)
--text-tertiary: #8a7f73
--accent: #a3907a        (Weekly --accent)
--accent-dim: #8a7a66
--score-high: #8a9e8b    (Weekly --trend-up)
--score-mid: #c4a882     (Weekly --score)
--score-low: #c47a6a
--chip-bg: rgba(163,144,122,0.12)
--chip-text: #a3907a
--shadow: 0 1px 3px rgba(0,0,0,.06)
--shadow-lg: 0 8px 24px rgba(0,0,0,.08)
```

### 4.3 Weekly Dark Theme

Add a dark theme block in Weekly's inline CSS using Daily's dark values. Add `data-theme` attribute on `<html>`, theme toggle button in nav, and JS for toggle + localStorage persistence.

### 4.4 Default Theme

- All pages default to `dark` (current behavior for Daily)
- Theme choice persisted in `localStorage('theme')`, shared across all pages

## 5. File Change Summary

| File | Change |
|------|--------|
| `web/static/style.css` | Update `[data-theme="light"]` to Morandi palette |
| `web/static/index.html` | Replace topbar with unified nav (add Explore + 周报 tabs) |
| `web/static/explore.html` | **New** — Explore page |
| `web/static/explore.js` | **New** — Explore page logic |
| `web/app.py` | Add `/explore` route, `date_from`/`date_to` to API endpoints |
| `storage/database.py` | Add `date_from`/`date_to` to `search_items()` and `get_stats()` |
| `docs/weekly.html` | Add dark theme CSS, unified nav, theme toggle |
| `docs/weekly.js` | Add theme toggle JS |

## 6. Out of Scope

- No changes to Daily page JS logic (`app.js`)
- No changes to weekly digest generation logic
- No new API endpoints (only new params on existing ones)
