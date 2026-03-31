/**
 * AI News Dashboard — Daily page
 * Depends on shared.js (loaded first)
 */

window.NEWS_PAGE = {
  // Daily uses single date param
  buildDateParams: function () {
    return NewsApp.state.date ? { date: NewsApp.state.date } : {};
  },

  // Daily shows relative time for recent items
  formatTime: function (iso) {
    if (!iso) return '';
    const d = new Date(iso);
    const now = new Date();
    const diff = (now - d) / 1000;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
  },
};

// ─── Daily-specific: date dropdown ───
async function loadDates() {
  const $dateSelect = document.getElementById('dateSelect');
  try {
    const dates = await NewsApp.fetchJSON(NewsApp.API.dates);
    $dateSelect.innerHTML = '<option value="">All dates</option>';
    dates.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.date;
      opt.textContent = `${d.date} (${d.count})`;
      $dateSelect.appendChild(opt);
    });
    if (dates.length > 0 && !NewsApp.state.date) {
      NewsApp.state.date = dates[0].date;
      $dateSelect.value = NewsApp.state.date;
    }
  } catch (e) {
    console.error('Failed to load dates:', e);
  }

  $dateSelect.addEventListener('change', () => {
    NewsApp.state.date = $dateSelect.value;
    NewsApp.state.page = 1;
    NewsApp.refresh();
  });
}

// ─── Init ───
NewsApp.state.date = '';

NewsApp.init(function () {
  loadDates();
});
