import threading
import time
import uuid
from typing import Any, Generator, Optional

import cloudscraper
import requests
import urllib3

from app.logger import logger
from app.model_registry import get_notion_model
from app.stream_parser import parse_stream

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class NotionUpstreamError(RuntimeError):
    """Notion 上游请求失败或返回异常内容。"""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        retriable: bool = True,
        response_excerpt: str = "",
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retriable = retriable
        self.response_excerpt = response_excerpt


class NotionOpusAPI:
    def __init__(self, account_config: dict):
        """
        从单组账号配置初始化 Notion 客户端。
        account_config 需要包含 token_v2, space_id, user_id, space_view_id, user_name, user_email
        """
        self.token_v2 = account_config.get("token_v2", "")
        self.space_id = account_config.get("space_id", "")
        self.user_id = account_config.get("user_id", "")
        self.space_view_id = account_config.get("space_view_id", "")
        self.user_name = account_config.get("user_name", "user")
        self.user_email = account_config.get("user_email", "")
        self.url = "https://www.notion.so/api/v3/runInferenceTranscript"
        self.delete_url = "https://www.notion.so/api/v3/saveTransactions"
        self.account_key = self.user_email or self.user_id or "unknown-account"

    def _to_notion_transcript(self, transcript: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for block in transcript:
            if block.get("type") != "config":
                converted.append(block)
                continue

            value = block.get("value")
            if not isinstance(value, dict):
                converted.append(block)
                continue

            notion_block = dict(block)
            notion_value = dict(value)
            notion_value["model"] = get_notion_model(str(value.get("model", "") or ""))
            notion_block["value"] = notion_value
            converted.append(notion_block)
        return converted

    def _resolve_thread_type(self, notion_transcript: list[dict[str, Any]]) -> str:
        for block in notion_transcript:
            if block.get("type") != "config":
                continue
            value = block.get("value")
            if isinstance(value, dict):
                thread_type = str(value.get("type", "") or "").strip()
                if thread_type:
                    return thread_type
        return "workflow"

    def _resolve_request_profile(self, thread_type: str) -> dict[str, Any]:
        is_markdown_chat = thread_type == "markdown-chat"
        return {
            "thread_type": thread_type,
            "create_thread": not is_markdown_chat,
            "is_partial_transcript": is_markdown_chat,
            "precreate_thread": is_markdown_chat,
            "include_debug_overrides": True,
        }

    def _build_thread_headers(self) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "cookie": f"token_v2={self.token_v2}",
            "x-notion-active-user-header": self.user_id,
            "x-notion-space-id": self.space_id,
        }

    def _create_thread(self, thread_id: str, thread_type: str) -> bool:
        payload = {
            "requestId": str(uuid.uuid4()),
            "transactions": [
                {
                    "id": str(uuid.uuid4()),
                    "spaceId": self.space_id,
                    "operations": [
                        {
                            "pointer": {"table": "thread", "id": thread_id, "spaceId": self.space_id},
                            "path": [],
                            "command": "set",
                            "args": {
                                "id": thread_id,
                                "version": 1,
                                "parent_id": self.space_id,
                                "parent_table": "space",
                                "space_id": self.space_id,
                                "created_time": int(time.time() * 1000),
                                "created_by_id": self.user_id,
                                "created_by_table": "notion_user",
                                "messages": [],
                                "data": {},
                                "alive": True,
                                "type": thread_type,
                            },
                        }
                    ],
                }
            ],
        }
        try:
            resp = requests.post(
                self.delete_url,
                json=payload,
                headers=self._build_thread_headers(),
                timeout=20,
            )
            if resp.status_code == 200:
                return True
            logger.warning(
                "Pre-create thread failed",
                extra={
                    "request_info": {
                        "event": "thread_precreate_failed",
                        "thread_id": thread_id,
                        "thread_type": thread_type,
                        "status": resp.status_code,
                    }
                },
            )
        except Exception:
            logger.warning(
                "Pre-create thread raised exception",
                exc_info=True,
                extra={
                    "request_info": {
                        "event": "thread_precreate_error",
                        "thread_id": thread_id,
                        "thread_type": thread_type,
                    }
                },
            )
        return False

    def delete_thread(self, thread_id: str) -> None:
        """
        通过 saveTransactions 接口将指定 thread 的 alive 状态设为 False，
        从而清理 Notion 主页面上的对话记录。
        此方法设计为在后台线程中调用，不影响主流输出。
        """
        headers = self._build_thread_headers()
        payload = {
            "requestId": str(uuid.uuid4()),
            "transactions": [
                {
                    "id": str(uuid.uuid4()),
                    "spaceId": self.space_id,
                    "operations": [
                        {
                            "pointer": {
                                "table": "thread",
                                "id": thread_id,
                                "spaceId": self.space_id,
                            },
                            "command": "update",
                            "path": [],
                            "args": {"alive": False},
                        }
                    ],
                }
            ],
        }
        try:
            resp = requests.post(self.delete_url, json=payload, headers=headers, timeout=15)
            if resp.status_code == 200:
                logger.info(
                    "Thread auto-deleted from Notion home",
                    extra={"request_info": {"event": "thread_deleted", "thread_id": thread_id}},
                )
            else:
                logger.warning(
                    f"Thread deletion failed: HTTP {resp.status_code}",
                    extra={"request_info": {"event": "thread_delete_failed", "thread_id": thread_id, "status": resp.status_code}},
                )
        except Exception as exc:
            logger.warning(
                f"Thread deletion raised an exception: {exc}",
                extra={"request_info": {"event": "thread_delete_error", "thread_id": thread_id}},
            )

    def stream_response(self, transcript: list, thread_id: Optional[str] = None) -> Generator[dict[str, Any], None, None]:
        """
        发起 Notion API 请求并返回结构化流生成器。
        接收完整的 transcript 列表作为参数。

        Args:
            transcript: 对话历史记录列表
            thread_id: 可选的已有 thread_id。如果提供，将重用该线程以保持上下文
        """
        if not isinstance(transcript, list) or not transcript:
            raise ValueError("Invalid transcript payload: transcript must be a non-empty list.")

        notion_transcript = self._to_notion_transcript(transcript)
        thread_type = self._resolve_thread_type(notion_transcript)
        request_profile = self._resolve_request_profile(thread_type)

        # 如果没有提供 thread_id，创建新的；否则重用已有的
        should_create_thread = thread_id is None
        thread_id = thread_id or str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        response = None

        # 保存 thread_id 以便外部访问
        self.current_thread_id = thread_id

        if request_profile["precreate_thread"] and should_create_thread:
            if not self._create_thread(thread_id, thread_type):
                should_create_thread = True
                request_profile["create_thread"] = True
                request_profile["is_partial_transcript"] = False
        elif not should_create_thread:
            # 如果重用已有线程，不要创建新线程
            request_profile["create_thread"] = False
            # 关键修复：设置 is_partial_transcript=True，让 Notion 接受客户端的历史消息
            request_profile["is_partial_transcript"] = True

        cookies = {
            "token_v2": self.token_v2,
            "notion_user_id": self.user_id,
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/x-ndjson",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "x-notion-space-id": self.space_id,
            "x-notion-active-user-header": self.user_id,
            "notion-audit-log-platform": "web",
            "notion-client-version": "23.13.20260228.0625",
            "origin": "https://www.notion.so",
            "referer": "https://www.notion.so/ai",
        }

        payload = {
            "traceId": trace_id,
            "spaceId": self.space_id,
            "threadId": thread_id,
            "threadType": thread_type,
            "createThread": request_profile["create_thread"],
            "generateTitle": True,
            "saveAllThreadOperations": True,
            "setUnreadState": True,
            "isPartialTranscript": request_profile["is_partial_transcript"],
            "asPatchResponse": True,
            "isUserInAnySalesAssistedSpace": False,
            "isSpaceSalesAssisted": False,
            "threadParentPointer": {
                "table": "space",
                "id": self.space_id,
                "spaceId": self.space_id,
            },
            "transcript": notion_transcript,
        }
        if request_profile["include_debug_overrides"]:
            payload["debugOverrides"] = {
                "emitAgentSearchExtractedResults": True,
                "cachedInferences": {},
                "annotationInferences": {},
                "emitInferences": False,
            }

        logger.info(
            "Dispatching request to Notion upstream",
            extra={
                "request_info": {
                    "event": "notion_upstream_request",
                    "trace_id": trace_id,
                    "thread_id": thread_id,
                    "thread_type": thread_type,
                    "create_thread": bool(request_profile["create_thread"]),
                    "is_partial_transcript": bool(request_profile["is_partial_transcript"]),
                    "account": self.account_key,
                    "space_id": self.space_id,
                }
            },
        )

        try:
            scraper = cloudscraper.create_scraper()
            response = scraper.post(
                self.url,
                cookies=cookies,
                headers=headers,
                json=payload,
                stream=True,
                timeout=(15, 120),
            )
            if response.status_code != 200:
                excerpt = (response.text or "").strip().replace("\n", " ")[:300]
                retriable = response.status_code >= 500  # 429 不再重试，避免账号被冷却
                raise NotionUpstreamError(
                    f"Notion upstream returned HTTP {response.status_code}.",
                    status_code=response.status_code,
                    retriable=retriable,
                    response_excerpt=excerpt,
                )

            emitted = False
            for chunk in parse_stream(response):
                emitted = True
                yield chunk

            if not emitted:
                raise NotionUpstreamError(
                    "Notion upstream returned an empty stream.",
                    status_code=502,
                    retriable=True,
                )

            # 流结束后，不再自动删除 thread
            # 原因：Notion API 的 workflow 模式依赖于服务器端保存的对话历史
            # 删除 thread 会导致后续请求无法获取历史消息（AI 失忆）
            # 保持 thread 存活可以维持对话上下文
            logger.info(
                "Thread completed and preserved for conversation context",
                extra={
                    "request_info": {
                        "event": "thread_completed_preserved",
                        "thread_id": thread_id,
                        "was_created_new": should_create_thread,
                    }
                },
            )
        except requests.exceptions.Timeout as exc:
            logger.error(f"Request timeout: {exc}", exc_info=True)
            raise NotionUpstreamError("Request to Notion upstream timed out.", retriable=True) from exc
        except requests.exceptions.RequestException as exc:
            logger.error(f"Request failed: {exc}", exc_info=True)
            # 不暴露原始异常细节给用户
            raise NotionUpstreamError("Request to Notion upstream failed. Please try again later.", retriable=True) from exc
        finally:
            if response is not None:
                response.close()
