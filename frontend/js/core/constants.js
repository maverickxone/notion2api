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

    MODEL_GROUPS: [
        {
            label: 'Anthropic',
            models: [
                { id: "claude-sonnet4.6", label: "Sonnet 4.6", icon: "✳️", desc: "Fast & efficient" },
                { id: "claude-opus4.6", label: "Opus 4.6", icon: "✳️" },
                { id: "claude-opus4.7", label: "Opus 4.7", icon: "✳️" },
                { id: "claude-opus4.8", label: "Opus 4.8", icon: "✳️", badge: "New" },
                { id: "claude-haiku4.5", label: "Haiku 4.5", icon: "✳️" },
            ]
        },
        {
            label: 'OpenAI',
            models: [
                { id: "gpt-5.2", label: "GPT-5.2", icon: "⚙" },
                { id: "gpt-5.4", label: "GPT-5.4", icon: "⚙" },
                { id: "gpt-5.4mini", label: "GPT-5.4 Mini", icon: "⚙", desc: "Fast & lightweight" },
                { id: "gpt-5.4nano", label: "GPT-5.4 Nano", icon: "⚙", desc: "Fastest & smallest" },
                { id: "gpt-5.5", label: "GPT-5.5", icon: "⚙", badge: "Beta" },
            ]
        },
        {
            label: 'Google',
            models: [
                { id: "gemini-3flash", label: "Gemini 3 Flash", icon: "✦", desc: "No thinking delay" },
                { id: "gemini-3.5flash", label: "Gemini 3.5 Flash", icon: "✦", badge: "New" },
                { id: "gemini-3.1pro", label: "Gemini 3.1 Pro", icon: "✦" },
                { id: "gemini-2.5flash", label: "Gemini 2.5 Flash", icon: "✦" },
            ]
        },
        {
            label: 'Moonshot',
            models: [
                { id: "kimi-2.6", label: "Kimi 2.6", icon: "🌙", badge: "Beta" },
            ]
        },
        {
            label: 'xAI',
            models: [
                { id: "grok-4.3", label: "Grok 4.3", icon: "◐", badge: "Beta" },
                { id: "grok-build0.1", label: "Grok Build 0.1", icon: "◐", badge: "Beta" },
            ]
        },
        {
            label: 'DeepSeek',
            models: [
                { id: "deepseek-v4pro", label: "DeepSeek V4 Pro", icon: "🔷", badge: "New" },
            ]
        },
        {
            label: 'Other',
            models: [
                { id: "minimax-m2.5", label: "MiniMax M2.5", icon: "◈", badge: "Beta" },
            ]
        }
    ],

    // Flat model list (for backward compat)
    MODELS: [
        { id: "claude-sonnet4.6", label: "Sonnet 4.6" },
        { id: "claude-opus4.6", label: "Opus 4.6" },
        { id: "claude-opus4.7", label: "Opus 4.7" },
        { id: "claude-opus4.8", label: "Opus 4.8" },
        { id: "claude-haiku4.5", label: "Haiku 4.5" },
        { id: "gpt-5.2", label: "GPT-5.2" },
        { id: "gpt-5.4", label: "GPT-5.4" },
        { id: "gpt-5.4mini", label: "GPT-5.4 Mini" },
        { id: "gpt-5.4nano", label: "GPT-5.4 Nano" },
        { id: "gpt-5.5", label: "GPT-5.5" },
        { id: "gemini-3flash", label: "Gemini 3 Flash" },
        { id: "gemini-3.5flash", label: "Gemini 3.5 Flash" },
        { id: "gemini-3.1pro", label: "Gemini 3.1 Pro" },
        { id: "gemini-2.5flash", label: "Gemini 2.5 Flash" },
        { id: "grok-4.3", label: "Grok 4.3" },
        { id: "grok-build0.1", label: "Grok Build 0.1" },
        { id: "minimax-m2.5", label: "MiniMax M2.5" },
        { id: "kimi-2.6", label: "Kimi 2.6" },
        { id: "deepseek-v4pro", label: "DeepSeek V4 Pro" },
    ],

    DEFAULT_MODEL: "claude-sonnet4.6",

    MODEL_DISPLAY_NAMES: {
        "claude-sonnet4.6": "Sonnet 4.6",
        "claude-opus4.6": "Opus 4.6",
        "claude-opus4.7": "Opus 4.7",
        "claude-opus4.8": "Opus 4.8",
        "claude-haiku4.5": "Haiku 4.5",
        "gpt-5.2": "GPT-5.2",
        "gpt-5.4": "GPT-5.4",
        "gpt-5.4mini": "GPT-5.4 Mini",
        "gpt-5.4nano": "GPT-5.4 Nano",
        "gpt-5.5": "GPT-5.5",
        "gemini-3flash": "Gemini 3 Flash",
        "gemini-3.5flash": "Gemini 3.5 Flash",
        "gemini-3.1pro": "Gemini 3.1 Pro",
        "gemini-2.5flash": "Gemini 2.5 Flash",
        "grok-4.3": "Grok 4.3",
        "grok-build0.1": "Grok Build 0.1",
        "minimax-m2.5": "MiniMax M2.5",
        "kimi-2.6": "Kimi 2.6",
        "deepseek-v4pro": "DeepSeek V4 Pro",
    },

    MODEL_ICONS: {
        "claude-sonnet4.6": "✳️",
        "claude-opus4.6": "✳️",
        "claude-opus4.7": "✳️",
        "claude-opus4.8": "✳️",
        "claude-haiku4.5": "✳️",
        "gpt-5.2": "⚙",
        "gpt-5.4": "⚙",
        "gpt-5.4mini": "⚙",
        "gpt-5.4nano": "⚙",
        "gpt-5.5": "⚙",
        "gemini-3flash": "✦",
        "gemini-3.5flash": "✦",
        "gemini-3.1pro": "✦",
        "gemini-2.5flash": "✦",
        "grok-4.3": "◐",
        "grok-build0.1": "◐",
        "minimax-m2.5": "◈",
        "kimi-2.6": "🌙",
        "deepseek-v4pro": "🔷",
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
