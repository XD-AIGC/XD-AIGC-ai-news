/**
 * AI Assistant Panel — right-side expandable chat with summarization
 * Depends on shared.js (uses NewsApp.state for filter params)
 */

const AIPanel = (function () {
  "use strict";

  let $panel, $body, $input, $sendBtn, $closeBtn;
  let chatHistory = []; // {role, content} for follow-up
  let isOpen = false;
  let isLoading = false;

  function getFilterParams() {
    const hook = window.NEWS_PAGE || {};
    const dateParams = (hook.buildDateParams || (() => ({})))();
    const s = NewsApp.state;
    return {
      ...dateParams,
      source: s.source || undefined,
      category: s.category || undefined,
      min_score: s.minScore || undefined,
    };
  }

  function createPanel() {
    const panel = document.createElement('div');
    panel.id = 'aiPanel';
    panel.className = 'ai-panel';
    panel.innerHTML = `
      <div class="ai-panel-header">
        <span class="ai-panel-title">AI 助手</span>
        <button id="aiPanelClose" class="ai-panel-close">&times;</button>
      </div>
      <div class="ai-panel-body" id="aiPanelBody"></div>
      <div class="ai-panel-footer">
        <input type="text" id="aiPanelInput" class="ai-panel-input" placeholder="继续提问..." autocomplete="off">
        <button id="aiPanelSend" class="ai-panel-send">发送</button>
      </div>`;
    document.body.appendChild(panel);

    $panel = panel;
    $body = document.getElementById('aiPanelBody');
    $input = document.getElementById('aiPanelInput');
    $sendBtn = document.getElementById('aiPanelSend');
    $closeBtn = document.getElementById('aiPanelClose');

    $closeBtn.addEventListener('click', close);
    $sendBtn.addEventListener('click', sendMessage);
    $input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
  }

  function open() {
    if (!$panel) createPanel();
    $panel.classList.add('open');
    isOpen = true;
    // Fresh summary each time panel opens
    chatHistory = [];
    $body.innerHTML = '';
    loadSummary();
  }

  function close() {
    if ($panel) $panel.classList.remove('open');
    isOpen = false;
  }

  function toggle() {
    isOpen ? close() : open();
  }

  function appendMessage(role, content) {
    const div = document.createElement('div');
    div.className = 'ai-msg ai-msg-' + role;
    div.innerHTML = renderMarkdown(content);
    $body.appendChild(div);
    $body.scrollTop = $body.scrollHeight;
  }

  function showLoading() {
    const div = document.createElement('div');
    div.className = 'ai-msg ai-msg-assistant ai-loading';
    div.innerHTML = '<span class="ai-dots"><span>.</span><span>.</span><span>.</span></span> 思考中';
    div.id = 'aiLoadingMsg';
    $body.appendChild(div);
    $body.scrollTop = $body.scrollHeight;
  }

  function removeLoading() {
    const el = document.getElementById('aiLoadingMsg');
    if (el) el.remove();
  }

  async function loadSummary() {
    isLoading = true;
    showLoading();

    try {
      const resp = await fetch('/api/summarize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(getFilterParams()),
      });
      const data = await resp.json();
      removeLoading();
      appendMessage('assistant', data.summary);
      chatHistory.push({ role: 'assistant', content: data.summary });
    } catch (e) {
      removeLoading();
      appendMessage('assistant', '抱歉，摘要加载失败，请稍后重试。');
    }
    isLoading = false;
  }

  async function sendMessage() {
    const text = $input.value.trim();
    if (!text || isLoading) return;

    $input.value = '';
    appendMessage('user', text);
    chatHistory.push({ role: 'user', content: text });

    isLoading = true;
    showLoading();

    try {
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: chatHistory,
          ...getFilterParams(),
        }),
      });
      const data = await resp.json();
      removeLoading();
      appendMessage('assistant', data.reply);
      chatHistory.push({ role: 'assistant', content: data.reply });
    } catch (e) {
      removeLoading();
      appendMessage('assistant', '抱歉，AI 助手暂时无法响应。');
    }
    isLoading = false;
  }

  // Simple markdown: headers, bold, lists, line breaks
  function renderMarkdown(text) {
    return text
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/^## (.+)$/gm, '<h3>$1</h3>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/^\- (.+)$/gm, '<li>$1</li>')
      .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
      .replace(/<\/ul>\s*<ul>/g, '')
      .replace(/\n{2,}/g, '<br><br>')
      .replace(/\n/g, '<br>');
  }

  return { open, close, toggle };
})();
