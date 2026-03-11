/**
 * AI News Dashboard - Static GitHub Pages version
 * All filtering/searching/pagination done client-side from JSON data files.
 */

const DATA_BASE = 'data';

const state = {
  date: '',
  source: '',
  category: '',
  q: '',
  minScore: 0,
  page: 1,
  pageSize: 40,
};

// Cached data
let allDates = [];
let currentItems = [];   // Raw items for current date
let filteredItems = [];   // After client-side filtering

// ─── DOM refs ───
const $grid        = document.getElementById('newsGrid');
const $pagination  = document.getElementById('pagination');
const $resultInfo  = document.getElementById('resultInfo');
const $loading     = document.getElementById('loadingOverlay');
const $dateSelect  = document.getElementById('dateSelect');
const $searchInput = document.getElementById('searchInput');
const $scoreSlider = document.getElementById('scoreSlider');
const $scoreValue  = document.getElementById('scoreValue');
const $sourceBox   = document.getElementById('sourceFilters');
const $categoryBox = document.getElementById('categoryFilters');
const $statsBox    = document.getElementById('statsContent');
const $sidebar     = document.getElementById('sidebar');

// ─── Fetch helpers ───
async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ─── Data loading ───
async function loadDates() {
  try {
    allDates = await fetchJSON(`${DATA_BASE}/dates.json`);
    $dateSelect.innerHTML = '';
    allDates.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.date;
      opt.textContent = `${d.date} (${d.count})`;
      $dateSelect.appendChild(opt);
    });
    if (allDates.length > 0 && !state.date) {
      state.date = allDates[0].date;
      $dateSelect.value = state.date;
    }
  } catch (e) {
    console.error('Failed to load dates:', e);
    $grid.innerHTML = emptyState('No data available yet');
  }
}

async function loadDateData() {
  if (!state.date) { currentItems = []; return; }
  showLoading(true);
  try {
    currentItems = await fetchJSON(`${DATA_BASE}/${state.date}.json`);
  } catch (e) {
    console.error('Failed to load date data:', e);
    currentItems = [];
  }
  showLoading(false);
}

async function loadStats() {
  if (!state.date) return;
  try {
    const data = await fetchJSON(`${DATA_BASE}/stats-${state.date}.json`);
    renderSidebar(data);
  } catch (e) {
    // Compute stats from current items if stats file missing
    renderSidebar(computeStats(currentItems));
  }
}

function computeStats(items) {
  const by_source = {};
  const by_category = {};
  items.forEach(item => {
    by_source[item.source_type] = (by_source[item.source_type] || 0) + 1;
    (item.ai_categories || []).forEach(c => {
      by_category[c] = (by_category[c] || 0) + 1;
    });
  });
  return { total: items.length, by_source, by_category };
}

function renderSidebar(data) {
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
}

// ─── Client-side filtering ───
function applyFilters() {
  const q = state.q.toLowerCase();
  filteredItems = currentItems.filter(item => {
    if (state.source && item.source_type !== state.source) return false;
    if (state.category && !(item.ai_categories || []).includes(state.category)) return false;
    if (state.minScore && (item.ai_score == null || item.ai_score < state.minScore)) return false;
    if (q) {
      const haystack = `${item.title} ${item.ai_summary || ''} ${item.content || ''} ${item.author || ''}`.toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });
}

function renderCurrentPage() {
  applyFilters();

  const total = filteredItems.length;
  const totalPages = Math.ceil(total / state.pageSize) || 1;
  if (state.page > totalPages) state.page = totalPages;

  const start = (state.page - 1) * state.pageSize;
  const pageItems = filteredItems.slice(start, start + state.pageSize);

  renderNews(pageItems);
  renderPagination(state.page, totalPages, total);
  $resultInfo.innerHTML = `Showing <strong>${pageItems.length}</strong> of <strong>${total}</strong> items`;
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
      renderCurrentPage();
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
  loadStats();
  renderCurrentPage();
}

let searchTimer;
$searchInput.addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.q = $searchInput.value.trim();
    state.page = 1;
    renderCurrentPage();
  }, 300);
});

$dateSelect.addEventListener('change', async () => {
  state.date = $dateSelect.value;
  state.source = '';
  state.category = '';
  state.page = 1;
  await loadDateData();
  loadStats();
  renderCurrentPage();
});

$scoreSlider.addEventListener('input', () => {
  state.minScore = parseFloat($scoreSlider.value);
  $scoreValue.textContent = state.minScore;
});

$scoreSlider.addEventListener('change', () => {
  state.page = 1;
  renderCurrentPage();
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
  const now = new Date();
  const diff = (now - d) / 1000;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
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

// ─── Init ───
(async function init() {
  const saved = localStorage.getItem('theme');
  if (saved) document.documentElement.dataset.theme = saved;

  await loadDates();
  await loadDateData();
  loadStats();
  renderCurrentPage();
})();
