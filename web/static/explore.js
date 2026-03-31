/**
 * AI News Dashboard — Explore page (date-range filtering)
 * Depends on shared.js (loaded first)
 */

// ─── Date range state ───
var dateFrom = '';
var dateTo = '';
var activeDays = 7;

window.NEWS_PAGE = {
  buildDateParams: function () {
    const p = {};
    if (dateFrom) p.date_from = dateFrom;
    if (dateTo) p.date_to = dateTo;
    return p;
  },

  // Explore always shows absolute date (not relative)
  formatTime: function (iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
  },
};

// ─── Date range helpers ───
function fmtDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function applyDays(days) {
  activeDays = days;
  const $dateFrom = document.getElementById('dateFrom');
  const $dateTo = document.getElementById('dateTo');
  if (days === 0) {
    dateFrom = ''; dateTo = '';
    $dateFrom.value = ''; $dateTo.value = '';
  } else {
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - (days - 1));
    dateFrom = fmtDate(from);
    dateTo = fmtDate(to);
    $dateFrom.value = dateFrom;
    $dateTo.value = dateTo;
  }
  syncChipHighlight();
}

function syncChipHighlight() {
  document.querySelectorAll('#dateRangeChips .chip').forEach(function (chip) {
    chip.classList.toggle('active', parseInt(chip.dataset.days) === activeDays);
  });
}

// ─── Explore-specific event bindings ───
function bindDateEvents() {
  document.querySelectorAll('#dateRangeChips .chip').forEach(function (chip) {
    chip.addEventListener('click', function () {
      applyDays(parseInt(chip.dataset.days));
      NewsApp.state.page = 1;
      NewsApp.refresh();
    });
  });

  var $dateFrom = document.getElementById('dateFrom');
  var $dateTo = document.getElementById('dateTo');

  $dateFrom.addEventListener('change', function () {
    dateFrom = $dateFrom.value;
    activeDays = -1;
    syncChipHighlight();
    NewsApp.state.page = 1;
    NewsApp.refresh();
  });

  $dateTo.addEventListener('change', function () {
    dateTo = $dateTo.value;
    activeDays = -1;
    syncChipHighlight();
    NewsApp.state.page = 1;
    NewsApp.refresh();
  });
}

// ─── Init ───
NewsApp.init(function () {
  applyDays(7);
  bindDateEvents();
});
