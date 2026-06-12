/**
 * Application Entry Point — Notion AI Studio
 */

window.NotionAI = window.NotionAI || {};

const STATE = window.NotionAI.Core.State.getState();
let memoryDegradedNotified = false;

// ─── Ambient Background ───────────────────────────────────────
const AmbientEngine = {
    canvas: null,
    ctx: null,
    particles: [],
    weatherType: 'default', // default | snow | rain | sunny | night
    animFrame: null,

    init() {
        this.canvas = document.getElementById('ambientCanvas');
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
        this._resize();
        window.addEventListener('resize', () => this._resize());

        // Determine weather from localStorage or auto
        const stored = localStorage.getItem('weatherTheme');
        if (stored && stored !== 'auto') {
            this.weatherType = stored;
        } else {
            this.weatherType = this._autoWeather();
        }

        this._createParticles();
        this._loop();
    },

    _resize() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
    },

    _autoWeather() {
        const h = new Date().getHours();
        if (h >= 6 && h < 18) return 'sunny';
        return 'night';
    },

    _createParticles() {
        this.particles = [];
        const count = this.weatherType === 'default' ? 30 :
                      this.weatherType === 'snow' ? 50 :
                      this.weatherType === 'rain' ? 80 :
                      this.weatherType === 'night' ? 40 : 20;

        for (let i = 0; i < count; i++) {
            this.particles.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height,
                size: Math.random() * 3 + 1,
                speedX: (Math.random() - 0.5) * 0.3,
                speedY: this.weatherType === 'rain' ? Math.random() * 3 + 2 :
                        this.weatherType === 'snow' ? Math.random() * 0.5 + 0.2 :
                        Math.random() * 0.15 + 0.05,
                opacity: Math.random() * 0.3 + 0.05,
                phase: Math.random() * Math.PI * 2,
            });
        }
    },

    _loop() {
        this.animFrame = requestAnimationFrame(() => this._loop());
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';

        this.particles.forEach(p => {
            p.x += p.speedX;
            p.y += p.speedY;
            p.phase += 0.01;

            // Wrap around
            if (p.y > this.canvas.height + 10) { p.y = -10; p.x = Math.random() * this.canvas.width; }
            if (p.x > this.canvas.width + 10) p.x = -10;
            if (p.x < -10) p.x = this.canvas.width + 10;

            this.ctx.beginPath();

            if (this.weatherType === 'rain') {
                // Rain lines
                this.ctx.moveTo(p.x, p.y);
                this.ctx.lineTo(p.x + 0.5, p.y + 8);
                this.ctx.strokeStyle = isDark ? `rgba(167,139,250,${p.opacity * 0.3})` : `rgba(139,92,246,${p.opacity * 0.2})`;
                this.ctx.lineWidth = 1;
                this.ctx.stroke();
            } else if (this.weatherType === 'night') {
                // Twinkling stars
                const twinkle = Math.sin(p.phase * 2) * 0.3 + 0.5;
                this.ctx.arc(p.x, p.y, p.size * 0.6, 0, Math.PI * 2);
                this.ctx.fillStyle = isDark ? `rgba(200,200,255,${twinkle * p.opacity})` : `rgba(139,92,246,${twinkle * p.opacity * 0.3})`;
                this.ctx.fill();
            } else {
                // Default / sunny / snow — soft circles
                this.ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
                const baseColor = isDark ? '167,139,250' : '139,92,246';
                this.ctx.fillStyle = `rgba(${baseColor},${p.opacity * (this.weatherType === 'snow' ? 0.5 : 0.15)})`;
                this.ctx.fill();
            }
        });
    },

    setWeather(type) {
        this.weatherType = type;
        localStorage.setItem('weatherTheme', type);
        this._createParticles();
    }
};

// Expose for external use
window.NotionAI.AmbientEngine = AmbientEngine;

// ─── Thinking Indicator ───────────────────────────────────────
let thinkingIndicatorEl = null;
let thinkingTimerInterval = null;
let thinkingStartTime = null;

function showThinkingIndicator() {
    removeThinkingIndicator();
    thinkingStartTime = Date.now();

    thinkingIndicatorEl = document.createElement('div');
    thinkingIndicatorEl.className = 'thinking-indicator fade-in';
    thinkingIndicatorEl.innerHTML = `
        <span class="thinking-indicator-text">Thinking...</span>
        <span class="thinking-indicator-timer">0s</span>
    `;

    document.getElementById('chatContainer').appendChild(thinkingIndicatorEl);
    window.NotionAI.Utils.DOM.scrollToBottom();

    const timerSpan = thinkingIndicatorEl.querySelector('.thinking-indicator-timer');
    thinkingTimerInterval = setInterval(() => {
        if (timerSpan && thinkingStartTime) {
            const elapsed = Math.round((Date.now() - thinkingStartTime) / 1000);
            timerSpan.textContent = `${elapsed}s`;
        }
    }, 1000);
}

function removeThinkingIndicator() {
    if (thinkingTimerInterval) {
        clearInterval(thinkingTimerInterval);
        thinkingTimerInterval = null;
    }
    if (thinkingIndicatorEl && thinkingIndicatorEl.parentNode) {
        thinkingIndicatorEl.parentNode.removeChild(thinkingIndicatorEl);
    }
    thinkingIndicatorEl = null;
    thinkingStartTime = null;
}

// ─── Init ─────────────────────────────────────────────────────
function init() {
    window.NotionAI.Chat.Storage.loadChats();
    window.NotionAI.Chat.Storage.saveChats();
    window.NotionAI.UI.Theme.init();
    window.NotionAI.API.Models.loadModels();
    window.NotionAI.Chat.Manager.renderChatList();
    updateWelcomeGreeting();
    bindEventListeners();
    populateModels();
    AmbientEngine.init();

    if (!STATE.currentChatId) {
        window.NotionAI.Chat.Manager.startNewChat();
    }
}

// ─── Event Listeners ──────────────────────────────────────────
function bindEventListeners() {
    document.getElementById('themeToggleBtn').addEventListener('click', () => {
        window.NotionAI.UI.Theme.toggle();
    });

    document.getElementById('newChatBtn').addEventListener('click', () => {
        window.NotionAI.Chat.Manager.startNewChat();
    });

    document.getElementById('openSidebarBtn').addEventListener('click', () => {
        window.NotionAI.UI.Sidebar.open();
    });
    document.getElementById('closeSidebarBtn').addEventListener('click', () => {
        window.NotionAI.UI.Sidebar.close();
    });
    document.getElementById('mobileBackdrop').addEventListener('click', () => {
        window.NotionAI.UI.Sidebar.close();
    });

    document.getElementById('chatInput').addEventListener('input', () => {
        window.NotionAI.UI.Input.autoResize();
    });
    document.getElementById('chatInput').addEventListener('keydown', (e) => {
        window.NotionAI.UI.Input.handleKeydown(e, handleSend);
    });
    document.getElementById('sendBtn').addEventListener('click', () => {
        if (STATE.isGenerating) {
            // Stop generation
            if (STATE.controller) {
                STATE.controller.abort();
            }
        } else {
            handleSend();
        }
    });

    document.getElementById('memoryBannerClose').addEventListener('click', () => {
        document.getElementById('memoryBanner').classList.add('hidden');
    });

    document.getElementById('settingsBtn').addEventListener('click', () => {
        window.NotionAI.API.Settings.open();
    });
    document.getElementById('cancelSettingsBtn').addEventListener('click', () => {
        window.NotionAI.API.Settings.close();
    });
    document.getElementById('saveSettingsBtn').addEventListener('click', () => {
        window.NotionAI.API.Settings.save();
    });

    document.getElementById('cancelRenameBtn').addEventListener('click', () => {
        window.NotionAI.UI.Modal.closeRenameModal();
    });
    document.getElementById('saveRenameBtn').addEventListener('click', () => {
        window.NotionAI.UI.Modal.saveRename();
    });
    document.getElementById('renameModalInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') window.NotionAI.UI.Modal.saveRename();
        if (e.key === 'Escape') window.NotionAI.UI.Modal.closeRenameModal();
    });

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

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Delete') {
            const activeEl = document.activeElement;
            const isInput = activeEl ? (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.isContentEditable) : false;
            if (!isInput) {
                const currentChatId = window.NotionAI.Core.State.get('currentChatId');
                if (currentChatId && currentChatId.startsWith('remote-chat-history:')) {
                    if (window.NotionAI.ChatHistoryMain) {
                        e.preventDefault();
                        window.NotionAI.ChatHistoryMain.deleteSelectedRemoteThreads();
                    }
                } else {
                    const selected = window.NotionAI.Core.State.get('selectedChatIds') || [];
                    if (selected.length > 0) {
                        e.preventDefault();
                        window.NotionAI.Chat.Manager.deleteChat(selected[0]);
                    }
                }
            }
        }
    });
}

// ─── Model Dropdown (Grouped) ─────────────────────────────────
function populateModels() {
    const listEl = document.getElementById('simpleModelList');
    listEl.innerHTML = '';

    const groups = window.NotionAI.Core.Constants.MODEL_GROUPS;
    const currentModel = window.NotionAI.API.Models.getCurrentModel();

    groups.forEach((group, gi) => {
        // Group label
        const label = document.createElement('div');
        label.className = 'model-group-label';
        label.textContent = group.label;
        listEl.appendChild(label);

        group.models.forEach(model => {
            const isSelected = model.id === currentModel;
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = `model-option${isSelected ? ' selected' : ''}`;

            btn.innerHTML = `
                <div class="model-option-left">
                    <span class="model-option-icon">${model.icon || ''}</span>
                    <span class="model-option-name">${model.label}</span>
                    ${model.badge ? `<span class="model-option-badge">${model.badge}</span>` : ''}
                </div>
                <svg class="model-option-check" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>
            `;

            btn.onclick = (e) => {
                e.stopPropagation();
                handleModelSelect(model.id, model.label, model.icon);
            };

            listEl.appendChild(btn);
        });

        // Divider between groups (not after last)
        if (gi < groups.length - 1) {
            const divider = document.createElement('div');
            divider.className = 'model-group-divider';
            listEl.appendChild(divider);
        }
    });
}

function handleModelSelect(modelId, label, icon) {
    window.NotionAI.API.Models.setCurrentModel(modelId, label);
    document.getElementById('modelTriggerText').textContent = label;
    document.getElementById('modelTriggerIcon').textContent = icon || '';
    document.getElementById('customModelDropdown').classList.remove('open');
    populateModels();
}

function toggleModelDropdown() {
    document.getElementById('customModelDropdown').classList.toggle('open');
}

// ─── Send Handler ─────────────────────────────────────────────
async function handleSend() {
    if (STATE.isGenerating) return;

    const text = window.NotionAI.UI.Input.getValue();
    if (!text) return;

    let chat = STATE.chats.find(c => c.id === STATE.currentChatId);
    const isNewChat = !chat;

    if (isNewChat) {
        chat = {
            id: STATE.currentChatId,
            title: text.length > 30 ? text.substring(0, 30) + '...' : text,
            messages: [],
            conversationId: null
        };
        STATE.chats.push(chat);
        document.getElementById('headerTitle').textContent = chat.title;
        document.getElementById('headerTitle').classList.remove('hidden');
    }

    // Update UI
    window.NotionAI.UI.Input.clear();
    document.getElementById('welcomeScreen').classList.add('hidden');

    // Add user message
    chat.messages.push({ role: 'user', content: text });
    window.NotionAI.Chat.Renderer.appendMessage('user', text, true);
    window.NotionAI.Chat.Storage.saveChats();
    window.NotionAI.Chat.Manager.renderChatList();
    window.NotionAI.Utils.DOM.scrollToBottom();

    // Show thinking indicator
    showThinkingIndicator();

    const selectedModel = window.NotionAI.API.Models.getCurrentModel();
    const selectedModelDisplayName = window.NotionAI.API.Models.getCurrentModelLabel();

    // Set generating state
    STATE.isGenerating = true;
    window.NotionAI.UI.Input.disable();
    _updateSendButton(true);

    // We'll create the AI wrapper only when first token arrives
    let aiWrapper = null;
    let firstTokenReceived = false;

    // Monkey-patch streaming to intercept first token
    const originalConsume = window.NotionAI.Chat.Streaming.consumePayload.bind(window.NotionAI.Chat.Streaming);
    window.NotionAI.Chat.Streaming.consumePayload = function(payload, aw, searchState, thinkingText, fullAiReply) {
        if (!firstTokenReceived && payload && payload !== '[DONE]') {
            try {
                const obj = JSON.parse(payload);
                const hasContent = obj?.choices?.[0]?.delta?.content;
                const hasThinking = obj?.choices?.[0]?.delta?.reasoning_content || obj?.type === 'thinking_chunk';
                if (hasContent || hasThinking) {
                    firstTokenReceived = true;
                    removeThinkingIndicator();
                }
            } catch(e) {}
        }
        return originalConsume(payload, aw, searchState, thinkingText, fullAiReply);
    };

    try {
        // Create AI message wrapper
        aiWrapper = window.NotionAI.Chat.Renderer.appendMessage('assistant', '', false, selectedModelDisplayName);
        aiWrapper._thinkingStartTime = Date.now();

        // Start thinking timer on the card
        const timerEl = aiWrapper.thinkingCardRef?.querySelector('.thinking-header-timer');
        if (timerEl) {
            aiWrapper._thinkingTimerInterval = setInterval(() => {
                if (aiWrapper._thinkingStartTime) {
                    const elapsed = Math.round((Date.now() - aiWrapper._thinkingStartTime) / 1000);
                    timerEl.textContent = `${elapsed}s`;
                }
            }, 1000);
        }

        window.NotionAI.Utils.DOM.scrollToBottom();

        const result = await window.NotionAI.Chat.Streaming.streamResponse(chat, selectedModel, aiWrapper);

        // Ensure thinking indicator is removed
        removeThinkingIndicator();

        // Stop thinking timer
        if (aiWrapper._thinkingTimerInterval) {
            clearInterval(aiWrapper._thinkingTimerInterval);
            aiWrapper._thinkingTimerInterval = null;
        }

        const normalizedSearch = window.NotionAI.Utils.Validation.normalizeSearchPayload(result.searchState);

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
        } else {
            window.NotionAI.Chat.Renderer.updateAIMessage(aiWrapper, '*No visible response received.*', true);
        }

    } catch (err) {
        removeThinkingIndicator();
        if (aiWrapper?._thinkingTimerInterval) {
            clearInterval(aiWrapper._thinkingTimerInterval);
        }
        if (err.name !== 'AbortError') {
            console.error('API Error:', err);
        }
    } finally {
        // Restore original consumePayload
        window.NotionAI.Chat.Streaming.consumePayload = originalConsume;

        STATE.isGenerating = false;
        window.NotionAI.UI.Input.enable();
        window.NotionAI.UI.Input.focus();
        STATE.controller = null;
        _updateSendButton(false);
    }
}

function _updateSendButton(isGenerating) {
    const btn = document.getElementById('sendBtn');
    const sendIcon = document.getElementById('sendIcon');
    const stopIcon = document.getElementById('stopIcon');

    if (isGenerating) {
        btn.classList.add('is-generating');
        sendIcon.classList.add('hidden');
        stopIcon.classList.remove('hidden');
        btn.title = 'Stop generation';
    } else {
        btn.classList.remove('is-generating');
        sendIcon.classList.remove('hidden');
        stopIcon.classList.add('hidden');
        btn.title = 'Send (Enter)';
    }
}

// ─── Welcome Greeting ─────────────────────────────────────────
function updateWelcomeGreeting() {
    const el = document.getElementById('welcomeGreeting');
    if (!el) return;

    const now = new Date();
    const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
    const cst = new Date(utc + (3600000 * 8));
    const h = cst.getHours() + cst.getMinutes() / 60;

    let greeting = 'What would you like to explore?';
    const G = window.NotionAI.Core.Constants.GREETINGS;
    if (h >= 5 && h < 9) greeting = G.EARLY_MORNING;
    else if (h >= 9 && h < 11.5) greeting = G.MORNING;
    else if (h >= 11.5 && h < 13.5) greeting = G.MIDDAY;
    else if (h >= 13.5 && h < 17) greeting = G.AFTERNOON;
    else if (h >= 17 && h < 19) greeting = G.GOLDEN_HOUR;
    else if (h >= 19 && h < 22) greeting = G.EVENING;
    else if (h >= 22 || h < 1) greeting = G.NIGHT_OWL;
    else if (h >= 1 && h < 5) greeting = G.LATE_NIGHT;

    el.textContent = greeting;
}

setInterval(updateWelcomeGreeting, 60000);

window.addEventListener('DOMContentLoaded', init);
