import datetime
import os
import re
import sqlite3
import uuid
from typing import Any, Dict, List, Optional

from app.logger import logger
from app.model_registry import get_thread_type, is_gemini_model


class ConversationManager:
    """SQLite-backed conversation history manager with layered memory."""

    WINDOW_SIZE = 16  # 16 条消息 = 8 轮对话
    WINDOW_ROUNDS = 8  # 8 轮对话
    SUMMARY_INJECT_LIMIT = 15
    RECALL_LIMIT = 5
    ASSISTANT_EMPTY_PLACEHOLDER = "[assistant_no_visible_content]"

    def __init__(self):
        self.db_path = os.getenv("DB_PATH", "./data/conversations.db")
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column_sql: str) -> None:
        """Ensure column exists while prioritizing SQLite IF NOT EXISTS syntax."""
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column_sql}")
            return
        except sqlite3.OperationalError:
            # Fallback for old SQLite builds without IF NOT EXISTS support.
            column_name = column_sql.split()[0]
            columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if column_name not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_sql}")

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    created_at INTEGER,
                    summary TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT,
                    role TEXT,
                    content TEXT,
                    created_at INTEGER,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS compressed_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    round_index INTEGER NOT NULL,
                    user_content TEXT NOT NULL,
                    assistant_content TEXT NOT NULL,
                    summary TEXT,
                    compress_status TEXT DEFAULT 'pending',
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS full_archive (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    round_index INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_full_archive_unique
                ON full_archive(conversation_id, round_index, role, content)
                """
            )

            # 新增：独立的滑动窗口表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sliding_window (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    round_number INTEGER NOT NULL,
                    user_content TEXT NOT NULL,
                    assistant_content TEXT NOT NULL,
                    assistant_thinking TEXT DEFAULT '',
                    compress_status TEXT DEFAULT 'active',
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sliding_window_conv_round
                ON sliding_window(conversation_id, round_number DESC)
                """
            )
            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_sliding_window_unique
                ON sliding_window(conversation_id, round_number)
                """
            )

            # Keep legacy summary for compatibility but do not write to it anymore.
            self._ensure_column(conn, "conversations", "summary TEXT")
            self._ensure_column(conn, "conversations", "next_round_index INTEGER DEFAULT 0")
            self._ensure_column(conn, "conversations", "compress_failed_at INTEGER")
            self._ensure_column(conn, "conversations", "thread_id TEXT")
            self._ensure_column(conn, "messages", "thinking TEXT")

            # Backfill next_round_index for pre-migration conversations that already had history.
            conn.execute(
                """
                UPDATE conversations
                SET next_round_index = (
                    SELECT CAST(COUNT(*) / 2 AS INTEGER)
                    FROM messages
                    WHERE messages.conversation_id = conversations.id
                )
                WHERE COALESCE(next_round_index, 0) = 0
                  AND EXISTS (
                    SELECT 1 FROM messages WHERE messages.conversation_id = conversations.id
                  )
                """
            )
            conn.commit()

    def _count_messages(self, conn: sqlite3.Connection, conversation_id: str) -> int:
        row = conn.execute(
            "SELECT COUNT(1) AS cnt FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        return int(row["cnt"]) if row else 0

    def _fetch_recent_messages(
        self,
        conn: sqlite3.Connection,
        conversation_id: str,
        limit: int,
    ) -> List[Dict[str, str]]:
        rows = conn.execute(
            """
            SELECT role, content, COALESCE(thinking, '') AS thinking
            FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (conversation_id, limit),
        ).fetchall()
        messages = [
            {
                "role": str(r["role"] or ""),
                "content": str(r["content"] or ""),
                "thinking": str(r["thinking"] or ""),
            }
            for r in rows
        ]
        messages.reverse()
        return messages

    def _build_assistant_memory_text(self, content: str, thinking: str) -> str:
        """Build a stable assistant text for memory pairing/compression."""
        content_text = str(content or "")
        if content_text.strip():
            return content_text

        thinking_text = str(thinking or "").strip()
        if not thinking_text:
            return self.ASSISTANT_EMPTY_PLACEHOLDER

        compact = re.sub(r"\s+", " ", thinking_text)
        if len(compact) > 180:
            compact = compact[:180].rstrip() + "..."
        return f"[assistant_thinking_only] {compact}"

    def _normalize_window_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        规范化窗口消息，确保 user → assistant 成对出现。

        修复前的问题：严格检查交替顺序，如果消息顺序不匹配期望就跳过，
        导致 AI 回复被丢失。

        修复后的逻辑：
        1. 保留所有有效的 user/assistant 消息
        2. 确保 user → assistant 成对（如果不成对，跳过）
        3. 移除末尾不完整的 user 消息（确保以 assistant 结束）
        """
        # 第一步：收集所有有效的消息
        normalized: List[Dict[str, str]] = []
        for msg in messages:
            role = msg.get("role", "")
            content = str(msg.get("content", "") or "")
            thinking = str(msg.get("thinking", "") or "")
            if role not in {"user", "assistant"}:
                continue

            if role == "user":
                if not content.strip():
                    continue
                normalized.append({"role": role, "content": content, "thinking": ""})
                continue

            # assistant: keep pair continuity even if visible content is empty.
            normalized.append(
                {
                    "role": role,
                    "content": self._build_assistant_memory_text(content, thinking),
                    "thinking": thinking,
                }
            )

        # 第二步：确保消息是成对的 user → assistant
        paired: List[Dict[str, str]] = []
        i = 0
        while i < len(normalized):
            # 检查当前消息和下一条消息是否构成 user → assistant 对
            if i + 1 < len(normalized):
                current = normalized[i]
                next_msg = normalized[i + 1]
                if current["role"] == "user" and next_msg["role"] == "assistant":
                    paired.extend([current, next_msg])
                    i += 2
                    continue

            # 如果不成对，跳过当前消息
            i += 1

        # 第三步：确保 transcript 以 assistant 消息结束（便于追加新的 user prompt）
        while paired and paired[-1]["role"] != "assistant":
            paired.pop()

        return paired

    def _archive_message(
        self,
        conn: sqlite3.Connection,
        conversation_id: str,
        role: str,
        content: str,
        round_index: int,
        created_at: int,
    ) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO full_archive (
                conversation_id, role, content, round_index, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, role, content, round_index, created_at),
        )

    def _build_dialog_block(
        self,
        role: str,
        content: str,
        notion_client: Any,
        *,
        gemini_mode: bool = False,
    ) -> Dict[str, Any]:
        if role == "assistant" and gemini_mode:
            return {
                "id": str(uuid.uuid4()),
                "type": "agent-inference",
                "value": [{"type": "text", "content": content}],
            }

        block: Dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "type": role,
            "value": [[content]],
        }
        if role == "user":
            block["userId"] = notion_client.user_id
        return block

    def _build_config_block(self, model_name: str, *, gemini_mode: bool = False) -> Dict[str, Any]:
        thread_type = get_thread_type(model_name)
        if gemini_mode:
            return {
                "id": str(uuid.uuid4()),
                "type": "config",
                "value": {
                    "type": thread_type,
                    "model": model_name,
                    "modelFromUser": True,
                    "useWebSearch": True,
                    "isCustomAgent": False,
                    "enableAgentAutomations": False,
                    "enableAgentIntegrations": False,
                    "enableBackgroundAgents": False,
                    "enableCodegenIntegration": False,
                    "enableCustomAgents": False,
                    "enableExperimentalIntegrations": False,
                    "enableLinkedDatabases": False,
                    "enableAgentViewVersionHistoryTool": False,
                    "enableDatabaseAgents": False,
                    "enableAgentComments": False,
                    "enableAgentForms": False,
                    "enableAgentMakesFormulas": False,
                    "enableUserSessionContext": False,
                    "searchScopes": [{"type": "everything"}],
                },
            }
        return {
            "id": str(uuid.uuid4()),
            "type": "config",
            "value": {
                "type": thread_type,
                "model": model_name,
                "modelFromUser": True,
                "useWebSearch": True,
                "useReadOnlyMode": False,
                "writerMode": False,
                "isCustomAgent": False,
                "isCustomAgentBuilder": False,
                "useCustomAgentDraft": False,
                "use_draft_actor_pointer": False,
                "enableAgentAutomations": True,
                "enableAgentIntegrations": True,
                "enableCustomAgents": True,
                "enableAgentDiffs": True,
                "enableAgentCreateDbTemplate": True,
                "enableCsvAttachmentSupport": True,
                "enableDatabaseAgents": False,
                "enableAgentThreadTools": False,
                "enableRunAgentTool": False,
                "enableAgentDashboards": False,
                "enableAgentCardCustomization": True,
                "enableSystemPromptAsPage": False,
                "enableUserSessionContext": False,
                "enableCreateAndRunThread": True,
                "enableAgentGenerateImage": False,
                "enableSpeculativeSearch": False,
                "enableUpdatePageV2Tool": True,
                "enableUpdatePageAutofixer": True,
                "enableUpdatePageMarkdownTree": False,
                "enableUpdatePageOrderUpdates": True,
                "enableAgentSupportPropertyReorder": True,
                "enableAgentVerification": False,
                "useServerUndo": True,
                "databaseAgentConfigMode": False,
                "isOnboardingAgent": False,
                "availableConnectors": [],
                "customConnectorNames": [],
                "searchScopes": [{"type": "everything"}],
                "useSearchToolV2": False,
                "useRulePrioritization": False,
                "enableExperimentalIntegrations": False,
                "enableAgentViewNotificationsTool": False,
                "enableScriptAgent": False,
                "enableScriptAgentAdvanced": False,
                "enableScriptAgentSlack": False,
                "enableScriptAgentMcpServers": False,
                "enableScriptAgentMail": False,
                "enableScriptAgentCalendar": False,
                "enableScriptAgentCustomAgentTools": False,
                "enableScriptAgentSearchConnectorsInCustomAgent": False,
                "enableScriptAgentGoogleDriveInCustomAgent": False,
                "enableQueryCalendar": False,
                "enableQueryMail": False,
                "enableMailExplicitToolCalls": True,
            },
        }

    def _build_context_block(self, notion_client: Any, *, gemini_mode: bool = False) -> Dict[str, Any]:
        surface = "ai_module" if gemini_mode else "workflows"
        return {
            "id": str(uuid.uuid4()),
            "type": "context",
            "value": {
                "timezone": "Asia/Shanghai",
                "userName": notion_client.user_name,
                "userId": notion_client.user_id,
                "userEmail": notion_client.user_email,
                "spaceName": "Notion",
                "spaceId": notion_client.space_id,
                "spaceViewId": notion_client.space_view_id,
                "currentDatetime": datetime.datetime.now().astimezone().isoformat(),
                "surface": surface,
                "agentName": notion_client.user_name,
            },
        }

    def _fetch_recent_done_summaries(self, conn: sqlite3.Connection, conversation_id: str) -> List[str]:
        rows = conn.execute(
            """
            SELECT summary
            FROM compressed_summaries
            WHERE conversation_id = ?
              AND compress_status = 'done'
              AND COALESCE(summary, '') <> ''
            ORDER BY round_index DESC
            LIMIT ?
            """,
            (conversation_id, self.SUMMARY_INJECT_LIMIT),
        ).fetchall()
        logger.info(
            "Loaded done compressed summaries for transcript injection",
            extra={
                "request_info": {
                    "event": "memory_summary_query_done",
                    "conversation_id": conversation_id,
                    "compress_status": "done",
                    "row_count": len(rows),
                }
            },
        )

        summaries: List[str] = []
        for row in rows:
            summary = str(row["summary"] or "").strip()
            if summary:
                summaries.append(summary)

        summaries.reverse()
        logger.info(
            "Prepared summary injection payload",
            extra={
                "request_info": {
                    "event": "memory_summary_payload_ready",
                    "conversation_id": conversation_id,
                    "summary_count": len(summaries),
                }
            },
        )
        return summaries

    def _has_failed_compression(self, conn: sqlite3.Connection, conversation_id: str) -> bool:
        row = conn.execute(
            """
            SELECT 1
            FROM compressed_summaries
            WHERE conversation_id = ?
              AND compress_status = 'failed'
            LIMIT 1
            """,
            (conversation_id,),
        ).fetchone()
        return row is not None

    def _search_recall_round_indices(
        self,
        conn: sqlite3.Connection,
        conversation_id: str,
        query: str,
    ) -> List[int]:
        keyword = (query or "").strip()
        if not keyword:
            return []

        like_pattern = f"%{keyword}%"
        rows = conn.execute(
            """
            SELECT round_index
            FROM compressed_summaries
            WHERE conversation_id = ?
              AND (
                  user_content LIKE ?
                  OR assistant_content LIKE ?
                  OR COALESCE(summary, '') LIKE ?
              )
            ORDER BY
              CASE
                WHEN COALESCE(summary, '') LIKE ? THEN 0
                WHEN user_content LIKE ? THEN 1
                ELSE 2
              END,
              round_index DESC
            LIMIT ?
            """,
            (
                conversation_id,
                like_pattern,
                like_pattern,
                like_pattern,
                like_pattern,
                like_pattern,
                self.RECALL_LIMIT,
            ),
        ).fetchall()

        return sorted({int(row["round_index"]) for row in rows})

    def _format_recalled_archive(
        self,
        conn: sqlite3.Connection,
        conversation_id: str,
        round_indices: List[int],
    ) -> str:
        if not round_indices:
            return ""

        placeholders = ",".join(["?"] * len(round_indices))
        rows = conn.execute(
            f"""
            SELECT round_index, role, content
            FROM full_archive
            WHERE conversation_id = ?
              AND round_index IN ({placeholders})
            ORDER BY round_index ASC, id ASC
            """,
            [conversation_id, *round_indices],
        ).fetchall()

        if not rows:
            return ""

        grouped: Dict[int, List[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault(int(row["round_index"]), []).append(row)

        role_map = {"user": "用户", "assistant": "AI", "system": "系统"}
        lines: List[str] = []
        for round_index in sorted(grouped.keys()):
            lines.append(f"[第 {round_index + 1} 轮]")
            for row in grouped[round_index]:
                label = role_map.get(str(row["role"]), str(row["role"]))
                lines.append(f"{label}：{row['content']}")
            lines.append("")
        return "\n".join(lines).strip()

    def new_conversation(self) -> str:
        conv_id = str(uuid.uuid4())
        created_at = int(datetime.datetime.now().timestamp())
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO conversations (id, title, created_at, next_round_index)
                VALUES (?, ?, ?, ?)
                """,
                (conv_id, "New Chat", created_at, 0),
            )
            conn.commit()
        logger.info(
            "Conversation created",
            extra={"request_info": {"event": "conversation_created", "conversation_id": conv_id}},
        )
        return conv_id

    def get_conversation_thread_id(self, conversation_id: str) -> Optional[str]:
        """获取对话关联的 Notion thread_id"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT thread_id FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            return row["thread_id"] if row and row["thread_id"] else None

    def set_conversation_thread_id(self, conversation_id: str, thread_id: str) -> None:
        """保存对话关联的 Notion thread_id"""
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE conversations SET thread_id = ? WHERE id = ?",
                (thread_id, conversation_id),
            )
            conn.commit()
            logger.info(
                "Saved thread_id for conversation",
                extra={
                    "request_info": {
                        "event": "thread_id_saved",
                        "conversation_id": conversation_id,
                        "thread_id": thread_id,
                    }
                },
            )

    def conversation_exists(self, conversation_id: str) -> bool:
        if not conversation_id:
            return False
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            return row is not None

    def add_message(self, conversation_id: str, role: str, content: str, thinking: str = "") -> None:
        """
        Append a single message.

        Compatibility note:
        - No compression is triggered here.
        - next_round_index increments only when an assistant message follows a user message.
        """
        if role not in {"user", "assistant", "system"}:
            raise ValueError(f"Invalid role: {role}")

        with self._get_conn() as conn:
            conv_row = conn.execute(
                "SELECT id, next_round_index FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if not conv_row:
                raise ValueError(f"Conversation ID '{conversation_id}' does not exist.")

            next_round_index = int(conv_row["next_round_index"] or 0)
            round_index = next_round_index

            previous = conn.execute(
                """
                SELECT role
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (conversation_id,),
            ).fetchone()
            previous_role = previous["role"] if previous else None

            created_at = int(datetime.datetime.now().timestamp())

            # 关键修复：检测并避免重复插入相同的消息
            # 检查最后一条消息是否与当前消息相同（role + content）
            last_message = conn.execute(
                """
                SELECT role, content
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (conversation_id,),
            ).fetchone()

            if last_message and str(last_message["role"]) == role and str(last_message["content"]) == content:
                logger.debug(
                    "Duplicate message detected, skipping insertion",
                    extra={
                        "request_info": {
                            "event": "conversation_duplicate_message_skipped",
                            "conversation_id": conversation_id,
                            "role": role,
                            "content_length": len(content),
                        }
                    },
                )
                return

            archive_text = (
                self._build_assistant_memory_text(content, thinking)
                if role == "assistant"
                else content
            )
            conn.execute(
                """
                INSERT INTO messages (conversation_id, role, content, thinking, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (conversation_id, role, content, thinking, created_at),
            )
            self._archive_message(conn, conversation_id, role, archive_text, round_index, created_at)

            if role == "assistant" and previous_role == "user":
                conn.execute(
                    "UPDATE conversations SET next_round_index = ? WHERE id = ?",
                    (next_round_index + 1, conversation_id),
                )

            conn.commit()

    def persist_round(
        self,
        conversation_id: str,
        user_prompt: str,
        assistant_reply: str,
        assistant_thinking: str = "",
    ) -> int:
        """
        Persist one complete user/assistant turn and advance round index.
        同时更新滑动窗口表。

        Returns:
            int: 当前轮次号（round_index）
        """
        with self._get_conn() as conn:
            conv_row = conn.execute(
                "SELECT id, next_round_index FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if not conv_row:
                raise ValueError(f"Conversation ID '{conversation_id}' does not exist.")

            round_index = int(conv_row["next_round_index"] or 0)
            created_at = int(datetime.datetime.now().timestamp())

            # 保留对 messages 表的写入（兼容性）
            conn.execute(
                """
                INSERT INTO messages (conversation_id, role, content, thinking, created_at)
                VALUES (?, 'user', ?, '', ?)
                """,
                (conversation_id, user_prompt, created_at),
            )
            conn.execute(
                """
                INSERT INTO messages (conversation_id, role, content, thinking, created_at)
                VALUES (?, 'assistant', ?, ?, ?)
                """,
                (conversation_id, assistant_reply, assistant_thinking, created_at),
            )

            assistant_memory_text = self._build_assistant_memory_text(assistant_reply, assistant_thinking)
            self._archive_message(conn, conversation_id, "user", user_prompt, round_index, created_at)
            self._archive_message(
                conn,
                conversation_id,
                "assistant",
                assistant_memory_text,
                round_index,
                created_at,
            )

            # 更新滑动窗口表（使用 UPSERT 确保幂等性和数据完整性）
            conn.execute(
                """
                INSERT INTO sliding_window (
                    conversation_id, round_number, user_content,
                    assistant_content, assistant_thinking, compress_status, created_at
                ) VALUES (?, ?, ?, ?, ?, 'active', ?)
                ON CONFLICT(conversation_id, round_number) DO UPDATE SET
                    user_content = excluded.user_content,
                    assistant_content = excluded.assistant_content,
                    assistant_thinking = excluded.assistant_thinking,
                    compress_status = 'active'
                """,
                (
                    conversation_id,
                    round_index,
                    user_prompt,
                    assistant_reply,
                    assistant_thinking,
                    created_at,
                ),
            )

            conn.execute(
                "UPDATE conversations SET next_round_index = ? WHERE id = ?",
                (round_index + 1, conversation_id),
            )
            conn.commit()

        return round_index

    # ==================== 滑动窗口管理 ====================

    def update_sliding_window(
        self,
        conversation_id: str,
        round_number: int,
        user_content: str,
        assistant_content: str,
        assistant_thinking: str = "",
    ) -> None:
        """
        更新滑动窗口：将当前轮对话插入 sliding_window 表。
        使用 UPSERT 确保幂等性和数据完整性。
        同时归档到 full_archive（已在 persist_round 中完成）。
        """
        created_at = int(datetime.datetime.now().timestamp())
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO sliding_window (
                    conversation_id, round_number, user_content,
                    assistant_content, assistant_thinking, compress_status, created_at
                ) VALUES (?, ?, ?, ?, ?, 'active', ?)
                ON CONFLICT(conversation_id, round_number) DO UPDATE SET
                    user_content = excluded.user_content,
                    assistant_content = excluded.assistant_content,
                    assistant_thinking = excluded.assistant_thinking,
                    compress_status = 'active'
                """,
                (
                    conversation_id,
                    round_number,
                    user_content,
                    assistant_content,
                    assistant_thinking,
                    created_at,
                ),
            )
            conn.commit()
            logger.info(
                "Sliding window updated",
                extra={
                    "request_info": {
                        "event": "sliding_window_updated",
                        "conversation_id": conversation_id,
                        "round_number": round_number,
                    }
                },
            )

    def get_sliding_window(
        self,
        conn: sqlite3.Connection,
        conversation_id: str,
        limit_rounds: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """
        获取滑动窗口内容，返回最近 N 轮对话（按 round_number 降序后反转）。
        天然成对返回 user + assistant，不再需要 _normalize_window_messages()。
        """
        if limit_rounds is None:
            limit_rounds = self.WINDOW_ROUNDS

        rows = conn.execute(
            """
            SELECT round_number, user_content, assistant_content, assistant_thinking, compress_status
            FROM sliding_window
            WHERE conversation_id = ? AND compress_status = 'active'
            ORDER BY round_number DESC
            LIMIT ?
            """,
            (conversation_id, limit_rounds),
        ).fetchall()

        # 添加调试日志（使用 INFO 级别确保可见）
        logger.info(
            "Retrieved sliding window data",
            extra={
                "request_info": {
                    "event": "sliding_window_query",
                    "conversation_id": conversation_id,
                    "limit_rounds": limit_rounds,
                    "actual_rows": len(rows),
                    "round_numbers": [r["round_number"] for r in rows] if rows else [],
                }
            },
        )

        if not rows:
            return []

        # 反转顺序（从旧到新），并转换为消息列表格式
        rows_list = list(rows)
        rows_list.reverse()

        messages: List[Dict[str, str]] = []
        for row in rows_list:
            # 添加 user 消息
            messages.append({
                "role": "user",
                "content": str(row["user_content"] or ""),
                "thinking": "",
            })
            # 添加 assistant 消息
            assistant_text = self._build_assistant_memory_text(
                str(row["assistant_content"] or ""),
                str(row["assistant_thinking"] or ""),
            )
            messages.append({
                "role": "assistant",
                "content": assistant_text,
                "thinking": str(row["assistant_thinking"] or ""),
            })

        return messages

    def cleanup_old_sliding_window(
        self,
        conn: sqlite3.Connection,
        conversation_id: str,
        keep_rounds: Optional[int] = None,
    ) -> int:
        """
        清理滑动窗口中的旧数据。
        只删除 compress_status='compressed' 的记录，确保压缩完成后才清理。
        返回删除的记录数。
        """
        if keep_rounds is None:
            keep_rounds = self.WINDOW_ROUNDS

        # 获取当前最大轮次
        max_round_row = conn.execute(
            """
            SELECT MAX(round_number) AS max_round
            FROM sliding_window
            WHERE conversation_id = ?
            """,
            (conversation_id,),
        ).fetchone()
        max_round = int(max_round_row["max_round"] or 0) if max_round_row else 0

        # 计算需要保留的最小轮次
        min_keep_round = max(0, max_round - keep_rounds + 1)

        # 只删除已压缩的旧数据
        result = conn.execute(
            """
            DELETE FROM sliding_window
            WHERE conversation_id = ?
              AND round_number < ?
              AND compress_status = 'compressed'
            """,
            (conversation_id, min_keep_round),
        )
        deleted_count = result.rowcount

        if deleted_count > 0:
            logger.info(
                "Cleaned up old sliding window records",
                extra={
                    "request_info": {
                        "event": "sliding_window_cleanup",
                        "conversation_id": conversation_id,
                        "deleted_count": deleted_count,
                        "min_keep_round": min_keep_round,
                    }
                },
            )

        return deleted_count

    def get_sliding_window_round_count(
        self,
        conn: sqlite3.Connection,
        conversation_id: str,
    ) -> int:
        """获取滑动窗口中的活跃轮数。"""
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT round_number) AS round_count
            FROM sliding_window
            WHERE conversation_id = ? AND compress_status = 'active'
            """,
            (conversation_id,),
        ).fetchone()
        return int(row["round_count"] or 0) if row else 0

    def migrate_messages_to_sliding_window(
        self,
        conversation_id: str,
        batch_size: int = 100,
        conn: Optional[sqlite3.Connection] = None,
    ) -> int:
        """
        将现有 messages 表中的数据迁移到 sliding_window 表。

        Args:
            conversation_id: 要迁移的对话 ID
            batch_size: 每批处理的消息数
            conn: 可选的数据库连接

        Returns:
            int: 迁移的轮次数
        """
        is_internal_conn = False
        if conn is None:
            conn = self._get_conn()
            is_internal_conn = True

        try:
            # 检查是否已有滑动窗口数据
            existing_rounds = self.get_sliding_window_round_count(conn, conversation_id)
            if existing_rounds > 0:
                logger.info(
                    "Sliding window already has data, skipping migration",
                    extra={
                        "request_info": {
                            "event": "migration_skipped",
                            "conversation_id": conversation_id,
                            "existing_rounds": existing_rounds,
                        }
                    },
                )
                return 0

            # 获取所有消息
            messages = conn.execute(
                """
                SELECT role, content, COALESCE(thinking, '') AS thinking, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (conversation_id,),
            ).fetchall()

            if not messages:
                return 0

            # 配对 user + assistant 消息
            migrated_rounds = 0
            round_number = 0
            i = 0
            created_at = int(datetime.datetime.now().timestamp())
            rounds_to_insert = []

            while i < len(messages):
                # 查找 user 消息
                if messages[i]["role"] != "user":
                    i += 1
                    continue

                user_content = str(messages[i]["content"] or "")
                if not user_content.strip():
                    i += 1
                    continue

                # 查找对应的 assistant 消息
                if i + 1 >= len(messages) or messages[i + 1]["role"] != "assistant":
                    i += 1
                    continue

                assistant_msg = messages[i + 1]
                assistant_content = str(assistant_msg["content"] or "")
                assistant_thinking = str(assistant_msg["thinking"] or "")
                msg_created_at = int(assistant_msg["created_at"] or created_at)

                rounds_to_insert.append((
                    conversation_id,
                    round_number,
                    user_content,
                    assistant_content,
                    assistant_thinking,
                    msg_created_at,
                ))

                migrated_rounds += 1
                round_number += 1
                i += 2

            if rounds_to_insert:
                # 批量插入到 sliding_window
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO sliding_window (
                        conversation_id, round_number, user_content,
                        assistant_content, assistant_thinking, compress_status, created_at
                    ) VALUES (?, ?, ?, ?, ?, 'active', ?)
                    """,
                    rounds_to_insert,
                )

                # 更新 next_round_index
                conn.execute(
                    """
                    UPDATE conversations
                    SET next_round_index = ?
                    WHERE id = ? AND COALESCE(next_round_index, 0) < ?
                    """,
                    (round_number, conversation_id, round_number),
                )

            if is_internal_conn:
                conn.commit()

            logger.info(
                "Migrated messages to sliding window",
                extra={
                    "request_info": {
                        "event": "migration_completed",
                        "conversation_id": conversation_id,
                        "migrated_rounds": migrated_rounds,
                        "total_messages": len(messages),
                    }
                },
            )

            return migrated_rounds
        finally:
            if is_internal_conn:
                conn.close()

    def migrate_all_conversations(self) -> Dict[str, int]:
        """
        迁移所有对话的 messages 到 sliding_window。
        优化点：单一查询识别待处理对话，批量处理并复用连接。

        Returns:
            Dict[str, int]: 每个对话 ID 对应的迁移轮次数
        """
        results: Dict[str, int] = {}

        with self._get_conn() as conn:
            # 找到有消息但没有滑动窗口记录的对话 ID
            # 这里的逻辑是：对话存在于 messages 表中，但不存在于 sliding_window 表中
            rows = conn.execute(
                """
                SELECT DISTINCT m.conversation_id
                FROM messages m
                LEFT JOIN sliding_window sw ON m.conversation_id = sw.conversation_id
                WHERE sw.conversation_id IS NULL
                """
            ).fetchall()
            conversation_ids = [row["conversation_id"] for row in rows]

        if not conversation_ids:
            logger.info("No conversations need migration.")
            return results

        # 批量处理以平衡性能和内存/锁持有时间
        batch_size = 50
        for i in range(0, len(conversation_ids), batch_size):
            batch_ids = conversation_ids[i:i+batch_size]
            with self._get_conn() as conn:
                for conv_id in batch_ids:
                    try:
                        migrated = self.migrate_messages_to_sliding_window(conv_id, conn=conn)
                        if migrated > 0:
                            results[conv_id] = migrated
                    except Exception as e:
                        logger.error(
                            "Failed to migrate conversation",
                            exc_info=True,
                            extra={
                                "request_info": {
                                    "event": "migration_failed",
                                    "conversation_id": conv_id,
                                    "error": str(e),
                                }
                            },
                        )
                conn.commit()

        logger.info(
            "Completed migration for all conversations",
            extra={
                "request_info": {
                    "event": "migration_all_completed",
                    "total_conversations": len(conversation_ids),
                    "migrated_conversations": len(results),
                    "total_rounds": sum(results.values()),
                }
            },
        )

        return results

    # ==================== 滑动窗口管理结束 ====================

    def get_transcript_payload(
        self,
        notion_client: Any,
        conversation_id: str,
        new_prompt: str,
        model_name: str,
        recall_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"Conversation ID '{conversation_id}' does not exist.")

            # 强制使用新的滑动窗口表（单一数据源）
            sliding_window_rounds = self.get_sliding_window_round_count(conn, conversation_id)
            recent_messages = self.get_sliding_window(conn, conversation_id)

            logger.info(
                "Using sliding window as single source of truth",
                extra={
                    "request_info": {
                        "event": "sliding_window_enforced",
                        "conversation_id": conversation_id,
                        "round_count": sliding_window_rounds,
                        "message_count": len(recent_messages),
                    }
                },
            )

            summaries = self._fetch_recent_done_summaries(conn, conversation_id)
            memory_degraded = False

            recall_round_indices = self._search_recall_round_indices(
                conn,
                conversation_id,
                recall_query or "",
            )
            recalled_text = self._format_recalled_archive(conn, conversation_id, recall_round_indices)

        transcript: List[Dict[str, Any]] = []
        gemini_mode = is_gemini_model(model_name)

        transcript.append(self._build_config_block(model_name, gemini_mode=gemini_mode))
        transcript.append(self._build_context_block(notion_client, gemini_mode=gemini_mode))

        # Summary injection must stay between context block and recent-window messages.
        if summaries:
            numbered = "\n".join(f"{idx + 1}. {item}" for idx, item in enumerate(summaries))
            transcript.append(
                self._build_dialog_block(
                    "user",
                    f"以下是本次对话的历史摘要（从早到晚）：\n{numbered}",
                    notion_client,
                    gemini_mode=gemini_mode,
                )
            )
            transcript.append(
                self._build_dialog_block(
                    "assistant",
                    "我已了解之前的对话背景。",
                    notion_client,
                    gemini_mode=gemini_mode,
                )
            )
            logger.info(
                "Injected compressed summaries into transcript",
                extra={
                    "request_info": {
                        "event": "memory_summary_injected",
                        "conversation_id": conversation_id,
                        "summary_count": len(summaries),
                    }
                },
            )

        # 添加调试日志（使用 INFO 级别确保可见）
        logger.info(
            "Adding recent_messages to transcript",
            extra={
                "request_info": {
                    "event": "recent_messages_addition",
                    "conversation_id": conversation_id,
                    "recent_messages_count": len(recent_messages),
                    "recent_messages_preview": [
                        {"role": msg.get("role"), "content_length": len(msg.get("content", ""))}
                        for msg in recent_messages
                    ]
                }
            },
        )

        for msg in recent_messages:
            transcript.append(
                self._build_dialog_block(
                    msg["role"],
                    msg["content"],
                    notion_client,
                    gemini_mode=gemini_mode,
                )
            )

        logger.info(
            "Final transcript size",
            extra={
                "request_info": {
                    "event": "transcript_final_size",
                    "conversation_id": conversation_id,
                    "transcript_length": len(transcript),
                    "transcript_block_types": [block.get("type") for block in transcript]
                }
            },
        )

        if recalled_text:
            transcript.append(
                self._build_dialog_block(
                    "user",
                    (
                        "【系统召回的相关历史记录】\n"
                        f"{recalled_text}\n\n"
                        "请基于以上历史回答用户的问题。"
                    ),
                    notion_client,
                    gemini_mode=gemini_mode,
                )
            )
            transcript.append(
                self._build_dialog_block(
                    "assistant",
                    "我已查阅相关历史记录，将综合作答。",
                    notion_client,
                    gemini_mode=gemini_mode,
                )
            )

        transcript.append(
            self._build_dialog_block(
                "user",
                new_prompt,
                notion_client,
                gemini_mode=gemini_mode,
            )
        )
        return {
            "transcript": transcript,
            "memory_degraded": memory_degraded,
        }

    def get_transcript(self, notion_client, conversation_id: str, new_prompt: str, model_name: str) -> list:
        payload = self.get_transcript_payload(
            notion_client=notion_client,
            conversation_id=conversation_id,
            new_prompt=new_prompt,
            model_name=model_name,
            recall_query=None,
        )
        return payload["transcript"]

    def delete_conversation(self, conversation_id: str) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            conn.commit()
            return cursor.rowcount > 0

    def list_conversations(self) -> List[str]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT id FROM conversations ORDER BY created_at DESC")
            return [row["id"] for row in cursor.fetchall()]


async def compress_sliding_window_round(
    manager: ConversationManager,
    conversation_id: str,
    round_number: int,
) -> bool:
    """
    压缩滑动窗口中指定轮次的对话。

    异步预压缩流程：
    1. 检查该轮次是否已压缩（幂等性）
    2. 标记为 'compressing' 防止并发
    3. 调用 LLM 生成摘要
    4. 写入 compressed_summaries
    5. 标记为 'compressed'

    Returns:
        bool: 压缩是否成功
    """
    from app.summarizer import (
        SummarizerUnavailableError,
        is_summarizer_configured,
        summarize_turn,
    )

    try:
        with manager._get_conn() as conn:
            # 检查该轮次是否存在且需要压缩
            round_row = conn.execute(
                """
                SELECT round_number, user_content, assistant_content, assistant_thinking, compress_status
                FROM sliding_window
                WHERE conversation_id = ? AND round_number = ?
                """,
                (conversation_id, round_number),
            ).fetchone()

            if not round_row:
                logger.debug(
                    "Sliding window round not found for compression",
                    extra={
                        "request_info": {
                            "event": "sliding_window_round_not_found",
                            "conversation_id": conversation_id,
                            "round_number": round_number,
                        }
                    },
                )
                return False

            if round_row["compress_status"] != "active":
                logger.debug(
                    "Sliding window round already compressed or compressing",
                    extra={
                        "request_info": {
                            "event": "sliding_window_round_already_compressed",
                            "conversation_id": conversation_id,
                            "round_number": round_number,
                            "compress_status": round_row["compress_status"],
                        }
                    },
                )
                return True  # 已压缩视为成功

            # 标记为正在压缩
            conn.execute(
                """
                UPDATE sliding_window
                SET compress_status = 'compressing'
                WHERE conversation_id = ? AND round_number = ? AND compress_status = 'active'
                """,
                (conversation_id, round_number),
            )
            conn.commit()

        # 获取旧的压缩摘要
        with manager._get_conn() as conn:
            old_summary_rows = conn.execute(
                """
                SELECT summary
                FROM compressed_summaries
                WHERE conversation_id = ?
                  AND compress_status = 'done'
                  AND COALESCE(summary, '') <> ''
                  AND round_index < ?
                ORDER BY round_index ASC
                """,
                (conversation_id, round_number),
            ).fetchall()
            old_summaries = [
                str(row["summary"] or "").strip()
                for row in old_summary_rows
                if str(row["summary"] or "").strip()
            ]

        if not is_summarizer_configured():
            logger.warning(
                "Skipping compression because summarizer is not configured",
                extra={
                    "request_info": {
                        "event": "sliding_window_compress_skipped_no_summarizer",
                        "conversation_id": conversation_id,
                        "round_number": round_number,
                    }
                },
            )
            # 恢复状态
            with manager._get_conn() as conn:
                conn.execute(
                    """
                    UPDATE sliding_window
                    SET compress_status = 'active'
                    WHERE conversation_id = ? AND round_number = ?
                    """,
                    (conversation_id, round_number),
                )
                conn.commit()
            return False

        user_content = str(round_row["user_content"] or "")
        assistant_content = manager._build_assistant_memory_text(
            str(round_row["assistant_content"] or ""),
            str(round_row["assistant_thinking"] or ""),
        )

        try:
            summary_text = await summarize_turn(
                old_summaries=old_summaries,
                user_msg=user_content,
                assistant_msg=assistant_content,
            )
        except SummarizerUnavailableError:
            logger.warning(
                "Compression summary unavailable",
                extra={
                    "request_info": {
                        "event": "sliding_window_compress_summary_unavailable",
                        "conversation_id": conversation_id,
                        "round_number": round_number,
                    }
                },
            )
            # 恢复状态以便下次重试
            with manager._get_conn() as conn:
                conn.execute(
                    """
                    UPDATE sliding_window
                    SET compress_status = 'active'
                    WHERE conversation_id = ? AND round_number = ?
                    """,
                    (conversation_id, round_number),
                )
                conn.commit()
            return False
        except Exception:
            logger.error(
                "Failed to summarize sliding window round",
                exc_info=True,
                extra={
                    "request_info": {
                        "event": "sliding_window_compress_summary_failed",
                        "conversation_id": conversation_id,
                        "round_number": round_number,
                    }
                },
            )
            # 恢复状态以便下次重试
            with manager._get_conn() as conn:
                conn.execute(
                    """
                    UPDATE sliding_window
                    SET compress_status = 'active'
                    WHERE conversation_id = ? AND round_number = ?
                    """,
                    (conversation_id, round_number),
                )
                conn.commit()
            return False

        summary_text = summary_text.strip()
        if not summary_text:
            logger.warning(
                "Compression summary was empty",
                extra={
                    "request_info": {
                        "event": "sliding_window_compress_summary_empty",
                        "conversation_id": conversation_id,
                        "round_number": round_number,
                    }
                },
            )
            # 恢复状态以便下次重试
            with manager._get_conn() as conn:
                conn.execute(
                    """
                    UPDATE sliding_window
                    SET compress_status = 'active'
                    WHERE conversation_id = ? AND round_number = ?
                    """,
                    (conversation_id, round_number),
                )
                conn.commit()
            return False

        # 写入压缩摘要并更新状态
        created_at = int(datetime.datetime.now().timestamp())
        with manager._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO compressed_summaries (
                    conversation_id, round_index, user_content,
                    assistant_content, summary, compress_status, created_at
                ) VALUES (?, ?, ?, ?, ?, 'done', ?)
                """,
                (
                    conversation_id,
                    round_number,
                    user_content,
                    assistant_content,
                    summary_text,
                    created_at,
                ),
            )
            conn.execute(
                """
                UPDATE sliding_window
                SET compress_status = 'compressed'
                WHERE conversation_id = ? AND round_number = ?
                """,
                (conversation_id, round_number),
            )
            conn.commit()

        logger.info(
            "Sliding window round compressed successfully",
            extra={
                "request_info": {
                    "event": "sliding_window_round_compressed",
                    "conversation_id": conversation_id,
                    "round_number": round_number,
                    "summary_length": len(summary_text),
                }
            },
        )
        return True

    except Exception:
        logger.error(
            "compress_sliding_window_round crashed",
            exc_info=True,
            extra={
                "request_info": {
                    "event": "sliding_window_compress_crashed",
                    "conversation_id": conversation_id,
                    "round_number": round_number,
                }
            },
        )
        # 尝试恢复状态
        try:
            with manager._get_conn() as conn:
                conn.execute(
                    """
                    UPDATE sliding_window
                    SET compress_status = 'active'
                    WHERE conversation_id = ? AND round_number = ?
                    """,
                    (conversation_id, round_number),
                )
                conn.commit()
        except Exception:
            pass
        return False


async def compress_round_if_needed(manager: ConversationManager, conversation_id: str) -> None:
    """
    Move old turns out of sliding window, archive raw text, and summarize with LLM.

    优先处理新的 sliding_window 表，兼容旧的 messages 表。

    Any failure is logged only and never raised to request path.
    """
    from app.summarizer import (
        SummarizerUnavailableError,
        is_summarizer_configured,
        summarize_turn,
    )

    try:
        # 优先处理新的滑动窗口表
        with manager._get_conn() as conn:
            sliding_round_count = manager.get_sliding_window_round_count(conn, conversation_id)
            if sliding_round_count > manager.WINDOW_ROUNDS:
                # 找到需要压缩的轮次
                max_round_row = conn.execute(
                    """
                    SELECT MAX(round_number) AS max_round
                    FROM sliding_window
                    WHERE conversation_id = ? AND compress_status = 'active'
                    """,
                    (conversation_id,),
                ).fetchone()
                max_round = int(max_round_row["max_round"] or 0) if max_round_row else 0

                # 计算需要压缩的最小轮次
                min_compress_round = max(0, max_round - manager.WINDOW_ROUNDS + 1)

                # 获取需要压缩的轮次
                rounds_to_compress = conn.execute(
                    """
                    SELECT round_number
                    FROM sliding_window
                    WHERE conversation_id = ?
                      AND compress_status = 'active'
                      AND round_number < ?
                    ORDER BY round_number ASC
                    """,
                    (conversation_id, min_compress_round),
                ).fetchall()

                for row in rounds_to_compress:
                    round_number = int(row["round_number"])
                    await compress_sliding_window_round(manager, conversation_id, round_number)

                # 清理已压缩的旧数据
                manager.cleanup_old_sliding_window(conn, conversation_id)
                return

        # 兼容旧的 messages 表（如果滑动窗口为空）
        while True:
            with manager._get_conn() as conn:
                conv_row = conn.execute(
                    """
                    SELECT id, next_round_index
                    FROM conversations
                    WHERE id = ?
                    """,
                    (conversation_id,),
                ).fetchone()
                if not conv_row:
                    return

                message_count = manager._count_messages(conn, conversation_id)
                if message_count <= manager.WINDOW_SIZE:
                    return

                oldest_rows = conn.execute(
                    """
                    SELECT id, role, content, COALESCE(thinking, '') AS thinking, created_at
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY created_at ASC, id ASC
                    LIMIT 2
                    """,
                    (conversation_id,),
                ).fetchall()
                if len(oldest_rows) < 2:
                    return

                oldest_user = oldest_rows[0]
                oldest_assistant = oldest_rows[1]
                if oldest_user["role"] != "user" or oldest_assistant["role"] != "assistant":
                    logger.warning(
                        "Skip compression due to non user/assistant oldest pair",
                        extra={
                            "request_info": {
                                "event": "conversation_compress_skipped",
                                "conversation_id": conversation_id,
                                "roles": [oldest_user["role"], oldest_assistant["role"]],
                            }
                        },
                    )
                    return

                next_round_index = int(conv_row["next_round_index"] or 0)
                rounds_in_messages = max(message_count // 2, 1)
                round_index = max(next_round_index - rounds_in_messages, 0)
                created_at = int(datetime.datetime.now().timestamp())

                old_summary_rows = conn.execute(
                    """
                    SELECT summary
                    FROM compressed_summaries
                    WHERE conversation_id = ?
                      AND compress_status = 'done'
                      AND COALESCE(summary, '') <> ''
                      AND round_index < ?
                    ORDER BY round_index ASC
                    """,
                    (conversation_id, round_index),
                ).fetchall()
                old_summaries = [str(row["summary"] or "").strip() for row in old_summary_rows if str(row["summary"] or "").strip()]
                logger.info(
                    "Prepared cumulative old summaries for turn compression",
                    extra={
                        "request_info": {
                            "event": "memory_cumulative_summaries_ready",
                            "conversation_id": conversation_id,
                            "current_round_index": round_index,
                            "old_summary_count": len(old_summaries),
                        }
                    },
                )

                candidate = {
                    "user_id": int(oldest_user["id"]),
                    "assistant_id": int(oldest_assistant["id"]),
                    "user_content": str(oldest_user["content"]),
                    "assistant_content": manager._build_assistant_memory_text(
                        str(oldest_assistant["content"]),
                        str(oldest_assistant["thinking"]),
                    ),
                    "user_created_at": int(oldest_user["created_at"] or created_at),
                    "assistant_created_at": int(oldest_assistant["created_at"] or created_at),
                    "round_index": round_index,
                    "created_at": created_at,
                }

            if not is_summarizer_configured():
                logger.warning(
                    "Skipping compression because summarizer is not configured",
                    extra={
                        "request_info": {
                            "event": "conversation_compress_skipped_no_summarizer",
                            "conversation_id": conversation_id,
                            "message_count": message_count,
                        }
                    },
                )
                return

            try:
                summary_text = await summarize_turn(
                    old_summaries=old_summaries,
                    user_msg=candidate["user_content"],
                    assistant_msg=candidate["assistant_content"],
                )
            except SummarizerUnavailableError:
                logger.warning(
                    "Compression summary unavailable; active messages retained",
                    extra={
                        "request_info": {
                            "event": "conversation_compress_summary_unavailable",
                            "conversation_id": conversation_id,
                            "round_index": candidate["round_index"],
                        }
                    },
                )
                return
            except Exception:
                logger.error(
                    "Failed to summarize compressed round",
                    exc_info=True,
                    extra={
                        "request_info": {
                            "event": "conversation_compress_summary_failed",
                            "conversation_id": conversation_id,
                            "round_index": candidate["round_index"],
                        }
                    },
                )
                return
            else:
                summary_text = summary_text.strip()
                if not summary_text:
                    logger.warning(
                        "Compression summary was empty; active messages retained",
                        extra={
                            "request_info": {
                                "event": "conversation_compress_summary_empty",
                                "conversation_id": conversation_id,
                                "round_index": candidate["round_index"],
                            }
                        },
                    )
                    return

                with manager._get_conn() as conn:
                    current_message_count = manager._count_messages(conn, conversation_id)
                    if current_message_count <= manager.WINDOW_SIZE:
                        return

                    current_pair = conn.execute(
                        """
                        SELECT id, role
                        FROM messages
                        WHERE id IN (?, ?)
                        ORDER BY created_at ASC, id ASC
                        """,
                        (candidate["user_id"], candidate["assistant_id"]),
                    ).fetchall()
                    if (
                        len(current_pair) != 2
                        or int(current_pair[0]["id"]) != candidate["user_id"]
                        or int(current_pair[1]["id"]) != candidate["assistant_id"]
                        or current_pair[0]["role"] != "user"
                        or current_pair[1]["role"] != "assistant"
                    ):
                        logger.info(
                            "Compression candidate changed before commit; retrying with fresh snapshot",
                            extra={
                                "request_info": {
                                    "event": "conversation_compress_candidate_stale",
                                    "conversation_id": conversation_id,
                                    "round_index": candidate["round_index"],
                                }
                            },
                        )
                        continue

                    conn.execute(
                        "DELETE FROM messages WHERE id IN (?, ?)",
                        (candidate["user_id"], candidate["assistant_id"]),
                    )
                    conn.execute(
                        """
                        INSERT INTO compressed_summaries (
                            conversation_id,
                            round_index,
                            user_content,
                            assistant_content,
                            summary,
                            compress_status,
                            created_at
                        )
                        VALUES (?, ?, ?, ?, ?, 'done', ?)
                        """,
                        (
                            conversation_id,
                            candidate["round_index"],
                            candidate["user_content"],
                            candidate["assistant_content"],
                            summary_text,
                            candidate["created_at"],
                        ),
                    )
                    manager._archive_message(
                        conn,
                        conversation_id,
                        "user",
                        candidate["user_content"],
                        candidate["round_index"],
                        candidate["user_created_at"],
                    )
                    manager._archive_message(
                        conn,
                        conversation_id,
                        "assistant",
                        candidate["assistant_content"],
                        candidate["round_index"],
                        candidate["assistant_created_at"],
                    )
                    conn.execute(
                        """
                        UPDATE conversations
                        SET compress_failed_at = NULL
                        WHERE id = ?
                        """,
                        (conversation_id,),
                    )
                    conn.commit()
    except Exception:
        logger.error(
            "compress_round_if_needed crashed",
            exc_info=True,
            extra={
                "request_info": {
                    "event": "conversation_compress_task_crashed",
                    "conversation_id": conversation_id,
                }
            },
        )


def build_lite_transcript(user_prompt: str, model_name: str) -> list[dict[str, Any]]:
    """构建 Lite 模式的最简 transcript（只有 config + user）"""
    from app.model_registry import get_notion_model, get_thread_type
    import uuid

    notion_model = get_notion_model(model_name)
    thread_type = get_thread_type(model_name)

    return [
        {
            "id": str(uuid.uuid4()),
            "type": "config",
            "value": {
                "type": thread_type,
                "model": notion_model,
                "modelFromUser": True,
            }
        },
        {
            "id": str(uuid.uuid4()),
            "type": "user",
            "value": [[user_prompt]]
        }
    ]


def build_standard_transcript(
    messages: list[dict[str, Any]],
    model_name: str,
    account: dict
) -> list[dict[str, Any]]:
    """
    构建 Standard 模式的 transcript（完整上下文）

    Args:
        messages: OpenAI 格式的 messages 数组（完整历史）
        model_name: 模型名称
        account: 账号信息字典，包含 user_id, space_id 等

    Returns:
        Notion transcript 数组

    参考：notion-2api 项目的实现
    """
    from app.model_registry import get_notion_model, get_thread_type
    import uuid
    from datetime import datetime
    notion_model = get_notion_model(model_name)
    thread_type = get_thread_type(model_name)

    # 基础 transcript：config + context
    transcript = [
        {
            "id": str(uuid.uuid4()),
            "type": "config",
            "value": {
                "type": thread_type,
                "model": notion_model,
                "modelFromUser": True,
                "useWebSearch": True,
            }
        },
        {
            "id": str(uuid.uuid4()),
            "type": "context",
            "value": {
                "timezone": "Asia/Shanghai",
                "currentDatetime": datetime.now().astimezone().isoformat(),
                "userId": account.get("user_id", ""),
                "spaceId": account.get("space_id", ""),
            }
        }
    ]

    # 收集所有 system 消息
    system_instructions = []
    user_messages = []

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")

        if role == "system":
            system_instructions.append(content)
        elif role == "user":
            user_messages.append(content)
        elif role == "assistant":
            # assistant 消息单独处理
            transcript.append({
                "id": str(uuid.uuid4()),
                "type": "agent-inference",
                "value": [
                    {
                        "type": "text",
                        "content": content
                    }
                ]
            })

    # 将 system 指令合并到第一条 user 消息（与 Lite/Heavy 模式保持一致）
    if user_messages:
        first_user_content = user_messages[0]
        if system_instructions:
            merged_system = "\n".join(system_instructions)
            first_user_content = f"[System Instructions: {merged_system}]\n\n{first_user_content}"

        transcript.append({
            "id": str(uuid.uuid4()),
            "type": "user",
            "value": [[first_user_content]],
            "userId": account.get("user_id", ""),
            "createdAt": datetime.now().astimezone().isoformat()
        })

        # 添加剩余的 user 消息
        for content in user_messages[1:]:
            transcript.append({
                "id": str(uuid.uuid4()),
                "type": "user",
                "value": [[content]],
                "userId": account.get("user_id", ""),
                "createdAt": datetime.now().astimezone().isoformat()
            })

    return transcript
