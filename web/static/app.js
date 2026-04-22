/**
 * AI News Dashboard — unified page with single-day and date-range modes
 * Depends on shared.js (loaded first)
 *
 * Note: ai vs. fashion is now resolved by route (/ vs. /fashion). The
 * Fashion tab in this page is a plain <a> link — no JS theme tracking.
 */

// ─── Date state ───
var dateMode = 'single'; // 'single' or 'range'
var singleDate = '';
var dateFrom = '';
var dateTo = '';
var activeDays = 7;

window.NEWS_PAGE = {
  buildDateParams: function () {
    if (dateMode === 'single') {
      return singleDate ? { date: singleDate } : {};
    }
    var p = {};
    if (dateFrom) p.date_from = dateFrom;
    if (dateTo) p.date_to = dateTo;
    return p;
  },

  formatTime: function (iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (dateMode === 'single') {
      var now = new Date();
      var diff = (now - d) / 1000;
      if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
      if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    }
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
  },
};

// ─── Date helpers ───
function fmtDate(d) {
  var y = d.getFullYear();
  var m = String(d.getMonth() + 1).padStart(2, '0');
  var day = String(d.getDate()).padStart(2, '0');
  return y + '-' + m + '-' + day;
}

function applyDays(days) {
  activeDays = days;
  var $from = document.getElementById('dateFrom');
  var $to = document.getElementById('dateTo');
  if (days === 0) {
    dateFrom = ''; dateTo = '';
    $from.value = ''; $to.value = '';
  } else {
    var to = new Date();
    var from = new Date();
    from.setDate(from.getDate() - (days - 1));
    dateFrom = fmtDate(from);
    dateTo = fmtDate(to);
    $from.value = dateFrom;
    $to.value = dateTo;
  }
  syncChipHighlight();
}

function syncChipHighlight() {
  document.querySelectorAll('#dateRangeChips .chip').forEach(function (chip) {
    chip.classList.toggle('active', parseInt(chip.dataset.days) === activeDays);
  });
}

// ─── Single-day: load date dropdown ───
async function loadDates() {
  var $sel = document.getElementById('dateSelect');
  try {
    var dates = await NewsApp.fetchJSON(NewsApp.API.dates + '?theme=ai');
    $sel.innerHTML = '<option value="">All dates</option>';
    dates.forEach(function (d) {
      var opt = document.createElement('option');
      opt.value = d.date;
      opt.textContent = d.date + ' (' + d.count + ')';
      $sel.appendChild(opt);
    });
    if (dates.length > 0 && !singleDate) {
      singleDate = dates[0].date;
      $sel.value = singleDate;
    }
  } catch (e) {
    console.error('Failed to load dates:', e);
  }
}

// ─── Mode switching ───
function switchMode(mode) {
  dateMode = mode;
  document.querySelectorAll('.date-mode-tab').forEach(function (tab) {
    tab.classList.toggle('active', tab.dataset.mode === mode);
  });
  document.getElementById('dateSingle').classList.toggle('hidden', mode !== 'single');
  document.getElementById('dateRange').classList.toggle('hidden', mode !== 'range');
  NewsApp.state.page = 1;
  NewsApp.refresh();
}

// ─── Bind events ───
function bindDateEvents() {
  // Mode tabs
  document.querySelectorAll('.date-mode-tab').forEach(function (tab) {
    tab.addEventListener('click', function () {
      switchMode(tab.dataset.mode);
    });
  });

  // Single-day dropdown
  document.getElementById('dateSelect').addEventListener('change', function () {
    singleDate = this.value;
    NewsApp.state.page = 1;
    NewsApp.refresh();
  });

  // Range chips
  document.querySelectorAll('#dateRangeChips .chip').forEach(function (chip) {
    chip.addEventListener('click', function () {
      applyDays(parseInt(chip.dataset.days));
      NewsApp.state.page = 1;
      NewsApp.refresh();
    });
  });

  // Range date inputs
  var $from = document.getElementById('dateFrom');
  var $to = document.getElementById('dateTo');

  $from.addEventListener('change', function () {
    dateFrom = $from.value;
    activeDays = -1;
    syncChipHighlight();
    NewsApp.state.page = 1;
    NewsApp.refresh();
  });

  $to.addEventListener('change', function () {
    dateTo = $to.value;
    activeDays = -1;
    syncChipHighlight();
    NewsApp.state.page = 1;
    NewsApp.refresh();
  });
}

// ─── Init ───
NewsApp.init(function () {
  // This page is the AI route; pin theme accordingly so fetch_news scopes correctly.
  if (window.NewsApp && window.NewsApp.state) {
    window.NewsApp.state.theme = 'ai';
  }
  loadDates();
  applyDays(7); // pre-fill range inputs
  bindDateEvents();
});
