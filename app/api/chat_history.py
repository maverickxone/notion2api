from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.chat_history.har_importer import import_har_object
from app.chat_history.notion_sync import hydrate_thread_from_notion, sync_chat_history_from_notion
from app.chat_history.store import ChatHistoryStore, get_default_chat_history_db_path
from app.notion_client import NotionUpstreamError

router = APIRouter(prefix="/chat-history", tags=["chat-history"])


def _store() -> ChatHistoryStore:
    return ChatHistoryStore()


def _bool_payload(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "full", "hydrate"}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _clean_thread_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, bool) or item is None or isinstance(item, (dict, list, tuple, set)):
            continue
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _get_account_client(request: Request, account_index: int):
    pool = request.app.state.account_pool
    clients = getattr(pool, "clients", [])
    if not clients:
        raise HTTPException(status_code=503, detail="No configured Notion accounts are available")
    if account_index < 0 or account_index >= len(clients):
        raise HTTPException(status_code=400, detail="account_index is out of range")
    return clients[account_index]


async def _request_payload(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Request body must be JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")
    return payload


def _bulk_delete_from_payload(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    thread_ids = _clean_thread_ids(payload.get("thread_ids") or payload.get("threadIds"))
    if not thread_ids:
        raise HTTPException(status_code=400, detail="thread_ids must contain at least one thread id")
    if len(thread_ids) > 200:
        raise HTTPException(status_code=400, detail="Bulk delete is limited to 200 thread ids per request")

    remote = _bool_payload(payload.get("remote"), default=True)
    local = _bool_payload(payload.get("local"), default=True)
    account_index = payload.get("account_index", 0)
    try:
        account_index = int(account_index)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid delete parameters") from exc

    store = _store()
    existing_ids = store.existing_thread_ids(thread_ids)
    results: dict[str, Any] = {"success": [], "failed": []}

    for thread_id in thread_ids:
        if thread_id not in existing_ids:
            results["failed"].append(
                {
                    "thread_id": thread_id,
                    "stage": "local_auth",
                    "error": "Thread ID not found in the local archive.",
                }
            )

    known_ids = [thread_id for thread_id in thread_ids if thread_id in existing_ids]

    if remote:
        client = _get_account_client(request, account_index)
        for thread_id in known_ids:
            try:
                remote_result = client.delete_threads([thread_id])
            except NotionUpstreamError as exc:
                results["failed"].append(
                    {
                        "thread_id": thread_id,
                        "stage": "remote",
                        "error": exc.response_excerpt or str(exc),
                    }
                )
                continue
            accepted = int(remote_result.get("remote_deleted", 0) or remote_result.get("remote_accepted", 0) or 0) > 0
            if accepted:
                results["success"].append(thread_id)
            else:
                results["failed"].append(
                    {
                        "thread_id": thread_id,
                        "stage": "remote",
                        "error": "Remote delete transaction was not accepted.",
                    }
                )
    else:
        results["success"].extend(known_ids)

    local_result: dict[str, int] = {"threads_deleted": 0, "messages_deleted": 0, "fts_deleted": 0}
    if local and results["success"]:
        local_result = store.delete_threads(results["success"])

    return {
        "requested": len(thread_ids),
        "remote": remote,
        "local": local,
        "results": results,
        "remote_result": {
            "remote_accepted": len(results["success"]) if remote else 0,
            "remote_failed": len([item for item in results["failed"] if item.get("stage") == "remote"]),
            "failed_ids": [item.get("thread_id") for item in results["failed"] if item.get("stage") == "remote"],
        },
        "local_result": local_result,
        "message": f"Processed {len(thread_ids)} thread(s): {len(results['success'])} succeeded, {len(results['failed'])} failed.",
    }


@router.get("/status")
def status() -> dict[str, Any]:
    return {
        "status": "ok",
        "db_path": get_default_chat_history_db_path(),
        "capabilities": [
            "har_import",
            "notion_direct_sync",
            "metadata_only_sync",
            "selected_thread_hydration",
            "bulk_remote_delete",
            "bulk_delete_partial_results",
            "bulk_delete_post_fallback",
            "hydration_diagnostics",
            "thread_debug",
            "local_archive",
            "local_search",
            "markdown_export",
        ],
    }


@router.post("/import/har")
async def import_har(request: Request) -> dict[str, Any]:
    """Import a browser HAR JSON object containing Notion AI chat-history records."""
    payload = await _request_payload(request)

    har = payload.get("har") if "har" in payload else payload
    if not isinstance(har, dict):
        raise HTTPException(status_code=400, detail="HAR payload must be a JSON object")

    bundle = import_har_object(har)
    imported = _store().upsert_bundle(bundle)
    return {"imported": imported, "endpoint_counts": bundle.get("endpoint_counts", {})}


@router.post("/sync/notion")
@router.post("/import/notion")
async def sync_from_notion(request: Request) -> dict[str, Any]:
    """Pull chat-history metadata by default; hydrate full message bodies only when requested."""
    try:
        payload = await request.json()
    except (TypeError, ValueError):
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    account_index = payload.get("account_index", 0)
    limit = payload.get("limit", 100)
    max_pages = payload.get("max_pages", 5)
    hydrate = _bool_payload(payload.get("hydrate"), default=False)

    try:
        account_index = int(account_index)
        limit = max(1, min(int(limit), 500))
        max_pages = max(1, min(int(max_pages), 20))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid import parameters") from exc

    client = _get_account_client(request, account_index)
    try:
        bundle = sync_chat_history_from_notion(client, limit=limit, max_pages=max_pages, hydrate=hydrate)
    except NotionUpstreamError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "message": "Unable to fetch chat history from Notion.",
                    "type": "upstream_error",
                    "param": None,
                    "code": "upstream_error",
                    "detail": exc.response_excerpt,
                }
            },
        ) from exc

    imported = _store().upsert_bundle(bundle)
    summary = dict(bundle.get("sync_summary", {}))
    summary.update(
        {
            "threads_inserted": imported.get("threads_inserted", 0),
            "threads_updated": imported.get("threads_updated", 0),
            "messages_inserted": imported.get("messages_inserted", 0),
            "messages_updated": imported.get("messages_updated", 0),
        }
    )
    return {
        "imported": imported,
        "endpoint_counts": bundle.get("endpoint_counts", {}),
        "source": "notion_direct_sync",
        "account_index": account_index,
        "stats": bundle.get("stats", {}),
        "sync_summary": summary,
    }


@router.get("/threads")
def list_threads(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> dict[str, Any]:
    return {"threads": _store().list_threads(limit=limit, offset=offset)}


@router.delete("/threads")
async def delete_threads(request: Request) -> dict[str, Any]:
    """Bulk-delete remote Notion chat threads and remove confirmed successes from the local archive."""
    return _bulk_delete_from_payload(request, await _request_payload(request))


@router.post("/threads/delete")
@router.post("/threads/bulk-delete")
async def post_delete_threads(request: Request) -> dict[str, Any]:
    """POST fallback for clients/proxies that reject DELETE with a JSON body."""
    return _bulk_delete_from_payload(request, await _request_payload(request))


@router.get("/threads/{thread_id}")
def get_thread(thread_id: str) -> dict[str, Any]:
    thread = _store().get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


@router.post("/threads/{thread_id}/hydrate")
async def hydrate_thread(thread_id: str, request: Request) -> dict[str, Any]:
    """Hydrate full messages for one selected archived thread."""
    try:
        payload = await request.json()
    except (TypeError, ValueError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    account_index = payload.get("account_index", 0)
    try:
        account_index = int(account_index)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid hydrate parameters") from exc

    store = _store()
    thread = store.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    try:
        bundle = hydrate_thread_from_notion(_get_account_client(request, account_index), thread)
    except NotionUpstreamError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "message": "Unable to hydrate chat thread from Notion.",
                    "type": "upstream_error",
                    "param": None,
                    "code": "upstream_error",
                    "detail": exc.response_excerpt,
                }
            },
        ) from exc

    imported = store.upsert_bundle(bundle)
    hydrated = store.get_thread(thread_id)
    return {
        "imported": imported,
        "endpoint_counts": bundle.get("endpoint_counts", {}),
        "stats": bundle.get("stats", {}),
        "thread": {
            "id": thread_id,
            "message_count": (hydrated or {}).get("message_count", 0),
            "hydrated": bool((hydrated or {}).get("message_count", 0)),
        },
    }


@router.post("/threads/{thread_id}/resume")
async def resume_thread(thread_id: str, request: Request) -> dict[str, Any]:
    """Create a real local conversation from one archived thread (fork or continue)."""
    payload = await _request_payload(request)
    mode = str(payload.get("mode") or "fork").strip().lower()
    if mode not in {"fork", "continue"}:
        raise HTTPException(status_code=400, detail="mode must be either 'fork' or 'continue'")

    thread = _store().get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    manager = request.app.state.conversation_manager
    conversation_id = manager.new_conversation()

    if mode == "continue":
        manager.set_conversation_thread_id(conversation_id, thread_id)

    seeded_messages: list[dict[str, str]] = []
    for message in thread.get("messages") or []:
        role = str(message.get("role") or "").strip().lower()
        if role not in {"user", "assistant", "system"}:
            continue
        content = str(message.get("text") or "").strip()
        if not content:
            continue
        manager.add_message(conversation_id, role, content)
        seeded_messages.append({"role": role, "content": content})

    return {
        "conversation_id": conversation_id,
        "mode": mode,
        "thread_id": thread_id,
        "seeded_message_count": len(seeded_messages),
        "title": str(thread.get("title") or thread_id),
        "messages": seeded_messages,
    }


@router.get("/threads/{thread_id}/debug")
def debug_thread(thread_id: str) -> dict[str, Any]:
    return _store().debug_thread(thread_id)


@router.get("/threads/{thread_id}/markdown", response_class=PlainTextResponse)
def export_markdown(thread_id: str) -> str:
    markdown = _store().thread_to_markdown(thread_id)
    if markdown is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return markdown


@router.get("/search")
def search(q: str = Query(..., min_length=1), limit: int = Query(25, ge=1, le=100)) -> dict[str, Any]:
    try:
        return {"results": _store().search(q, limit=limit)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
