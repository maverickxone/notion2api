/**
 * State Management Module
 * Manages global application state
 */

// Initialize namespace
window.NotionAI = window.NotionAI || {};
window.NotionAI.Core = window.NotionAI.Core || {};

window.NotionAI.Core.State = {
    // Global state object
    _state: {
        baseUrl: localStorage.getItem('claude_base_url') || window.location.origin,
        apiKey: '',
        theme: localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
        chats: JSON.parse(localStorage.getItem('claude_chats')) || [],
        currentChatId: null,
        selectedChatIds: [],
        isGenerating: false,
        controller: null,
        modelDisplayNames: {},
        chatToRename: null
    },

    /**
     * Loads stored API key from localStorage or sessionStorage
     * @returns {string} API key or empty string
     */
    loadStoredApiKey() {
        const apiKey = localStorage.getItem('claude_api_key') ||
                      sessionStorage.getItem('claude_api_key') ||
                      '';
        return apiKey;
    },

    /**
     * Persists API key to both localStorage and sessionStorage
     * @param {string} apiKey - API key to store
     */
    persistApiKey(apiKey) {
        if (apiKey) {
            localStorage.setItem('claude_api_key', apiKey);
            sessionStorage.setItem('claude_api_key', apiKey);
        } else {
            localStorage.removeItem('claude_api_key');
            sessionStorage.removeItem('claude_api_key');
        }
    },

    /**
     * Gets a state value by key
     * @param {string} key - State key
     * @returns {*} State value
     */
    get(key) {
        return this._state[key];
    },

    /**
     * Sets a state value by key
     * @param {string} key - State key
     * @param {*} value - New value
     */
    set(key, value) {
        this._state[key] = value;
    },

    /**
     * Gets the entire state object (for compatibility)
     * @returns {Object} Complete state object
     */
    getState() {
        return this._state;
    }
};

// Initialize state with API key loading
window.NotionAI.Core.State._state.apiKey = window.NotionAI.Core.State.loadStoredApiKey();
