MODEL_MAP: dict[str, str] = {
    "claude-opus4.6": "avocado-froyo-medium",
    "claude-sonnet4.6": "almond-croissant-low",
    "gemini-3.1pro": "galette-medium-thinking",
    "gpt-5.2": "oatmeal-cookie",
}

NOTION_MODEL_REVERSE_MAP: dict[str, str] = {value: key for key, value in MODEL_MAP.items()}

DISPLAY_NAMES: dict[str, str] = {
    "claude-opus4.6": "Claude Opus 4.6",
    "claude-sonnet4.6": "Claude Sonnet 4.6",
    "gemini-3.1pro": "Gemini 3.1 Pro",
    "gpt-5.2": "GPT-5.2",
}

MODEL_ICONS: dict[str, str] = {
    "claude-opus4.6": "✳️",
    "claude-sonnet4.6": "✳️",
    "gemini-3.1pro": "✦",
    "gpt-5.2": "⚙",
}

DEFAULT_MODEL = "claude-opus4.6"


def get_notion_model(model_name: str) -> str:
    return MODEL_MAP.get(model_name, MODEL_MAP[DEFAULT_MODEL])


def get_standard_model(model_name: str) -> str:
    if model_name in MODEL_MAP:
        return model_name
    return NOTION_MODEL_REVERSE_MAP.get(model_name, DEFAULT_MODEL)


def list_available_models() -> list[str]:
    return list(MODEL_MAP.keys())


def is_supported_model(model_name: str) -> bool:
    return model_name in MODEL_MAP


def get_display_name(model_name: str) -> str:
    standard_name = get_standard_model(model_name)
    return DISPLAY_NAMES.get(standard_name, standard_name)


def get_model_icon(model_name: str) -> str:
    standard_name = get_standard_model(model_name)
    return MODEL_ICONS.get(standard_name, "")
