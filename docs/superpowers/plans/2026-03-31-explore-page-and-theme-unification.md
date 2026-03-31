# Explore Page + Theme/Nav Unification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Explore page with date-range filtering, unify navigation and theme across Daily/Explore/Weekly pages.

**Architecture:** Backend adds `date_from`/`date_to` params to existing API endpoints (backward compatible). New Explore page reuses `style.css` and same layout as Daily. Weekly page gets dark theme CSS + theme toggle. All three pages share a unified nav bar and `localStorage`-based theme persistence.

**Tech Stack:** Python (FastAPI, SQLite), vanilla JS, CSS custom properties

**Note:** This project has no test suite. Verify changes by running the web server and testing in browser.

---

### Task 1: Backend — Add date range support to database

**Files:**
- Modify: `storage/database.py:206-253` (`search_items` method)
- Modify: `storage/database.py:174-204` (`get_stats` method)

- [ ] **Step 1: Add `date_from`/`date_to` to `search_items()`**

In `storage/database.py`, replace the `search_items` method signature and date filtering:

```python
def search_items(
    self,
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    source: str | None = None,
    category: str | None = None,
    q: str | None = None,
    min_score: float | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[ContentItem], int]:
    """Multi-filter paginated search. Returns (items, total_count)."""
    conditions: list[str] = []
    params: list = []

    if date:
        conditions.append("collected_at LIKE ?")
        params.append(f"{date}%")
    elif date_from and date_to:
        conditions.append("collected_at >= ? AND collected_at <= ?")
        params.extend([f"{date_from}T00:00:00", f"{date_to}T23:59:59"])
    elif date_from:
        conditions.append("collected_at >= ?")
        params.append(f"{date_from}T00:00:00")
    elif date_to:
        conditions.append("collected_at <= ?")
        params.append(f"{date_to}T23:59:59")
```

The rest of the method (source, category, q, min_score filtering + pagination) stays unchanged.

- [ ] **Step 2: Add `date_from`/`date_to` to `get_stats()`**

Replace the `get_stats` method signature and where-clause construction:

```python
def get_stats(
    self,
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Return aggregate stats: source/category breakdowns."""
    conditions: list[str] = []
    params: list = []
    if date:
        conditions.append("collected_at LIKE ?")
        params.append(f"{date}%")
    elif date_from and date_to:
        conditions.append("collected_at >= ? AND collected_at <= ?")
        params.extend([f"{date_from}T00:00:00", f"{date_to}T23:59:59"])
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
```

The rest of `get_stats` stays unchanged (it already uses `where` and `params`).

- [ ] **Step 3: Verify backend**

Run: `cd /mnt/d/GIT/XD-AIGC-ai-news && python -c "
from storage.database import NewsDatabase
db = NewsDatabase('./data/news.db')
db.connect()
items, total = db.search_items(date_from='2026-03-25', date_to='2026-03-31', page_size=5)
print(f'date_range: {total} items, first: {items[0].title if items else \"none\"}')
items2, total2 = db.search_items(date='2026-03-25', page_size=5)
print(f'single_date: {total2} items (backward compat OK)')
stats = db.get_stats(date_from='2026-03-25', date_to='2026-03-31')
print(f'stats: {stats[\"total\"]} total, sources: {list(stats[\"by_source\"].keys())}')
db.close()
"`

Expected: Three lines of output with item counts > 0, no errors.

- [ ] **Step 4: Commit**

```bash
git add storage/database.py
git commit -m "feat: add date_from/date_to range support to search_items and get_stats"
```

---

### Task 2: Backend — Add date range params to API endpoints + Explore route

**Files:**
- Modify: `web/app.py:52-74` (list_news endpoint)
- Modify: `web/app.py:86-95` (stats endpoint)
- Add route: `web/app.py` (explore page route)

- [ ] **Step 1: Update `/api/news` endpoint**

In `web/app.py`, update the `list_news` function:

```python
@app.get("/api/news", response_model=PaginatedNews)
def list_news(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_from: Optional[str] = Query(None, description="Range start YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="Range end YYYY-MM-DD"),
    source: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Search query"),
    min_score: Optional[float] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    db = _get_db()
    try:
        items, total = db.search_items(
            date=date, date_from=date_from, date_to=date_to,
            source=source, category=category,
            q=q, min_score=min_score, page=page, page_size=page_size,
        )
        pages = (total + page_size - 1) // page_size if total else 0
        return PaginatedNews(
            items=[_item_to_resp(i) for i in items],
            total=total, page=page, page_size=page_size, pages=pages,
        )
    finally:
        db.close()
```

- [ ] **Step 2: Update `/api/stats` endpoint**

```python
@app.get("/api/stats")
def stats(
    date: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    db = _get_db()
    try:
        return db.get_stats(date=date, date_from=date_from, date_to=date_to)
    finally:
        db.close()
```

- [ ] **Step 3: Add `/explore` route**

Add after the existing `/weekly` route block in `web/app.py`:

```python
@app.get("/explore")
def explore():
    return FileResponse(STATIC_DIR / "explore.html")

@app.get("/explore.js")
def explore_js():
    return FileResponse(STATIC_DIR / "explore.js", media_type="application/javascript")
```

- [ ] **Step 4: Commit**

```bash
git add web/app.py
git commit -m "feat: add date_from/date_to to API endpoints, add /explore route"
```

---

### Task 3: Update light theme to Morandi palette

**Files:**
- Modify: `web/static/style.css:33-51` (`[data-theme="light"]` block)

- [ ] **Step 1: Replace light theme variables**

In `web/static/style.css`, replace the entire `[data-theme="light"]` block:

```css
[data-theme="light"] {
  --bg-base: #e8e0d8;
  --bg-surface: #f5f0eb;
  --bg-surface-hover: #ede6de;
  --bg-elevated: #f5f0eb;
  --border: #d5cdc3;
  --border-light: #ddd5cb;
  --text-primary: #4a4039;
  --text-secondary: #6b5f54;
  --text-tertiary: #8a7f73;
  --accent: #a3907a;
  --accent-dim: #8a7a66;
  --score-high: #8a9e8b;
  --score-mid: #c4a882;
  --score-low: #c47a6a;
  --chip-bg: rgba(163, 144, 122, 0.12);
  --chip-text: #a3907a;
  --shadow: 0 1px 3px rgba(0,0,0,.06);
  --shadow-lg: 0 8px 24px rgba(0,0,0,.08);
}
```

- [ ] **Step 2: Commit**

```bash
git add web/static/style.css
git commit -m "feat: update light theme to Morandi palette"
```

---

### Task 4: Unify Daily page navigation

**Files:**
- Modify: `web/static/index.html:12-31` (topbar section)

- [ ] **Step 1: Replace topbar HTML**

In `web/static/index.html`, replace the entire `<header class="topbar">...</header>` block with:

```html
<header class="topbar">
  <div class="topbar-left">
    <h1 class="logo">AI News</h1>
    <div class="topbar-tabs">
      <a href="/" class="topbar-tab active">Daily</a>
      <a href="/explore" class="topbar-tab">Explore</a>
      <a href="/weekly" class="topbar-tab">周报</a>
    </div>
  </div>
  <div class="topbar-center">
    <div class="search-box">
      <svg class="search-icon" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd"/></svg>
      <input type="text" id="searchInput" placeholder="Search news..." autocomplete="off">
    </div>
  </div>
  <div class="topbar-right">
    <button id="themeToggle" class="icon-btn" title="Toggle theme">
      <svg class="icon-sun" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" clip-rule="evenodd"/></svg>
      <svg class="icon-moon" viewBox="0 0 20 20" fill="currentColor"><path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z"/></svg>
    </button>
  </div>
</header>
```

- [ ] **Step 2: Add topbar-tabs CSS to `style.css`**

Add after the `.icon-btn svg` rule (around line 170) in `web/static/style.css`:

```css
/* Nav Tabs */
.topbar-tabs {
  display: flex;
  gap: 2px;
  margin-left: 12px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 2px;
}

.topbar-tab {
  padding: 4px 14px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  text-decoration: none;
  transition: all var(--transition);
}

.topbar-tab:hover {
  color: var(--text-primary);
  text-decoration: none;
}

.topbar-tab.active {
  background: var(--bg-surface-hover);
  color: var(--text-primary);
}
```

- [ ] **Step 3: Remove old `.logo-sub` CSS rule** from `style.css` (lines 99-103) — no longer used.

- [ ] **Step 4: Verify Daily page**

Run server locally: `python main.py --serve --port 8800`
Open `http://localhost:8800/` — verify:
- Nav shows `AI News [Daily] [Explore] [周报]`
- Daily tab is highlighted
- Theme toggle still works
- Light theme now has Morandi colors
- All existing functionality (date select, source/category filters, search, pagination) still works

- [ ] **Step 5: Commit**

```bash
git add web/static/index.html web/static/style.css
git commit -m "feat: unify Daily nav bar with tabs, add topbar-tabs CSS"
```

---

### Task 5: Create Explore page

**Files:**
- Create: `web/static/explore.html`
- Create: `web/static/explore.js`

- [ ] **Step 1: Create `web/static/explore.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI News — Explore</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header class="topbar">
    <div class="topbar-left">
      <h1 class="logo">AI News</h1>
      <div class="topbar-tabs">
        <a href="/" class="topbar-tab">Daily</a>
        <a href="/explore" class="topbar-tab active">Explore</a>
        <a href="/weekly" class="topbar-tab">周报</a>
      </div>
    </div>
    <div class="topbar-center">
      <div class="search-box">
        <svg class="search-icon" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd"/></svg>
        <input type="text" id="searchInput" placeholder="Search news..." autocomplete="off">
      </div>
    </div>
    <div class="topbar-right">
      <button id="themeToggle" class="icon-btn" title="Toggle theme">
        <svg class="icon-sun" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" clip-rule="evenodd"/></svg>
        <svg class="icon-moon" viewBox="0 0 20 20" fill="currentColor"><path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z"/></svg>
      </button>
    </div>
  </header>

  <div class="layout">
    <aside class="sidebar" id="sidebar">
      <!-- Date Range -->
      <section class="sidebar-section">
        <h3 class="sidebar-title">Date Range</h3>
        <div id="dateRangeChips" class="filter-chips">
          <button class="chip" data-days="3">3d</button>
          <button class="chip active" data-days="7">7d</button>
          <button class="chip" data-days="14">14d</button>
          <button class="chip" data-days="30">30d</button>
          <button class="chip" data-days="0">All</button>
        </div>
        <div class="date-inputs">
          <input type="date" id="dateFrom" class="select-input">
          <input type="date" id="dateTo" class="select-input">
        </div>
      </section>

      <!-- Source Filter -->
      <section class="sidebar-section">
        <h3 class="sidebar-title">Source</h3>
        <div id="sourceFilters" class="filter-chips"></div>
      </section>

      <!-- Category Filter -->
      <section class="sidebar-section">
        <h3 class="sidebar-title">Category</h3>
        <div id="categoryFilters" class="filter-chips"></div>
      </section>

      <!-- Score Filter -->
      <section class="sidebar-section">
        <h3 class="sidebar-title">Min Score</h3>
        <div class="score-slider">
          <input type="range" id="scoreSlider" min="0" max="10" step="0.5" value="0">
          <span id="scoreValue" class="score-label">0</span>
        </div>
      </section>

      <!-- Stats -->
      <section class="sidebar-section">
        <h3 class="sidebar-title">Stats</h3>
        <div id="statsContent" class="stats-grid"></div>
      </section>
    </aside>

    <main class="main-content">
      <div class="content-header">
        <div id="resultInfo" class="result-info"></div>
        <button id="sidebarToggle" class="icon-btn sidebar-toggle">
          <svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 5a1 1 0 011-1h6a1 1 0 110 2H4a1 1 0 01-1-1z" clip-rule="evenodd"/></svg>
        </button>
      </div>
      <div id="newsGrid" class="news-grid"></div>
      <div id="pagination" class="pagination"></div>
      <div id="loadingOverlay" class="loading-overlay">
        <div class="spinner"></div>
      </div>
    </main>
  </div>

  <script src="/static/explore.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create `web/static/explore.js`**

```js
/**
 * AI News Explore — date-range browsing with card list
 */

const API = {
  news: '/api/news',
  stats: '/api/stats',
};

const state = {
  dateFrom: '',
  dateTo: '',
  activeDays: 7,
  source: '',
  category: '',
  q: '',
  minScore: 0,
  page: 1,
  pageSize: 50,
};

// ─── DOM refs ───
const $grid        = document.getElementById('newsGrid');
const $pagination  = document.getElementById('pagination');
const $resultInfo  = document.getElementById('resultInfo');
const $loading     = document.getElementById('loadingOverlay');
const $searchInput = document.getElementById('searchInput');
const $scoreSlider = document.getElementById('scoreSlider');
const $scoreValue  = document.getElementById('scoreValue');
const $sourceBox   = document.getElementById('sourceFilters');
const $categoryBox = document.getElementById('categoryFilters');
const $statsBox    = document.getElementById('statsContent');
const $sidebar     = document.getElementById('sidebar');
const $dateChips   = document.getElementById('dateRangeChips');
const $dateFrom    = document.getElementById('dateFrom');
const $dateTo      = document.getElementById('dateTo');

// ─── Helpers ───
function fmtDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function buildQuery(params) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== '' && v !== null && v !== undefined && v !== 0) qs.set(k, v);
  }
  return qs.toString();
}

// ─── Date range ───
function applyDays(days) {
  state.activeDays = days;
  if (days === 0) {
    state.dateFrom = '';
    state.dateTo = '';
    $dateFrom.value = '';
    $dateTo.value = '';
  } else {
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - (days - 1));
    state.dateFrom = fmtDate(from);
    state.dateTo = fmtDate(to);
    $dateFrom.value = state.dateFrom;
    $dateTo.value = state.dateTo;
  }
  syncChipHighlight();
}

function syncChipHighlight() {
  $dateChips.querySelectorAll('.chip').forEach(c => {
    c.classList.toggle('active', parseInt(c.dataset.days) === state.activeDays);
  });
}

// ─── Data loading ───
async function loadStats() {
  try {
    const statsQ = new URLSearchParams();
    if (state.dateFrom) statsQ.set('date_from', state.dateFrom);
    if (state.dateTo) statsQ.set('date_to', state.dateTo);
    const params = statsQ.toString() ? `?${statsQ}` : '';
    const data = await fetchJSON(API.stats + params);

    $sourceBox.innerHTML = '';
    const sources = Object.entries(data.by_source || {}).sort((a, b) => b[1] - a[1]);
    sources.forEach(([src, count]) => {
      const chip = document.createElement('button');
      chip.className = `chip${state.source === src ? ' active' : ''}`;
      chip.dataset.value = src;
      chip.innerHTML = `${sourceLabel(src)} <span class="count">${count}</span>`;
      chip.addEventListener('click', () => toggleFilter('source', src));
      $sourceBox.appendChild(chip);
    });

    $categoryBox.innerHTML = '';
    const cats = Object.entries(data.by_category || {}).sort((a, b) => b[1] - a[1]);
    cats.forEach(([cat, count]) => {
      const chip = document.createElement('button');
      chip.className = `chip${state.category === cat ? ' active' : ''}`;
      chip.dataset.value = cat;
      chip.innerHTML = `${cat} <span class="count">${count}</span>`;
      chip.addEventListener('click', () => toggleFilter('category', cat));
      $categoryBox.appendChild(chip);
    });

    $statsBox.innerHTML = `
      <div class="stat-item"><div class="stat-value">${data.total}</div><div class="stat-label">Total</div></div>
      <div class="stat-item"><div class="stat-value">${sources.length}</div><div class="stat-label">Sources</div></div>
    `;
  } catch (e) {
    console.error('Failed to load stats:', e);
  }
}

async function loadNews() {
  showLoading(true);
  try {
    const qs = buildQuery({
      date_from: state.dateFrom || undefined,
      date_to: state.dateTo || undefined,
      source: state.source,
      category: state.category,
      q: state.q,
      min_score: state.minScore || undefined,
      page: state.page,
      page_size: state.pageSize,
    });
    const data = await fetchJSON(`${API.news}?${qs}`);
    renderNews(data.items);
    renderPagination(data.page, data.pages, data.total);
    $resultInfo.innerHTML = `Showing <strong>${data.items.length}</strong> of <strong>${data.total}</strong> items`;
  } catch (e) {
    console.error('Failed to load news:', e);
    $grid.innerHTML = emptyState('Failed to load news');
    $resultInfo.textContent = '';
  } finally {
    showLoading(false);
  }
}

// ─── Renderers ───
function renderNews(items) {
  if (!items.length) {
    $grid.innerHTML = emptyState('No news found for the current filters');
    return;
  }
  $grid.innerHTML = items.map(cardHTML).join('');
}

function cardHTML(item) {
  const scoreClass = item.ai_score >= 7 ? 'high' : item.ai_score >= 4 ? 'mid' : item.ai_score != null ? 'low' : 'none';
  const scoreText = item.ai_score != null ? item.ai_score.toFixed(1) : '\u2014';
  const summary = item.ai_summary || truncate(item.content, 180);
  const timeStr = formatTime(item.published_at || item.collected_at);
  const cats = (item.ai_categories || []).map(c => `<span class="category-tag">${esc(c)}</span>`).join('');

  return `
    <article class="news-card">
      <div class="card-header">
        <div class="card-score ${scoreClass}">${scoreText}</div>
        <h3 class="card-title"><a href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.title)}</a></h3>
      </div>
      ${summary ? `<p class="card-summary">${esc(summary)}</p>` : ''}
      <div class="card-meta">
        <span class="source-badge ${item.source_type}">${sourceLabel(item.source_type)}</span>
        ${cats}
        ${item.author ? `<span class="card-author">${esc(item.author)}</span>` : ''}
        <span class="card-time">${timeStr}</span>
      </div>
    </article>`;
}

function renderPagination(current, total, count) {
  if (total <= 1) { $pagination.innerHTML = ''; return; }
  let html = `<button class="page-btn" ${current <= 1 ? 'disabled' : ''} data-page="${current - 1}">&laquo;</button>`;
  const range = pagRange(current, total);
  range.forEach(p => {
    if (p === '...') {
      html += `<span class="page-btn" style="border:none;cursor:default">...</span>`;
    } else {
      html += `<button class="page-btn${p === current ? ' active' : ''}" data-page="${p}">${p}</button>`;
    }
  });
  html += `<button class="page-btn" ${current >= total ? 'disabled' : ''} data-page="${current + 1}">&raquo;</button>`;
  $pagination.innerHTML = html;
  $pagination.querySelectorAll('button[data-page]').forEach(btn => {
    btn.addEventListener('click', () => {
      state.page = parseInt(btn.dataset.page);
      loadNews();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  });
}

function pagRange(cur, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages = [1];
  if (cur > 3) pages.push('...');
  for (let i = Math.max(2, cur - 1); i <= Math.min(total - 1, cur + 1); i++) pages.push(i);
  if (cur < total - 2) pages.push('...');
  pages.push(total);
  return pages;
}

// ─── Interactions ───
function toggleFilter(key, value) {
  state[key] = state[key] === value ? '' : value;
  state.page = 1;
  refresh();
}

let searchTimer;
$searchInput.addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.q = $searchInput.value.trim();
    state.page = 1;
    loadNews();
  }, 400);
});

$dateChips.addEventListener('click', (e) => {
  const chip = e.target.closest('.chip');
  if (!chip) return;
  applyDays(parseInt(chip.dataset.days));
  state.page = 1;
  refresh();
});

$dateFrom.addEventListener('change', () => {
  state.dateFrom = $dateFrom.value;
  state.activeDays = -1;
  syncChipHighlight();
  state.page = 1;
  refresh();
});

$dateTo.addEventListener('change', () => {
  state.dateTo = $dateTo.value;
  state.activeDays = -1;
  syncChipHighlight();
  state.page = 1;
  refresh();
});

$scoreSlider.addEventListener('input', () => {
  state.minScore = parseFloat($scoreSlider.value);
  $scoreValue.textContent = state.minScore;
});

$scoreSlider.addEventListener('change', () => {
  state.page = 1;
  loadNews();
});

document.getElementById('themeToggle').addEventListener('click', () => {
  const html = document.documentElement;
  const next = html.dataset.theme === 'dark' ? 'light' : 'dark';
  html.dataset.theme = next;
  localStorage.setItem('theme', next);
});

document.getElementById('sidebarToggle').addEventListener('click', () => {
  $sidebar.classList.toggle('open');
});

// ─── Utilities ───
function sourceLabel(s) {
  const map = {
    rss: 'RSS', github: 'GitHub', hackernews: 'HN',
    reddit: 'Reddit', telegram: 'Telegram', youtube: 'YouTube',
    bilibili: 'Bilibili', twitter: 'Twitter', manual: 'Manual',
  };
  return map[s] || s;
}

function esc(str) {
  if (!str) return '';
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function truncate(s, len) {
  if (!s) return '';
  return s.length > len ? s.slice(0, len) + '...' : s;
}

function formatTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

function showLoading(on) {
  $loading.classList.toggle('active', on);
}

function emptyState(msg) {
  return `<div class="empty-state">
    <svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>
    <p>${msg}</p>
  </div>`;
}

async function refresh() {
  await Promise.all([loadStats(), loadNews()]);
}

// ─── Init ───
(function init() {
  const saved = localStorage.getItem('theme');
  if (saved) document.documentElement.dataset.theme = saved;

  applyDays(7);
  refresh();
})();
```

- [ ] **Step 3: Add `.date-inputs` CSS to `style.css`**

Add after the `.filter-chips` block (around line 235) in `web/static/style.css`:

```css
.date-inputs {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

.date-inputs input[type="date"] {
  flex: 1;
  height: 32px;
  padding: 0 6px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 12px;
  font-family: var(--font-body);
  outline: none;
}

.date-inputs input[type="date"]:focus {
  border-color: var(--accent);
}
```

- [ ] **Step 4: Verify Explore page**

Open `http://localhost:8800/explore` — verify:
- Nav shows with Explore tab highlighted
- Default 7d range selected, date inputs populated
- Card list loads with items from last 7 days
- Click "14d" → date inputs update, cards reload
- Manually change a date input → chip highlight clears
- Source/Category chips filter correctly
- Search, score slider, pagination all work
- Theme toggle works

- [ ] **Step 5: Commit**

```bash
git add web/static/explore.html web/static/explore.js web/static/style.css
git commit -m "feat: add Explore page with date-range filtering"
```

---

### Task 6: Add dark theme and unified nav to Weekly page

**Files:**
- Modify: `docs/weekly.html` (inline CSS + HTML)
- Modify: `docs/weekly.js` (add theme init)

- [ ] **Step 1: Add dark theme CSS variables to `docs/weekly.html`**

In `docs/weekly.html`, replace the `:root` block (lines 11-27) with light+dark variants:

```css
/* ── Light (Morandi) ── */
:root,
[data-theme="light"] {
  --bg: #e8e0d8;
  --card: #f5f0eb;
  --panel-bg: #ddd5cb;
  --panel-border: #5a5249;
  --text-primary: #4a4039;
  --text-secondary: #6b5f54;
  --accent: #a3907a;
  --score: #c4a882;
  --trend-up: #8a9e8b;
  --story1: #c4a882;
  --story2: #8a9e8b;
  --story3: #c9a87e;
  --max-width: 1380px;
  --radius: 10px;
  --radius-sm: 6px;
}

/* ── Dark ── */
[data-theme="dark"] {
  --bg: #0d1117;
  --card: #161b22;
  --panel-bg: #21262d;
  --panel-border: #30363d;
  --text-primary: #e6edf3;
  --text-secondary: #8b949e;
  --accent: #58a6ff;
  --score: #d29922;
  --trend-up: #3fb950;
  --story1: #d29922;
  --story2: #3fb950;
  --story3: #d29922;
}
```

- [ ] **Step 2: Add `data-theme` to HTML tag**

Change line 2 from:
```html
<html lang="zh-CN">
```
to:
```html
<html lang="zh-CN" data-theme="dark">
```

- [ ] **Step 3: Replace topbar HTML with unified nav + theme toggle**

Replace the `<nav class="topbar">...</nav>` block (lines 548-559) with:

```html
<nav class="topbar">
  <div class="topbar-logo">AI News</div>
  <div class="topbar-tabs">
    <a href="/" class="topbar-tab">Daily</a>
    <a href="/explore" class="topbar-tab">Explore</a>
    <a href="/weekly" class="topbar-tab active">周报</a>
  </div>
  <div class="week-selector">
    <button id="prevWeek" title="上一周">&#8592;</button>
    <span id="weekLabel" class="week-label">—</span>
    <button id="nextWeek" title="下一周">&#8594;</button>
  </div>
  <button id="themeToggle" class="theme-toggle" title="Toggle theme">
    <svg class="icon-sun" viewBox="0 0 20 20" fill="currentColor" width="18" height="18"><path fill-rule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" clip-rule="evenodd"/></svg>
    <svg class="icon-moon" viewBox="0 0 20 20" fill="currentColor" width="18" height="18"><path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z"/></svg>
  </button>
</nav>
```

- [ ] **Step 4: Add theme toggle CSS to Weekly's inline styles**

Add after the `.topbar-tab.active` rule (around line 93) in the `<style>` block:

```css
.theme-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--panel-bg);
  background: var(--card);
  color: var(--text-secondary);
  cursor: pointer;
  margin-left: auto;
}

.theme-toggle:hover { color: var(--text-primary); }
.theme-toggle svg { width: 18px; height: 18px; }

[data-theme="dark"] .icon-sun { display: none; }
[data-theme="dark"] .icon-moon { display: block; }
[data-theme="light"] .icon-sun,
:root .icon-sun { display: block; }
[data-theme="light"] .icon-moon,
:root .icon-moon { display: none; }
```

- [ ] **Step 5: Add theme toggle JS to `docs/weekly.js`**

Add at the very beginning of the IIFE (after line 3 `"use strict";`):

```js
// ── Theme ──
var savedTheme = localStorage.getItem("theme") || "dark";
document.documentElement.setAttribute("data-theme", savedTheme);

var themeBtn = document.getElementById("themeToggle");
if (themeBtn) {
  themeBtn.addEventListener("click", function () {
    var current = document.documentElement.getAttribute("data-theme");
    var next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
  });
}
```

- [ ] **Step 6: Verify Weekly page**

Open `http://localhost:8800/weekly` — verify:
- Nav shows `Daily | Explore | 周报` with 周报 highlighted
- Theme toggle button visible
- Click toggle → switches between Morandi light and dark theme
- Week selector still works (prev/next/hash)
- All comic panels, stories, top10, stats render correctly in both themes
- Switch theme on Weekly, navigate to Daily → same theme persists

- [ ] **Step 7: Commit**

```bash
git add docs/weekly.html docs/weekly.js
git commit -m "feat: add dark theme and unified nav to Weekly page"
```

---

### Task 7: Deploy and verify on server

**Files:** No code changes, deployment only.

- [ ] **Step 1: Push all commits**

```bash
git push
```

- [ ] **Step 2: Pull on server and restart**

```bash
ssh ubuntu@10.102.80.15 "cd /AIGC_Group/XD-AIGC-ai-news && git pull && sudo systemctl restart ai-news-web.service && sleep 1 && systemctl status ai-news-web.service --no-pager"
```

Expected: `active (running)`

- [ ] **Step 3: End-to-end verification on server**

Open `http://10.102.80.15:8800` and test:
1. Daily page: nav tabs visible, light Morandi theme works, existing filters work
2. Explore page: date range chips + date inputs work, 7d default, source/category filtering
3. Weekly page: dark/light toggle works, week navigation works
4. Theme persists across all three pages via localStorage
