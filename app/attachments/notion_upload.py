"""Notion-side attachment staging client (mockable, minimal staging flow).

This module implements a layered uploader that talks to a Notion-style
upstream via a pluggable client. Network interactions are delegated to the
provided `notion_client` where possible so tests can mock the client easily.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.attachments.loader import load_attachment_data
from app.attachments.models import InputAttachment, LoadedAttachment, UploadedAttachment


class NotionAttachmentUploadError(RuntimeError):
    """Raised when Notion upload staging or polling fails in a non-retriable way."""

    def __init__(self, message: str, *, reason: str | None = None):
        super().__init__(message)
        self.reason = reason


class NotionAttachmentUploader:
    def __init__(self, notion_client: Any, poll_interval: float | None = None, poll_timeout: float | None = None) -> None:
        self.notion = notion_client

        if poll_interval is None:
            if hasattr(notion_client, "poll_interval") and notion_client.poll_interval is not None:
                poll_interval = notion_client.poll_interval
            else:
                try:
                    poll_interval = float(os.getenv("NOTION_ATTACHMENT_POLL_INTERVAL_SECONDS", "2.0"))
                except (TypeError, ValueError):
                    poll_interval = 2.0

        if poll_timeout is None:
            if hasattr(notion_client, "poll_timeout") and notion_client.poll_timeout is not None:
                poll_timeout = notion_client.poll_timeout
            else:
                try:
                    poll_timeout = float(os.getenv("NOTION_ATTACHMENT_POLL_TIMEOUT_SECONDS", "60.0"))
                except (TypeError, ValueError):
                    poll_timeout = 60.0

        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout

    def upload_attachments(
        self,
        *,
        thread_id: str,
        attachments: List[InputAttachment],
        create_thread: bool = False,
    ) -> Tuple[List[UploadedAttachment], str]:
        uploaded: List[UploadedAttachment] = []
        current_thread_id = thread_id
        should_create_thread = create_thread
        # For each normalized attachment, load bytes and stage
        for att in attachments:
            loaded = load_attachment_data(att)
            descriptor = self.get_upload_descriptor(thread_id=current_thread_id, attachment=att, loaded=loaded, create_thread=should_create_thread)
            if descriptor.get("chat_id"):
                current_thread_id = str(descriptor["chat_id"]).strip() or current_thread_id
            should_create_thread = False
            # perform the multipart upload using the descriptor
            self.do_multipart_upload(descriptor, loaded)
            # extract a definitive file id — must be present in descriptor
            file_id = self.extract_attachment_file_id(descriptor)
            if not file_id:
                raise NotionAttachmentUploadError("Upload descriptor missing file identifier", reason="missing_file_id")

            attachment_url = str(descriptor.get("attachment_url") or "")
            if not attachment_url:
                raise NotionAttachmentUploadError("Upload descriptor missing attachment URL", reason="missing_attachment_url")

            task_id = self.enqueue_attachment_processing(attachment_url=attachment_url, thread_id=current_thread_id)
            result = self.wait_attachment_task(task_id)
            # normalize result handling
            if not isinstance(result, dict) or not result.get("success"):
                raise NotionAttachmentUploadError(f"Attachment processing failed for task {task_id}", reason="task_failed")

            signed_url = self.get_signed_attachment_url(attachment_url=attachment_url, thread_id=current_thread_id, download_name=loaded.name)
            metadata = self.build_attachment_step_metadata(uploaded={
                "fileSizeBytes": loaded.size_bytes,
                "contentType": loaded.content_type,
                "source": loaded.source,
                "taskId": task_id,
                "fileId": file_id,
                "attachmentUrl": attachment_url,
            })

            uploaded.append(
                UploadedAttachment(
                    name=loaded.name,
                    content_type=loaded.content_type,
                    size_bytes=loaded.size_bytes,
                    source=loaded.source,
                    file_id=file_id,
                    thread_mounted=True,
                    attachment_url=attachment_url,
                    signed_get_url=signed_url or descriptor.get("signed_get_url", "") or "",
                    task_id=task_id,
                    metadata=metadata,
                )
            )

        return uploaded, current_thread_id

    # The following methods delegate to the notion client when available so tests can mock them.
    def get_upload_descriptor(self, *, thread_id: str, attachment: InputAttachment, loaded: LoadedAttachment, create_thread: bool) -> Dict[str, Any]:
        if not hasattr(self.notion, "request_upload_descriptor"):
            raise NotionAttachmentUploadError("Notion client missing request_upload_descriptor", reason="missing_method")

        descriptor = self.notion.request_upload_descriptor(
            name=loaded.name,
            content_type=loaded.content_type,
            size=loaded.size_bytes,
            thread_id=thread_id,
            create_thread=create_thread,
        )

        # validate basic descriptor shape
        if not isinstance(descriptor, dict):
            raise NotionAttachmentUploadError("Invalid upload descriptor returned by Notion client", reason="invalid_descriptor")

        fields = descriptor.get("fields")
        if fields is not None and not isinstance(fields, dict):
            raise NotionAttachmentUploadError("Upload descriptor fields must be a dict", reason="invalid_descriptor_fields")

        # require either upload_url (for multipart) or file_id/attachment_url provided
        if not descriptor.get("upload_url") and not descriptor.get("file_id") and not descriptor.get("attachment_url"):
            raise NotionAttachmentUploadError("Upload descriptor missing upload_url or file identifier", reason="descriptor_incomplete")

        return descriptor

    def do_multipart_upload(self, descriptor: Dict[str, Any], loaded: LoadedAttachment) -> None:
        # Prefer notion client helper
        if hasattr(self.notion, "perform_multipart_upload"):
            try:
                return self.notion.perform_multipart_upload(descriptor=descriptor, name=loaded.name, data=loaded.data, content_type=loaded.content_type)
            except Exception as exc:
                raise NotionAttachmentUploadError("Notion client multipart upload failed", reason="upload_failed") from exc

        # Otherwise require an upload_url for direct multipart upload
        upload_url = descriptor.get("upload_url")
        if not upload_url:
            raise NotionAttachmentUploadError("No upload_url available for multipart upload", reason="missing_upload_url")

        fields = descriptor.get("fields") or {}
        import requests

        files = {"file": (loaded.name, loaded.data, loaded.content_type)}
        try:
            resp = requests.post(upload_url, data=fields, files=files, timeout=60)
        except Exception as exc:
            raise NotionAttachmentUploadError("Multipart upload HTTP request failed", reason="upload_http_error") from exc

        if resp.status_code < 200 or resp.status_code >= 300:
            raise NotionAttachmentUploadError(f"Multipart upload failed with HTTP {resp.status_code}", reason="upload_http_status")

    def extract_attachment_file_id(self, descriptor: Dict[str, Any]) -> Optional[str]:
        fid = descriptor.get("file_id")
        if fid:
            return fid
        file_obj = descriptor.get("file")
        if isinstance(file_obj, dict):
            return file_obj.get("id")
        # try parse attachment_url if present (not guaranteed)
        attachment_url = descriptor.get("attachment_url")
        if isinstance(attachment_url, str) and attachment_url:
            # naive parse: basename
            try:
                from urllib.parse import urlparse

                path = urlparse(attachment_url).path
                if path:
                    return path.rstrip("/").split("/")[-1]
            except Exception:
                pass
        return None

    def enqueue_attachment_processing(self, *, attachment_url: str, thread_id: str) -> str:
        if not hasattr(self.notion, "enqueue_attachment_processing"):
            raise NotionAttachmentUploadError("Notion client missing enqueue_attachment_processing", reason="missing_method")
        return self.notion.enqueue_attachment_processing(attachment_url=attachment_url, thread_id=thread_id)

    def wait_attachment_task(self, task_id: str) -> Dict[str, Any]:
        # Poll notion client for task status
        start = time.time()
        while True:
            if not hasattr(self.notion, "get_task_status"):
                raise NotionAttachmentUploadError("Notion client missing get_task_status", reason="missing_method")

            status = self.notion.get_task_status(task_id)
            if not isinstance(status, dict):
                raise NotionAttachmentUploadError("Malformed task status result", reason="malformed_status")

            state = status.get("status")
            if state in {"completed", "failed"}:
                return {"success": bool(status.get("success", state == "completed")), "status": state}

            if time.time() - start > self.poll_timeout:
                raise NotionAttachmentUploadError("Attachment task polling timed out", reason="timeout")

            time.sleep(self.poll_interval)

    def get_signed_attachment_url(self, *, attachment_url: str, thread_id: str, download_name: str) -> str:
        if not hasattr(self.notion, "get_signed_read_url"):
            return ""
        return self.notion.get_signed_read_url(attachment_url, thread_id=thread_id, download_name=download_name)

    def build_attachment_step_metadata(self, uploaded: Dict[str, Any]) -> Dict[str, Any]:
        # Only include safe, non-sensitive metadata
        allowed_keys = {"fileSizeBytes", "contentType", "source", "taskId", "fileId", "attachmentUrl"}
        return {k: v for k, v in uploaded.items() if k in allowed_keys}
