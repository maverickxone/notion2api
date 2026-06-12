from app.model_registry import (
    get_display_name,
    get_notion_model,
    get_standard_model,
    get_thread_type,
    is_supported_model,
)


def test_captured_notion_backend_mappings_are_registered():
    expected = {
        "gpt-5.2": "oatmeal-cookie",
        "gpt-5.4": "oval-kumquat-medium",
        "gpt-5.5": "opal-quince-medium",
        "gemini-2.5flash": "vertex-gemini-2.5-flash",
        "gemini-3.5flash": "vertex-gemini-3.5-flash",
        "claude-sonnet4.6": "almond-croissant-low",
        "claude-opus4.6": "avocado-froyo-medium",
        "claude-opus4.7": "apricot-sorbet-high",
        "claude-opus4.8": "ambrosia-tart-high",
        "gpt-5.4mini": "oregon-grape-medium",
        "gpt-5.4nano": "otaheite-apple-medium",
        "minimax-m2.5": "fireworks-minimax-m2.5",
        "kimi-2.6": "fireworks-kimi-k2.6",
        "deepseek-v4pro": "baseten-deepseek-v4-pro",
        "grok-4.3": "xigua-mochi-medium",
        "grok-build0.1": "xinomavro-cake",
        "gemini-3.1pro": "galette-medium-thinking",
        "claude-haiku4.5": "anthropic-haiku-4.5",
        "gemini-3flash": "gingerbread",
    }

    for public_name, notion_name in expected.items():
        assert is_supported_model(public_name)
        assert get_notion_model(public_name) == notion_name
        assert get_standard_model(notion_name) == public_name


def test_captured_display_names_are_registered():
    assert get_display_name("grok-4.3") == "Grok 4.3"
    assert get_display_name("grok-build0.1") == "Grok Build 0.1"
    assert get_display_name("minimax-m2.5") == "MiniMax M2.5"
    assert get_display_name("claude-haiku4.5") == "Claude Haiku 4.5"


def test_gemini_3_5_flash_no_longer_uses_markdown_chat_route():
    assert get_thread_type("gemini-2.5flash") == "workflow"
    assert get_thread_type("gemini-3.5flash") == "workflow"
