/**
 * Fashion masonry page — image-first cards via CSS columns.
 * Depends on shared.js (loaded first).
 */

var dateMode = 'single';
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
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
  },

  cardHTML: function (item) {
    if (!item.image_url) return '';
    var title = NewsApp.esc(item.title || '');
    var src = NewsApp.esc(item.image_url);
    var url = NewsApp.esc(item.url);
    var source = NewsApp.sourceLabel(item.source_type);
    var scoreText = item.ai_score != null ? item.ai_score.toFixed(1) : '';
    var scoreBadge = scoreText
      ? '<span class="masonry-score">' + scoreText + '</span>'
      : '';

    return '' +
      '<a class="masonry-card" href="' + url + '" target="_blank" rel="noopener">' +
      '  <div class="masonry-img-wrap">' +
      '    <img class="masonry-img" src="' + src + '" alt="" loading="lazy" referrerpolicy="no-referrer"' +
      '         onerror="this.closest(\'.masonry-card\').remove()">' +
      scoreBadge +
      '  </div>' +
      '  <div class="masonry-meta">' +
      '    <h3 class="masonry-title">' + title + '</h3>' +
      '    <span class="masonry-source">' + source + '</span>' +
      '  </div>' +
      '</a>';
  },
};

function fmtDate(d) {
  return d.getFullYear() + '-' +
    String(d.getMonth() + 1).padStart(2, '0') + '-' +
    String(d.getDate()).padStart(2, '0');
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

async function loadDates() {
  var $sel = document.getElementById('dateSelect');
  try {
    var dates = await NewsApp.fetchJSON(NewsApp.API.dates + '?theme=fashion');
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

function bindDateEvents() {
  document.querySelectorAll('.date-mode-tab').forEach(function (tab) {
    tab.addEventListener('click', function () { switchMode(tab.dataset.mode); });
  });
  document.getElementById('dateSelect').addEventListener('change', function () {
    singleDate = this.value;
    NewsApp.state.page = 1;
    NewsApp.refresh();
  });
  document.querySelectorAll('#dateRangeChips .chip').forEach(function (chip) {
    chip.addEventListener('click', function () {
      applyDays(parseInt(chip.dataset.days));
      NewsApp.state.page = 1;
      NewsApp.refresh();
    });
  });
  var $from = document.getElementById('dateFrom');
  var $to = document.getElementById('dateTo');
  $from.addEventListener('change', function () {
    dateFrom = $from.value; activeDays = -1; syncChipHighlight();
    NewsApp.state.page = 1; NewsApp.refresh();
  });
  $to.addEventListener('change', function () {
    dateTo = $to.value; activeDays = -1; syncChipHighlight();
    NewsApp.state.page = 1; NewsApp.refresh();
  });
}

NewsApp.init(function () {
  NewsApp.state.theme = 'fashion';
  NewsApp.state.hasImage = true;
  NewsApp.state.pageSize = 60;

  loadDates();
  applyDays(7);
  bindDateEvents();
});
