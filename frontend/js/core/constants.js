/**
 * Constants Module — Notion AI Studio
 */

window.NotionAI = window.NotionAI || {};
window.NotionAI.Core = window.NotionAI.Core || {};

window.NotionAI.Core.Constants = {
    STORAGE_KEYS: {
        API_KEY: 'claude_api_key',
        BASE_URL: 'claude_base_url',
        CHATS: 'claude_chats',
        THEME: 'theme'
    },

    API: {
        CHAT_COMPLETIONS: '/v1/chat/completions',
        DELETE_CONVERSATION: (id) => `/v1/conversations/${encodeURIComponent(id)}`
    },

    // Model definitions with grouping
    MODEL_GROUPS: [
        {
            label: 'Anthropic',
            models: [
                { id: "claude-sonnet4.6", label: "Sonnet 4.6", icon: "✳️", desc: "Fast & efficient" },
                { id: "claude-sonnet5", label: "Sonnet 5", icon: "✳️", badge: "New" },
                { id: "claude-opus4.6", label: "Opus 4.6", icon: "✳️" },
                { id: "claude-opus4.7", label: "Opus 4.7", icon: "✳️" },
                { id: "claude-opus4.8", label: "Opus 4.8", icon: "✳️" },
                { id: "claude-opus5", label: "Opus 5", icon: "✳️", badge: "New" },
                { id: "claude-haiku4.5", label: "Haiku 4.5", icon: "✳️" },
            ]
        },
        {
            label: 'OpenAI',
            models: [
                { id: "gpt-6-astra", label: "GPT-6 Astra", icon: "⚙", badge: "New" },
                { id: "gpt-5.6-sol", label: "GPT-5.6 Sol", icon: "⚙", badge: "New" },
                { id: "gpt-5.6-terra", label: "GPT-5.6 Terra", icon: "⚙", badge: "New" },
                { id: "gpt-5.6-luna", label: "GPT-5.6 Luna", icon: "⚙", badge: "New" },
                { id: "gpt-5.4", label: "GPT-5.4", icon: "⚙" },
                { id: "gpt-5.5", label: "GPT-5.5", icon: "⚙", badge: "Beta" },
            ]
        },
        {
            label: 'Google',
            models: [
                { id: "gemini-3.5flash", label: "Gemini 3.5 Flash", icon: "✦", badge: "New" },
                { id: "gemini-3.1pro", label: "Gemini 3.1 Pro", icon: "✦" },
                { id: "gemini-3flash", label: "Gemini 3 Flash", icon: "✦" },
            ]
        },
        {
            label: 'Moonshot',
            models: [
                { id: "kimi-2.7", label: "Kimi K2.7 Code", icon: "🌙", badge: "New" },
            ]
        },
        {
            label: 'xAI',
            models: [
                { id: "grok-4.3", label: "Grok 4.3", icon: "⚡", badge: "New" },
                { id: "spacexai-4.5", label: "SpaceXAI 4.5", icon: "⚡", badge: "New" },
                { id: "grok-build0.1", label: "Grok Build 0.1", icon: "⚡", badge: "New" },
            ]
        },
        {
            label: 'DeepSeek',
            models: [
                { id: "deepseek-v4pro", label: "DeepSeek V4 Pro", icon: "🐋", badge: "New" },
            ]
        },
        {
            label: 'Zhipu',
            models: [
                { id: "glm-5.2", label: "GLM 5.2", icon: "◆", badge: "New" },
            ]
        },
        {
            label: 'Notion',
            models: [
                { id: "fable-5", label: "Fable 5", icon: "◇", badge: "New" },
            ]
        }
    ],

    // Flat model list (for backward compat)
    MODELS: [
        { id: "claude-sonnet4.6", label: "Sonnet 4.6" },
        { id: "claude-sonnet5", label: "Sonnet 5" },
        { id: "claude-opus4.6", label: "Opus 4.6" },
        { id: "claude-opus4.7", label: "Opus 4.7" },
        { id: "claude-opus4.8", label: "Opus 4.8" },
        { id: "claude-opus5", label: "Opus 5" },
        { id: "claude-haiku4.5", label: "Haiku 4.5" },
        { id: "gpt-6-astra", label: "GPT-6 Astra" },
        { id: "gpt-5.6-sol", label: "GPT-5.6 Sol" },
        { id: "gpt-5.6-terra", label: "GPT-5.6 Terra" },
        { id: "gpt-5.6-luna", label: "GPT-5.6 Luna" },
        { id: "gpt-5.4", label: "GPT-5.4" },
        { id: "gpt-5.5", label: "GPT-5.5" },
        { id: "gemini-3.5flash", label: "Gemini 3.5 Flash" },
        { id: "gemini-3.1pro", label: "Gemini 3.1 Pro" },
        { id: "gemini-3flash", label: "Gemini 3 Flash" },
        { id: "kimi-2.7", label: "Kimi K2.7 Code" },
        { id: "grok-4.3", label: "Grok 4.3" },
        { id: "spacexai-4.5", label: "SpaceXAI 4.5" },
        { id: "grok-build0.1", label: "Grok Build 0.1" },
        { id: "deepseek-v4pro", label: "DeepSeek V4 Pro" },
        { id: "glm-5.2", label: "GLM 5.2" },
        { id: "fable-5", label: "Fable 5" },
    ],

    DEFAULT_MODEL: "claude-sonnet4.6",

    MODEL_DISPLAY_NAMES: {
        "claude-sonnet4.6": "Sonnet 4.6",
        "claude-sonnet5": "Sonnet 5",
        "claude-opus4.6": "Opus 4.6",
        "claude-opus4.7": "Opus 4.7",
        "claude-opus4.8": "Opus 4.8",
        "claude-opus5": "Opus 5",
        "claude-haiku4.5": "Haiku 4.5",
        "gpt-6-astra": "GPT-6 Astra",
        "gpt-5.6-sol": "GPT-5.6 Sol",
        "gpt-5.6-terra": "GPT-5.6 Terra",
        "gpt-5.6-luna": "GPT-5.6 Luna",
        "gpt-5.4": "GPT-5.4",
        "gpt-5.5": "GPT-5.5",
        "gemini-3.5flash": "Gemini 3.5 Flash",
        "gemini-3.1pro": "Gemini 3.1 Pro",
        "gemini-3flash": "Gemini 3 Flash",
        "kimi-2.7": "Kimi K2.7 Code",
        "grok-4.3": "Grok 4.3",
        "spacexai-4.5": "SpaceXAI 4.5",
        "grok-build0.1": "Grok Build 0.1",
        "deepseek-v4pro": "DeepSeek V4 Pro",
        "glm-5.2": "GLM 5.2",
        "fable-5": "Fable 5",
    },

    MODEL_ICONS: {
        "claude-sonnet4.6": "✳️",
        "claude-sonnet5": "✳️",
        "claude-opus4.6": "✳️",
        "claude-opus4.7": "✳️",
        "claude-opus4.8": "✳️",
        "claude-opus5": "✳️",
        "claude-haiku4.5": "✳️",
        "gpt-6-astra": "⚙",
        "gpt-5.6-sol": "⚙",
        "gpt-5.6-terra": "⚙",
        "gpt-5.6-luna": "⚙",
        "gpt-5.4": "⚙",
        "gpt-5.5": "⚙",
        "gemini-3.5flash": "✦",
        "gemini-3.1pro": "✦",
        "gemini-3flash": "✦",
        "kimi-2.7": "🌙",
        "grok-4.3": "⚡",
        "spacexai-4.5": "⚡",
        "grok-build0.1": "⚡",
        "deepseek-v4pro": "🐋",
        "glm-5.2": "◆",
        "fable-5": "◇",
    },

    GREETINGS: {
        EARLY_MORNING: "Early bird thinking",
        MORNING: "Morning clarity",
        MIDDAY: "Midday focus",
        AFTERNOON: "Afternoon momentum",
        GOLDEN_HOUR: "Golden hour thinking",
        EVENING: "Evening deep work",
        NIGHT_OWL: "Night owl mode",
        LATE_NIGHT: "Late night thinking"
    },

    CLIENT_TYPE: 'Web'
};
