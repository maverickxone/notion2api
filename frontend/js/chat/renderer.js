/**
 * Renderer Module
 * Handles message DOM rendering and updates
 */

// Initialize namespace
window.NotionAI = window.NotionAI || {};
window.NotionAI.Chat = window.NotionAI.Chat || {};

window.NotionAI.Chat.Renderer = {
    /**
     * Creates a message element wrapper
     * @param {string} role - Message role ('user' or 'assistant')
     * @param {string} modelDisplayName - Model display name for assistant messages
     * @returns {Object} Object containing wrapper and bubble elements
     */
    createMessageElement(role, modelDisplayName = 'Assistant') {
        const wrapper = document.createElement('div');
        wrapper.className = `flex w-full mb-4 ${role === 'user' ? 'justify-end' : 'justify-start'}`;

        if (role === 'assistant') {
            wrapper.classList.add('items-end', 'gap-3', 'relative', 'pb-[40px]');

            const starContainer = this.createStarIcon(modelDisplayName);
            wrapper.appendChild(starContainer);
            wrapper.starIconRef = starContainer.querySelector('svg');
        }

        const bubble = document.createElement('div');
        if (role === 'user') {
            bubble.className = 'max-w-[85%] bg-claudeUserMsg dark:bg-darkUserMsg text-claudeText dark:text-darkText px-4 py-3 rounded-2xl rounded-tr-sm text-[15px] whitespace-pre-wrap leading-relaxed';
        } else {
            bubble.className = 'w-full max-w-full text-claudeText dark:text-darkText px-2 py-1 text-[15px] relative group overflow-hidden';
        }

        wrapper.appendChild(bubble);
        return { wrapper, bubble };
    },

    /**
     * Creates the star icon for AI messages
     * @param {string} modelDisplayName - Model display name
     * @returns {HTMLElement} Star container element
     */
    createStarIcon(modelDisplayName) {
        const starContainer = document.createElement('div');
        starContainer.className = 'message-star-container relative flex-shrink-0 opacity-0 transition-opacity duration-300';

        setTimeout(() => starContainer.classList.remove('opacity-0'), 50);

        starContainer.innerHTML = `
            <div class="star-tooltip absolute bottom-full mb-2 left-1/2 -translate-x-1/2 whitespace-nowrap">
                ${modelDisplayName}
            </div>
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="28" height="28" class="text-accent message-star cursor-pointer star-generating" style="fill: currentColor;">
                <path d="m19.6 66.5 19.7-11 .3-1-.3-.5h-1l-3.3-.2-11.2-.3L14 53l-9.5-.5-2.4-.5L0 49l1.2-1.5 2-1.3 2.9.2 6.3.5 9.5.6 6.9.4L38 49.1h1.6l.2-.7-.5-.4-.4-.4L29 41l-10.6-7-5.6-4.1-3-2-1.5-2-.6-4.2 2.7-3 3.7.3.9.2 3.7 2.9 8 6.1L37 36l1.5 1.2.6-.4.1-.3-.7-1.1L33 25l-6-10.4-2.7-4.3-.7-2.6c-.3-1-.4-2-.4-3l3-4.2L28 0l4.2.6L33.8 2l2.6 6 4.1 9.3L47 29.9l2 3.8 1 3.4.3 1h.7v-.5l1.5-7.2 1-8.7 1-11.2.3-3.2 1.6-3.8 3-2L61 2.6l2 2.9-.3 1.8-1.1 7.7L59 27.1l-1.5 8.2h.9l1-1.1 4.1-5.4 6.9-8.6 3-3.5L77 13l2.3-1.8h4.3l3.1 4.7-1.4 4.9-4.4 5.6-3.7 4.7-5.3 7.1-3.2 5.7.3.4h.7l12-2.6 6.4-1.1 7.6-1.3 3.5 1.6.4 1.6-1.4 3.4-8.2 2-9.6 2-14.3 3.3-.2.1.2.3 6.4.6 2.8.2h6.8l12.6 1 3.3 2 1.9 2.7-.3 2-5.1 2.6-6.8-1.6-16-3.8-5.4-1.3h-.8v.4l4.6 4.5 8.3 7.5L89 80.1l1.5 2.4-1.3 2-1.4-.2-9.2-7-3.6-3-8-6.8h-.5v.7l1.8 2.7 9.8 14.7.5 4.5-.7 1.4-2.6 1-2.7-.6-5.8-8-6-9.4-7-8.2-.5.4-2.9 30.2-1.3 1.5-3 1.2-2.5-2-1.4-3 1.4-6.2 1.6-8 1.3-6.4 1.2-7.9.7-2.6v-.2H49L43 72l-9 12.3-7.2 7.6-1.7.7-3-1.5.3-2.8L24 86l10-12.8 6-7.9 4-4.6-.1-.5h-.3L17.2 77.4l-4.7.6-2.2.2-3 1-1 8-5.5Z" />
            </svg>
        `;

        const svg = starContainer.querySelector('svg');
        svg.addEventListener('click', () => {
            svg.classList.remove('star-click-anim');
            void svg.offsetWidth;
            svg.classList.add('star-click-anim');
        });

        return starContainer;
    },

    /**
     * Updates AI message content in DOM
     * @param {Object} wrapper - Message wrapper element
     * @param {string} content - Markdown content
     * @param {boolean} isFinished - Whether streaming is finished
     */
    updateAIMessage(wrapper, content, isFinished) {
        if (isFinished && wrapper.starIconRef) {
            wrapper.starIconRef.classList.remove('star-generating');
        }

        const mdDiv = wrapper.mdDivRef;
        if (!content && !isFinished) {
            mdDiv.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
            return;
        }

        window.NotionAI.Utils.Markdown.setSafeMarkdown(mdDiv, content);

        if (isFinished) {
            mdDiv.querySelectorAll('pre code').forEach((block) => {
                if (!block.dataset.highlighted) {
                    hljs.highlightElement(block);
                }
            });
            window.NotionAI.Utils.DOM.addCodeBlockCopyButtons(mdDiv);
        }

        const chatContainer = document.getElementById('chatContainer');
        if (chatContainer.scrollHeight - chatContainer.scrollTop < chatContainer.clientHeight + 100) {
            window.NotionAI.Utils.DOM.scrollToBottom();
        }
    },

    /**
     * Updates thinking panel visibility and content
     * @param {Object} wrapper - Message wrapper element
     */
    updateThinkingPanel(wrapper) {
        const container = wrapper.thinkingContainerRef;
        if (!container) return;

        const rawText = String(wrapper.thinkingText || '');
        const hasThinking = rawText.trim().length > 0;

        if (!hasThinking) {
            container.classList.add('hidden');
            wrapper.thinkingDetailsRef.classList.add('hidden');
            return;
        }

        container.classList.remove('hidden');
        const arrow = wrapper.thinkingExpanded ? '▾' : '▸';
        const modelName = (wrapper.thinkingModelDisplayName || 'Assistant').trim() || 'Assistant';
        wrapper.thinkingToggleRef.textContent = `${modelName}'s thinking: ${arrow}`;

        if (wrapper.thinkingExpanded) {
            wrapper.thinkingDetailsRef.classList.remove('hidden');
            window.NotionAI.Utils.Markdown.setSafeMarkdown(wrapper.thinkingMarkdownRef, rawText);
        } else {
            wrapper.thinkingDetailsRef.classList.add('hidden');
        }
    },

    /**
     * Updates search panel visibility and content
     * @param {Object} wrapper - Message wrapper element
     */
    updateSearchPanel(wrapper) {
        const container = wrapper.searchContainerRef;
        if (!container) return;

        const queries = wrapper.searchData?.queries || [];
        const sources = wrapper.searchData?.sources || [];
        const hasSearchData = queries.length > 0 || sources.length > 0;

        if (!hasSearchData) {
            container.classList.add('hidden');
            return;
        }

        container.classList.remove('hidden');

        const displayCount = sources.length || queries.length;
        const arrow = wrapper.searchExpanded ? '▾' : '▸';
        wrapper.searchToggleRef.textContent = `Searched ${displayCount} source${displayCount !== 1 ? 's' : ''} ${arrow}`;

        wrapper.searchQueryRef.textContent = queries.length
            ? `Searched: ${queries.map(q => `"${q}"`).join(', ')} `
            : 'Web search executed';

        wrapper.searchLinksRef.innerHTML = '';
        if (sources.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'search-empty';
            empty.textContent = 'No sources to display.';
            wrapper.searchLinksRef.appendChild(empty);
        } else {
            sources.forEach(source => {
                const row = document.createElement('div');
                if (source.url) {
                    const link = document.createElement('a');
                    link.className = 'search-source-link';
                    link.href = source.url;
                    link.target = '_blank';
                    link.rel = 'noopener noreferrer';
                    link.textContent = source.title || source.url;
                    row.appendChild(link);
                } else {
                    row.textContent = source.title;
                }
                wrapper.searchLinksRef.appendChild(row);
            });
        }

        if (wrapper.searchExpanded) {
            wrapper.searchDetailsRef.classList.remove('hidden');
        } else {
            wrapper.searchDetailsRef.classList.add('hidden');
        }
    },

    /**
     * Appends a message to the chat container
     * @param {string} role - Message role ('user' or 'assistant')
     * @param {string} content - Message content
     * @param {boolean} isFinished - Whether message is complete
     * @param {string} modelDisplayName - Model display name for assistant
     * @returns {Object} Message wrapper with references
     */
    appendMessage(role, content, isFinished = false, modelDisplayName = null) {
        const resolvedModelDisplayName = (modelDisplayName ||
            window.NotionAI.API.Models.getModelDisplayName(
                window.NotionAI.API.Models.getCurrentModel()
            )).trim() || 'Assistant';

        const { wrapper, bubble } = this.createMessageElement(role, resolvedModelDisplayName);

        if (role === 'user') {
            bubble.textContent = content;
        } else {
            const refs = this.appendAssistantContent(bubble, content, isFinished, resolvedModelDisplayName);
            Object.assign(wrapper, refs);
            this.setupAssistantPanelListeners(wrapper);
        }

        document.getElementById('chatContainer').appendChild(wrapper);
        return wrapper;
    },

    /**
     * Appends content to assistant message bubble
     * @param {HTMLElement} bubble - Bubble element
     * @param {string} content - Message content
     * @param {boolean} isFinished - Whether message is complete
     * @param {string} modelDisplayName - Model display name
     */
    appendAssistantContent(bubble, content, isFinished, modelDisplayName) {
        // Search panel
        const searchContainer = document.createElement('div');
        searchContainer.className = 'search-sources hidden';
        searchContainer.innerHTML = `
            <button class="search-toggle" type="button">已搜索 0 个来源 ▸</button>
            <div class="search-details hidden">
                <div class="search-query"></div>
                <div class="search-links"></div>
            </div>
        `;
        bubble.appendChild(searchContainer);

        // Thinking panel
        const thinkingContainer = document.createElement('div');
        thinkingContainer.className = 'thinking-sources hidden';
        thinkingContainer.innerHTML = `
            <button class="thinking-toggle" type="button">${modelDisplayName}'s thinking: ▸</button>
            <div class="thinking-details hidden">
                <div class="markdown-body thinking-markdown text-claudeText dark:text-darkText"></div>
            </div>
        `;
        bubble.appendChild(thinkingContainer);

        // Markdown content
        const mdDiv = document.createElement('div');
        mdDiv.className = 'markdown-body text-claudeText dark:text-darkText';
        bubble.appendChild(mdDiv);

        if (content === '') {
            if (isFinished) {
                window.NotionAI.Utils.Markdown.setSafeMarkdown(mdDiv, '*No visible response received.*');
            } else {
                mdDiv.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
            }
        } else {
            window.NotionAI.Utils.Markdown.setSafeMarkdown(mdDiv, content);
            if (isFinished) {
                mdDiv.querySelectorAll('pre code').forEach((block) => {
                    hljs.highlightElement(block);
                });
                window.NotionAI.Utils.DOM.addCodeBlockCopyButtons(mdDiv);
            }
        }

        return {
            bubbleRef: bubble,
            mdDivRef: mdDiv,
            searchContainerRef: searchContainer,
            searchToggleRef: searchContainer.querySelector('.search-toggle'),
            searchDetailsRef: searchContainer.querySelector('.search-details'),
            searchQueryRef: searchContainer.querySelector('.search-query'),
            searchLinksRef: searchContainer.querySelector('.search-links'),
            searchExpanded: false,
            searchData: { queries: [], sources: [] },
            thinkingContainerRef: thinkingContainer,
            thinkingToggleRef: thinkingContainer.querySelector('.thinking-toggle'),
            thinkingDetailsRef: thinkingContainer.querySelector('.thinking-details'),
            thinkingMarkdownRef: thinkingContainer.querySelector('.thinking-markdown'),
            thinkingExpanded: false,
            thinkingText: '',
            thinkingModelDisplayName: modelDisplayName
        };
    },

    /**
     * Sets up event listeners for assistant panels
     * @param {Object} wrapper - Message wrapper
     */
    setupAssistantPanelListeners(wrapper) {
        const searchToggle = wrapper.querySelector('.search-toggle');
        const thinkingToggle = wrapper.querySelector('.thinking-toggle');

        if (searchToggle) {
            searchToggle.addEventListener('click', () => {
                wrapper.searchExpanded = !wrapper.searchExpanded;
                this.updateSearchPanel(wrapper);
            });
        }

        if (thinkingToggle) {
            thinkingToggle.addEventListener('click', () => {
                wrapper.thinkingExpanded = !wrapper.thinkingExpanded;
                this.updateThinkingPanel(wrapper);
            });
        }
    }
};
