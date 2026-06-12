(() => {
  const THREADS_ENDPOINT = '/v1/chat-history/threads';
  const DELETE_ENDPOINT = '/v1/chat-history/threads/delete';
  const PAGE_SIZE = 50;
  const BULK_DELETE_SIZE = 200;
  const REMOTE_ID_PREFIX = 'remote-chat-history:';
  const state = {
    threads: [],
    selectedIds: new Set(),
    offset: 0,
    hasMore: true,
    loading: false,
    deleting: false,
    activeThreadId: null,
    patched: false,
    showDuplicatesOnly: false,
    hydrating: false
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

  function esc(value) {
    const node = document.createElement('div');
    node.textContent = value == null ? '' : String(value);
    return node.innerHTML;
  }

  function ensureStyles() {
    if (document.getElementById('chatHistoryMainStyles')) return;
    const style = document.createElement('style');
    style.id = 'chatHistoryMainStyles';
    style.textContent = `
      .chat-section-header{position:sticky;top:0;background:var(--bg-sidebar);z-index:11;padding:12px 16px 4px;line-height:1.2}
      .chat-history-main-day{font-size:10px;text-transform:uppercase;color:var(--text-tertiary);letter-spacing:.08em;padding:8px 16px 3px;display:flex;justify-content:space-between;align-items:center}
      .chat-history-main-day-hydrate{background:none;border:none;color:var(--accent,#7c3aed);font-size:9px;cursor:pointer;padding:0;text-transform:none;letter-spacing:normal}
      .chat-history-main-day-hydrate:hover:not(:disabled){text-decoration:underline}
      .chat-history-main-day-hydrate:disabled{opacity:0.5;cursor:not-allowed}
      .chat-history-main-toolbar{position:sticky;top:29px;background:var(--bg-sidebar);z-index:10;display:flex;gap:6px;align-items:center;padding:3px 12px 7px;flex-wrap:wrap;border-bottom:1px solid var(--border)}
      .chat-history-main-toolbar button{border:1px solid var(--border);background:transparent;color:var(--text-secondary);border-radius:4px;font-size:11px;padding:4px 6px;line-height:1.1}
      .chat-history-main-toolbar button:hover:not(:disabled){background:var(--bg-hover);color:var(--text)}
      .chat-history-main-toolbar button:disabled{opacity:.45;cursor:not-allowed}
      .chat-history-main-toolbar label{font-size:11px;color:var(--text-secondary);display:flex;align-items:center;gap:4px;cursor:pointer;user-select:none}
      .chat-history-main-toolbar label input{margin:0;cursor:pointer}
      .chat-history-main-summary{width:100%;font-size:10px;color:var(--text-tertiary);padding:0 1px}
      .chat-history-main-delete{color:#a94442!important;border-color:#a94442!important}
      .chat-item.chat-history-main-item{align-items:flex-start;gap:8px;padding-top:7px;padding-bottom:7px}
      .chat-history-main-checkbox{margin-top:4px;flex-shrink:0}
      .chat-history-main-text{min-width:0;flex:1;display:flex;flex-direction:column;gap:2px}
      .chat-history-main-meta{font-size:10px;color:var(--text-tertiary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .chat-history-main-dot{width:7px;height:7px;border-radius:999px;margin-top:6px;flex-shrink:0;background:var(--text-tertiary);opacity:.7}
      .chat-history-main-dot.hydrated{background:#2e7d32;opacity:1}
      .chat-history-main-dot.hydrating{background:#7c3aed;opacity:1;animation:chat-dot-pulse 1s infinite alternate}
      @keyframes chat-dot-pulse{0%{opacity:.3}100%{opacity:1}}
      .chat-history-main-empty{font-size:12px;color:var(--text-tertiary);padding:8px 12px;line-height:1.4}
      .chat-history-main-status{max-width:720px;margin:32px auto;padding:0 24px;color:var(--text-secondary);font-size:14px;line-height:1.6}
      .chat-history-steps{max-width:720px;margin:18px auto;color:var(--text-secondary);font-size:13px}
      .chat-history-steps summary{cursor:pointer;display:flex;align-items:center;gap:8px;width:max-content;list-style:none}
      .chat-history-steps summary::-webkit-details-marker{display:none}
      .chat-history-steps summary::after{content:'›';font-size:20px;line-height:1;transform:translateY(-1px)}
      .chat-history-steps[open] summary::after{transform:rotate(90deg)}
      .chat-history-step-list{margin-top:10px;border-left:1px solid var(--border);padding-left:14px;display:flex;flex-direction:column;gap:8px}
      .chat-history-step-item{color:var(--text-tertiary);font-size:12px;line-height:1.4}
      .chat-history-step-item strong{color:var(--text-secondary);font-weight:500}
    `;
    document.head.appendChild(style);
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
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  function setInputArchivedMode(enabled) {
    const input = document.getElementById('chatInput');
    const send = document.getElementById('sendBtn');
    if (input) {
      if (!input.dataset.localPlaceholder) input.dataset.localPlaceholder = input.placeholder || '';
      input.disabled = enabled;
      input.placeholder = enabled ? 'Archived chat selected' : input.dataset.localPlaceholder;
    }
    if (send) send.disabled = enabled;
  }

  function clearRemoteSelection() {
    state.activeThreadId = null;
    setInputArchivedMode(false);
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

  async function postJson(path, body = {}) {
    const response = await fetch(`${getBaseUrl()}${path}`, {
      method: 'POST',
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

  function renderStatus(message) {
    document.getElementById('welcomeScreen')?.classList.add('hidden');
    const container = document.getElementById('chatContainer');
    if (!container) return;
    container.innerHTML = `<div class="chat-history-main-status">${esc(message)}</div>`;
  }

  function renderMessages(thread) {
    const container = document.getElementById('chatContainer');
    if (!container) return;
    container.innerHTML = '';
    const messages = Array.isArray(thread?.messages) ? thread.messages : [];
    if (!messages.length) {
      renderStatus('This archived thread has no hydrated messages yet.');
      return;
    }
    const appendSteps = () => {
      const steps = Array.isArray(thread?.steps) ? thread.steps : [];
      if (!steps.length) return;
      const details = document.createElement('details');
      details.className = 'chat-history-steps';
      const summary = document.createElement('summary');
      summary.textContent = `${steps.length} step${steps.length === 1 ? '' : 's'}`;
      const list = document.createElement('div');
      list.className = 'chat-history-step-list';
      steps.forEach(step => {
        const item = document.createElement('div');
        item.className = 'chat-history-step-item';
        const label = document.createElement('strong');
        label.textContent = step.label || step.type || 'Step';
        item.appendChild(label);
        if (step.detail) item.appendChild(document.createTextNode(` · ${step.detail}`));
        list.appendChild(item);
      });
      details.appendChild(summary);
      details.appendChild(list);
      container.appendChild(details);
    };
    let insertedSteps = false;
    messages.forEach((message, index) => {
      const role = String(message.role || '').toLowerCase() === 'user' ? 'user' : 'assistant';
      window.NotionAI.Chat.Renderer.appendMessage(role, message.text || '', true, 'Remote history');
      if (!insertedSteps && (role === 'user' || index === messages.length - 1)) {
        appendSteps();
        insertedSteps = true;
      }
    });
    window.NotionAI.Utils.DOM.scrollToBottom();
  }

  function updateThread(threadId, updates) {
    const thread = state.threads.find(item => item.id === threadId);
    if (thread) Object.assign(thread, updates);
  }

  function pruneSelectionToLoadedThreads() {
    const loadedIds = new Set(state.threads.map(thread => thread.id));
    for (const id of Array.from(state.selectedIds)) {
      if (!loadedIds.has(id)) state.selectedIds.delete(id);
    }
  }

  function getTitleCounts() {
    const counts = {};
    for (const thread of state.threads) {
      const title = String(thread.title || '').trim().toLowerCase();
      if (!title) continue;
      counts[title] = (counts[title] || 0) + 1;
    }
    return counts;
  }

  function matchesFilter(thread, titleCounts) {
    if (state.showDuplicatesOnly) {
      const title = String(thread.title || '').trim().toLowerCase();
      if (!title || (titleCounts[title] || 0) <= 1) {
        return false;
      }
    }
    const searchInput = document.getElementById('searchInput');
    const query = (searchInput ? searchInput.value : '').trim().toLowerCase();
    if (!query) return true;
    const haystack = [
      thread?.id,
      thread?.title,
      thread?.first_message_preview,
      thread?.last_message_preview,
      thread?.created_time,
      thread?.last_edited_time,
      thread?.updated_at
    ].map(value => String(value || '').toLowerCase()).join('\n');
    return haystack.includes(query);
  }

  function getVisibleThreads() {
    const titleCounts = getTitleCounts();
    return state.threads.filter(t => matchesFilter(t, titleCounts));
  }

  function selectRemoteCheckbox(threadId, checked) {
    if (checked) state.selectedIds.add(threadId);
    else state.selectedIds.delete(threadId);
    window.NotionAI?.Chat?.Manager?.renderChatList?.();
  }

  async function loadInitialRemoteThreads() {
    if (state.loading) return;
    state.loading = true;
    state.offset = 0;
    state.hasMore = true;
    state.threads = [];
    window.NotionAI?.Chat?.Manager?.renderChatList?.();
    try {
      const data = await fetchJson(`${THREADS_ENDPOINT}?limit=${PAGE_SIZE}&offset=0`);
      const page = Array.isArray(data?.threads) ? data.threads : [];
      state.threads = page.filter(t => t?.id);
      state.offset = page.length;
      state.hasMore = page.length === PAGE_SIZE;
      pruneSelectionToLoadedThreads();
    } catch (err) {
      console.warn('Unable to load initial remote threads', err);
      renderStatus(`Unable to load remote chats: ${err?.message || String(err)}`);
    } finally {
      state.loading = false;
      window.NotionAI?.Chat?.Manager?.renderChatList?.();
    }
  }

  async function loadNextBatch() {
    if (state.loading || !state.hasMore) return;
    state.loading = true;
    const chatList = document.getElementById('chatList');
    const savedScrollTop = chatList ? chatList.scrollTop : 0;
    window.NotionAI?.Chat?.Manager?.renderChatList?.();
    try {
      const data = await fetchJson(`${THREADS_ENDPOINT}?limit=${PAGE_SIZE}&offset=${state.offset}`);
      const page = Array.isArray(data?.threads) ? data.threads : [];
      const seen = new Set(state.threads.map(t => t.id));
      const newThreads = [];
      for (const thread of page) {
        if (thread?.id && !seen.has(thread.id)) {
          newThreads.push(thread);
        }
      }
      state.threads = [...state.threads, ...newThreads];
      state.offset += page.length;
      state.hasMore = page.length === PAGE_SIZE;
      pruneSelectionToLoadedThreads();
    } catch (err) {
      console.warn('Unable to load next batch of remote threads', err);
    } finally {
      state.loading = false;
      window.NotionAI?.Chat?.Manager?.renderChatList?.();
      if (chatList) {
        chatList.scrollTop = savedScrollTop;
      }
    }
  }

  function handleScroll(e) {
    const el = e.target;
    if (state.loading || !state.hasMore) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 50) {
      loadNextBatch();
    }
  }

  async function selectFilteredRemoteThreads() {
    if (state.loading || state.deleting) return;
    const visibleThreads = getVisibleThreads();
    for (const thread of visibleThreads) {
      if (thread?.id) state.selectedIds.add(thread.id);
    }
    window.NotionAI?.Chat?.Manager?.renderChatList?.();
  }

  function clearSelectedRemoteThreads() {
    state.selectedIds.clear();
    window.NotionAI?.Chat?.Manager?.renderChatList?.();
  }

  function showConfirmDialog(message, onConfirm) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay fade-in';
    overlay.style.zIndex = '999999';

    const content = document.createElement('div');
    content.className = 'modal-content modal-sm';

    const header = document.createElement('div');
    header.className = 'modal-header';
    const title = document.createElement('h3');
    title.textContent = 'Confirm Delete';
    header.appendChild(title);

    const body = document.createElement('div');
    body.className = 'modal-body';
    body.style.fontSize = '13px';
    body.style.lineHeight = '1.4';
    body.style.color = 'var(--text-secondary)';
    body.textContent = message;

    const footer = document.createElement('div');
    footer.className = 'modal-footer';

    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'btn-secondary';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.addEventListener('click', () => {
      document.body.removeChild(overlay);
    });

    const confirmBtn = document.createElement('button');
    confirmBtn.type = 'button';
    confirmBtn.className = 'btn-primary';
    confirmBtn.style.backgroundColor = '#a94442';
    confirmBtn.style.borderColor = '#a94442';
    confirmBtn.style.color = '#ffffff';
    confirmBtn.textContent = 'Delete';
    confirmBtn.addEventListener('click', () => {
      document.body.removeChild(overlay);
      onConfirm();
    });

    footer.appendChild(cancelBtn);
    footer.appendChild(confirmBtn);

    content.appendChild(header);
    content.appendChild(body);
    content.appendChild(footer);
    overlay.appendChild(content);

    document.body.appendChild(overlay);
  }

  async function deleteSelectedRemoteThreads() {
    const ids = Array.from(state.selectedIds);
    if (!ids.length || state.deleting) return;

    showConfirmDialog(
      `Delete ${ids.length} selected remote chat(s)? Confirmed deletes will also be removed from the local archive.`,
      async () => {
        state.deleting = true;
        window.NotionAI?.Chat?.Manager?.renderChatList?.();
        const successIds = [];
        const failed = [];
        try {
          for (let index = 0; index < ids.length; index += BULK_DELETE_SIZE) {
            const batch = ids.slice(index, index + BULK_DELETE_SIZE);
            const result = await postJson(DELETE_ENDPOINT, {
              thread_ids: batch,
              account_index: 0,
              remote: true,
              local: true
            });
            if (Array.isArray(result?.results?.success)) successIds.push(...result.results.success);
            if (Array.isArray(result?.results?.failed)) failed.push(...result.results.failed);
          }

          const successSet = new Set(successIds);
          state.threads = state.threads.filter(thread => !successSet.has(thread.id));
          state.selectedIds.clear();
          for (const failedItem of failed) {
            if (failedItem?.thread_id) state.selectedIds.add(failedItem.thread_id);
          }
          if (state.activeThreadId && successSet.has(state.activeThreadId)) {
            clearRemoteSelection();
            renderStatus('Deleted selected archived chat.');
          }
          const suffix = failed.length ? ` ${failed.length} failed and remain selected.` : '';
          console.info(`Deleted ${successIds.length} remote chat(s).${suffix}`, { successIds, failed });
        } catch (err) {
          console.warn('Unable to delete selected remote chats', err);
          renderStatus(`Bulk delete failed: ${err?.message || String(err)}`);
        } finally {
          state.deleting = false;
          window.NotionAI?.Chat?.Manager?.renderChatList?.();
        }
      }
    );
  }

  async function hydrateThreads(threadsToHydrate) {
    if (state.hydrating) return;
    state.hydrating = true;
    window.NotionAI?.Chat?.Manager?.renderChatList?.();
    try {
      for (const thread of threadsToHydrate) {
        if (thread.hydrated || Number(thread.message_count || 0) > 0) continue;
        updateThread(thread.id, { hydrating: true });
        window.NotionAI?.Chat?.Manager?.renderChatList?.();
        try {
          const hydration = await postJson(`${THREADS_ENDPOINT}/${encodeURIComponent(thread.id)}/hydrate`);
          const count = Number(hydration?.thread?.message_count ?? thread.message_count ?? 0);
          updateThread(thread.id, {
            message_count: count,
            hydrated: Boolean(hydration?.thread?.hydrated || count > 0),
            hydrating: false
          });
        } catch (err) {
          console.warn(`Failed to hydrate thread ${thread.id}`, err);
          updateThread(thread.id, { hydrating: false });
        }
      }
    } finally {
      state.hydrating = false;
      window.NotionAI?.Chat?.Manager?.renderChatList?.();
    }
  }

  async function selectRemoteThread(thread) {
    if (window.NotionAI?.Core?.State?.get?.('isGenerating')) return;
    state.activeThreadId = thread.id;
    window.NotionAI.Core.State.set('currentChatId', `${REMOTE_ID_PREFIX}${thread.id}`);
    setInputArchivedMode(true);
    document.getElementById('welcomeScreen')?.classList.add('hidden');
    const header = document.getElementById('headerTitle');
    if (header) {
      header.textContent = thread.title || thread.id;
      header.classList.remove('hidden');
    }
    renderStatus(`Loading ${thread.title || thread.id}...`);
    if (window.innerWidth < 768) window.NotionAI.UI.Sidebar.close();
    window.NotionAI.Chat.Manager.renderChatList();

    try {
      const hydration = await postJson(`${THREADS_ENDPOINT}/${encodeURIComponent(thread.id)}/hydrate`);
      const count = Number(hydration?.thread?.message_count ?? thread.message_count ?? 0);
      updateThread(thread.id, { message_count: count, hydrated: Boolean(hydration?.thread?.hydrated || count > 0) });
      window.NotionAI.Chat.Manager.renderChatList();
      const hydratedThread = await fetchJson(`${THREADS_ENDPOINT}/${encodeURIComponent(thread.id)}`);
      updateThread(thread.id, {
        message_count: Number(hydratedThread?.message_count || 0),
        hydrated: Boolean(hydratedThread?.hydrated || Number(hydratedThread?.message_count || 0) > 0),
        first_message_preview: hydratedThread?.first_message_preview,
        last_message_preview: hydratedThread?.last_message_preview
      });
      renderMessages(hydratedThread);
    } catch (err) {
      renderStatus(err?.message || String(err));
    } finally {
      window.NotionAI.Chat.Manager.renderChatList();
    }
  }

  async function reloadSelectedRemoteThread() {
    if (!state.activeThreadId) return;
    const thread = state.threads.find(item => item.id === state.activeThreadId);
    if (!thread) return;
    await selectRemoteThread(thread);
  }
  
  function handleRemoteChatClick(e, thread) {
    if (window.NotionAI?.Core?.State?.get?.('isGenerating')) return;

    const threads = getVisibleThreads();

    if (e.ctrlKey || e.metaKey) {
      if (state.selectedIds.has(thread.id)) {
        state.selectedIds.delete(thread.id);
        if (state.activeThreadId === thread.id) {
          const loadedArray = Array.from(state.selectedIds);
          const nextActiveId = loadedArray[loadedArray.length - 1] || null;
          if (nextActiveId) {
            const nextActiveThread = state.threads.find(t => t.id === nextActiveId);
            if (nextActiveThread) selectRemoteThread(nextActiveThread);
          } else {
            clearRemoteSelection();
          }
        } else {
          window.NotionAI?.Chat?.Manager?.renderChatList?.();
        }
      } else {
        state.selectedIds.add(thread.id);
        selectRemoteThread(thread);
      }
    } else if (e.shiftKey) {
      const endIdx = threads.findIndex(t => t.id === thread.id);
      let startIdx = threads.findIndex(t => t.id === state.activeThreadId);
      if (startIdx === -1) startIdx = 0;

      const minIdx = Math.min(startIdx, endIdx);
      const maxIdx = Math.max(startIdx, endIdx);
      for (let i = minIdx; i <= maxIdx; i++) {
        state.selectedIds.add(threads[i].id);
      }
      selectRemoteThread(thread);
    } else {
      state.selectedIds.clear();
      state.selectedIds.add(thread.id);
      selectRemoteThread(thread);
    }
  }

  function renderRemoteChats(chatList) {
    if (!chatList) return;
    const threads = getVisibleThreads();

    const searchInput = document.getElementById('searchInput');
    const isSearchActive = Boolean((searchInput ? searchInput.value : '').trim());

    if (!state.threads.length && !state.loading && !isSearchActive && !state.showDuplicatesOnly) return;

    const header = document.createElement('div');
    header.className = 'chat-section-header';
    header.textContent = 'REMOTE CHATS';
    chatList.appendChild(header);

    const toolbar = document.createElement('div');
    toolbar.className = 'chat-history-main-toolbar';

    const dupLabel = document.createElement('label');
    const dupCheckbox = document.createElement('input');
    dupCheckbox.type = 'checkbox';
    dupCheckbox.checked = state.showDuplicatesOnly;
    dupCheckbox.addEventListener('change', (e) => {
      state.showDuplicatesOnly = e.target.checked;
      window.NotionAI?.Chat?.Manager?.renderChatList?.();
    });
    dupLabel.appendChild(dupCheckbox);
    dupLabel.appendChild(document.createTextNode('Duplicates'));

    const selectedCount = state.selectedIds.size;
    const visibleCount = threads.length;

    const selectBtn = document.createElement('button');
    selectBtn.type = 'button';
    selectBtn.textContent = 'Select filtered';
    selectBtn.disabled = state.deleting || state.loading || !threads.length;
    selectBtn.title = 'Select every currently matching conversation.';
    selectBtn.addEventListener('click', event => {
      event.stopPropagation();
      selectFilteredRemoteThreads();
    });

    const clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.textContent = 'Clear';
    clearBtn.disabled = state.deleting || (!selectedCount && !isSearchActive && !state.showDuplicatesOnly);
    clearBtn.addEventListener('click', event => {
      event.stopPropagation();
      state.showDuplicatesOnly = false;
      if (searchInput) {
        searchInput.value = '';
        searchInput.dispatchEvent(new Event('input', { bubbles: true }));
      }
      clearSelectedRemoteThreads();
    });

    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'chat-history-main-delete';
    deleteBtn.textContent = selectedCount ? `Delete (${selectedCount})` : 'Delete';
    deleteBtn.disabled = state.deleting || !selectedCount;
    deleteBtn.addEventListener('click', event => {
      event.stopPropagation();
      deleteSelectedRemoteThreads();
    });

    const summary = document.createElement('div');
    summary.className = 'chat-history-main-summary';
    const filterText = (isSearchActive || state.showDuplicatesOnly) ? `${visibleCount} matched` : `${visibleCount} visible`;
    summary.textContent = `${filterText}; ${state.threads.length} loaded; ${selectedCount} selected`;

    toolbar.appendChild(dupLabel);
    toolbar.appendChild(selectBtn);
    toolbar.appendChild(clearBtn);
    toolbar.appendChild(deleteBtn);
    toolbar.appendChild(summary);
    chatList.appendChild(toolbar);

    if (state.loading && !state.threads.length) {
      const loading = document.createElement('div');
      loading.className = 'chat-history-main-status';
      loading.style.margin = '8px 12px';
      loading.style.padding = '0';
      loading.textContent = 'Loading remote chats...';
      chatList.appendChild(loading);
      return;
    }

    if (!threads.length) {
      const empty = document.createElement('div');
      empty.className = 'chat-history-main-empty';
      empty.textContent = (isSearchActive || state.showDuplicatesOnly)
        ? 'No remote chats match this filter.'
        : 'No remote chats are loaded.';
      chatList.appendChild(empty);
    }

    let currentDay = '';
    threads.forEach(thread => {
      const label = dayLabel(thread);
      if (label !== currentDay) {
        currentDay = label;
        const dayThreads = threads.filter(t => dayLabel(t) === label);
        const unhydratedDayThreads = dayThreads.filter(t => !t.hydrated && Number(t.message_count || 0) === 0);

        const day = document.createElement('div');
        day.className = 'chat-history-main-day';
        day.style.display = 'flex';
        day.style.justifyContent = 'space-between';
        day.style.alignItems = 'center';

        const labelSpan = document.createElement('span');
        labelSpan.textContent = label;
        day.appendChild(labelSpan);

        if (unhydratedDayThreads.length > 0) {
          const hydrateAllBtn = document.createElement('button');
          hydrateAllBtn.type = 'button';
          hydrateAllBtn.className = 'chat-history-main-day-hydrate';
          hydrateAllBtn.textContent = `Hydrate all (${unhydratedDayThreads.length})`;
          if (state.hydrating) {
            hydrateAllBtn.disabled = true;
            hydrateAllBtn.style.opacity = '0.5';
            hydrateAllBtn.style.cursor = 'not-allowed';
          }
          hydrateAllBtn.onclick = (e) => {
            e.stopPropagation();
            hydrateThreads(unhydratedDayThreads);
          };
          day.appendChild(hydrateAllBtn);
        }

        chatList.appendChild(day);
      }

      const item = document.createElement('div');
      const isSelected = state.selectedIds.has(thread.id);
      item.className = `chat-item chat-history-main-item${thread.id === state.activeThreadId ? ' active' : ''}${isSelected ? ' selected' : ''}`;
      item.onclick = (e) => handleRemoteChatClick(e, thread);

      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'chat-history-main-checkbox';
      checkbox.checked = state.selectedIds.has(thread.id);
      checkbox.title = 'Select for bulk delete';
      checkbox.addEventListener('click', event => {
        event.stopPropagation();
        selectRemoteCheckbox(thread.id, Boolean(event.target.checked));
      });

      const text = document.createElement('div');
      text.className = 'chat-history-main-text';

      const title = document.createElement('span');
      title.className = 'chat-item-title';
      title.textContent = thread.title || thread.id;

      const meta = document.createElement('span');
      meta.className = 'chat-history-main-meta';
      const count = Number(thread.message_count || 0);
      meta.textContent = count > 0 ? `${count} messages` : 'metadata only';

      const dot = document.createElement('span');
      if (thread.hydrating) {
        dot.className = 'chat-history-main-dot hydrating';
        dot.title = 'Hydrating...';
      } else {
        dot.className = `chat-history-main-dot${Boolean(thread.hydrated || count > 0) ? ' hydrated' : ''}`;
        dot.title = count > 0 ? 'Hydrated' : 'Metadata only';
      }

      text.appendChild(title);
      text.appendChild(meta);
      item.appendChild(checkbox);
      item.appendChild(text);
      item.appendChild(dot);
      chatList.appendChild(item);
    });

    if (state.loading && state.threads.length > 0) {
      const loadingIndicator = document.createElement('div');
      loadingIndicator.className = 'chat-history-main-status';
      loadingIndicator.style.margin = '8px 12px';
      loadingIndicator.style.padding = '0';
      loadingIndicator.textContent = 'Loading more chats...';
      chatList.appendChild(loadingIndicator);
    }
  }

  async function refresh() {
    await loadInitialRemoteThreads();
  }

  function patchChatManager() {
    const manager = window.NotionAI?.Chat?.Manager;
    if (!manager || state.patched) return false;
    const originalRender = manager.renderChatList.bind(manager);
    const originalStart = manager.startNewChat.bind(manager);
    const originalSelect = manager.selectChat.bind(manager);

    manager.renderChatList = function patchedRenderChatList(...args) {
      const chatList = document.getElementById('chatList');
      const savedScrollTop = chatList ? chatList.scrollTop : 0;

      originalRender(...args);

      const newChatList = document.getElementById('chatList');
      if (newChatList) {
        if (!newChatList.dataset.patchedScroll) {
          newChatList.dataset.patchedScroll = 'true';
          newChatList.addEventListener('scroll', handleScroll);
        }
        
        const searchInput = document.getElementById('searchInput');
        if (searchInput && !searchInput.dataset.patchedSearch) {
          searchInput.dataset.patchedSearch = 'true';
          searchInput.addEventListener('input', () => {
            window.NotionAI?.Chat?.Manager?.renderChatList?.();
          });
        }
      }

      renderRemoteChats(newChatList);

      if (newChatList) {
        newChatList.scrollTop = savedScrollTop;
      }
    };
    manager.startNewChat = function patchedStartNewChat(...args) {
      clearRemoteSelection();
      return originalStart(...args);
    };
    manager.selectChat = function patchedSelectChat(...args) {
      clearRemoteSelection();
      return originalSelect(...args);
    };

    state.patched = true;
    return true;
  }

  function init() {
    ensureStyles();
    if (!patchChatManager()) {
      setTimeout(init, 100);
      return;
    }
    window.addEventListener('chat-history:updated', async (event) => {
      await refresh();
      const hydrate = Boolean(event?.detail?.hydrate);
      if (hydrate) {
        await reloadSelectedRemoteThread();
      }
    });
    refresh();
  }

  window.NotionAI = window.NotionAI || {};
  window.NotionAI.ChatHistoryMain = {
    refresh,
    reloadSelectedRemoteThread,
    clearRemoteSelection,
    deleteSelectedRemoteThreads,
    clearSelectedRemoteThreads,
    selectFilteredRemoteThreads
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
