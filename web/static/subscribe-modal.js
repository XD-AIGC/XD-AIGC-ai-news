/**
 * Subscribe Analyzer Modal
 *
 * Wires the #subscribe-modal <dialog> element:
 *   - #btn-add-subscribe opens the modal
 *   - Pastes URL → /api/subscribe/analyze → shows result
 *   - User can edit theme/focus_areas/name, then /api/subscribe/confirm
 *
 * The modal markup is injected into the body on first load if it isn't
 * already present, so any page that loads this script + has a
 * #btn-add-subscribe button gets the full subscribe flow.
 */
(function () {
  const FOCUS_AREAS_BY_THEME = {
    ai: ['开源模型', 'ComfyUI', '商用产品', 'Agent & Skills', '3D生成与重建', '训练与部署'],
    fashion: ['潮流', '时装', 'AI × 时尚'],
  };

  const MODAL_HTML = '' +
    '<dialog id="subscribe-modal" class="subscribe-modal">' +
    '  <form method="dialog" id="subscribe-form" onsubmit="return false;">' +
    '    <h2>添加订阅</h2>' +
    '    <div class="modal-state" data-state="input">' +
    '      <label for="subscribe-url">粘贴订阅链接（RSS / YouTube / Twitter / Bilibili / 小红书 / 微博）:</label>' +
    '      <input type="url" id="subscribe-url" placeholder="https://..." required>' +
    '      <div class="modal-actions">' +
    '        <button type="button" id="btn-analyze" class="btn-primary">分析</button>' +
    '        <button type="button" id="btn-cancel-input" class="btn-tertiary">取消</button>' +
    '      </div>' +
    '    </div>' +
    '    <div class="modal-state" data-state="loading" hidden>' +
    '      <div class="spinner"></div>' +
    '      <p>正在分析中（抓取样本 + AI 判断），可能需要 5-15 秒...</p>' +
    '    </div>' +
    '    <div class="modal-state" data-state="result" hidden>' +
    '      <div id="result-already-subscribed" hidden><p class="info">✓ 此源已在订阅中。</p></div>' +
    '      <div id="result-previously-rejected" hidden>' +
    '        <p class="warning">⚠ 你之前拒绝过此源。</p>' +
    '        <button type="button" id="btn-reanalyze" class="btn-secondary">重新分析</button>' +
    '      </div>' +
    '      <div id="result-main">' +
    '        <p><strong>已识别：</strong> <span id="r-type"></span></p>' +
    '        <h3>样本内容</h3><ul id="r-sample"></ul>' +
    '        <h3>AI 建议</h3>' +
    '        <p><strong>理由：</strong> <span id="r-reasoning"></span></p>' +
    '        <p><strong>质量分：</strong> <span id="r-score"></span> / 10</p>' +
    '        <label>主题: <select id="r-theme">' +
    '          <option value="ai">🤖 AI</option>' +
    '          <option value="fashion">👗 时尚</option>' +
    '        </select></label>' +
    '        <label>focus_area (多选): <select id="r-focus-areas" multiple size="4"></select></label>' +
    '        <label>源名称: <input type="text" id="r-name"></label>' +
    '        <div class="modal-actions">' +
    '          <button type="button" id="btn-confirm-accept" class="btn-primary">确认订阅</button>' +
    '          <button type="button" id="btn-confirm-reject" class="btn-secondary">拒绝</button>' +
    '          <button type="button" id="btn-cancel" class="btn-tertiary">取消</button>' +
    '        </div>' +
    '      </div>' +
    '    </div>' +
    '    <div class="modal-state" data-state="error" hidden>' +
    '      <p class="error" id="error-message"></p>' +
    '      <div class="modal-actions">' +
    '        <button type="button" id="btn-retry" class="btn-primary">重试</button>' +
    '        <button type="button" id="btn-cancel-error" class="btn-tertiary">取消</button>' +
    '      </div>' +
    '    </div>' +
    '  </form>' +
    '</dialog>';

  let modal = document.getElementById('subscribe-modal');
  if (!modal) {
    document.body.insertAdjacentHTML('beforeend', MODAL_HTML);
    modal = document.getElementById('subscribe-modal');
  }
  if (!modal) return;   // belt-and-suspenders

  const btnOpen = document.getElementById('btn-add-subscribe');
  const btnAnalyze = document.getElementById('btn-analyze');
  const btnAccept = document.getElementById('btn-confirm-accept');
  const btnReject = document.getElementById('btn-confirm-reject');
  const btnCancel = document.getElementById('btn-cancel');
  const btnCancelInput = document.getElementById('btn-cancel-input');
  const btnCancelError = document.getElementById('btn-cancel-error');
  const btnRetry = document.getElementById('btn-retry');
  const btnReanalyze = document.getElementById('btn-reanalyze');

  let currentAnalysisId = null;

  function setState(name) {
    modal.querySelectorAll('.modal-state').forEach(function (el) {
      el.hidden = el.dataset.state !== name;
    });
  }

  function openModal() {
    document.getElementById('subscribe-url').value = '';
    setState('input');
    modal.showModal();
  }

  function closeModal() {
    modal.close();
    currentAnalysisId = null;
  }

  function renderFocusAreaOptions(theme, selected) {
    const select = document.getElementById('r-focus-areas');
    select.innerHTML = '';
    const all = FOCUS_AREAS_BY_THEME[theme] || [];
    for (const fa of all) {
      const opt = document.createElement('option');
      opt.value = fa;
      opt.textContent = fa;
      if (selected && selected.includes(fa)) opt.selected = true;
      select.appendChild(opt);
    }
  }

  async function doAnalyze(url) {
    setState('loading');
    try {
      const resp = await fetch('/api/subscribe/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(function () { return {}; });
        throw new Error(err.detail || 'HTTP ' + resp.status);
      }
      const result = await resp.json();
      showResult(result);
    } catch (e) {
      showError((e && e.message) || 'Analysis failed');
    }
  }

  function showResult(result) {
    currentAnalysisId = result.analysis_id;
    setState('result');

    document.getElementById('result-already-subscribed').hidden = !result.already_subscribed;
    document.getElementById('result-previously-rejected').hidden = !result.previously_rejected;

    if (result.already_subscribed) {
      document.getElementById('result-main').hidden = true;
      return;
    }
    document.getElementById('result-main').hidden = false;

    document.getElementById('r-type').textContent = result.detected_type;
    document.getElementById('r-reasoning').textContent = (result.llm && result.llm.reasoning) || '';
    document.getElementById('r-score').textContent =
      (result.llm && result.llm.quality_score != null) ? result.llm.quality_score : '-';

    const theme = (result.llm && result.llm.theme === 'fashion') ? 'fashion' : 'ai';
    document.getElementById('r-theme').value = theme;
    renderFocusAreaOptions(theme, (result.llm && result.llm.suggested_focus_areas) || []);

    // Sample list
    const ul = document.getElementById('r-sample');
    ul.innerHTML = '';
    const samples = result.sample || [];
    for (const s of samples) {
      const li = document.createElement('li');
      const title = document.createElement('strong');
      title.textContent = s.title || '';
      const snippet = document.createElement('div');
      snippet.style.color = 'var(--text-muted, #888)';
      snippet.style.fontSize = '0.8rem';
      snippet.textContent = (s.snippet || '').slice(0, 200);
      li.appendChild(title);
      li.appendChild(snippet);
      ul.appendChild(li);
    }

    // Pre-fill name from URL hostname
    const nameInput = document.getElementById('r-name');
    if (!nameInput.value) {
      try {
        const u = new URL(document.getElementById('subscribe-url').value);
        nameInput.value = u.hostname.replace(/^www\./, '');
      } catch (e) {
        nameInput.value = '';
      }
    }
  }

  function showError(msg) {
    setState('error');
    document.getElementById('error-message').textContent = msg;
  }

  async function doConfirm(action) {
    if (!currentAnalysisId) return;
    const body = { analysis_id: currentAnalysisId, action: action };
    if (action === 'accept') {
      body.overrides = {
        theme: document.getElementById('r-theme').value,
        focus_areas: Array.from(document.getElementById('r-focus-areas').selectedOptions).map(function (o) { return o.value; }),
        name: document.getElementById('r-name').value.trim(),
      };
    }
    try {
      const resp = await fetch('/api/subscribe/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        showError('确认失败，请重试');
        return;
      }
      await resp.json();
      alert(action === 'accept' ? '订阅已添加，下次采集生效。' : '已拒绝。');
      closeModal();
    } catch (e) {
      showError('网络错误：' + ((e && e.message) || 'unknown'));
    }
  }

  // Wire up once
  if (btnOpen) btnOpen.addEventListener('click', openModal);
  if (btnAnalyze) btnAnalyze.addEventListener('click', function () {
    const url = document.getElementById('subscribe-url').value.trim();
    if (!url) return;
    doAnalyze(url);
  });
  if (btnAccept) btnAccept.addEventListener('click', function () { doConfirm('accept'); });
  if (btnReject) btnReject.addEventListener('click', function () { doConfirm('reject'); });
  if (btnCancel) btnCancel.addEventListener('click', closeModal);
  if (btnCancelInput) btnCancelInput.addEventListener('click', closeModal);
  if (btnCancelError) btnCancelError.addEventListener('click', closeModal);
  if (btnRetry) btnRetry.addEventListener('click', function () { setState('input'); });
  if (btnReanalyze) btnReanalyze.addEventListener('click', function () {
    const url = document.getElementById('subscribe-url').value.trim();
    if (url) doAnalyze(url);
  });

  // Theme change updates focus_area options
  const themeSel = document.getElementById('r-theme');
  if (themeSel) {
    themeSel.addEventListener('change', function () {
      renderFocusAreaOptions(themeSel.value, []);
    });
  }
})();
