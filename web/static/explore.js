/**
 * AI News Dashboard - Explore page (date-range filtering)
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
const $dateFrom    = document.getElementById('dateFrom');
const $dateTo      = document.getElementById('dateTo');

// ─── Fetch helpers ───
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

// ─── Date range helpers ───
function fmtDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

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
  document.querySelectorAll('#dateRangeChips .chip').forEach(chip => {
    const d = parseInt(chip.dataset.days);
    chip.classList.toggle('active', d === state.activeDays);
  });
}

// ─── Data loading ───
async function loadStats() {
  try {
    const qs = new URLSearchParams();
    if (state.dateFrom) qs.set('date_from', state.dateFrom);
    if (state.dateTo) qs.set('date_to', state.dateTo);
    const data = await fetchJSON(`${API.stats}?${qs.toString()}`);

    // Source chips
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

    // Category chips
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

    // Stats summary
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
      date_from: state.dateFrom,
      date_to: state.dateTo,
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
  const scoreText = item.ai_score != null ? item.ai_score.toFixed(1) : '—';
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
  const pages = [];
  pages.push(1);
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

document.querySelectorAll('#dateRangeChips .chip').forEach(chip => {
  chip.addEventListener('click', () => {
    applyDays(parseInt(chip.dataset.days));
    state.page = 1;
    refresh();
  });
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

let searchTimer;
$searchInput.addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.q = $searchInput.value.trim();
    state.page = 1;
    loadNews();
  }, 400);
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
