(() => {
  const THREADS_ENDPOINT = '/v1/chat-history/threads';
  const PAGE_SIZE = 50;
  const browserState = {
    threads: [],
    selectedIds: new Set(),
    offset: 0,
    hasMore: false,
    loading: false,
    activeThreadId: null
  };

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
    const headers = { 'Accept': 'application/json', 'X-Client-Type': 'Web' };
    const key = getApiKey();
    if (key) headers.Authorization = `Bearer ${key}`;
    return headers;
  }

  function esc(text) {
    const node = document.createElement('div');
    node.textContent = text == null ? '' : String(text);
    return node.innerHTML;
  }

  function ensureStyles() {
    if (document.getElementById('chatHistoryBrowserStyles')) return;
    const style = document.createElement('style');
    style.id = 'chatHistoryBrowserStyles';
    style.textContent = `
      .chat-history-browser-modal .modal-content{width:min(1180px,92vw);height:min(760px,86vh);display:flex;flex-direction:column}
      .chat-history-browser-modal .modal-body{flex:1;min-height:0;display:flex;flex-direction:column;padding:0}
      .chat-history-browser-summary{padding:12px 20px;border-bottom:1px solid var(--border);font-size:12px;color:var(--text-secondary);display:flex;gap:14px;flex-wrap:wrap;align-items:center}
      .chat-history-browser-layout{flex:1;min-height:0;display:grid;grid-template-columns:340px 1fr}
      .chat-history-browser-list{border-right:1px solid var(--border);overflow:auto;padding:12px}
      .chat-history-browser-preview{overflow:auto;padding:24px}
      .chat-history-browser-day{font-size:11px;font-weight:700;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0;margin:14px 0 8px}
      .chat-history-browser-item{width:100%;text-align:left;border:1px solid var(--border);border-radius:8px;padding:10px 12px;margin-bottom:8px;background:var(--card-bg);color:var(--text);display:flex;gap:8px;align-items:flex-start}
      .chat-history-browser-item:hover{border-color:var(--border-hover);background:var(--bg-hover)}
      .chat-history-browser-item.active{border-color:var(--border-active)}
      .chat-history-browser-checkbox{margin-top:2px;flex-shrink:0}
      .chat-history-browser-item-body{min-width:0;flex:1}
      .chat-history-browser-title{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:4px}
      .chat-history-browser-meta{font-size:11px;color:var(--text-tertiary);line-height:1.5}
      .chat-history-hydrated-yes{color:#2e7d32}
      .chat-history-hydrated-no{color:#a94442}
      .chat-history-browser-load-more{width:100%;margin:8px 0 4px}
      .chat-history-browser-delete-btn{color:#a94442;border-color:#a94442!important}
      .chat-history-browser-delete-btn:disabled{opacity:.45;cursor:not-allowed}
      .chat-history-empty-warning{border:1px solid #f0ad4e;background:rgba(240,173,78,.12);border-radius:8px;padding:10px 12px;margin:12px 0;color:var(--text-secondary);font-size:13px;line-height:1.5}
      .chat-history-browser-markdown{font-size:14px;line-height:1.65;color:var(--text);white-space:normal}
      .chat-history-browser-markdown pre{white-space:pre-wrap;word-break:break-word;background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;padding:12px}
      .chat-history-browser-markdown code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px}
      @media(max-width:768px){.chat-history-browser-layout{grid-template-columns:1fr}.chat-history-browser-list{border-right:0;border-bottom:1px solid var(--border);max-height:260px}.chat-history-browser-preview{padding:16px}}
    `;
    document.head.appendChild(style);
  }

  function ensureModal() {
    let modal = document.getElementById('chatHistoryBrowserModal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.id = 'chatHistoryBrowserModal';
    modal.className = 'modal-overlay hidden chat-history-browser-modal';
    modal.innerHTML = `
      <div class="modal-content">
        <div class="modal-header">
          <h3>Remote chat history</h3>
          <div style="display:flex;align-items:center;gap:8px">
            <button id="selectAllChatHistoryBrowserBtn" class="btn-secondary" type="button">Select loaded</button>
            <button id="clearChatHistoryBrowserSelectionBtn" class="btn-secondary" type="button">Clear</button>
            <button id="deleteChatHistoryBrowserBtn" class="btn-secondary chat-history-browser-delete-btn" type="button" disabled>Delete selected</button>
            <button id="refreshChatHistoryBrowserBtn" class="btn-secondary" type="button">Refresh</button>
            <button id="closeChatHistoryBrowserBtn" class="modal-close-btn" type="button" aria-label="Close">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
            </button>
          </div>
        </div>
        <div class="modal-body">
          <div id="chatHistoryBrowserSummary" class="chat-history-browser-summary">Loading synced threads...</div>
          <div class="chat-history-browser-layout">
            <div id="chatHistoryBrowserList" class="chat-history-browser-list"></div>
            <div id="chatHistoryBrowserPreview" class="chat-history-browser-preview">
              <div class="chat-history-browser-markdown">Select a synced thread to load its full content.</div>
            </div>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    document.getElementById('closeChatHistoryBrowserBtn').addEventListener('click', closeModal);
    document.getElementById('refreshChatHistoryBrowserBtn').addEventListener('click', () => loadThreads());
    document.getElementById('selectAllChatHistoryBrowserBtn').addEventListener('click', selectLoadedThreads);
    document.getElementById('clearChatHistoryBrowserSelectionBtn').addEventListener('click', clearSelection);
    document.getElementById('deleteChatHistoryBrowserBtn').addEventListener('click', deleteSelectedThreads);
    modal.addEventListener('click', event => {
      if (event.target === modal) closeModal();
    });
    return modal;
  }

  function updateSelectionControls() {
    const count = browserState.selectedIds.size;
    const deleteBtn = document.getElementById('deleteChatHistoryBrowserBtn');
    if (deleteBtn) {
      deleteBtn.disabled = count === 0;
      deleteBtn.textContent = count ? `Delete selected (${count})` : 'Delete selected';
    }
    document.querySelectorAll('[data-chat-history-select]').forEach(input => {
      input.checked = browserState.selectedIds.has(input.dataset.threadId);
    });
    updateSummary();
  }

  function updateSummary() {
    const hydrated = browserState.threads.filter(t => Number(t.message_count || 0) > 0).length;
    const selected = browserState.selectedIds.size;
    setSummary(`Loaded threads: ${browserState.threads.length}${browserState.hasMore ? '+' : ''} · Selected: ${selected} · Hydrated: ${hydrated} · Empty: ${browserState.threads.length - hydrated}`);
  }

  function setSummary(text) {
    const el = document.getElementById('chatHistoryBrowserSummary');
    if (el) el.textContent = text;
  }

  function setIdlePreview(threads) {
    const preview = document.getElementById('chatHistoryBrowserPreview');
    if (!preview) return;
    const total = Array.isArray(threads) ? threads.length : 0;
    preview.innerHTML = `
      <div class="chat-history-browser-summary" style="padding:0 0 12px;border-bottom:0">
        <span>Total loaded threads: ${total}</span>
        <span>Full content: loaded on selection</span>
      </div>
      <div class="chat-history-browser-markdown">Select a synced thread to hydrate and load its markdown. Use the checkboxes to bulk-delete remote chat history.</div>
    `;
  }

  function renderMarkdown(markdown) {
    if (window.NotionAI?.Utils?.Markdown?.renderToSafeHtml) {
      return window.NotionAI.Utils.Markdown.renderToSafeHtml(markdown || '');
    }
    if (window.marked && window.DOMPurify) {
      return DOMPurify.sanitize(marked.parse(markdown || ''));
    }
    return `<pre>${esc(markdown || '')}</pre>`;
  }

  function threadTimestamp(thread) {
    const value = thread.updated_at || thread.last_edited_time || thread.created_time || '';
    if (typeof value === 'number') return value;
    const text = String(value || '').trim();
    if (/^\d+$/.test(text)) return Number(text);
    const parsed = Date.parse(text);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function dayLabel(thread) {
    const ts = threadTimestamp(thread);
    if (!ts) return 'Unknown date';
    const date = new Date(ts);
    if (Number.isNaN(date.getTime())) return 'Unknown date';
    const today = new Date();
    const startToday = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
    const startDate = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
    const diffDays = Math.round((startToday - startDate) / 86400000);
    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  }

  async function fetchJson(path) {
    const response = await fetch(`${getBaseUrl()}${path}`, { headers: getHeaders() });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const message = data?.detail || data?.error?.message || `HTTP ${response.status}`;
      throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
    }
    return data;
  }

  async function fetchText(path) {
    const response = await fetch(`${getBaseUrl()}${path}`, { headers: getHeaders() });
    const text = await response.text();
    if (!response.ok) throw new Error(text || `HTTP ${response.status}`);
    return text;
  }

  async function requestJson(path, method, body = {}) {
    const response = await fetch(`${getBaseUrl()}${path}`, {
      method,
      headers: { ...getHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const message = data?.detail || data?.error?.message || `HTTP ${response.status}`;
      throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
    }
    return data || {};
  }

  function postJson(path, body = {}) {
    return requestJson(path, 'POST', body);
  }

  function deleteJson(path, body = {}) {
    return requestJson(path, 'DELETE', body);
  }

  function updateThreadListItem(threadId, updates) {
    const thread = browserState.threads.find(item => item.id === threadId);
    if (thread) Object.assign(thread, updates);
    const btn = Array.from(document.querySelectorAll('.chat-history-browser-item')).find(item => item.dataset.threadId === threadId);
    if (!btn) return;
    const count = Number(updates.message_count ?? thread?.message_count ?? 0);
    const hydrated = Boolean(updates.hydrated ?? thread?.hydrated ?? count > 0);
    const countEl = btn.querySelector('[data-chat-history-count]');
    const hydratedEl = btn.querySelector('[data-chat-history-hydrated]');
    if (countEl) countEl.textContent = String(count);
    if (hydratedEl) {
      hydratedEl.textContent = hydrated ? 'yes' : 'no';
      hydratedEl.className = hydrated ? 'chat-history-hydrated-yes' : 'chat-history-hydrated-no';
    }
    updateSummary();
  }

  function toggleThreadSelection(threadId, checked) {
    if (checked) browserState.selectedIds.add(threadId);
    else browserState.selectedIds.delete(threadId);
    updateSelectionControls();
  }

  function selectLoadedThreads() {
    for (const thread of browserState.threads) {
      if (thread?.id) browserState.selectedIds.add(thread.id);
    }
    updateSelectionControls();
  }

  function clearSelection() {
    browserState.selectedIds.clear();
    updateSelectionControls();
  }

  async function deleteSelectedThreads() {
    const ids = Array.from(browserState.selectedIds);
    if (!ids.length) return;
    const confirmed = window.confirm(`Delete ${ids.length} selected remote chat(s)? This also removes confirmed deletions from the local archive.`);
    if (!confirmed) return;

    const deleteBtn = document.getElementById('deleteChatHistoryBrowserBtn');
    if (deleteBtn) {
      deleteBtn.disabled = true;
      deleteBtn.textContent = 'Deleting...';
    }
    const preview = document.getElementById('chatHistoryBrowserPreview');
    if (preview) preview.innerHTML = `<div class="chat-history-browser-markdown">Deleting ${ids.length} selected remote chat(s)...</div>`;

    try {
      const result = await deleteJson(THREADS_ENDPOINT, {
        thread_ids: ids,
        account_index: 0,
        remote: true,
        local: true
      });
      const successIds = Array.isArray(result?.results?.success) ? result.results.success : [];
      const failed = Array.isArray(result?.results?.failed) ? result.results.failed : [];
      const successSet = new Set(successIds);
      browserState.threads = browserState.threads.filter(thread => !successSet.has(thread.id));
      browserState.selectedIds.clear();
      for (const failedItem of failed) {
        if (failedItem?.thread_id) browserState.selectedIds.add(failedItem.thread_id);
      }
      renderThreadList(browserState.threads);
      updateSelectionControls();
      window.NotionAI?.ChatHistoryMain?.refresh?.();
      const failureHtml = failed.length
        ? `<br>${failed.length} chat(s) were not removed and remain selected.<br><pre>${esc(failed.map(item => `${item.thread_id}: ${item.error || item.stage || 'failed'}`).join('\n'))}</pre>`
        : '';
      if (preview) {
        preview.innerHTML = `
          <div class="chat-history-empty-warning">
            Removed ${esc(successIds.length)} confirmed remote chat(s).<br>
            Local archive removed ${esc(result?.local_result?.threads_deleted ?? 0)} thread row(s) and ${esc(result?.local_result?.messages_deleted ?? 0)} message row(s).
            ${failureHtml}
          </div>
        `;
      }
    } catch (err) {
      if (preview) preview.innerHTML = `<div class="chat-history-empty-warning">${esc(err?.message || String(err))}</div>`;
    } finally {
      updateSelectionControls();
    }
  }

  function renderThreadList(threads) {
    const list = document.getElementById('chatHistoryBrowserList');
    if (!list) return;
    list.innerHTML = '';
    if (!threads.length) {
      list.innerHTML = '<div class="chat-history-empty-warning">No synced threads found. Use Import chats → Pull from Notion first.</div>';
      return;
    }
    let currentDay = '';
    for (const thread of threads) {
      const label = dayLabel(thread);
      if (label !== currentDay) {
        currentDay = label;
        const header = document.createElement('div');
        header.className = 'chat-history-browser-day';
        header.textContent = label;
        list.appendChild(header);
      }
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'chat-history-browser-item';
      btn.dataset.threadId = thread.id;
      const count = Number(thread.message_count || 0);
      const hydrated = Boolean(thread.hydrated || count > 0);
      btn.innerHTML = `
        <input class="chat-history-browser-checkbox" data-chat-history-select data-thread-id="${esc(thread.id)}" type="checkbox" ${browserState.selectedIds.has(thread.id) ? 'checked' : ''} aria-label="Select chat">
        <div class="chat-history-browser-item-body">
          <div class="chat-history-browser-title">${esc(thread.title || thread.id)}</div>
          <div class="chat-history-browser-meta">
            Messages: <span data-chat-history-count>${count}</span> · Hydrated: <span data-chat-history-hydrated class="${hydrated ? 'chat-history-hydrated-yes' : 'chat-history-hydrated-no'}">${hydrated ? 'yes' : 'no'}</span><br>
            Updated: ${esc(thread.updated_at || thread.last_edited_time || thread.created_time || 'Unknown date')}<br>
            ${esc(thread.first_message_preview || thread.last_message_preview || '')}
          </div>
        </div>
      `;
      const checkbox = btn.querySelector('[data-chat-history-select]');
      checkbox?.addEventListener('click', event => {
        event.stopPropagation();
        toggleThreadSelection(thread.id, Boolean(event.target.checked));
      });
      btn.addEventListener('click', event => {
        if (event.target?.matches?.('[data-chat-history-select]')) return;
        selectThread(thread, threads);
      });
      list.appendChild(btn);
    }
    if (browserState.hasMore) {
      const loadMore = document.createElement('button');
      loadMore.type = 'button';
      loadMore.className = 'btn-secondary chat-history-browser-load-more';
      loadMore.textContent = browserState.loading ? 'Loading...' : 'Load more';
      loadMore.disabled = browserState.loading;
      loadMore.addEventListener('click', () => loadThreads({ append: true }));
      list.appendChild(loadMore);
    }
  }

  async function selectThread(thread, threads) {
    browserState.activeThreadId = thread.id;
    const list = document.getElementById('chatHistoryBrowserList');
    list?.querySelectorAll('.chat-history-browser-item').forEach(el => el.classList.toggle('active', el.dataset.threadId === thread.id));
    const preview = document.getElementById('chatHistoryBrowserPreview');
    if (!preview) return;
    const count = Number(thread.message_count || 0);
    preview.innerHTML = `<div class="chat-history-browser-markdown">Hydrating ${esc(thread.title || thread.id)}...</div>`;
    try {
      const hydration = await postJson(`${THREADS_ENDPOINT}/${encodeURIComponent(thread.id)}/hydrate`);
      const selectedCount = Number(hydration?.thread?.message_count ?? count);
      const selectedHydrated = Boolean(hydration?.thread?.hydrated || selectedCount > 0);
      thread.message_count = selectedCount;
      thread.hydrated = selectedHydrated;
      updateThreadListItem(thread.id, { message_count: selectedCount, hydrated: selectedHydrated });
      window.NotionAI?.ChatHistoryMain?.refresh?.();
      preview.innerHTML = `<div class="chat-history-browser-markdown">Loading ${esc(thread.title || thread.id)}...</div>`;
      const markdown = await fetchText(`${THREADS_ENDPOINT}/${encodeURIComponent(thread.id)}/markdown`);
      const warning = selectedCount === 0
        ? '<div class="chat-history-empty-warning"><strong>Empty hydrated message set.</strong><br>This thread record exists, but no message rows are attached yet. Run a larger sync, then check the debug endpoint for raw message fields.</div>'
        : '';
      preview.innerHTML = `
        <div class="chat-history-browser-summary" style="padding:0 0 12px;border-bottom:0">
          <span>Total synced threads: ${threads.length}</span>
          <span>Selected messages: ${selectedCount}</span>
          <span>Hydrated: ${selectedHydrated ? 'yes' : 'no'}</span>
        </div>
        ${warning}
        <div class="chat-history-browser-markdown">${renderMarkdown(markdown)}</div>
      `;
    } catch (err) {
      preview.innerHTML = `<div class="chat-history-empty-warning">${esc(err?.message || String(err))}</div>`;
    }
  }

  async function loadThreads(options = {}) {
    const append = Boolean(options.append);
    if (browserState.loading) return;
    browserState.loading = true;
    const list = document.getElementById('chatHistoryBrowserList');
    const preview = document.getElementById('chatHistoryBrowserPreview');
    if (!append) {
      browserState.threads = [];
      browserState.selectedIds.clear();
      browserState.offset = 0;
      browserState.hasMore = false;
      if (list) list.innerHTML = '<div class="chat-history-browser-meta">Loading...</div>';
      if (preview) preview.innerHTML = '<div class="chat-history-browser-markdown">Select a synced thread to load its full content.</div>';
      setSummary('Loading synced threads...');
      updateSelectionControls();
    } else {
      renderThreadList(browserState.threads);
    }
    try {
      const data = await fetchJson(`${THREADS_ENDPOINT}?limit=${PAGE_SIZE}&offset=${browserState.offset}`);
      const page = Array.isArray(data?.threads) ? data.threads : [];
      browserState.threads = append ? browserState.threads.concat(page) : page;
      browserState.offset += page.length;
      browserState.hasMore = page.length === PAGE_SIZE;
      browserState.loading = false;
      updateSummary();
      renderThreadList(browserState.threads);
      updateSelectionControls();
      if (!browserState.activeThreadId) {
        setIdlePreview(browserState.threads);
      }
    } catch (err) {
      browserState.loading = false;
      setSummary('Failed to load chat history.');
      if (list) list.innerHTML = `<div class="chat-history-empty-warning">${esc(err?.message || String(err))}</div>`;
    }
  }

  async function reloadSelected() {
    if (!browserState.activeThreadId) return;
    const thread = browserState.threads.find(item => item.id === browserState.activeThreadId);
    if (!thread) {
      browserState.activeThreadId = null;
      return;
    }
    await selectThread(thread, browserState.threads);
  }

  function openModal() {
    ensureStyles();
    const modal = ensureModal();
    modal.classList.remove('hidden');
    loadThreads();
  }

  function closeModal() {
    document.getElementById('chatHistoryBrowserModal')?.classList.add('hidden');
  }

  function injectButton() {
    if (document.getElementById('chatHistoryBrowseBtn')) return true;
    const footer = document.querySelector('.sidebar-footer');
    if (!footer) return false;
    const btn = document.createElement('button');
    btn.id = 'chatHistoryBrowseBtn';
    btn.className = 'sidebar-footer-btn';
    btn.type = 'button';
    btn.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 8h10M7 12h10M7 16h6"/></svg>
      Browse chats
    `;
    btn.addEventListener('click', openModal);
    const settings = document.getElementById('settingsBtn');
    footer.insertBefore(btn, settings || footer.firstChild);
    return true;
  }

  function init() {
    ensureStyles();
    window.addEventListener('chat-history:updated', async () => {
      const isOpen = !document.getElementById('chatHistoryBrowserModal')?.classList.contains('hidden');
      await loadThreads();
      if (isOpen) await reloadSelected();
    });
    if (injectButton()) return;
    const observer = new MutationObserver(() => {
      if (injectButton()) observer.disconnect();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => observer.disconnect(), 10000);
  }

  window.NotionAI = window.NotionAI || {};
  window.NotionAI.ChatHistoryBrowser = {
    refresh: () => loadThreads(),
    reloadSelected,
    open: openModal
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
