/**
 * Subscription management page:
 *   - Lists all user_sources with status filtering tabs
 *   - Per-row actions: enable / disable / accept pending / delete
 */
(function () {
  let currentStatus = '';

  async function loadList() {
    const tbody = document.getElementById('subscriptions-body');
    tbody.innerHTML = '<tr><td colspan="7">加载中...</td></tr>';

    const url = currentStatus
      ? '/api/subscribe/list?status=' + encodeURIComponent(currentStatus)
      : '/api/subscribe/list';
    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const rows = await resp.json();
      render(rows);
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="7">加载失败: ' + escapeHtml((e && e.message) || '') + '</td></tr>';
    }
  }

  function render(rows) {
    const tbody = document.getElementById('subscriptions-body');
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="7">暂无数据</td></tr>';
      return;
    }

    tbody.innerHTML = rows.map(function (r) {
      const fa = (r.focus_areas || []).join(', ');
      const themeBadge = r.theme === 'fashion' ? '👗 时尚' : '🤖 AI';
      let fetchStatus;
      if (r.last_fetch_status === 'ok') {
        fetchStatus = '✓';
      } else if (r.last_fetch_status) {
        fetchStatus = '<span class="error-inline" title="' + escapeHtml(r.last_fetch_status) + '">✗</span>';
      } else {
        fetchStatus = '—';
      }

      let actionBtns = '';
      if (r.status === 'active') {
        actionBtns += '<button data-action="disable" data-id="' + r.id + '">禁用</button>';
      } else if (r.status === 'disabled') {
        actionBtns += '<button data-action="enable" data-id="' + r.id + '">启用</button>';
      } else if (r.status === 'pending') {
        actionBtns += '<button data-action="accept" data-id="' + r.id + '">确认</button>';
      }
      actionBtns += '<button data-action="delete" data-id="' + r.id + '">删除</button>';

      return '<tr>'
        + '<td>' + escapeHtml(r.name || r.url) + '</td>'
        + '<td>' + escapeHtml(r.source_type) + '</td>'
        + '<td>' + themeBadge + '</td>'
        + '<td>' + escapeHtml(fa) + '</td>'
        + '<td>' + escapeHtml(r.status) + '</td>'
        + '<td>' + (r.last_fetch_at || '—') + ' ' + fetchStatus + '</td>'
        + '<td>' + actionBtns + '</td>'
        + '</tr>';
    }).join('');

    tbody.querySelectorAll('button[data-action]').forEach(function (btn) {
      btn.addEventListener('click', onRowAction);
    });
  }

  async function onRowAction(evt) {
    const id = evt.target.dataset.id;
    const action = evt.target.dataset.action;
    let payload;
    let method = 'PATCH';

    if (action === 'disable') {
      payload = { status: 'disabled' };
    } else if (action === 'enable') {
      payload = { status: 'active' };
    } else if (action === 'accept') {
      payload = { status: 'active' };
    } else if (action === 'delete') {
      if (!confirm('删除这个订阅？')) return;
      method = 'DELETE';
      payload = null;
    } else {
      return;
    }

    const opts = { method: method, headers: { 'Content-Type': 'application/json' } };
    if (payload) opts.body = JSON.stringify(payload);

    const resp = await fetch('/api/subscribe/' + id, opts);
    if (!resp.ok) {
      alert('操作失败: HTTP ' + resp.status);
      return;
    }
    loadList();
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      }[c];
    });
  }

  document.querySelectorAll('.status-tab').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.status-tab').forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      currentStatus = btn.dataset.status;
      loadList();
    });
  });

  document.addEventListener('DOMContentLoaded', loadList);
})();
