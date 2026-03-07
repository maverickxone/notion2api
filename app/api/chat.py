import asyncio
import json
import re
import time
import uuid
from typing import Any, Dict, Generator, Iterable, List, Tuple

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from app.conversation import compress_round_if_needed
from app.limiter import limiter
from app.logger import logger
from app.model_registry import is_supported_model, list_available_models
from app.notion_client import NotionUpstreamError
from app.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ChatMessageResponseChoice,
)

router = APIRouter()

RECALL_INTENT_KEYWORDS = [
    "之前",
    "上次",
    "以前",
    "你还记得",
    "我们之前",
    "earlier",
    "before",
    "recall",
    "remember",
    "之前说过",
    "历史记录",
    "找一下",
    "搜索记忆",
]


def _build_stream_chunk(response_id: str, model: str, *, content: str = "", role: str = "", finish_reason=None) -> str:
    delta: Dict[str, Any] = {}
    if role:
        delta["role"] = role
    if content:
        delta["content"] = content

    payload = {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _build_search_metadata_chunk(search_data: dict[str, Any]) -> str:
    payload = {
        "type": "search_metadata",
        "searches": search_data,
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _build_thinking_chunk(text: str) -> str:
    payload = {
        "type": "thinking_chunk",
        "text": text,
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _normalize_stream_item(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        return {"type": "content", "text": item}

    if isinstance(item, dict):
        item_type = str(item.get("type", "") or "").lower()
        if item_type == "content":
            return {"type": "content", "text": str(item.get("text", "") or "")}
        if item_type == "search":
            payload = item.get("data")
            return {"type": "search", "data": payload if isinstance(payload, dict) else {}}
        if item_type == "thinking":
            return {"type": "thinking", "text": str(item.get("text", "") or "")}

    return {"type": "unknown"}


def _iter_stream_items(first_item: Any, stream_gen: Iterable[Any]) -> Generator[Any, None, None]:
    if first_item is not None:
        yield first_item
    for item in stream_gen:
        yield item


def _contains_recall_intent(text: str) -> bool:
    lowered = text.lower()
    for keyword in RECALL_INTENT_KEYWORDS:
        if keyword.isascii():
            if keyword.lower() in lowered:
                return True
            continue
        if keyword in text:
            return True
    return False


def _extract_recall_query(text: str) -> str:
    cleaned = text
    for keyword in RECALL_INTENT_KEYWORDS:
        if keyword.isascii():
            cleaned = re.sub(rf"\b{re.escape(keyword)}\b", " ", cleaned, flags=re.IGNORECASE)
        else:
            cleaned = cleaned.replace(keyword, " ")
    cleaned = re.sub(r"[\s，。！？、,.!?;:：]+", " ", cleaned).strip()
    return cleaned or text.strip()


def _prepare_messages(req_body: ChatCompletionRequest) -> Tuple[str, List[Tuple[str, str]], str]:
    system_messages = []
    dialogue_messages = []

    for msg in req_body.messages:
        if msg.role == "system":
            if msg.content.strip():
                system_messages.append(msg.content.strip())
            continue
        dialogue_messages.append((msg.role, msg.content))

    if not dialogue_messages:
        raise HTTPException(
            status_code=400,
            detail="The messages list must contain at least one user message.",
        )

    last_role, user_prompt = dialogue_messages[-1]
    raw_user_prompt = user_prompt
    history_messages = dialogue_messages[:-1]

    if last_role != "user":
        raise HTTPException(status_code=400, detail="The last message must be from role 'user'.")
    if not user_prompt.strip():
        raise HTTPException(status_code=400, detail="The last user message cannot be empty.")

    if system_messages:
        merged_system_prompt = "\n".join(system_messages)
        user_prompt = f"[System Instructions: {merged_system_prompt}]\n\n{user_prompt}"

    return user_prompt, history_messages, raw_user_prompt


def _persist_round(
    manager,
    background_tasks: BackgroundTasks,
    conversation_id: str,
    user_prompt: str,
    assistant_reply: str,
) -> None:
    manager.persist_round(conversation_id, user_prompt, assistant_reply)
    background_tasks.add_task(
        compress_round_if_needed,
        manager=manager,
        conversation_id=conversation_id,
    )


def _persist_history_messages(manager, conversation_id: str, history_messages: List[Tuple[str, str]]) -> None:
    for role, content in history_messages:
        manager.add_message(conversation_id, role, content)


def _is_client_disconnect_error(exc: BaseException) -> bool:
    if isinstance(exc, asyncio.CancelledError):
        return True
    if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
        return True
    if isinstance(exc, OSError):
        return exc.errno in {32, 54, 104, 10053, 10054}
    return False


@router.post("/chat/completions", tags=["chat"])
@limiter.limit("10/minute")
async def create_chat_completion(
    request: Request,
    req_body: ChatCompletionRequest,
    background_tasks: BackgroundTasks,
    response: Response,
):
    """
    创建聊天请求，严格兼容 OpenAI API。
    """
    pool = request.app.state.account_pool
    manager = request.app.state.conversation_manager

    user_prompt, history_messages, raw_user_prompt = _prepare_messages(req_body)
    recall_query = _extract_recall_query(raw_user_prompt) if _contains_recall_intent(raw_user_prompt) else None

    if not is_supported_model(req_body.model):
        available_models = list_available_models()
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported model '{req_body.model}'. Available models: {', '.join(available_models)}",
        )

    conversation_id = req_body.conversation_id.strip() if req_body.conversation_id else ""
    restore_history = False
    if not conversation_id:
        conversation_id = manager.new_conversation()
        restore_history = True
    elif not manager.conversation_exists(conversation_id):
        logger.warning(
            "Conversation id not found, creating a fresh conversation",
            extra={
                "request_info": {
                    "event": "conversation_id_not_found",
                    "provided_conversation_id": conversation_id,
                }
            },
        )
        conversation_id = manager.new_conversation()
        restore_history = True

    if restore_history and history_messages:
        _persist_history_messages(manager, conversation_id, history_messages)

    response_id = f"chatcmpl-{uuid.uuid4().hex}"
    max_retries = min(3, len(pool.clients))

    for attempt in range(1, max_retries + 1):
        client = None
        try:
            client = pool.get_client()
            transcript_payload = manager.get_transcript_payload(
                notion_client=client,
                conversation_id=conversation_id,
                new_prompt=user_prompt,
                model_name=req_body.model,
                recall_query=recall_query,
            )
            transcript = transcript_payload["transcript"]
            memory_degraded = bool(transcript_payload.get("memory_degraded"))
            memory_headers = {"X-Memory-Status": "degraded"} if memory_degraded else {}

            stream_gen = client.stream_response(transcript)
            first_item = next(stream_gen, None)

            if first_item is None:
                raise NotionUpstreamError("Notion upstream returned empty content.", retriable=True)

            def openai_stream_generator() -> Generator[str, None, None]:
                full_text_accumulator = ""
                assistant_started = False

                try:
                    for raw_item in _iter_stream_items(first_item, stream_gen):
                        item = _normalize_stream_item(raw_item)
                        item_type = item.get("type")

                        if item_type == "search":
                            search_data = item.get("data")
                            if isinstance(search_data, dict) and search_data:
                                yield _build_search_metadata_chunk(search_data)
                            continue

                        if item_type == "thinking":
                            thinking_text = item.get("text", "")
                            if thinking_text:
                                yield _build_thinking_chunk(thinking_text)
                            continue

                        if item_type != "content":
                            continue

                        chunk_text = item.get("text", "")
                        if not chunk_text:
                            continue

                        full_text_accumulator += chunk_text
                        if not assistant_started:
                            assistant_started = True
                            yield _build_stream_chunk(
                                response_id,
                                req_body.model,
                                role="assistant",
                                content=chunk_text,
                            )
                            continue

                        yield _build_stream_chunk(response_id, req_body.model, content=chunk_text)
                except asyncio.CancelledError:
                    logger.info(
                        "Streaming response cancelled by downstream client",
                        extra={
                            "request_info": {
                                "event": "stream_cancelled_by_client",
                                "conversation_id": conversation_id,
                                "attempt": attempt,
                            }
                        },
                    )
                    raise
                except BaseException as exc:
                    if _is_client_disconnect_error(exc):
                        logger.info(
                            "Streaming connection closed by downstream client",
                            extra={
                                "request_info": {
                                    "event": "stream_client_disconnected",
                                    "conversation_id": conversation_id,
                                    "attempt": attempt,
                                }
                            },
                        )
                        return
                    if isinstance(exc, NotionUpstreamError) and client is not None and exc.retriable:
                        pool.mark_failed(client)
                    log_method = logger.warning if isinstance(exc, NotionUpstreamError) else logger.error
                    log_method(
                        "Streaming response interrupted",
                        exc_info=True,
                        extra={
                            "request_info": {
                                "event": "stream_interrupted",
                                "conversation_id": conversation_id,
                                "attempt": attempt,
                                "is_upstream_error": isinstance(exc, NotionUpstreamError),
                            }
                        },
                    )
                    error_hint = "\n\n[上游连接中断，请稍后重试。]"
                    full_text_accumulator += error_hint
                    if not assistant_started:
                        assistant_started = True
                        yield _build_stream_chunk(
                            response_id,
                            req_body.model,
                            role="assistant",
                            content=error_hint,
                        )
                    else:
                        yield _build_stream_chunk(response_id, req_body.model, content=error_hint)
                finally:
                    if full_text_accumulator.strip():
                        try:
                            _persist_round(
                                manager,
                                background_tasks,
                                conversation_id,
                                user_prompt,
                                full_text_accumulator,
                            )
                        except Exception:
                            logger.error(
                                "Failed to persist conversation round",
                                exc_info=True,
                                extra={
                                    "request_info": {
                                        "event": "conversation_persist_failed",
                                        "conversation_id": conversation_id,
                                    }
                                },
                            )
                    yield _build_stream_chunk(response_id, req_body.model, finish_reason="stop")
                    yield "data: [DONE]\n\n"

            if req_body.stream:
                stream_headers = {
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "X-Conversation-Id": conversation_id,
                    **memory_headers,
                }
                return StreamingResponse(
                    openai_stream_generator(),
                    media_type="text/event-stream",
                    headers=stream_headers,
                )

            content_parts: list[str] = []
            for raw_item in _iter_stream_items(first_item, stream_gen):
                item = _normalize_stream_item(raw_item)
                if item.get("type") != "content":
                    continue
                chunk_text = item.get("text", "")
                if chunk_text:
                    content_parts.append(chunk_text)

            full_text = "".join(content_parts)
            if not full_text.strip():
                raise NotionUpstreamError("Notion upstream returned empty content.", retriable=True)

            _persist_round(manager, background_tasks, conversation_id, user_prompt, full_text)
            response.headers["X-Conversation-Id"] = conversation_id
            if memory_degraded:
                response.headers["X-Memory-Status"] = "degraded"

            return ChatCompletionResponse(
                id=response_id,
                model=req_body.model,
                choices=[
                    ChatMessageResponseChoice(
                        message=ChatMessage(role="assistant", content=full_text)
                    )
                ],
            )
        except NotionUpstreamError as exc:
            if client is not None and exc.retriable:
                pool.mark_failed(client)
            logger.warning(
                "Notion upstream failed",
                extra={
                    "request_info": {
                        "event": "notion_upstream_failed",
                        "attempt": attempt,
                        "max_retries": max_retries,
                        "conversation_id": conversation_id,
                        "status_code": exc.status_code,
                        "retriable": exc.retriable,
                        "response_excerpt": exc.response_excerpt,
                    }
                },
            )
            if attempt == max_retries or not exc.retriable:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
        except RuntimeError as exc:
            logger.error(
                "No available client in account pool",
                extra={"request_info": {"event": "account_pool_unavailable", "detail": str(exc)}},
            )
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception:
            if client is not None:
                pool.mark_failed(client)
            logger.error(
                "Unhandled chat completion error",
                exc_info=True,
                extra={
                    "request_info": {
                        "event": "chat_completion_unhandled_exception",
                        "attempt": attempt,
                        "conversation_id": conversation_id,
                    }
                },
            )
            if attempt == max_retries:
                raise HTTPException(
                    status_code=500,
                    detail="Unexpected internal error while generating completion.",
                )

    raise HTTPException(status_code=503, detail="Service unavailable: all upstream retries exhausted.")


@router.delete("/conversations/{conversation_id}", tags=["chat"])
async def delete_conversation(conversation_id: str, request: Request):
    manager = request.app.state.conversation_manager
    deleted = manager.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"id": conversation_id, "deleted": True}
