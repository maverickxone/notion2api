from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.chat_history.store import ChatHistoryStore

router = APIRouter(prefix="/chat-history", tags=["chat-history"])

_VALID_RESUME_MODES = {"fork", "continue"}


async def _request_payload(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _get_conversation_manager(request: Request) -> Any:
    manager = getattr(request.app.state, "conversation_manager", None)
    if manager is None:
        raise HTTPException(
            status_code=409,
            detail="Resume/fork requires heavy mode conversation storage.",
        )
    return manager


def _clean_resume_messages(thread: dict[str, Any]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for item in thread.get("messages") or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        text = str(item.get("text") or item.get("content") or "").strip()
        if not text:
            continue
        cleaned.append({"role": role, "content": text})
    return cleaned


def _update_conversation_title(manager: Any, conversation_id: str, title: str) -> None:
    clean_title = str(title or "").strip()
    if not clean_title:
        return
    try:
        with manager._get_conn() as conn:  # noqa: SLF001 - ConversationManager has no public title setter yet.
            conn.execute(
                "UPDATE conversations SET title = ? WHERE id = ?",
                (clean_title[:240], conversation_id),
            )
            conn.commit()
    except Exception:
        # Title restoration is cosmetic; do not fail resume/fork because of it.
        return


@router.post("/threads/{thread_id}/resume")
async def resume_thread(thread_id: str, request: Request) -> dict[str, Any]:
    """Convert a hydrated chat-history thread into an active local conversation.

    mode="fork" seeds the local conversation but starts a fresh upstream Notion thread
    on the next user message. mode="continue" also binds the new conversation to the
    original Notion thread id so the next user message attempts true remote continuation.
    """
    payload = await _request_payload(request)
    mode = str(payload.get("mode") or "fork").strip().lower()
    if mode not in _VALID_RESUME_MODES:
        raise HTTPException(status_code=400, detail="mode must be either 'fork' or 'continue'")

    store = ChatHistoryStore()
    thread = store.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    messages = _clean_resume_messages(thread)
    if not messages:
        raise HTTPException(
            status_code=409,
            detail="Thread has no hydrated user/assistant messages to resume.",
        )

    manager = _get_conversation_manager(request)
    conversation_id = manager.new_conversation()
    title = str(thread.get("title") or thread.get("first_message_preview") or thread_id).strip()
    _update_conversation_title(manager, conversation_id, title)

    seeded = 0
    for message in messages:
        manager.add_message(conversation_id, message["role"], message["content"])
        seeded += 1

    bound_thread_id = None
    if mode == "continue":
        manager.set_conversation_thread_id(conversation_id, thread_id)
        bound_thread_id = thread_id

    return {
        "conversation_id": conversation_id,
        "mode": mode,
        "thread_id": thread_id,
        "remote_thread_id": thread_id,
        "bound_thread_id": bound_thread_id,
        "messages_seeded": seeded,
        "title": title,
        "messages": messages,
    }
