import tempfile
import unittest
from pathlib import Path

from app.chat_history.store import ChatHistoryStore


class ChatHistoryBulkDeleteTests(unittest.TestCase):
    def test_existing_thread_ids_filters_unknown_and_non_scalar_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ChatHistoryStore(str(Path(tmp) / "chat_history.db"))
            store.upsert_bundle(
                {
                    "threads": {
                        "thread-1": {"id": "thread-1", "title": "First"},
                        "thread-2": {"id": "thread-2", "title": "Second"},
                    },
                    "messages": {},
                }
            )

            self.assertEqual(
                store.existing_thread_ids(["thread-1", "missing", {"bad": "id"}, "thread-2", "thread-1"]),
                {"thread-1", "thread-2"},
            )

    def test_delete_threads_removes_threads_messages_and_fts_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ChatHistoryStore(str(Path(tmp) / "chat_history.db"))
            store.upsert_bundle(
                {
                    "threads": {
                        "thread-1": {"id": "thread-1", "title": "First"},
                        "thread-2": {"id": "thread-2", "title": "Second"},
                    },
                    "messages": {
                        "msg-1": {"id": "msg-1", "thread_id": "thread-1", "role": "user", "text": "delete me"},
                        "msg-2": {"id": "msg-2", "thread_id": "thread-2", "role": "user", "text": "keep me"},
                    },
                }
            )

            result = store.delete_threads(["thread-1", "missing"])

            self.assertEqual(result["threads_deleted"], 1)
            self.assertEqual(result["messages_deleted"], 1)
            self.assertEqual(result["fts_deleted"], 1)
            self.assertIsNone(store.get_thread("thread-1"))
            remaining = store.get_thread("thread-2")
            self.assertIsNotNone(remaining)
            self.assertEqual(remaining["message_count"], 1)
            search_results = store.search("keep me")
            self.assertEqual(len(search_results), 1)
            self.assertEqual(search_results[0]["id"], "msg-2")
            self.assertEqual(search_results[0]["thread_id"], "thread-2")
            self.assertEqual(search_results[0]["role"], "user")
            self.assertIn(search_results[0]["snippet"], {"[keep me]", "[keep] [me]"})
            self.assertEqual(store.search("delete me"), [])

    def test_bulk_delete_ui_consumes_per_thread_results(self) -> None:
        ui_path = Path(__file__).resolve().parents[1] / "frontend" / "js" / "chat-history-browser.js"
        script = ui_path.read_text(encoding="utf-8")

        self.assertIn("result?.results?.success", script)
        self.assertIn("result?.results?.failed", script)
        self.assertIn("const successSet = new Set(successIds)", script)
        self.assertIn("browserState.threads = browserState.threads.filter(thread => !successSet.has(thread.id))", script)
        self.assertIn("browserState.selectedIds.add(failedItem.thread_id)", script)
        self.assertNotIn("const idSet = new Set(ids)", script)
        self.assertNotIn("filter(thread => !idSet.has(thread.id))", script)


if __name__ == "__main__":
    unittest.main()
