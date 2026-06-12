import unittest

from app.chat_history.extractor import (
    describe_thread_record,
    extract_message_ids,
    merge_records_into_bundle,
    normalize_message,
    normalize_thread,
)


class ChatHistoryExtractorTests(unittest.TestCase):
    def test_extract_message_id_field_variants(self) -> None:
        value = {
            "messages": ["m1", {"id": "m2"}],
            "message_ids": ["m3"],
            "thread_message_ids": ["m4"],
            "messageIds": ["m5"],
            "threadMessageIds": ["m6"],
            "conversation_messages": [{"messageId": "m7"}],
            "conversationMessages": [{"uuid": "m8"}],
            "records": [{"pointer": {"id": "m9"}}],
            "items": [{"value": {"id": "m10"}}],
        }

        self.assertEqual(
            extract_message_ids(value),
            [
                "m1",
                "m2",
                "m3",
                "m4",
                "m5",
                "m6",
                "m7",
                "m8",
                "m9",
                "m10",
            ],
        )

    def test_normalize_message_field_variants(self) -> None:
        msg = normalize_message(
            None,
            {
                "messageId": "msg-1",
                "authorRole": "assistant",
                "threadId": "thread-1",
                "markdown": "hello from markdown",
            },
        )

        if msg is None:
            self.fail("normalize_message returned None")
        self.assertEqual(msg["id"], "msg-1")
        self.assertEqual(msg["role"], "assistant")
        self.assertEqual(msg["thread_id"], "thread-1")
        self.assertIn("hello from markdown", msg["text"])

    def test_merge_records_with_inline_conversation_messages(self) -> None:
        bundle = {"threads": {}, "messages": {}, "endpoint_counts": {}}
        merge_records_into_bundle(
            bundle,
            {
                "transcripts": [
                    {
                        "id": "thread-1",
                        "title": "Thread One",
                        "conversationMessages": [
                            {"messageId": "msg-1", "authorRole": "user", "body": "hello"},
                            {"messageId": "msg-2", "authorRole": "assistant", "content": "world"},
                        ],
                    }
                ]
            },
        )

        self.assertIn("thread-1", bundle["threads"])
        self.assertEqual(bundle["threads"]["thread-1"]["message_ids"], ["msg-1", "msg-2"])
        self.assertEqual(bundle["messages"]["msg-1"]["thread_id"], "thread-1")
        self.assertEqual(bundle["messages"]["msg-2"]["text"], "world")

    def test_describe_thread_record_includes_message_raw_fields(self) -> None:
        description = describe_thread_record(
            {"id": "thread-1", "raw": {"token_v2": "secret-token", "title": "Thread One"}, "messages": [{"id": "not-in-thread-sample"}]},
            [
                {
                    "id": "msg-1",
                    "thread_id": "thread-1",
                    "role": "assistant",
                    "text": "hello",
                    "raw": {"authorization": "Bearer secret", "content": "hello"},
                }
            ],
        )

        self.assertTrue(description["thread_exists"])
        self.assertEqual(description["message_count"], 1)
        self.assertIn("token_v2", description["raw_fields_seen"])
        self.assertIn("authorization", description["raw_fields_seen"])
        self.assertNotIn("messages", description["sample"]["thread"])
        self.assertEqual(description["sample"]["thread"]["raw"]["token_v2"], "[redacted]")
        self.assertEqual(description["sample"]["messages"][0]["raw"]["authorization"], "[redacted]")

    def test_normalize_message_uses_nested_data_title_as_text_fallback(self) -> None:
        msg = normalize_message(
            "msg-1",
            {
                "parent_id": "thread-1",
                "type": "workflow",
                "data": {
                    "icon": "/icons/chat_lightgray.svg",
                    "title": "Create Windows UI with hotkey",
                },
            },
        )

        if msg is None:
            self.fail("normalize_message returned None")
        self.assertEqual(msg["text"], "Create Windows UI with hotkey")

    def test_normalize_thread_preserves_numeric_notion_timestamps(self) -> None:
        thread = normalize_thread(
            None,
            {
                "id": "thread-1",
                "title": "Study plan creation",
                "created_at": 1779160000000,
                "updated_at": 1779160848204,
                "type": "workflow",
            },
        )

        if thread is None:
            self.fail("normalize_thread returned None")
        self.assertEqual(thread["created_time"], "1779160000000")
        self.assertEqual(thread["last_edited_time"], "1779160848204")

    def test_agent_inference_uses_visible_text_only(self) -> None:
        msg = normalize_message(
            "msg-1",
            {
                "type": "agent-inference",
                "thread_id": "thread-1",
                "startedAt": 1779160892191,
                "value": [
                    {"type": "thinking", "content": "internal reasoning"},
                    {"type": "text", "content": '<lang primary="en-US"/>'},
                    {"type": "text", "content": "Visible assistant answer"},
                    {"type": "tool_use", "name": "create-pages", "content": '{"pages":[]}'},
                ],
            },
        )

        if msg is None:
            self.fail("normalize_message returned None")
        self.assertEqual(msg["role"], "assistant")
        self.assertEqual(msg["text"], "Visible assistant answer")
        self.assertEqual(msg["created_time"], "1779160892191")

    def test_tool_result_records_are_not_visible_messages(self) -> None:
        self.assertIsNone(
            normalize_message(
                "tool-1",
                {
                    "type": "agent-tool-result",
                    "toolName": "create-pages",
                    "error": "Cannot create page",
                    "startedAt": 1779160892191,
                },
            )
        )


if __name__ == "__main__":
    unittest.main()
