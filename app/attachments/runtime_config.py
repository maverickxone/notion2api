from __future__ import annotations

import os
from typing import Any

from app.config import API_KEY, HOST

_RUNTIME_ATTACHMENT_ENABLED: bool | None = None
_PATCHED = False


def _env_bool_text(value: str | None) -> bool | None:
    if value is None:
        return None
    stripped = value.strip().lower()
    if stripped in {"1", "true", "yes", "y", "on"}:
        return True
    if stripped in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _configured_host_is_public() -> bool:
    host = str(HOST or "").strip().lower()
    return host in {"0.0.0.0", "::", "[::]"}


def default_attachments_enabled() -> bool:
    configured = _env_bool_text(os.getenv("ENABLE_ATTACHMENTS"))
    if configured is not None:
        return configured
    # Default on only in the safer cases: explicit API key or local-only host config.
    return bool(API_KEY) or not _configured_host_is_public()


def get_runtime_attachment_enabled() -> bool:
    if _RUNTIME_ATTACHMENT_ENABLED is not None:
        return _RUNTIME_ATTACHMENT_ENABLED
    return default_attachments_enabled()


def set_runtime_attachment_enabled(enabled: bool) -> bool:
    global _RUNTIME_ATTACHMENT_ENABLED
    _RUNTIME_ATTACHMENT_ENABLED = bool(enabled)
    return _RUNTIME_ATTACHMENT_ENABLED


def apply_attachment_runtime_config() -> None:
    global _PATCHED
    if _PATCHED:
        return

    from app.attachments.security import AttachmentPolicy

    original_from_env = AttachmentPolicy.from_env.__func__

    @classmethod
    def patched_from_env(cls: type[AttachmentPolicy]) -> AttachmentPolicy:
        policy = original_from_env(cls)
        policy.enabled = get_runtime_attachment_enabled()
        return policy

    AttachmentPolicy.from_env = patched_from_env
    _PATCHED = True


def attachment_runtime_state() -> dict[str, Any]:
    return {
        "enabled": get_runtime_attachment_enabled(),
        "runtime_override": _RUNTIME_ATTACHMENT_ENABLED,
        "env_value": os.getenv("ENABLE_ATTACHMENTS"),
        "default_enabled": default_attachments_enabled(),
    }
