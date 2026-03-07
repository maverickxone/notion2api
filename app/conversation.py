import datetime
import os
import sqlite3
import uuid
from typing import Any, Dict, List, Optional

from app.logger import logger


class ConversationManager:
    """SQLite-backed conversation history manager with layered memory."""

    WINDOW_SIZE = 10
    SUMMARY_INJECT_LIMIT = 15
    RECALL_LIMIT = 5

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

            # Keep legacy summary for compatibility but do not write to it anymore.
            self._ensure_column(conn, "conversations", "summary TEXT")
            self._ensure_column(conn, "conversations", "next_round_index INTEGER DEFAULT 0")
            self._ensure_column(conn, "conversations", "compress_failed_at INTEGER")

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
            SELECT role, content
            FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (conversation_id, limit),
        ).fetchall()
        messages = [{"role": r["role"], "content": r["content"]} for r in rows]
        messages.reverse()
        return messages

    def _normalize_window_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        normalized: List[Dict[str, str]] = []
        expected_role = "user"
        for msg in messages:
            role = msg.get("role", "")
            if role not in {"user", "assistant"}:
                continue
            if role != expected_role:
                continue
            normalized.append({"role": role, "content": msg.get("content", "")})
            expected_role = "assistant" if expected_role == "user" else "user"

        # Keep transcript append-safe for a new user prompt.
        while normalized and normalized[-1]["role"] != "assistant":
            normalized.pop()
        return normalized

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

    def _build_dialog_block(self, role: str, content: str, notion_client: Any) -> Dict[str, Any]:
        block: Dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "type": role,
            "value": [[content]],
        }
        if role == "user":
            block["userId"] = notion_client.user_id
        return block

    def _build_config_block(self, model_name: str) -> Dict[str, Any]:
        return {
            "id": str(uuid.uuid4()),
            "type": "config",
            "value": {
                "type": "workflow",
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

    def _build_context_block(self, notion_client: Any) -> Dict[str, Any]:
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
                "surface": "ai_module",
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

    def conversation_exists(self, conversation_id: str) -> bool:
        if not conversation_id:
            return False
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            return row is not None

    def add_message(self, conversation_id: str, role: str, content: str) -> None:
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
            conn.execute(
                """
                INSERT INTO messages (conversation_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, role, content, created_at),
            )
            self._archive_message(conn, conversation_id, role, content, round_index, created_at)

            if role == "assistant" and previous_role == "user":
                conn.execute(
                    "UPDATE conversations SET next_round_index = ? WHERE id = ?",
                    (next_round_index + 1, conversation_id),
                )

            conn.commit()

    def persist_round(self, conversation_id: str, user_prompt: str, assistant_reply: str) -> None:
        """Persist one complete user/assistant turn and advance round index."""
        with self._get_conn() as conn:
            conv_row = conn.execute(
                "SELECT id, next_round_index FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if not conv_row:
                raise ValueError(f"Conversation ID '{conversation_id}' does not exist.")

            round_index = int(conv_row["next_round_index"] or 0)
            created_at = int(datetime.datetime.now().timestamp())

            conn.execute(
                """
                INSERT INTO messages (conversation_id, role, content, created_at)
                VALUES (?, 'user', ?, ?)
                """,
                (conversation_id, user_prompt, created_at),
            )
            conn.execute(
                """
                INSERT INTO messages (conversation_id, role, content, created_at)
                VALUES (?, 'assistant', ?, ?)
                """,
                (conversation_id, assistant_reply, created_at),
            )

            self._archive_message(conn, conversation_id, "user", user_prompt, round_index, created_at)
            self._archive_message(conn, conversation_id, "assistant", assistant_reply, round_index, created_at)

            conn.execute(
                "UPDATE conversations SET next_round_index = ? WHERE id = ?",
                (round_index + 1, conversation_id),
            )
            conn.commit()

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

            message_count = self._count_messages(conn, conversation_id)
            active_window_limit = message_count if message_count > self.WINDOW_SIZE else self.WINDOW_SIZE
            recent_messages = self._fetch_recent_messages(conn, conversation_id, active_window_limit)
            summaries = self._fetch_recent_done_summaries(conn, conversation_id)
            memory_degraded = False

            recall_round_indices = self._search_recall_round_indices(
                conn,
                conversation_id,
                recall_query or "",
            )
            recalled_text = self._format_recalled_archive(conn, conversation_id, recall_round_indices)

        recent_messages = self._normalize_window_messages(recent_messages)
        transcript: List[Dict[str, Any]] = []

        transcript.append(self._build_config_block(model_name))
        transcript.append(self._build_context_block(notion_client))

        # Summary injection must stay between context block and recent-window messages.
        if summaries:
            numbered = "\n".join(f"{idx + 1}. {item}" for idx, item in enumerate(summaries))
            transcript.append(
                self._build_dialog_block(
                    "user",
                    f"以下是本次对话的历史摘要（从早到晚）：\n{numbered}",
                    notion_client,
                )
            )
            transcript.append(
                self._build_dialog_block(
                    "assistant",
                    "我已了解之前的对话背景。",
                    notion_client,
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

        for msg in recent_messages:
            transcript.append(self._build_dialog_block(msg["role"], msg["content"], notion_client))

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
                )
            )
            transcript.append(
                self._build_dialog_block(
                    "assistant",
                    "我已查阅相关历史记录，将综合作答。",
                    notion_client,
                )
            )

        transcript.append(self._build_dialog_block("user", new_prompt, notion_client))
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


async def compress_round_if_needed(manager: ConversationManager, conversation_id: str) -> None:
    """
    Move old turns out of sliding window, archive raw text, and summarize with LLM.

    Any failure is logged only and never raised to request path.
    """
    from app.summarizer import (
        SummarizerUnavailableError,
        is_summarizer_configured,
        summarize_turn,
    )

    try:
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
                    SELECT id, role, content, created_at
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
                    "assistant_content": str(oldest_assistant["content"]),
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
