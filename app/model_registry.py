from app.core.models import normalize_model_id


MODEL_MAP: dict[str, str] = {
    # Anthropic
    "claude-sonnet4.6": "almond-croissant-low",
    "claude-opus4.6": "avocado-froyo-medium",
    "claude-opus4.7": "apricot-sorbet-high",
    "claude-opus4.8": "ambrosia-tart-high",
    "claude-haiku4.5": "anthropic-haiku-4.5",
    # OpenAI
    "gpt-5.2": "oatmeal-cookie",
    "gpt-5.4": "oval-kumquat-medium",
    "gpt-5.4mini": "oregon-grape-medium",
    "gpt-5.4nano": "otaheite-apple-medium",
    "gpt-5.5": "opal-quince-medium",
    # Google
    "gemini-3flash": "gingerbread",
    "gemini-3.1pro": "galette-medium-thinking",
    "gemini-3.5flash": "vertex-gemini-3.5-flash",
    "gemini-2.5flash": "vertex-gemini-2.5-flash",
    # xAI
    "grok-4.3": "xigua-mochi-medium",
    "grok-build0.1": "xinomavro-cake",
    # Other
    "minimax-m2.5": "fireworks-minimax-m2.5",
    "kimi-2.6": "fireworks-kimi-k2.6",
    "deepseek-v4pro": "baseten-deepseek-v4-pro",
}

NOTION_MODEL_REVERSE_MAP: dict[str, str] = {value: key for key, value in MODEL_MAP.items()}

DISPLAY_NAMES: dict[str, str] = {
    # Anthropic
    "claude-sonnet4.6": "Claude Sonnet 4.6",
    "claude-opus4.6": "Claude Opus 4.6",
    "claude-opus4.7": "Claude Opus 4.7",
    "claude-opus4.8": "Claude Opus 4.8",
    "claude-haiku4.5": "Claude Haiku 4.5",
    # OpenAI
    "gpt-5.2": "GPT-5.2",
    "gpt-5.4": "GPT-5.4",
    "gpt-5.4mini": "GPT-5.4 Mini",
    "gpt-5.4nano": "GPT-5.4 Nano",
    "gpt-5.5": "GPT-5.5",
    # Google
    "gemini-3flash": "Gemini 3 Flash",
    "gemini-3.1pro": "Gemini 3.1 Pro",
    "gemini-3.5flash": "Gemini 3.5 Flash",
    "gemini-2.5flash": "Gemini 2.5 Flash",
    # xAI
    "grok-4.3": "Grok 4.3",
    "grok-build0.1": "Grok Build 0.1",
    # Other
    "minimax-m2.5": "MiniMax M2.5",
    "kimi-2.6": "Kimi 2.6",
    "deepseek-v4pro": "DeepSeek V4 Pro",
}

MODEL_ICONS: dict[str, str] = {
    # Anthropic
    "claude-sonnet4.6": "✳️",
    "claude-opus4.6": "✳️",
    "claude-opus4.7": "✳️",
    "claude-opus4.8": "✳️",
    "claude-haiku4.5": "✳️",
    # OpenAI
    "gpt-5.2": "⚙",
    "gpt-5.4": "⚙",
    "gpt-5.4mini": "⚙",
    "gpt-5.4nano": "⚙",
    "gpt-5.5": "⚙",
    # Google
    "gemini-3flash": "✦",
    "gemini-3.1pro": "✦",
    "gemini-3.5flash": "✦",
    "gemini-2.5flash": "✦",
    # xAI
    "grok-4.3": "◐",
    "grok-build0.1": "◐",
    # Other
    "minimax-m2.5": "◈",
    "kimi-2.6": "🌙",
    "deepseek-v4pro": "🔷",
}

# 默认使用 Sonnet 4.6（速度和质量的最佳平衡）
DEFAULT_MODEL = "claude-sonnet4.6"


def get_notion_model(model_name: str) -> str:
    normalized_name = get_standard_model(model_name)
    return MODEL_MAP.get(normalized_name, MODEL_MAP[DEFAULT_MODEL])


# Notion's public model metadata currently advertises the newer Gemini models
# through workflow/custom-agent capable routes. Keeping them on markdown-chat
# causes Notion upstream 502 responses.
MARKDOWN_CHAT_MODELS: set[str] = {
}


def is_gemini_model(model_name: str) -> bool:
    """判断是否为 Gemini 系列模型（用于 config block 构建等）"""
    standard_name = get_standard_model(model_name)
    if standard_name.startswith("gemini-"):
        return True
    notion_model = get_notion_model(standard_name)
    return notion_model.startswith("vertex-") or notion_model.startswith("galette-")


def get_thread_type(model_name: str) -> str:
    """
    根据模型确定 Notion thread type。
    只有 vertex- 前缀的模型走 markdown-chat，其余全部走 workflow。
    """
    standard_name = get_standard_model(model_name)
    notion_model = get_notion_model(standard_name)
    if notion_model in MARKDOWN_CHAT_MODELS:
        return "markdown-chat"
    return "workflow"


def get_standard_model(model_name: str) -> str:
    model_name = normalize_model_id(model_name)
    if not model_name:
        return DEFAULT_MODEL
    if model_name in MODEL_MAP:
        return model_name
    return NOTION_MODEL_REVERSE_MAP.get(model_name, DEFAULT_MODEL)


def list_available_models() -> list[str]:
    return list(MODEL_MAP.keys())


def is_supported_model(model_name: str) -> bool:
    normalized_name = normalize_model_id(model_name)
    return bool(normalized_name and normalized_name in MODEL_MAP)


def get_display_name(model_name: str) -> str:
    standard_name = get_standard_model(model_name)
    return DISPLAY_NAMES.get(standard_name, standard_name)


def get_model_icon(model_name: str) -> str:
    standard_name = get_standard_model(model_name)
    return MODEL_ICONS.get(standard_name, "")
