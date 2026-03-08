import asyncio
from difflib import SequenceMatcher
import json
import re
import time
import uuid
from typing import Any, Dict, Generator, Iterable, List, Tuple

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

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


def _build_stream_chunk(
    response_id: str,
    model: str,
    *,
    content: str = "",
    reasoning_content: str = "",
    role: str = "",
    finish_reason=None,
) -> str:
    delta: Dict[str, Any] = {}
    if role:
        delta["role"] = role
    if content:
        delta["content"] = content
    if reasoning_content:
        delta["reasoning_content"] = reasoning_content

    payload = {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _build_local_ui_chunk(
    response_id: str,
    model: str,
    event_type: str,
    **payload_fields: Any,
) -> str:
    payload: Dict[str, Any] = {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": None}],
        "type": event_type,
    }
    payload.update(payload_fields)
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _format_search_results_md(search_data: dict[str, Any]) -> str:
    """将搜索数据格式化为 Markdown 引用块，以便标准客户端显示。"""
    lines = []
    queries = search_data.get("queries", [])
    if queries:
        lines.append(f"> 🔍 **已搜索:** {', '.join(queries)}")

    sources = search_data.get("sources", [])
    if sources:
        lines.append("> 🌐 **来源:**")
        for i, src in enumerate(sources[:5], 1):  # 最多显示5个来源，避免刷屏
            title = src.get("title") or src.get("url") or "未知来源"
            url = src.get("url")
            if url:
                lines.append(f"> {i}. [{title}]({url})")
            else:
                lines.append(f"> {i}. {title}")
    
    if lines:
        return "\n".join(lines) + "\n\n"
    return ""


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
        if item_type == "final_content":
            return {
                "type": "final_content",
                "text": str(item.get("text", "") or ""),
                "source_type": str(item.get("source_type", "") or ""),
                "source_length": item.get("source_length"),
            }

    return {"type": "unknown"}


def _iter_stream_items(first_item: Any, stream_gen: Iterable[Any]) -> Generator[Any, None, None]:
    if first_item is not None:
        yield first_item
    for item in stream_gen:
        yield item


def _compute_missing_suffix(current_text: str, final_text: str) -> str:
    if not final_text:
        return ""
    if not current_text:
        return final_text
    if final_text.startswith(current_text):
        return final_text[len(current_text):]
    return ""


def _select_best_final_reply(
    streamed_text: str,
    final_text: str,
    final_source_type: str,
) -> tuple[str, str]:
    streamed = streamed_text or ""
    final = final_text or ""
    streamed_stripped = streamed.strip()
    final_stripped = final.strip()
    source = (final_source_type or "").strip().lower()

    if not final_stripped:
        return streamed, "streamed_only"
    if not streamed_stripped:
        return final, "final_only"
    if final.startswith(streamed):
        return final, "final_extends_streamed"
    if streamed.startswith(final):
        if source == "title" or len(final_stripped) <= max(32, int(len(streamed_stripped) * 0.35)):
            return streamed, "streamed_beats_short_final"
        return final, "final_prefix_of_streamed"

    # Diverged content: usually prefer richer non-title final content.
    if source == "title" and len(final_stripped) < max(48, int(len(streamed_stripped) * 0.6)):
        return streamed, "streamed_beats_title"
    if len(final_stripped) >= max(48, int(len(streamed_stripped) * 0.6)):
        return final, "final_diverged_preferred"
    return streamed, "streamed_diverged_preferred"


def _normalize_overlap_text(text: str) -> str:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return ""
    normalized = re.sub(r"```.*?```", " ", normalized, flags=re.DOTALL)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def _trim_redundant_thinking(thinking_text: str, final_reply: str) -> tuple[str, str, float]:
    thinking = str(thinking_text or "").strip()
    final = str(final_reply or "").strip()
    if not thinking or not final:
        return thinking, "missing_text", 0.0

    normalized_thinking = _normalize_overlap_text(thinking)
    normalized_final = _normalize_overlap_text(final)
    if not normalized_thinking or not normalized_final:
        return thinking, "missing_normalized_text", 0.0

    overlap_ratio = SequenceMatcher(None, normalized_thinking, normalized_final).ratio()
    if normalized_thinking == normalized_final:
        return "", "identical", overlap_ratio

    if thinking.endswith(final):
        prefix = thinking[: -len(final)].rstrip()
        if len(_normalize_overlap_text(prefix)) >= 10:
            return prefix, "suffix_trimmed", overlap_ratio
        return "", "suffix_cleared", overlap_ratio

    if (
        overlap_ratio >= 0.92
        and (
            normalized_thinking in normalized_final
            or normalized_final in normalized_thinking
        )
    ):
        return "", "high_overlap_cleared", overlap_ratio

    return thinking, "kept", overlap_ratio


def _build_thinking_replacement(
    streamed_content_text: str,
    thinking_text: str,
    final_reply: str,
    final_source_type: str,
) -> dict[str, Any] | None:
    source = str(final_source_type or "").strip().lower()
    if source != "agent-inference":
        return None

    normalized_final = _normalize_overlap_text(final_reply)
    normalized_streamed = _normalize_overlap_text(streamed_content_text)
    if not normalized_final or not _normalize_overlap_text(thinking_text):
        return None

    # 只在几乎没有真实正文增量时做裁决，避免误伤复杂推理场景。
    if normalized_streamed and len(normalized_streamed) >= max(10, int(len(normalized_final) * 0.35)):
        return None

    replacement, decision, overlap_ratio = _trim_redundant_thinking(thinking_text, final_reply)
    if replacement == str(thinking_text or "").strip():
        return None

    return {
        "thinking": replacement,
        "decision": decision,
        "overlap_ratio": round(overlap_ratio, 4),
        "source_type": source,
    }


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
                streamed_content_accumulator = ""
                thinking_accumulator = ""
                authoritative_final_content = ""
                authoritative_final_source_type = ""
                assistant_started = False
                pending_search_md = ""
                client_type = request.headers.get("X-Client-Type", "").lower()

                try:
                    for raw_item in _iter_stream_items(first_item, stream_gen):
                        item = _normalize_stream_item(raw_item)
                        item_type = item.get("type")

                        if item_type == "search":
                            search_data = item.get("data")
                            if isinstance(search_data, dict) and search_data:
                                pending_search_md += _format_search_results_md(search_data)
                                if client_type == "web":
                                    yield _build_local_ui_chunk(
                                        response_id,
                                        req_body.model,
                                        "search_metadata",
                                        searches=search_data,
                                    )
                            continue

                        if item_type == "final_content":
                            final_text = str(item.get("text", "") or "").strip()
                            if final_text:
                                authoritative_final_content = final_text
                                authoritative_final_source_type = str(item.get("source_type", "") or "")
                            continue

                        if item_type == "thinking":
                            thinking_text = item.get("text", "")
                            if thinking_text:
                                thinking_accumulator += thinking_text
                                if not assistant_started:
                                    assistant_started = True
                                    yield _build_stream_chunk(
                                        response_id,
                                        req_body.model,
                                        role="assistant",
                                        reasoning_content=thinking_text,
                                    )
                                else:
                                    yield _build_stream_chunk(
                                        response_id,
                                        req_body.model,
                                        reasoning_content=thinking_text,
                                    )
                            continue

                        if item_type != "content":
                            continue

                        chunk_text = item.get("text", "")
                        if not chunk_text and not pending_search_md:
                            continue

                        # 在第一个正文内容发出前，把积攒的搜索信息拼上去
                        if pending_search_md and client_type != "web":
                            chunk_text = pending_search_md + chunk_text
                        
                        if pending_search_md:
                            pending_search_md = ""

                        streamed_content_accumulator += chunk_text
                        if not assistant_started:
                            assistant_started = True
                            yield _build_stream_chunk(
                                response_id,
                                req_body.model,
                                role="assistant",
                                content=chunk_text,
                            )
                        else:
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
                    streamed_content_accumulator += error_hint
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
                    final_reply, reply_decision = _select_best_final_reply(
                        streamed_content_accumulator,
                        authoritative_final_content,
                        authoritative_final_source_type,
                    )

                    missing_suffix = _compute_missing_suffix(streamed_content_accumulator, final_reply)
                    if missing_suffix:
                        suffix_to_emit = missing_suffix
                        if pending_search_md and client_type != "web" and not streamed_content_accumulator:
                            suffix_to_emit = pending_search_md + suffix_to_emit
                            pending_search_md = ""
                        if not assistant_started:
                            assistant_started = True
                            yield _build_stream_chunk(
                                response_id,
                                req_body.model,
                                role="assistant",
                                content=suffix_to_emit,
                            )
                        else:
                            yield _build_stream_chunk(response_id, req_body.model, content=suffix_to_emit)
                        streamed_content_accumulator += suffix_to_emit
                    elif final_reply != streamed_content_accumulator:
                        # Diverged bodies cannot be safely "patched" in plain OpenAI deltas.
                        # Web client supports replace event to keep rendered body aligned with persisted final reply.
                        if client_type == "web":
                            yield _build_local_ui_chunk(
                                response_id,
                                req_body.model,
                                "content_replace",
                                content=final_reply,
                                source_type=authoritative_final_source_type,
                                decision=reply_decision,
                            )
                            streamed_content_accumulator = final_reply
                        elif not streamed_content_accumulator and final_reply:
                            # Non-web fallback when nothing has been shown yet.
                            emit_text = final_reply
                            if pending_search_md and client_type != "web":
                                emit_text = pending_search_md + emit_text
                                pending_search_md = ""
                            if not assistant_started:
                                assistant_started = True
                                yield _build_stream_chunk(
                                    response_id,
                                    req_body.model,
                                    role="assistant",
                                    content=emit_text,
                                )
                            else:
                                yield _build_stream_chunk(response_id, req_body.model, content=emit_text)
                            streamed_content_accumulator = final_reply

                    thinking_replacement = _build_thinking_replacement(
                        streamed_content_accumulator,
                        thinking_accumulator,
                        final_reply,
                        authoritative_final_source_type,
                    )
                    if client_type == "web" and thinking_replacement is not None:
                        yield _build_local_ui_chunk(
                            response_id,
                            req_body.model,
                            "thinking_replace",
                            thinking=thinking_replacement["thinking"],
                            decision=thinking_replacement["decision"],
                            overlap_ratio=thinking_replacement["overlap_ratio"],
                            source_type=thinking_replacement["source_type"],
                            reply_decision=reply_decision,
                        )

                    if final_reply.strip():
                        try:
                            _persist_round(
                                manager,
                                background_tasks,
                                conversation_id,
                                user_prompt,
                                final_reply,
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
            authoritative_final_content = ""
            authoritative_final_source_type = ""
            for raw_item in _iter_stream_items(first_item, stream_gen):
                item = _normalize_stream_item(raw_item)
                item_type = item.get("type")
                if item_type == "final_content":
                    final_text = str(item.get("text", "") or "").strip()
                    if final_text:
                        authoritative_final_content = final_text
                        authoritative_final_source_type = str(item.get("source_type", "") or "")
                    continue
                if item_type != "content":
                    continue
                chunk_text = item.get("text", "")
                if chunk_text:
                    content_parts.append(chunk_text)

            full_text, _ = _select_best_final_reply(
                "".join(content_parts),
                authoritative_final_content,
                authoritative_final_source_type,
            )
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
            # 返回标准的 OpenAI 错误格式，让客户端（如 Cherry Studio）能直观显示报错
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "message": str(exc),
                        "type": "rate_limit_error",
                        "code": "account_pool_cooling"
                    }
                }
            )
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
