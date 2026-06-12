"""Load attachment bytes from inline data, remote URLs, or local paths."""

from __future__ import annotations

import base64
import binascii
import mimetypes
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from app.attachments.errors import AttachmentError
from app.attachments.models import InputAttachment, LoadedAttachment
from app.attachments.security import (
    AttachmentPolicy,
    validate_content_type,
    validate_local_path_allowed,
    validate_remote_url,
    validate_size,
)


def _decode_data_url(value: str) -> tuple[bytes, str]:
    header, separator, payload = value.partition(",")
    if not separator or not header.startswith("data:"):
        raise AttachmentError(
            "Invalid attachment data URL.",
            code="invalid_attachment_data_url",
            param="attachments.data",
        )
    content_type = header[5:].split(";", 1)[0].strip().lower()
    is_base64 = ";base64" in header.lower()
    if not is_base64:
        return payload.encode("utf-8"), content_type

    try:
        return base64.b64decode(payload, validate=True), content_type
    except binascii.Error as exc:
        raise AttachmentError(
            "Invalid base64 attachment data.",
            code="invalid_attachment_base64",
            param="attachments.data",
        ) from exc


def decode_inline_data(value: bytes | str) -> tuple[bytes, str]:
    if isinstance(value, bytes):
        return value, ""
    text = str(value or "").strip()
    if text.startswith("data:"):
        return _decode_data_url(text)
    try:
        return base64.b64decode(text, validate=True), ""
    except binascii.Error as exc:
        raise AttachmentError(
            "Invalid base64 attachment data.",
            code="invalid_attachment_base64",
            param="attachments.data",
        ) from exc


def infer_content_type(name: str, fallback: str = "") -> str:
    if fallback:
        return fallback.split(";", 1)[0].strip().lower()
    guessed, _ = mimetypes.guess_type(name or "")
    return str(guessed or "").lower()


def _infer_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name
    return name or "attachment"


def _load_local_path(attachment: InputAttachment, policy: AttachmentPolicy) -> LoadedAttachment:
    validate_local_path_allowed(policy)
    path = Path(attachment.path).expanduser().resolve()

    if policy.local_root:
        root = Path(policy.local_root).expanduser().resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise AttachmentError(
                "Local attachment path is outside ATTACHMENT_LOCAL_ROOT.",
                code="attachment_path_outside_root",
                param="attachments.path",
            ) from exc

    data = path.read_bytes()
    validate_size(len(data), policy)
    name = attachment.name or path.name or "attachment"
    content_type = validate_content_type(infer_content_type(name, attachment.content_type), policy)
    return LoadedAttachment(
        name=name,
        content_type=content_type,
        size_bytes=len(data),
        source="local_path",
        data=data,
    )


def _load_remote_url(
    attachment: InputAttachment,
    policy: AttachmentPolicy,
    session: requests.Session | None,
) -> LoadedAttachment:
    url = validate_remote_url(attachment.url, policy)
    http = session or requests.Session()

    for redirect_index in range(policy.max_redirects + 1):
        response = http.get(
            url,
            stream=True,
            timeout=policy.download_timeout_seconds,
            allow_redirects=False,
        )
        if response.is_redirect or response.is_permanent_redirect:
            if redirect_index >= policy.max_redirects:
                raise AttachmentError(
                    "Remote attachment URL exceeded redirect limit.",
                    code="attachment_url_redirect_limit",
                    param="attachments.url",
                )
            location = response.headers.get("Location", "")
            if not location:
                raise AttachmentError(
                    "Remote attachment redirect did not include a Location header.",
                    code="attachment_url_bad_redirect",
                    param="attachments.url",
                )
            url = validate_remote_url(urljoin(url, location), policy)
            continue

        if response.status_code < 200 or response.status_code >= 300:
            raise AttachmentError(
                f"Remote attachment download failed with HTTP {response.status_code}.",
                code="attachment_url_download_failed",
                param="attachments.url",
            )

        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            validate_size(total, policy)
            chunks.append(chunk)
        data = b"".join(chunks)
        name = attachment.name or _infer_name_from_url(response.url)
        content_type = validate_content_type(
            infer_content_type(name, response.headers.get("Content-Type") or attachment.content_type),
            policy,
        )
        return LoadedAttachment(
            name=name,
            content_type=content_type,
            size_bytes=len(data),
            source="remote_url",
            data=data,
        )

    raise AttachmentError(
        "Remote attachment URL could not be downloaded.",
        code="attachment_url_download_failed",
        param="attachments.url",
    )


def load_attachment_data(
    attachment: InputAttachment,
    policy: AttachmentPolicy | None = None,
    session: requests.Session | None = None,
) -> LoadedAttachment:
    """Load and validate bytes for one normalized attachment."""

    policy = policy or AttachmentPolicy.from_env()

    if attachment.source == "inline_data":
        data, inline_type = decode_inline_data(attachment.data)
        validate_size(len(data), policy)
        name = attachment.name or "attachment"
        content_type = validate_content_type(infer_content_type(name, attachment.content_type or inline_type), policy)
        return LoadedAttachment(
            name=name,
            content_type=content_type,
            size_bytes=len(data),
            source="inline_data",
            data=data,
        )

    if attachment.source == "local_path":
        return _load_local_path(attachment, policy)

    if attachment.source == "remote_url":
        return _load_remote_url(attachment, policy, session)

    raise AttachmentError(
        "Attachment has no usable source.",
        code="attachment_source_missing",
        param="attachments",
    )
