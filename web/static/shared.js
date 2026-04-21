/**
 * AI News Dashboard — shared utilities, renderers, and sidebar logic.
 *
 * Both app.js (Daily) and explore.js (Explore) import this via <script>.
 * Each page sets window.NEWS_PAGE = { buildDateParams, formatTime }
 * before loading shared.js, then calls NewsApp.init(afterInit).
 */

const NewsApp = (function () {
  "use strict";

  const API = { news: '/api/news', stats: '/api/stats', dates: '/api/dates' };

  // State — pages may extend via NewsApp.state
  const state = {
    source: '',
    category: '',
    theme: 'ai',           // content theme (ai / fashion)
    q: '',
    minScore: 0,
    page: 1,
    pageSize: 50,
  };

  // ─── DOM refs ───
  let $grid, $pagination, $resultInfo, $loading,
      $searchInput, $scoreSlider, $scoreValue,
      $sourceBox, $categoryBox, $statsBox, $sidebar;

  function bindDOM() {
    $grid        = document.getElementById('newsGrid');
    $pagination  = document.getElementById('pagination');
    $resultInfo  = document.getElementById('resultInfo');
    $loading     = document.getElementById('loadingOverlay');
    $searchInput = document.getElementById('searchInput');
    $scoreSlider = document.getElementById('scoreSlider');
    $scoreValue  = document.getElementById('scoreValue');
    $sourceBox   = document.getElementById('sourceFilters');
    $categoryBox = document.getElementById('categoryFilters');
    $statsBox    = document.getElementById('statsContent');
    $sidebar     = document.getElementById('sidebar');
  }

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

  // ─── Page hook: each page provides buildDateParams() and formatTime() ───
  function getPageHook() { return window.NEWS_PAGE || {}; }

  // ─── Data loading ───
  async function loadStats() {
    try {
      const dateParams = (getPageHook().buildDateParams || (() => ({})))();
      const qs = new URLSearchParams(dateParams);
      if (state.theme) qs.set('theme', state.theme);
      const data = await fetchJSON(`${API.stats}?${qs}`);

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
      const dateParams = (getPageHook().buildDateParams || (() => ({})))();
      const qs = buildQuery({
        ...dateParams,
        source: state.source,
        category: state.category,
        theme: state.theme,
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
    const fmtTime = getPageHook().formatTime || formatTimeDefault;
    const timeStr = fmtTime(item.published_at || item.collected_at);
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

  function renderPagination(current, total) {
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

  function bindSharedEvents() {
    let searchTimer;
    if ($searchInput) {
      $searchInput.addEventListener('input', () => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => {
          state.q = $searchInput.value.trim();
          state.page = 1;
          loadNews();
        }, 400);
      });
    }

    if ($scoreSlider) {
      $scoreSlider.addEventListener('input', () => {
        state.minScore = parseFloat($scoreSlider.value);
        $scoreValue.textContent = state.minScore;
      });
      $scoreSlider.addEventListener('change', () => {
        state.page = 1;
        loadNews();
      });
    }

    const themeBtn = document.getElementById('themeToggle');
    if (themeBtn) {
      themeBtn.addEventListener('click', () => {
        const html = document.documentElement;
        const next = html.dataset.theme === 'dark' ? 'light' : 'dark';
        html.dataset.theme = next;
        localStorage.setItem('theme', next);
      });
    }

    const sidebarBtn = document.getElementById('sidebarToggle');
    if (sidebarBtn) {
      sidebarBtn.addEventListener('click', () => {
        $sidebar.classList.toggle('open');
      });
    }

    const aiBtn = document.getElementById('aiToggle');
    if (aiBtn && typeof AIPanel !== 'undefined') {
      aiBtn.addEventListener('click', () => AIPanel.toggle());
    }
  }

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

  function formatTimeDefault(iso) {
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

  // ─── Topbar ───
  function renderTopbar() {
    const path = window.location.pathname;
    const isWeekly = path === '/weekly' || path === '/weekly.html';
    const activeTab = isWeekly ? 'weekly' : 'news';

    const sunIcon = '<svg class="icon-sun" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" clip-rule="evenodd"/></svg>';
    const moonIcon = '<svg class="icon-moon" viewBox="0 0 20 20" fill="currentColor"><path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z"/></svg>';

    // Right side: page-specific controls + theme toggle
    let rightHTML = '';
    if (isWeekly) {
      rightHTML = `
        <div class="week-selector">
          <button id="prevWeek" title="上一周">&#8592;</button>
          <span id="weekLabel" class="week-label">\u2014</span>
          <button id="nextWeek" title="下一周">&#8594;</button>
        </div>`;
    } else {
      rightHTML = `
        <div class="search-box">
          <svg class="search-icon" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd"/></svg>
          <input type="text" id="searchInput" placeholder="Search news..." autocomplete="off">
        </div>`;
    }
    rightHTML += `<button id="themeToggle" class="icon-btn" title="Toggle theme">${sunIcon}${moonIcon}</button>`;
    rightHTML += `<button id="aiToggle" class="icon-btn ai-toggle-btn" title="AI 助手"><svg viewBox="0 0 20 20" fill="currentColor"><path d="M2 5a2 2 0 012-2h7a2 2 0 012 2v4a2 2 0 01-2 2H9l-3 3v-3H4a2 2 0 01-2-2V5z"/><path d="M15 7v2a4 4 0 01-4 4H9.828l-1.766 1.767A2 2 0 0011 16h2l3 3v-3h1a2 2 0 002-2V9a2 2 0 00-2-2h-2z"/></svg></button>`;

    const el = document.getElementById('topbar');
    el.innerHTML = `
      <div class="topbar-left"><h1 class="logo">AI News</h1></div>
      <div class="topbar-center">
        <div class="topbar-tabs">
          <a href="/" class="topbar-tab${activeTab === 'news' ? ' active' : ''}">News</a>
          <a href="/weekly" class="topbar-tab${activeTab === 'weekly' ? ' active' : ''}">\u5468\u62A5</a>
        </div>
      </div>
      <div class="topbar-right">${rightHTML}</div>`;
  }

  // ─── Init ───
  function init(afterInit) {
    const saved = localStorage.getItem('theme');
    if (saved) document.documentElement.dataset.theme = saved;

    renderTopbar();
    bindDOM();
    bindSharedEvents();
    if (afterInit) afterInit();
    refresh();
  }

  // Lightweight init for pages that don't use the news sidebar (e.g., weekly)
  function initTopbarOnly() {
    const saved = localStorage.getItem('theme');
    if (saved) document.documentElement.dataset.theme = saved;
    renderTopbar();
    // Bind theme toggle
    const themeBtn = document.getElementById('themeToggle');
    if (themeBtn) {
      themeBtn.addEventListener('click', function () {
        const html = document.documentElement;
        const next = html.dataset.theme === 'dark' ? 'light' : 'dark';
        html.dataset.theme = next;
        localStorage.setItem('theme', next);
      });
    }
    // Bind AI toggle
    const aiBtn = document.getElementById('aiToggle');
    if (aiBtn && typeof AIPanel !== 'undefined') {
      aiBtn.addEventListener('click', function () { AIPanel.toggle(); });
    }
  }

  return { state, init, initTopbarOnly, refresh, loadNews, fetchJSON, API };
})();

// Expose to window so scripts loaded separately (e.g. app.js checking
// `window.NewsApp`) can reach the module. Top-level `const` in a classic
// <script> tag does NOT attach to window automatically.
window.NewsApp = NewsApp;
