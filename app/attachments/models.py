"""Attachment data models used by the upload pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

AttachmentSource = Literal["inline_data", "remote_url", "local_path"]

DEFAULT_ATTACHMENT_PROMPT = "Analyze the uploaded attachment."


@dataclass(slots=True)
class InputAttachment:
    """Normalized attachment descriptor extracted from an OpenAI-compatible request."""

    name: str = ""
    content_type: str = ""
    source: AttachmentSource | str = ""
    url: str = ""
    path: str = ""
    data: bytes | str = b""

    def __repr__(self) -> str:  # hide raw data to avoid accidental leaks when stringified
        return f"InputAttachment(name={self.name!r}, content_type={self.content_type!r}, source={self.source!r}, url={self.url!r}, path={self.path!r}, data=<redacted>)"


@dataclass(slots=True)
class LoadedAttachment:
    """Attachment bytes after validation and source loading."""

    name: str
    content_type: str
    size_bytes: int
    source: str
    data: bytes


@dataclass(slots=True)
class UploadedAttachment:
    """Attachment metadata after Notion-side staging and processing."""

    name: str
    content_type: str
    size_bytes: int
    source: str
    file_id: str = ""
    thread_mounted: bool = False
    attachment_url: str = ""
    signed_get_url: str = ""
    task_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
