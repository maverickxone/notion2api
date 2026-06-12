(() => {
  const REMOTE_ID_PREFIX = 'remote-chat-history:';
  const THREADS_ENDPOINT = '/v1/chat-history/threads';

  function getBaseUrl() {
    if (window.NotionAI?.Core?.State?.get) {
      return window.NotionAI.Core.State.get('baseUrl') || window.location.origin;
    }
    return localStorage.getItem('claude_base_url') || window.location.origin;
  }

  function getApiKey() {
    if (window.NotionAI?.Core?.State?.get) {
      return window.NotionAI.Core.State.get('apiKey') || '';
    }
    return localStorage.getItem('claude_api_key') || sessionStorage.getItem('claude_api_key') || '';
  }

  function getHeaders() {
    const headers = { 'Accept': 'application/json', 'Content-Type': 'application/json', 'X-Client-Type': 'Web' };
    const key = getApiKey();
    if (key) headers.Authorization = `Bearer ${key}`;
    return headers;
  }

  function currentRemoteThreadId() {
    const currentChatId = String(window.NotionAI?.Core?.State?.get?.('currentChatId') || '');
    if (!currentChatId.startsWith(REMOTE_ID_PREFIX)) return '';
    return currentChatId.slice(REMOTE_ID_PREFIX.length);
  }

  function normalizeMessages(messages) {
    if (!Array.isArray(messages)) return [];
    return messages
      .map(message => {
        if (!message || typeof message !== 'object') return null;
        const role = String(message.role || '').toLowerCase();
        if (role !== 'user' && role !== 'assistant') return null;
        const content = String(message.content || message.text || '').trim();
        if (!content) return null;
        return role === 'assistant'
          ? { role, content, thinking: '', search: { queries: [], sources: [] }, modelDisplayName: 'Remote history' }
          : { role, content };
      })
      .filter(Boolean);
  }

  function addOrReplaceLocalChat(result) {
    const conversationId = String(result?.conversation_id || '').trim();
    if (!conversationId) throw new Error('Resume response did not include a conversation_id.');

    const mode = String(result?.mode || 'fork').toLowerCase() === 'continue' ? 'continue' : 'fork';
    const title = String(result?.title || result?.thread_id || 'Resumed chat').trim();
    const remoteThreadId = result?.remote_thread_id || result?.thread_id || null;
    const chatId = Date.now().toString();
    const messages = normalizeMessages(result?.messages || []);

    const chat = {
      id: chatId,
      title: mode === 'continue' ? `${title} (continued)` : `${title} (fork)`,
      messages,
      starred: false,
      conversationId,
      remoteThreadId,
      resumeMode: mode
    };

    let chats = window.NotionAI?.Core?.State?.get?.('chats') || [];
    chats = Array.isArray(chats)
      ? chats.filter(item => !(item?.conversationId === conversationId || (remoteThreadId && item?.remoteThreadId === remoteThreadId && item?.resumeMode === mode)))
      : [];
    chats.unshift(chat);
    window.NotionAI.Core.State.set('chats', chats);
    window.NotionAI.Chat.Storage.saveChats();
    return chatId;
  }

  async function resumeRemoteThread(mode, button) {
    const threadId = currentRemoteThreadId();
    if (!threadId) return;
    const originalText = button?.textContent || '';
    if (button) {
      button.disabled = true;
      button.textContent = mode === 'continue' ? 'Continuing...' : 'Forking...';
    }
    try {
      const response = await fetch(`${getBaseUrl()}${THREADS_ENDPOINT}/${encodeURIComponent(threadId)}/resume`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ mode })
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const message = data?.detail || data?.error?.message || `HTTP ${response.status}`;
        throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
      }

      const chatId = addOrReplaceLocalChat(data || {});
      window.NotionAI?.ChatHistoryMain?.clearRemoteSelection?.();
      window.NotionAI.Chat.Manager.selectChat(chatId);
      window.NotionAI.UI.Input.focus();
    } catch (err) {
      showResumeError(err?.message || String(err));
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalText;
      }
    }
  }

  function showResumeError(message) {
    const bar = document.getElementById('chatHistoryResumeBar');
    if (!bar) return;
    let error = bar.querySelector('[data-chat-history-resume-error]');
    if (!error) {
      error = document.createElement('div');
      error.dataset.chatHistoryResumeError = 'true';
      error.className = 'chat-history-resume-error';
      bar.appendChild(error);
    }
    error.textContent = message;
  }

  function ensureStyles() {
    if (document.getElementById('chatHistoryResumeStyles')) return;
    const style = document.createElement('style');
    style.id = 'chatHistoryResumeStyles';
    style.textContent = `
      .chat-history-resume-bar{max-width:720px;margin:0 auto 18px;padding:12px 14px;border:1px solid var(--border);border-radius:10px;background:var(--bg-secondary);color:var(--text-secondary);font-size:13px;line-height:1.45;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
      .chat-history-resume-bar strong{color:var(--text);font-weight:600}
      .chat-history-resume-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-left:auto}
      .chat-history-resume-btn{border:1px solid var(--border);border-radius:6px;padding:6px 9px;background:var(--card-bg);color:var(--text);font-size:12px}
      .chat-history-resume-btn.primary{background:var(--send-bg);color:var(--send-color);border-color:var(--send-bg)}
      .chat-history-resume-btn:hover:not(:disabled){border-color:var(--border-hover)}
      .chat-history-resume-btn:disabled{opacity:.55;cursor:not-allowed}
      .chat-history-resume-error{width:100%;color:#a94442;font-size:12px;margin-top:2px}
    `;
    document.head.appendChild(style);
  }

  function renderResumeBar() {
    ensureStyles();
    const container = document.getElementById('chatContainer');
    if (!container) return;

    const existing = document.getElementById('chatHistoryResumeBar');
    const threadId = currentRemoteThreadId();
    if (!threadId) {
      existing?.remove();
      return;
    }
    if (existing) return;

    const bar = document.createElement('div');
    bar.id = 'chatHistoryResumeBar';
    bar.className = 'chat-history-resume-bar';
    bar.innerHTML = `
      <div><strong>Viewing synced chat.</strong> Choose how to make it editable.</div>
      <div class="chat-history-resume-actions">
        <button class="chat-history-resume-btn primary" type="button" data-chat-history-resume-mode="fork">Fork as new chat</button>
        <button class="chat-history-resume-btn" type="button" data-chat-history-resume-mode="continue">Continue original thread</button>
      </div>
    `;
    bar.querySelectorAll('[data-chat-history-resume-mode]').forEach(button => {
      button.addEventListener('click', event => {
        event.stopPropagation();
        resumeRemoteThread(button.dataset.chatHistoryResumeMode, button);
      });
    });
    container.prepend(bar);
  }

  function init() {
    ensureStyles();
    renderResumeBar();
    const observer = new MutationObserver(() => renderResumeBar());
    observer.observe(document.body, { childList: true, subtree: true });
  }

  window.NotionAI = window.NotionAI || {};
  window.NotionAI.ChatHistoryResume = {
    renderResumeBar,
    resumeRemoteThread
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
