/**
 * Chat Manager Module — Notion AI Studio
 */

window.NotionAI = window.NotionAI || {};
window.NotionAI.Chat = window.NotionAI.Chat || {};

window.NotionAI.Chat.Manager = {
    startNewChat() {
        if (window.NotionAI.Core.State.get('isGenerating')) return;

        const currentChatId = Date.now().toString();
        window.NotionAI.Core.State.set('currentChatId', currentChatId);
        window.NotionAI.Core.State.set('selectedChatIds', [currentChatId]);

        document.getElementById('headerTitle').classList.add('hidden');
        document.getElementById('chatContainer').innerHTML = '';
        window.NotionAI.UI.Input.clear();

        const welcomeScreen = document.getElementById('welcomeScreen');
        welcomeScreen.classList.remove('hidden');

        if (window.innerWidth < 768) {
            window.NotionAI.UI.Sidebar.close();
        }

        window.NotionAI.UI.Input.focus();
        this.renderChatList();
    },

    selectChat(chatId) {
        if (window.NotionAI.Core.State.get('isGenerating')) return;

        const chats = window.NotionAI.Core.State.get('chats');
        const chat = chats.find(c => c.id === chatId);
        if (!chat) return;

        window.NotionAI.Core.State.set('currentChatId', chatId);
        const selected = window.NotionAI.Core.State.get('selectedChatIds') || [];
        if (!selected.includes(chatId)) {
            window.NotionAI.Core.State.set('selectedChatIds', [chatId]);
        }

        document.getElementById('welcomeScreen').classList.add('hidden');
        document.getElementById('chatContainer').innerHTML = '';

        document.getElementById('headerTitle').textContent = chat.title;
        document.getElementById('headerTitle').classList.remove('hidden');

        chat.messages.forEach(msg => {
            const wrapper = window.NotionAI.Chat.Renderer.appendMessage(
                msg.role,
                msg.content,
                true,
                msg.modelDisplayName || null
            );

            if (msg.role === 'assistant') {
                const restoredThinking = typeof msg.thinking === 'string' ? msg.thinking : '';
                const restoredSearch = window.NotionAI.Utils.Validation.normalizeSearchPayload(msg.search);

                if (restoredThinking.trim()) {
                    wrapper.thinkingText = restoredThinking;
                    window.NotionAI.Chat.Renderer.updateThinkingPanel(wrapper);
                }

                if ((restoredSearch.queries.length + restoredSearch.sources.length) > 0) {
                    wrapper.searchData = restoredSearch;
                    window.NotionAI.Chat.Renderer.updateSearchPanel(wrapper);
                }
            }
        });

        if (window.innerWidth < 768) {
            window.NotionAI.UI.Sidebar.close();
        }

        window.NotionAI.Utils.DOM.scrollToBottom();
        this.renderChatList();
    },

    handleChatClick(e, chatId) {
        if (window.NotionAI.Core.State.get('isGenerating')) return;
        const chats = window.NotionAI.Core.State.get('chats');
        const starred = chats.filter(c => c.starred).sort((a, b) => b.id - a.id);
        const recent = chats.filter(c => !c.starred).sort((a, b) => b.id - a.id);
        const searchVal = (document.getElementById('searchInput')?.value || '').trim().toLowerCase();
        const filter = searchVal ? c => c.title.toLowerCase().includes(searchVal) : null;
        
        const starredFiltered = filter ? starred.filter(filter) : starred;
        const recentFiltered = filter ? recent.filter(filter) : recent;
        const allRendered = [...starredFiltered, ...recentFiltered];
        
        let selected = [...(window.NotionAI.Core.State.get('selectedChatIds') || [])];
        
        if (e.ctrlKey || e.metaKey) {
            if (selected.includes(chatId)) {
                selected = selected.filter(id => id !== chatId);
                window.NotionAI.Core.State.set('selectedChatIds', selected);
                if (window.NotionAI.Core.State.get('currentChatId') === chatId) {
                    const nextActive = selected[selected.length - 1] || null;
                    if (nextActive) {
                        this.selectChat(nextActive);
                    } else {
                        this.startNewChat();
                    }
                } else {
                    this.renderChatList();
                }
            } else {
                selected.push(chatId);
                window.NotionAI.Core.State.set('selectedChatIds', selected);
                this.selectChat(chatId);
            }
        } else if (e.shiftKey) {
            const endIdx = allRendered.findIndex(c => c.id === chatId);
            let startIdx = allRendered.findIndex(c => c.id === window.NotionAI.Core.State.get('currentChatId'));
            if (startIdx === -1) startIdx = 0;
            
            const minIdx = Math.min(startIdx, endIdx);
            const maxIdx = Math.max(startIdx, endIdx);
            const newSelected = [];
            for (let i = minIdx; i <= maxIdx; i++) {
                newSelected.push(allRendered[i].id);
            }
            window.NotionAI.Core.State.set('selectedChatIds', newSelected);
            this.selectChat(chatId);
        } else {
            window.NotionAI.Core.State.set('selectedChatIds', [chatId]);
            this.selectChat(chatId);
        }
    },

    async deleteChat(chatId) {
        if (window.NotionAI.Core.State.get('isGenerating')) return;

        const selected = window.NotionAI.Core.State.get('selectedChatIds') || [];
        const targets = selected.includes(chatId) ? selected : [chatId];
        if (targets.length > 1) {
            if (!confirm(`Delete ${targets.length} selected chats?`)) return;
        } else {
            const chats = window.NotionAI.Core.State.get('chats');
            const chat = chats.find(c => c.id === chatId);
            if (!chat) return;
            if (!confirm(`Delete chat "${chat.title}"?`)) return;
        }

        for (const id of targets) {
            const chats = window.NotionAI.Core.State.get('chats');
            const chat = chats.find(c => c.id === id);
            if (chat) {
                if (chat.conversationId) {
                    try {
                        await window.NotionAI.API.Client.deleteConversation(chat.conversationId);
                    } catch (e) {
                        console.warn(`Failed to delete conversation ${chat.conversationId} on backend:`, e);
                    }
                }
                window.NotionAI.Chat.Storage.deleteChat(id);
            }
        }

        const newSelected = selected.filter(id => !targets.includes(id));
        window.NotionAI.Core.State.set('selectedChatIds', newSelected);

        const currentChatId = window.NotionAI.Core.State.get('currentChatId');
        if (targets.includes(currentChatId)) {
            if (newSelected.length > 0) {
                this.selectChat(newSelected[newSelected.length - 1]);
            } else {
                this.startNewChat();
            }
        } else {
            this.renderChatList();
        }
    },

    renameChat(chatId, newTitle) {
        window.NotionAI.Chat.Storage.updateChatTitle(chatId, newTitle);

        const currentChatId = window.NotionAI.Core.State.get('currentChatId');
        if (currentChatId === chatId) {
            document.getElementById('headerTitle').textContent = newTitle;
        }

        this.renderChatList();
    },

    toggleStar(chatId) {
        window.NotionAI.Chat.Storage.toggleStar(chatId);
        this.renderChatList();
    },

    renderChatList() {
        const chatList = document.getElementById('chatList');
        chatList.innerHTML = '';

        const chats = window.NotionAI.Core.State.get('chats');
        const currentChatId = window.NotionAI.Core.State.get('currentChatId');

        const starred = chats.filter(c => c.starred).sort((a, b) => b.id - a.id);
        const recent = chats.filter(c => !c.starred).sort((a, b) => b.id - a.id);

        const renderItems = (items) => {
            items.forEach(chat => {
                const item = document.createElement('div');
                const selected = window.NotionAI.Core.State.get('selectedChatIds') || [];
                const isSelected = selected.includes(chat.id);
                item.className = `chat-item${chat.id === currentChatId ? ' active' : ''}${isSelected ? ' selected' : ''}`;
                item.onclick = (e) => this.handleChatClick(e, chat.id);

                const title = document.createElement('span');
                title.className = 'chat-item-title';
                title.textContent = chat.title;

                const menuContainer = document.createElement('div');
                menuContainer.className = 'chat-dropdown-container';
                menuContainer.style.position = 'relative';
                menuContainer.style.display = 'flex';
                menuContainer.style.alignItems = 'center';

                const menuBtn = document.createElement('button');
                menuBtn.className = 'chat-item-menu-btn';
                menuBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="1.5"></circle><circle cx="6" cy="12" r="1.5"></circle><circle cx="18" cy="12" r="1.5"></circle></svg>';
                menuBtn.onclick = (e) => {
                    e.stopPropagation();
                    this.toggleChatDropdown(e, chat.id);
                };

                const dropdown = this._createDropdown(chat);

                menuContainer.appendChild(menuBtn);
                menuContainer.appendChild(dropdown);

                item.appendChild(title);
                item.appendChild(menuContainer);
                chatList.appendChild(item);
            });
        };

        if (starred.length > 0) {
            const header = document.createElement('div');
            header.className = 'chat-section-header';
            header.textContent = 'Starred';
            chatList.appendChild(header);
            renderItems(starred);
        }

        if (recent.length > 0) {
            const header = document.createElement('div');
            header.className = 'chat-section-header';
            header.textContent = 'Recents';
            chatList.appendChild(header);
            renderItems(recent);
        }
    },

    _createDropdown(chat) {
        const dropdown = document.createElement('div');
        dropdown.id = `dropdown-${chat.id}`;
        dropdown.className = 'custom-dropdown';

        const actions = [
            { action: 'star', label: chat.starred ? 'Unstar' : 'Star', icon: '⭐' },
            { action: 'rename', label: 'Rename', icon: '✏️' },
            { action: 'divider' },
            { action: 'delete', label: 'Delete', icon: '🗑️', danger: true },
        ];

        actions.forEach(a => {
            if (a.action === 'divider') {
                const div = document.createElement('div');
                div.className = 'dropdown-divider';
                dropdown.appendChild(div);
                return;
            }

            const btn = document.createElement('button');
            btn.className = `dropdown-item${a.danger ? ' danger' : ''}`;
            btn.textContent = `${a.icon} ${a.label}`;
            btn.onclick = (e) => {
                e.stopPropagation();
                this.closeChatDropdown();
                this.handleMenuAction(a.action, chat.id);
            };
            dropdown.appendChild(btn);
        });

        return dropdown;
    },

    handleMenuAction(action, chatId) {
        switch (action) {
            case 'star': this.toggleStar(chatId); break;
            case 'rename': window.NotionAI.UI.Modal.openRenameModal(chatId); break;
            case 'delete': this.deleteChat(chatId); break;
        }
    },

    toggleChatDropdown(e, chatId) {
        e.stopPropagation();
        if (this._activeDropdownId && this._activeDropdownId !== chatId) {
            this.closeChatDropdown();
        }
        const menu = document.getElementById(`dropdown-${chatId}`);
        if (menu) {
            if (menu.classList.contains('open')) {
                menu.classList.remove('open');
                this._activeDropdownId = null;
            } else {
                menu.classList.add('open');
                this._activeDropdownId = chatId;
            }
        }
    },

    closeChatDropdown() {
        if (this._activeDropdownId) {
            const menu = document.getElementById(`dropdown-${this._activeDropdownId}`);
            if (menu) menu.classList.remove('open');
            this._activeDropdownId = null;
        }
    },

    addSectionHeader(text) {
        const chatList = document.getElementById('chatList');
        const header = document.createElement('div');
        header.className = 'chat-section-header';
        header.textContent = text;
        chatList.appendChild(header);
    }
};

document.addEventListener('click', (e) => {
    if (!e.target.closest('.chat-dropdown-container')) {
        window.NotionAI.Chat.Manager.closeChatDropdown();
    }
});
