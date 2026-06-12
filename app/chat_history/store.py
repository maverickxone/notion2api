"""SQLite-backed chat history storage and query helpers."""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from typing import Any

from app.chat_history.extractor import describe_thread_record, visible_message_role, visible_message_text

DDL = """
CREATE TABLE IF NOT EXISTS chat_threads (
  id TEXT PRIMARY KEY,
  title TEXT,
  created_time TEXT,
  last_edited_time TEXT,
  alive INTEGER,
  message_ids_json TEXT NOT NULL DEFAULT '[]',
  raw_json TEXT NOT NULL DEFAULT '{}',
  imported_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE TABLE IF NOT EXISTS chat_messages (
  id TEXT PRIMARY KEY,
  thread_id TEXT,
  role TEXT,
  text TEXT NOT NULL DEFAULT '',
  created_time TEXT,
  raw_json TEXT NOT NULL DEFAULT '{}',
  imported_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE VIRTUAL TABLE IF NOT EXISTS chat_messages_fts USING fts5(id UNINDEXED, thread_id UNINDEXED, role UNINDEXED, text, tokenize='unicode61');
"""


def get_default_chat_history_db_path() -> str:
    explicit = os.getenv("CHAT_HISTORY_DB_PATH")
    if explicit:
        return explicit
    base = os.getenv("DB_PATH", "./data/conversations.db")
    return os.path.join(os.path.dirname(os.path.abspath(base)), "chat_history.db")


def _quote_fts_phrase(query: str) -> str:
    return '"' + query.replace('"', '""') + '"'


def _preview(text: str | None, limit: int = 180) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _json_object(value: str | None) -> dict[str, Any]:
    try:
        decoded = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _id_text(value: Any) -> str | None:
    if isinstance(value, bool) or value is None or isinstance(value, (dict, list, tuple, set)):
        return None
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return text or None
    return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    if _is_scalar(value):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return str(value)


def _json_dumps(value: Any, fallback: Any) -> str:
    try:
        return json.dumps(value if value is not None else fallback, ensure_ascii=False, default=str)
    except TypeError:
        return json.dumps(fallback, ensure_ascii=False, default=str)


def _message_ids_json(value: Any) -> str:
    if not isinstance(value, list):
        return "[]"
    ids = [_id_text(item) for item in value]
    return json.dumps([item for item in ids if item], ensure_ascii=False)


def _clean_ids(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _id_text(value)
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _thread_timestamp_expr(alias: str = "t") -> str:
    return (
        f"COALESCE("
        f"NULLIF({alias}.last_edited_time,''),"
        f"NULLIF({alias}.created_time,''),"
        f"CAST(json_extract({alias}.raw_json, '$.updated_at') AS TEXT),"
        f"CAST(json_extract({alias}.raw_json, '$.updated_time') AS TEXT),"
        f"CAST(json_extract({alias}.raw_json, '$.last_edited_time') AS TEXT),"
        f"CAST(json_extract({alias}.raw_json, '$.created_at') AS TEXT),"
        f"CAST(json_extract({alias}.raw_json, '$.created_time') AS TEXT),"
        f"{alias}.imported_at"
        f")"
    )


def _time_sort_value(value: Any) -> tuple[int, str]:
    text = str(value or "").strip()
    if not text:
        return (0, "")
    if text.isdigit():
        return (int(text), text)
    try:
        from datetime import datetime

        normalized = text.replace("Z", "+00:00")
        return (int(datetime.fromisoformat(normalized).timestamp() * 1000), text)
    except (TypeError, ValueError, OverflowError):
        return (0, text)


def _display_message(message: dict[str, Any]) -> dict[str, Any] | None:
    raw = message.get("raw") if isinstance(message.get("raw"), dict) else {}
    text = visible_message_text(raw) if raw else str(message.get("text") or "").strip()
    if not text:
        return None
    role = visible_message_role(raw) if raw else None
    if not role:
        role = str(message.get("role") or "").strip()
    if not role:
        return None
    if role not in {"user", "assistant"}:
        if role == "text":
            role = "assistant"
        else:
            return None
    created_time = str(message.get("created_time") or "").strip()
    if not created_time and raw:
        created_time = _text(raw.get("createdAt") or raw.get("created_time") or raw.get("startedAt"))
    out = dict(message)
    out["role"] = role
    out["text"] = text
    out["created_time"] = created_time
    return out


def _visible_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    visible: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for message in messages:
        display = _display_message(message)
        if not display:
            continue
        dedupe_key = (str(display.get("role") or ""), " ".join(str(display.get("text") or "").split()))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        visible.append(display)
    return sorted(visible, key=lambda item: (_time_sort_value(item.get("created_time")), str(item.get("id") or "")))


def _process_steps(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    seen: set[str] = set()
    inference_step_ids: set[str] = set()
    for message in messages:
        raw_any = message.get("raw")
        raw = raw_any if isinstance(raw_any, dict) else {}
        if raw.get("type") == "agent-inference":
            inference_step_ids.add(str(raw.get("id")))

    for message in messages:
        raw_any = message.get("raw")
        raw = raw_any if isinstance(raw_any, dict) else {}
        raw_type = str(raw.get("type") or "").strip()
        label = ""
        detail = ""
        if raw_type == "agent-tool-result":
            if str(raw.get("agentStepId") or "") in inference_step_ids:
                continue
            label = str(raw.get("toolName") or raw.get("toolType") or "Tool result").strip()
            detail = str(raw.get("error") or raw.get("state") or "").strip()
        elif raw_type == "agent-inference":
            value_parts = raw.get("value")
            if not isinstance(value_parts, list):
                value_parts = []
            for part in value_parts:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "tool_use":
                    label = str(part.get("name") or "Tool use").strip()
                    break
        elif raw_type == "agent-search-query-generation":
            label = "Search query generation"
        if not label:
            continue
        key = f"{raw_type}:{label}:{detail}:{raw.get('id') or message.get('id')}"
        if key in seen:
            continue
        seen.add(key)
        created_time = str(message.get("created_time") or "").strip()
        if not created_time:
            created_time = _text(raw.get("createdAt") or raw.get("created_time") or raw.get("startedAt"))
        steps.append(
            {
                "id": str(raw.get("id") or message.get("id") or ""),
                "type": raw_type,
                "label": label,
                "detail": detail,
                "created_time": created_time,
            }
        )
    return sorted(steps, key=lambda item: (_time_sort_value(item.get("created_time")), str(item.get("id") or "")))


class ChatHistoryStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or get_default_chat_history_db_path()
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        with self._conn() as conn:
            conn.executescript(DDL)
            conn.commit()

    @contextlib.contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def upsert_bundle(self, bundle: dict[str, Any]) -> dict[str, int]:
        threads = bundle.get("threads", {})
        messages = bundle.get("messages", {})
        result = {
            "threads": len(threads),
            "messages": len(messages),
            "threads_inserted": 0,
            "threads_updated": 0,
            "messages_inserted": 0,
            "messages_updated": 0,
            "threads_skipped": 0,
            "messages_skipped": 0,
        }
        with self._conn() as conn:
            for t in threads.values():
                if not isinstance(t, dict):
                    result["threads_skipped"] += 1
                    continue
                thread_id = _id_text(t.get("id"))
                if not thread_id:
                    result["threads_skipped"] += 1
                    continue
                proposed = (
                    _text(t.get("title")),
                    _text(t.get("created_time")),
                    _text(t.get("last_edited_time") or t.get("updated_at")),
                    None if t.get("alive") is None else int(bool(t.get("alive"))),
                    _message_ids_json(t.get("message_ids")),
                    _json_dumps(t.get("raw"), {}),
                )
                existing = conn.execute(
                    "SELECT title,created_time,last_edited_time,alive,message_ids_json,raw_json FROM chat_threads WHERE id=?",
                    (thread_id,),
                ).fetchone()
                conn.execute(
                    """INSERT INTO chat_threads(id,title,created_time,last_edited_time,alive,message_ids_json,raw_json)
                    VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET title=excluded.title,last_edited_time=excluded.last_edited_time,alive=excluded.alive,message_ids_json=excluded.message_ids_json,raw_json=excluded.raw_json""",
                    (thread_id, *proposed),
                )
                if existing is None:
                    result["threads_inserted"] += 1
                elif tuple(existing) != proposed:
                    result["threads_updated"] += 1
            for m in messages.values():
                if not isinstance(m, dict):
                    result["messages_skipped"] += 1
                    continue
                message_id = _id_text(m.get("id"))
                if not message_id:
                    result["messages_skipped"] += 1
                    continue
                thread_id = _id_text(m.get("thread_id"))
                role = _text(m.get("role"))
                text = _text(m.get("text"))
                created_time = _text(m.get("created_time"))
                proposed = (
                    thread_id,
                    role,
                    text,
                    created_time,
                    _json_dumps(m.get("raw"), {}),
                )
                existing = conn.execute(
                    "SELECT thread_id,role,text,created_time,raw_json FROM chat_messages WHERE id=?",
                    (message_id,),
                ).fetchone()
                conn.execute(
                    """INSERT INTO chat_messages(id,thread_id,role,text,created_time,raw_json)
                    VALUES(?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET thread_id=excluded.thread_id,role=excluded.role,text=excluded.text,created_time=excluded.created_time,raw_json=excluded.raw_json""",
                    (message_id, *proposed),
                )
                conn.execute("DELETE FROM chat_messages_fts WHERE id=?", (message_id,))
                conn.execute("INSERT INTO chat_messages_fts(id,thread_id,role,text) VALUES(?,?,?,?)", (message_id, thread_id, role, text))
                if existing is None:
                    result["messages_inserted"] += 1
                elif tuple(existing) != proposed:
                    result["messages_updated"] += 1
            conn.commit()
        return result

    def existing_thread_ids(self, thread_ids: list[Any]) -> set[str]:
        ids = _clean_ids(thread_ids)
        if not ids:
            return set()
        existing: set[str] = set()
        with self._conn() as conn:
            for thread_id in ids:
                row = conn.execute("SELECT id FROM chat_threads WHERE id=?", (thread_id,)).fetchone()
                if row:
                    existing.add(str(row["id"]))
        return existing

    def delete_threads(self, thread_ids: list[Any]) -> dict[str, int]:
        ids = _clean_ids(thread_ids)
        result = {
            "requested": len(thread_ids) if isinstance(thread_ids, list) else 0,
            "valid_ids": len(ids),
            "threads_deleted": 0,
            "messages_deleted": 0,
            "fts_deleted": 0,
        }
        with self._conn() as conn:
            for thread_id in ids:
                message_rows = conn.execute(
                    "SELECT id FROM chat_messages WHERE thread_id=?",
                    (thread_id,),
                ).fetchall()
                for row in message_rows:
                    deleted = conn.execute(
                        "DELETE FROM chat_messages_fts WHERE id=?",
                        (row["id"],),
                    ).rowcount
                    if deleted and deleted > 0:
                        result["fts_deleted"] += deleted
                deleted_messages = conn.execute(
                    "DELETE FROM chat_messages WHERE thread_id=?",
                    (thread_id,),
                ).rowcount
                if deleted_messages and deleted_messages > 0:
                    result["messages_deleted"] += deleted_messages
                deleted_threads = conn.execute(
                    "DELETE FROM chat_threads WHERE id=?",
                    (thread_id,),
                ).rowcount
                if deleted_threads and deleted_threads > 0:
                    result["threads_deleted"] += deleted_threads
            conn.commit()
        return result

    def list_threads(self, limit: int = 50, offset: int = 0, include_inactive: bool = False) -> list[dict[str, Any]]:
        filters = [
            """(
              json_extract(t.raw_json, '$.type') IN ('workflow', 'markdown-chat')
              OR json_extract(t.raw_json, '$.title') IS NOT NULL
            )"""
        ]
        if not include_inactive:
            filters.append("COALESCE(t.alive,1) != 0")
        where = "WHERE " + " AND ".join(filters)
        order_expr = _thread_timestamp_expr("t")
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT
                  t.id,
                  t.title,
                  t.created_time,
                  t.last_edited_time,
                  {order_expr} AS updated_at,
                  t.alive,
                  COUNT(m.id) AS message_count,
                  MIN(m.created_time) AS first_message_time,
                  MAX(m.created_time) AS last_message_time,
                  (
                    SELECT m1.text FROM chat_messages m1
                    WHERE m1.thread_id=t.id
                    ORDER BY m1.created_time, m1.id LIMIT 1
                  ) AS first_message_text,
                  (
                    SELECT m2.text FROM chat_messages m2
                    WHERE m2.thread_id=t.id
                    ORDER BY m2.created_time DESC, m2.id DESC LIMIT 1
                  ) AS last_message_text
                FROM chat_threads t
                LEFT JOIN chat_messages m ON m.thread_id=t.id
                {where}
                GROUP BY t.id
                ORDER BY {order_expr} DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
            out: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                item["message_count"] = int(item.get("message_count") or 0)
                item["hydrated"] = item["message_count"] > 0
                item["first_message_preview"] = _preview(item.pop("first_message_text", ""))
                item["last_message_preview"] = _preview(item.pop("last_message_text", ""))
                out.append(item)
            return out

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            t = conn.execute("SELECT * FROM chat_threads WHERE id=?", (thread_id,)).fetchone()
            if not t:
                return None
            msgs = conn.execute("SELECT id,thread_id,role,text,created_time,raw_json FROM chat_messages WHERE thread_id=? ORDER BY created_time,id", (thread_id,)).fetchall()
        out = dict(t)
        out["message_ids"] = json.loads(out.pop("message_ids_json") or "[]")
        out["raw"] = _json_object(out.pop("raw_json") or "{}")
        messages: list[dict[str, Any]] = []
        for row in msgs:
            message = dict(row)
            message["raw"] = _json_object(message.pop("raw_json") or "{}")
            messages.append(message)
        out["messages"] = _visible_messages(messages)
        out["steps"] = _process_steps(messages)
        out["message_count"] = len(out["messages"])
        out["hydrated"] = out["message_count"] > 0
        out["first_message_preview"] = _preview(out["messages"][0].get("text") if out["messages"] else "")
        out["last_message_preview"] = _preview(out["messages"][-1].get("text") if out["messages"] else "")
        out["updated_at"] = out.get("last_edited_time") or out.get("created_time") or ""
        return out

    def debug_thread(self, thread_id: str) -> dict[str, Any]:
        thread = self.get_thread(thread_id)
        if not thread:
            return {"thread_exists": False, "message_count": 0, "raw_fields_seen": [], "known_message_fields_found": [], "sample": {}}
        return describe_thread_record(thread, thread.get("messages") or [])

    def search(self, query: str, limit: int = 25) -> list[dict[str, Any]]:
        query = str(query or "").strip()
        if not query:
            return []
        sql = "SELECT id,thread_id,role,snippet(chat_messages_fts,3,'[',']',' ... ',16) AS snippet FROM chat_messages_fts WHERE chat_messages_fts MATCH ? LIMIT ?"
        with self._conn() as conn:
            try:
                rows = conn.execute(sql, (query, limit)).fetchall()
            except sqlite3.OperationalError:
                try:
                    rows = conn.execute(sql, (_quote_fts_phrase(query), limit)).fetchall()
                except sqlite3.OperationalError as exc:
                    raise ValueError("Invalid chat-history search query") from exc
            return [dict(r) for r in rows]

    def thread_to_markdown(self, thread_id: str) -> str | None:
        thread = self.get_thread(thread_id)
        if not thread:
            return None
        lines = [f"# {thread.get('title') or thread.get('id')}", "", f"Thread ID: `{thread.get('id')}`", "", f"Messages: {thread.get('message_count', 0)}", ""]
        if not thread.get("messages"):
            lines += ["> This thread exists in the archive, but no message records are hydrated yet.", ""]
        for msg in thread.get("messages", []):
            lines += [f"## {str(msg.get('role') or 'message').title()}", "", str(msg.get("text") or ""), ""]
        return "\n".join(lines)
