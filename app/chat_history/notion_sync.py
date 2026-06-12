from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.chat_history.extractor import collect_hydration_message_ids
from app.chat_history.har_importer import import_chat_object
from app.notion_client import NotionOpusAPI, NotionUpstreamError


TRANSCRIPTS_ENDPOINT = "https://www.notion.so/api/v3/getInferenceTranscriptsForUser"
HYDRATE_ENDPOINT = "https://www.notion.so/api/v3/syncRecordValuesSpaceInitial"


def _merge_bundle(target: dict[str, Any], source: dict[str, Any]) -> None:
    target["threads"].update(source.get("threads", {}))
    target["messages"].update(source.get("messages", {}))


def _post_json(client: NotionOpusAPI, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    # pylint: disable-next=protected-access
    response = client._scraper.post(  # noqa: SLF001 - reusing the client transport and auth headers
        url,
        # pylint: disable-next=protected-access
        headers=client._build_chat_history_headers(),  # noqa: SLF001 - shared header shape already exists on the client
        json=payload,
        timeout=(15, 60),
    )

    if response.status_code != 200:
        excerpt = (response.text or "").strip().replace("\n", " ")[:300]
        raise NotionUpstreamError(
            f"Notion chat-history sync returned HTTP {response.status_code}.",
            status_code=response.status_code,
            retriable=response.status_code >= 500 or response.status_code == 429,
            response_excerpt=excerpt,
        )

    try:
        body = response.json()
    except Exception as exc:
        raise NotionUpstreamError(
            "Notion chat-history sync returned invalid JSON.",
            status_code=502,
            retriable=True,
            response_excerpt=(response.text or "").strip()[:300],
        ) from exc

    if not isinstance(body, dict):
        raise NotionUpstreamError(
            "Notion chat-history sync returned an unexpected payload.",
            status_code=502,
            retriable=True,
            response_excerpt=(response.text or "").strip()[:300],
        )

    return body


def _threads_without_messages(bundle: dict[str, Any]) -> int:
    messages_by_thread: dict[str, int] = defaultdict(int)
    for message in bundle.get("messages", {}).values():
        thread_id = message.get("thread_id")
        if isinstance(thread_id, str) and thread_id.strip():
            messages_by_thread[thread_id] += 1
    count = 0
    for thread_id, thread in bundle.get("threads", {}).items():
        if not thread.get("message_ids") and not messages_by_thread.get(thread_id):
            count += 1
    return count


def _collect_page_hydration_ids(page_bundle: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for thread in page_bundle.get("threads", {}).values():
        ids.update(collect_hydration_message_ids(thread))
        raw = thread.get("raw") if isinstance(thread, dict) else None
        if raw:
            ids.update(collect_hydration_message_ids(raw))
    for message in page_bundle.get("messages", {}).values():
        ids.update(collect_hydration_message_ids(message))
        raw = message.get("raw") if isinstance(message, dict) else None
        if raw:
            ids.update(collect_hydration_message_ids(raw))
    return {message_id for message_id in ids if isinstance(message_id, str) and message_id.strip()}


def hydrate_message_ids_from_notion(
    client: NotionOpusAPI,
    message_ids: list[str] | set[str],
    *,
    fallback_thread_id: str | None = None,
    hydrate_batch_size: int = 50,
) -> dict[str, Any]:
    """Hydrate specific Notion thread-message IDs into a chat-history bundle."""
    clean_ids = sorted({str(message_id).strip() for message_id in message_ids if str(message_id or "").strip()})
    bundle: dict[str, Any] = {"threads": {}, "messages": {}, "endpoint_counts": defaultdict(int)}
    hydration_batches = 0
    hydrated_messages_seen = 0

    for start_index in range(0, len(clean_ids), hydrate_batch_size):
        batch = clean_ids[start_index:start_index + hydrate_batch_size]
        hydrate_payload = {
            "requests": [
                {
                    "pointer": {
                        "table": "thread_message",
                        "id": message_id,
                        "spaceId": client.space_id,
                    },
                    "version": -1,
                }
                for message_id in batch
            ]
        }
        hydrate_obj = _post_json(client, HYDRATE_ENDPOINT, hydrate_payload)
        bundle["endpoint_counts"]["syncRecordValuesSpaceInitial"] += 1
        hydration_batches += 1
        hydrate_bundle = import_chat_object(hydrate_obj)
        if fallback_thread_id:
            for message in hydrate_bundle.get("messages", {}).values():
                if not message.get("thread_id"):
                    message["thread_id"] = fallback_thread_id
        hydrated_messages_seen += len(hydrate_bundle.get("messages", {}))
        _merge_bundle(bundle, hydrate_bundle)

    bundle["endpoint_counts"] = dict(bundle["endpoint_counts"])
    bundle["stats"] = {
        "hydration_candidate_ids": len(clean_ids),
        "hydrated_message_ids": len(clean_ids),
        "hydration_batches": hydration_batches,
        "hydrated_messages_seen": hydrated_messages_seen,
        "messages": len(bundle.get("messages", {})),
    }
    return bundle


def hydrate_thread_record_from_notion(client: NotionOpusAPI, thread_id: str) -> dict[str, Any]:
    payload = {
        "requests": [
            {
                "pointer": {
                    "table": "thread",
                    "id": thread_id,
                    "spaceId": client.space_id,
                },
                "version": -1,
            }
        ]
    }
    hydrate_obj = _post_json(client, HYDRATE_ENDPOINT, payload)
    bundle = import_chat_object(hydrate_obj)
    bundle["endpoint_counts"] = {"syncRecordValuesSpaceInitial": 1}
    return bundle


def hydrate_thread_from_notion(
    client: NotionOpusAPI,
    thread: dict[str, Any],
    *,
    hydrate_batch_size: int = 50,
) -> dict[str, Any]:
    """Hydrate only the messages referenced by one selected archived thread."""
    thread_id = str(thread.get("id") or "").strip() or None
    ids: set[str] = set()
    ids.update(collect_hydration_message_ids(thread))
    raw = thread.get("raw") if isinstance(thread.get("raw"), dict) else None
    if raw:
        ids.update(collect_hydration_message_ids(raw))
    thread_bundle: dict[str, Any] = {"threads": {}, "messages": {}, "endpoint_counts": {}}
    if thread_id:
        thread_bundle = hydrate_thread_record_from_notion(client, thread_id)
        hydrated_thread = thread_bundle.get("threads", {}).get(thread_id)
        if hydrated_thread:
            ids.update(collect_hydration_message_ids(hydrated_thread))
            hydrated_raw = hydrated_thread.get("raw") if isinstance(hydrated_thread.get("raw"), dict) else None
            if hydrated_raw:
                ids.update(collect_hydration_message_ids(hydrated_raw))
    if not ids and thread_id:
        ids.add(thread_id)

    bundle = hydrate_message_ids_from_notion(
        client,
        ids,
        fallback_thread_id=thread_id,
        hydrate_batch_size=hydrate_batch_size,
    )
    if thread_bundle.get("threads"):
        _merge_bundle(bundle, {"threads": thread_bundle.get("threads", {}), "messages": {}})
        for key, value in thread_bundle.get("endpoint_counts", {}).items():
            bundle["endpoint_counts"][key] = bundle["endpoint_counts"].get(key, 0) + value
        if "stats" in bundle:
            bundle["stats"]["hydration_batches"] = bundle["stats"].get("hydration_batches", 0) + sum(thread_bundle.get("endpoint_counts", {}).values())
    fallback_text = str(thread.get("title") or thread.get("first_message_preview") or thread.get("last_message_preview") or "").strip()
    if thread_id and fallback_text:
        for message in bundle.get("messages", {}).values():
            if message.get("id") == thread_id or not message.get("thread_id"):
                message["thread_id"] = thread_id
            if message.get("thread_id") == thread_id and not str(message.get("text") or "").strip():
                message["text"] = fallback_text
    return bundle


def sync_chat_history_from_notion(
    client: NotionOpusAPI,
    *,
    limit: int = 50,
    max_pages: int = 20,
    hydrate: bool = False,
    hydrate_batch_size: int = 50,
) -> dict[str, Any]:
    """Read-only direct sync from Notion transcript RPCs into the local archive bundle."""
    thread_parent_pointer = {
        "table": "space",
        "id": client.space_id,
        "spaceId": client.space_id,
    }

    bundle: dict[str, Any] = {"threads": {}, "messages": {}, "endpoint_counts": defaultdict(int)}
    seen_message_ids: set[str] = set()
    cursor: str | None = None
    pages_scanned = 0
    stopped_reason = "completed"

    while pages_scanned < max_pages:
        payload: dict[str, Any] = {
            "threadParentPointer": thread_parent_pointer,
            "limit": limit,
            "includeWriterChats": False,
        }
        if cursor:
            payload["cursor"] = cursor

        page_obj = _post_json(client, TRANSCRIPTS_ENDPOINT, payload)
        pages_scanned += 1
        bundle["endpoint_counts"]["getInferenceTranscriptsForUser"] += 1

        page_bundle = import_chat_object(page_obj)
        _merge_bundle(bundle, page_bundle)
        seen_message_ids.update(_collect_page_hydration_ids(page_bundle))

        if not page_bundle.get("threads") and not page_bundle.get("messages"):
            stopped_reason = "empty_page"

        next_cursor = page_obj.get("nextCursor") or page_obj.get("next_cursor")
        has_more = bool(page_obj.get("hasMore"))
        if isinstance(next_cursor, str) and next_cursor.strip() and has_more:
            cursor = next_cursor.strip()
            continue
        cursor = next_cursor if isinstance(next_cursor, str) else None
        if stopped_reason != "empty_page":
            stopped_reason = "no_next_cursor" if not cursor else "has_more_false"
        break
    else:
        stopped_reason = "max_pages"

    message_ids = sorted(seen_message_ids)
    hydration_batches = 0
    hydrated_messages_seen = 0
    if hydrate:
        hydrate_bundle = hydrate_message_ids_from_notion(
            client,
            message_ids,
            hydrate_batch_size=hydrate_batch_size,
        )
        _merge_bundle(bundle, hydrate_bundle)
        for key, value in hydrate_bundle.get("endpoint_counts", {}).items():
            bundle["endpoint_counts"][key] += value
        hydrate_stats = hydrate_bundle.get("stats", {})
        hydration_batches = int(hydrate_stats.get("hydration_batches") or 0)
        hydrated_messages_seen = int(hydrate_stats.get("hydrated_messages_seen") or 0)

    messages_seen = len(bundle["messages"])
    summary = {
        "pages_scanned": pages_scanned,
        "threads_seen": len(bundle["threads"]),
        "messages_seen": messages_seen,
        "threads_without_messages": _threads_without_messages(bundle),
        "next_cursor": cursor,
        "stopped_reason": stopped_reason,
        "hydrate": bool(hydrate),
        "hydration_candidate_ids": len(message_ids),
        "hydration_batches": hydration_batches,
        "hydrated_messages_seen": hydrated_messages_seen,
    }
    bundle["endpoint_counts"] = dict(bundle["endpoint_counts"])
    bundle["sync_summary"] = summary
    bundle["stats"] = {
        "pages_fetched": pages_scanned,
        "pages_scanned": pages_scanned,
        "threads": len(bundle["threads"]),
        "messages": messages_seen,
        "hydrated_message_ids": len(message_ids) if hydrate else 0,
        "hydration_candidate_ids": len(message_ids),
        "hydration_batches": hydration_batches,
        "hydrated_messages_seen": hydrated_messages_seen,
        "threads_without_messages": summary["threads_without_messages"],
        "next_cursor": cursor,
        "stopped_reason": stopped_reason,
        "hydrate": bool(hydrate),
    }
    return bundle
