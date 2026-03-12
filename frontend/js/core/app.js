/**
 * Application Entry Point
 * Initializes the application and binds all event handlers
 */

// Initialize namespace
window.NotionAI = window.NotionAI || {};

// Global STATE for backward compatibility
const STATE = window.NotionAI.Core.State.getState();
let memoryDegradedNotified = false;

/**
 * Main application initialization
 */
function init() {
    // Initialize storage
    window.NotionAI.Chat.Storage.loadChats();
    window.NotionAI.Chat.Storage.saveChats();

    // Initialize theme
    window.NotionAI.UI.Theme.init();

    // Load models
    window.NotionAI.API.Models.loadModels();

    // Render initial UI
    window.NotionAI.Chat.Manager.renderChatList();
    updateWelcomeGreeting();

    // Bind event listeners
    bindEventListeners();

    // Initialize model dropdown
    populateModels();

    // Start new chat if none selected
    if (!STATE.currentChatId) {
        window.NotionAI.Chat.Manager.startNewChat();
    }
}

/**
 * Binds all event listeners
 */
function bindEventListeners() {
    // Theme toggle
    document.getElementById('themeToggleBtn').addEventListener('click', () => {
        window.NotionAI.UI.Theme.toggle();
    });

    // New chat
    document.getElementById('newChatBtn').addEventListener('click', () => {
        window.NotionAI.Chat.Manager.startNewChat();
    });

    // Sidebar
    document.getElementById('openSidebarBtn').addEventListener('click', () => {
        window.NotionAI.UI.Sidebar.open();
    });
    document.getElementById('closeSidebarBtn').addEventListener('click', () => {
        window.NotionAI.UI.Sidebar.close();
    });
    document.getElementById('mobileBackdrop').addEventListener('click', () => {
        window.NotionAI.UI.Sidebar.close();
    });

    // Input
    document.getElementById('chatInput').addEventListener('input', () => {
        window.NotionAI.UI.Input.autoResize();
    });
    document.getElementById('chatInput').addEventListener('keydown', (e) => {
        window.NotionAI.UI.Input.handleKeydown(e, handleSend);
    });
    document.getElementById('sendBtn').addEventListener('click', handleSend);

    // Memory banner
    document.getElementById('memoryBannerClose').addEventListener('click', () => {
        document.getElementById('memoryBanner').classList.add('hidden');
    });

    // Settings
    document.getElementById('settingsBtn').addEventListener('click', () => {
        window.NotionAI.API.Settings.open();
    });
    document.getElementById('cancelSettingsBtn').addEventListener('click', () => {
        window.NotionAI.API.Settings.close();
    });
    document.getElementById('saveSettingsBtn').addEventListener('click', () => {
        window.NotionAI.API.Settings.save();
    });

    // Rename modal
    document.getElementById('cancelRenameBtn').addEventListener('click', () => {
        window.NotionAI.UI.Modal.closeRenameModal();
    });
    document.getElementById('saveRenameBtn').addEventListener('click', () => {
        window.NotionAI.UI.Modal.saveRename();
    });
    document.getElementById('renameModalInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            window.NotionAI.UI.Modal.saveRename();
        }
        if (e.key === 'Escape') {
            window.NotionAI.UI.Modal.closeRenameModal();
        }
    });

    // Model dropdown
    document.getElementById('modelTriggerBtn').addEventListener('click', (e) => {
        e.stopPropagation();
        toggleModelDropdown();
    });

    document.addEventListener('click', (e) => {
        const dropdown = document.getElementById('customModelDropdown');
        if (!dropdown.contains(e.target) && e.target.id !== 'modelTriggerBtn') {
            dropdown.classList.remove('open');
        }
    });
}

/**
 * Populates model dropdown with available models
 */
function populateModels() {
    const modelList = document.getElementById('simpleModelList');
    modelList.innerHTML = '';

    const models = window.NotionAI.API.Models.getAvailableModels();
    const currentModel = window.NotionAI.API.Models.getCurrentModel();

    models.forEach(model => {
        const isSelected = model.id === currentModel;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'w-full text-left py-2 px-3 rounded-md hover:bg-black/5 dark:hover:bg-white/5 text-[14px] transition-colors flex justify-between items-center group';

        const contentWrapper = document.createElement('div');
        contentWrapper.className = 'flex flex-col items-start gap-0.5';

        const titleRow = document.createElement('div');
        titleRow.className = 'flex items-center gap-2';

        const labelSpan = document.createElement('span');
        labelSpan.textContent = model.label;
        if (isSelected) {
            labelSpan.className = 'font-medium';
        }
        titleRow.appendChild(labelSpan);

        // Add Beta badge for Gemini 3.1 and GPT 5.4
        const needsBeta = model.label.toLowerCase().includes('gemini') || model.label.toLowerCase().includes('5.4');
        if (needsBeta) {
            const betaBadge = document.createElement('span');
            betaBadge.className = 'model-beta-badge';
            betaBadge.textContent = 'Beta';
            titleRow.appendChild(betaBadge);
        }

        contentWrapper.appendChild(titleRow);

        // Add descriptions
        if (model.label.toLowerCase().includes('sonnet') && model.label.includes('4.6')) {
            const desc = document.createElement('div');
            desc.className = 'model-desc';
            desc.textContent = 'Most efficient for everyday tasks';
            contentWrapper.appendChild(desc);
        } else if (model.label.toLowerCase().includes('gemini')) {
            const desc = document.createElement('div');
            desc.className = 'model-desc';
            desc.textContent = 'Smart but Think longer';
            contentWrapper.appendChild(desc);
        }

        btn.appendChild(contentWrapper);

        if (isSelected) {
            const checkIcon = document.createElement('span');
            checkIcon.className = 'text-blue-500';
            checkIcon.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
            btn.appendChild(checkIcon);
        } else {
            const emptySpace = document.createElement('span');
            emptySpace.className = 'opacity-0 scale-75 group-hover:opacity-20 transition-all';
            emptySpace.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
            btn.appendChild(emptySpace);
        }

        btn.onclick = (e) => {
            e.stopPropagation();
            handleModelSelect(model.id, model.label);
        };

        modelList.appendChild(btn);
    });
}

/**
 * Handles model selection
 * @param {string} modelId - Model ID
 * @param {string} label - Model label
 */
function handleModelSelect(modelId, label) {
    window.NotionAI.API.Models.setCurrentModel(modelId, label);
    document.getElementById('modelTriggerText').textContent = label;
    document.getElementById('customModelDropdown').classList.remove('open');
    populateModels();
}

/**
 * Toggles model dropdown visibility
 */
function toggleModelDropdown() {
    document.getElementById('customModelDropdown').classList.toggle('open');
}

/**
 * Handles sending chat messages
 */
async function handleSend() {
    if (STATE.isGenerating) return;

    const text = window.NotionAI.UI.Input.getValue();
    if (!text) return;

    // Get or create chat
    let chat = STATE.chats.find(c => c.id === STATE.currentChatId);
    const isNewChat = !chat;

    if (isNewChat) {
        chat = {
            id: STATE.currentChatId,
            title: text.length > 12 ? text.substring(0, 12) + '...' : text,
            messages: [],
            conversationId: null
        };
        STATE.chats.push(chat);

        document.getElementById('headerTitle').textContent = chat.title;
        document.getElementById('headerTitle').classList.remove('opacity-0');
    }

    // Update UI
    window.NotionAI.UI.Input.clear();
    document.getElementById('welcomeScreen').classList.add('hidden');

    const inputWrapper = document.getElementById('inputAreaWrapper');
    inputWrapper.classList.remove('initial-state-container');
    inputWrapper.classList.add('chat-state-container');

    const selectorContainer = document.querySelector('.model-selector-container');
    if (selectorContainer) {
        selectorContainer.classList.remove('dropdown-down');
        selectorContainer.classList.add('dropdown-up');
    }

    document.getElementById('inputBgMask').classList.remove('opacity-0');
    document.getElementById('inputGradientMask').classList.remove('opacity-0');

    // Add user message
    chat.messages.push({ role: 'user', content: text });
    window.NotionAI.Chat.Renderer.appendMessage('user', text, true);
    window.NotionAI.Chat.Storage.saveChats();
    window.NotionAI.Chat.Manager.renderChatList();
    window.NotionAI.Utils.DOM.scrollToBottom();

    // Get selected model
    const selectedModel = window.NotionAI.API.Models.getCurrentModel();
    const selectedModelDisplayName = window.NotionAI.API.Models.getCurrentModelLabel();

    // Create AI message wrapper
    const aiWrapper = window.NotionAI.Chat.Renderer.appendMessage('assistant', '', false, selectedModelDisplayName);
    window.NotionAI.Utils.DOM.scrollToBottom();

    // Set generating state
    STATE.isGenerating = true;
    window.NotionAI.UI.Input.disable();

    try {
        // Stream response
        const result = await window.NotionAI.Chat.Streaming.streamResponse(chat, selectedModel, aiWrapper);

        // Save AI message
        const normalizedSearch = window.NotionAI.Utils.Validation.normalizeSearchPayload(result.searchState);
        const hasThinking = result.thinkingText.trim().length > 0;
        const hasSearch = (normalizedSearch.queries.length + normalizedSearch.sources.length) > 0;

        if (result.fullAiReply.trim()) {
            window.NotionAI.Chat.Renderer.updateAIMessage(aiWrapper, result.fullAiReply, true);
            chat.messages.push({
                role: 'assistant',
                content: result.fullAiReply,
                thinking: result.thinkingText,
                search: normalizedSearch,
                modelDisplayName: selectedModelDisplayName
            });
            window.NotionAI.Chat.Storage.saveChats();
        } else if (hasThinking || hasSearch) {
            window.NotionAI.Chat.Renderer.updateAIMessage(aiWrapper, '*No visible response received.*', true);
            chat.messages.push({
                role: 'assistant',
                content: '',
                thinking: result.thinkingText,
                search: normalizedSearch,
                modelDisplayName: selectedModelDisplayName
            });
            window.NotionAI.Chat.Storage.saveChats();
        } else {
            window.NotionAI.Chat.Renderer.updateAIMessage(aiWrapper, '*No visible response received.*', true);
        }

    } catch (err) {
        if (err.name !== 'AbortError') {
            console.error('API Error:', err);
        }
    } finally {
        STATE.isGenerating = false;
        window.NotionAI.UI.Input.enable();
        window.NotionAI.UI.Input.focus();
        STATE.controller = null;
    }
}

/**
 * Updates welcome greeting based on time of day
 */
function updateWelcomeGreeting() {
    const greetingEl = document.getElementById('welcomeGreeting');
    if (!greetingEl) return;

    // Get current time in China Standard Time (UTC+8)
    const now = new Date();
    const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
    const cstDate = new Date(utc + (3600000 * 8));
    const hour = cstDate.getHours();
    const minute = cstDate.getMinutes();
    const timeStr = hour + minute / 60;

    let greeting = window.NotionAI.Core.Constants.GREETINGS.GOLDEN_HOUR;
    if (timeStr >= 5 && timeStr < 9) {
        greeting = window.NotionAI.Core.Constants.GREETINGS.EARLY_MORNING;
    } else if (timeStr >= 9 && timeStr < 11.5) {
        greeting = window.NotionAI.Core.Constants.GREETINGS.MORNING;
    } else if (timeStr >= 11.5 && timeStr < 13.5) {
        greeting = window.NotionAI.Core.Constants.GREETINGS.MIDDAY;
    } else if (timeStr >= 13.5 && timeStr < 17) {
        greeting = window.NotionAI.Core.Constants.GREETINGS.AFTERNOON;
    } else if (timeStr >= 17 && timeStr < 19) {
        greeting = window.NotionAI.Core.Constants.GREETINGS.GOLDEN_HOUR;
    } else if (timeStr >= 19 && timeStr < 22) {
        greeting = window.NotionAI.Core.Constants.GREETINGS.EVENING;
    } else if (timeStr >= 22 || timeStr < 1) {
        greeting = window.NotionAI.Core.Constants.GREETINGS.NIGHT_OWL;
    } else if (timeStr >= 1 && timeStr < 5) {
        greeting = window.NotionAI.Core.Constants.GREETINGS.LATE_NIGHT;
    }

    greetingEl.textContent = greeting;
}

// Update greeting every minute
setInterval(updateWelcomeGreeting, 60000);

// Initialize app when DOM is ready
window.addEventListener('DOMContentLoaded', init);
