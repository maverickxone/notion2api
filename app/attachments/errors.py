"""Attachment-specific exceptions."""

from __future__ import annotations


class AttachmentError(ValueError):
    """Base exception for caller-side attachment validation failures."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "invalid_attachment",
        param: str = "attachments",
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.param = param
        self.status_code = status_code
