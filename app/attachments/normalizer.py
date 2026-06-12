"""Normalize OpenAI-compatible attachment request shapes."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.attachments.models import DEFAULT_ATTACHMENT_PROMPT, InputAttachment

TEXT_PART_TYPES = {"text", "input_text", "output_text"}
ATTACHMENT_PART_TYPES = {"image_url", "input_image", "file", "input_file", "attachment"}


def _string(value: Any) -> str:
    return str(value or "").strip()


def _content_type_from_data_url(value: str) -> str:
    if not value.startswith("data:"):
        return ""
    header = value.split(",", 1)[0]
    return header[5:].split(";", 1)[0].strip().lower()


def _looks_like_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme.lower() in {"http", "https"}


def _looks_like_windows_path(value: str) -> bool:
    return len(value) >= 3 and value[1] == ":" and value[2] in {"\\", "/"}


def _looks_like_path(value: str) -> bool:
    if not value:
        return False
    if _looks_like_windows_path(value):
        return True
    if value.startswith(("/", "\\\\", ".\\", "./", "..\\", "../")):
        return True

    parsed = urlparse(value)
    if parsed.scheme.lower() == "file":
        return True
    if parsed.scheme:
        return False
    return False


def _image_url_value(part: dict[str, Any]) -> str:
    image_url = part.get("image_url")
    if isinstance(image_url, dict):
        return _string(image_url.get("url"))
    return _string(image_url)


def _attachment_name(part: dict[str, Any], fallback: str = "") -> str:
    return _string(
        part.get("name")
        or part.get("filename")
        or part.get("file_name")
        or part.get("title")
        or fallback
    )


def _attachment_content_type(part: dict[str, Any], inline_value: str = "") -> str:
    explicit = _string(
        part.get("content_type")
        or part.get("mime_type")
        or part.get("media_type")
    ).lower()
    if explicit:
        return explicit
    data_url_type = _content_type_from_data_url(inline_value)
    if data_url_type:
        return data_url_type
    if part.get("type") in {"image_url", "input_image"}:
        return "image/png"
    return ""


def _attachment_from_reference(part: dict[str, Any], ref: str) -> InputAttachment:
    content_type = _attachment_content_type(part, ref)
    name = _attachment_name(part)
    if ref.startswith("data:"):
        return InputAttachment(name=name, content_type=content_type, source="inline_data", data=ref)
    if _looks_like_url(ref):
        return InputAttachment(name=name, content_type=content_type, source="remote_url", url=ref)
    if _looks_like_path(ref):
        return InputAttachment(name=name, content_type=content_type, source="local_path", path=ref)
    return InputAttachment(name=name, content_type=content_type, source="inline_data", data=ref)


def _attachment_from_part(part: dict[str, Any]) -> InputAttachment | None:
    part_type = _string(part.get("type")).lower()

    if part_type in {"image_url", "input_image"}:
        ref = _image_url_value(part) or _string(part.get("url"))
        if ref:
            return _attachment_from_reference(part, ref)

    if part_type in {"file", "input_file", "attachment"} or any(
        key in part for key in ("file_data", "data", "file_url", "url", "path")
    ):
        inline_value = _string(part.get("file_data") or part.get("data"))
        if inline_value:
            return _attachment_from_reference(part, inline_value)

        ref = _string(part.get("file_url") or part.get("url") or part.get("path"))
        if ref:
            return _attachment_from_reference(part, ref)

    image_ref = _image_url_value(part)
    if image_ref:
        return _attachment_from_reference(part, image_ref)

    return None


def _top_level_attachment(item: Any) -> InputAttachment | None:
    if not isinstance(item, dict):
        return None
    normalized = dict(item)
    if not normalized.get("type"):
        content_type = _string(normalized.get("content_type") or normalized.get("mime_type")).lower()
        if content_type.startswith("image/") or normalized.get("image_url"):
            normalized["type"] = "image_url"
        else:
            normalized["type"] = "file"
    return _attachment_from_part(normalized)


def _attachment_signature(attachment: InputAttachment) -> tuple[Any, ...]:
    data_value = attachment.data
    if isinstance(data_value, bytes):
        data_value = data_value.decode("utf-8", errors="ignore")
    return (
        str(attachment.source or ""),
        str(attachment.name or ""),
        str(attachment.content_type or ""),
        str(attachment.url or ""),
        str(attachment.path or ""),
        str(data_value or ""),
    )


def _extract_text_and_attachments(content: Any) -> tuple[str, list[InputAttachment]]:
    if content is None:
        return "", []
    if isinstance(content, str):
        return content, []
    if not isinstance(content, list):
        return str(content), []

    text_parts: list[str] = []
    attachments: list[InputAttachment] = []

    for item in content:
        if isinstance(item, str):
            if item:
                text_parts.append(item)
            continue
        if not isinstance(item, dict):
            continue

        item_type = _string(item.get("type")).lower()
        if item_type in TEXT_PART_TYPES or (not item_type and "text" in item):
            text = _string(item.get("text"))
            if text:
                text_parts.append(text)
            continue

        attachment = _attachment_from_part(item)
        if attachment is not None:
            attachments.append(attachment)
            continue

        if "text" in item:
            text = _string(item.get("text"))
            if text:
                text_parts.append(text)

    return "\n".join(part for part in text_parts if part), attachments


def _append_attachment_fallback(messages: list[dict[str, Any]], attachments: list[InputAttachment]) -> None:
    if not attachments:
        return
    for msg in reversed(messages):
        if str(msg.get("role") or "").lower() == "user":
            if not _string(msg.get("content")):
                msg["content"] = DEFAULT_ATTACHMENT_PROMPT
            return
    messages.append({"role": "user", "content": DEFAULT_ATTACHMENT_PROMPT})


def normalize_chat_messages(
    messages: list[dict[str, Any]],
    top_level_attachments: list[Any] | None = None,
) -> tuple[list[dict[str, Any]], list[InputAttachment]]:
    """Return text-clean messages and normalized attachments."""

    normalized_messages: list[dict[str, Any]] = []
    attachments: list[InputAttachment] = []

    for raw_message in messages or []:
        if not isinstance(raw_message, dict):
            continue
        msg = dict(raw_message)
        text, message_attachments = _extract_text_and_attachments(msg.get("content"))
        msg["content"] = text
        normalized_messages.append(msg)
        attachments.extend(message_attachments)

    for item in top_level_attachments or []:
        attachment = _top_level_attachment(item)
        if attachment is not None and _attachment_signature(attachment) not in {
            _attachment_signature(existing) for existing in attachments
        }:
            attachments.append(attachment)

    _append_attachment_fallback(normalized_messages, attachments)
    return normalized_messages, attachments


def normalize_responses_input(
    input_value: Any,
    top_level_attachments: list[Any] | None = None,
) -> tuple[list[dict[str, Any]], list[InputAttachment]]:
    """Return chat-compatible messages and normalized attachments from Responses input."""

    if isinstance(input_value, str):
        return normalize_chat_messages(
            [{"role": "user", "content": input_value}],
            top_level_attachments,
        )

    messages: list[dict[str, Any]] = []
    attachments: list[InputAttachment] = []

    if isinstance(input_value, list):
        for item in input_value:
            if isinstance(item, str):
                messages.append({"role": "user", "content": item})
                continue
            if not isinstance(item, dict):
                continue

            role = _string(item.get("role") or "user").lower()
            if role == "developer":
                role = "system"
            if role not in {"system", "user", "assistant"}:
                role = "user"

            if item.get("type") == "message" and "content" in item:
                text, item_attachments = _extract_text_and_attachments(item.get("content"))
            elif "content" in item:
                text, item_attachments = _extract_text_and_attachments(item.get("content"))
            elif _string(item.get("type")).lower() in TEXT_PART_TYPES:
                text = _string(item.get("text"))
                item_attachments = []
            else:
                attachment = _attachment_from_part(item)
                text = ""
                item_attachments = [attachment] if attachment is not None else []

            if text:
                messages.append({"role": role, "content": text})
            attachments.extend(item_attachments)

    cleaned_messages, top_level = normalize_chat_messages(messages, top_level_attachments)
    attachments = [*attachments, *top_level]
    _append_attachment_fallback(cleaned_messages, attachments)
    return cleaned_messages, attachments
