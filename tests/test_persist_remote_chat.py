import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.server import app
from app.config import API_KEY
from app.schemas import ChatCompletionRequest
from app.notion_client import NotionOpusAPI

class PersistRemoteChatTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.__enter__()
        self.auth_headers = {}
        if API_KEY:
            self.auth_headers = {"Authorization": f"Bearer {API_KEY}"}

    def tearDown(self):
        try:
            self.client.__exit__(None, None, None)
        except Exception:
            pass

    def test_schema_accepts_metadata(self):
        """Verify ChatCompletionRequest parses and validates metadata field."""
        data = {
            "model": "gpt-5.5",
            "messages": [{"role": "user", "content": "hello"}],
            "metadata": {
                "persist_remote_chat": True,
                "some_other_flag": "test"
            }
        }
        req = ChatCompletionRequest(**data)
        self.assertIsNotNone(req.metadata)
        self.assertEqual(req.metadata.get("persist_remote_chat"), True)
        self.assertEqual(req.metadata.get("some_other_flag"), "test")

    def test_stream_response_persistence_override_true(self):
        """Verify stream_response overrides settings to persist when persist_remote_chat=True."""
        client_mock = NotionOpusAPI({"user_id": "u1", "space_id": "s1", "token_v2": "t1"})
        
        # Patch dependencies that require network/cookies to avoid network calls
        with patch.object(client_mock, "_to_notion_transcript", return_value=[]), \
             patch.object(client_mock, "_resolve_thread_type", return_value="markdown-chat"), \
             patch.object(client_mock, "_resolve_request_profile", return_value={"precreate_thread": True, "create_thread": True, "is_partial_transcript": False, "include_debug_overrides": False}), \
             patch.object(client_mock, "_build_cookie_header", return_value=""), \
             patch.object(client_mock, "_scraper", MagicMock()) as mock_scraper:
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            def mock_parse_stream(res):
                yield {"type": "content", "text": "hello"}

            with patch("app.notion_client.parse_stream", side_effect=mock_parse_stream):
                mock_scraper.post.return_value = mock_response
                
                # Retrieve the stream generator with persist_remote_chat=True
                gen = client_mock.stream_response(
                    transcript=[{"role": "user", "content": "hi"}],
                    thread_id="test-thread-id",
                    persist_remote_chat=True
                )
                
                # Execute the generator to run downstream stream handling logic
                list(gen)
                
                # Check that delete_thread was NOT called since persist_remote_chat is True (overriding default delete_after_stream)
                with patch.object(client_mock, "delete_thread") as mock_delete:
                    # Execute again
                    gen = client_mock.stream_response(
                        transcript=[{"role": "user", "content": "hi"}],
                        thread_id="test-thread-id",
                        persist_remote_chat=True
                    )
                    list(gen)
                    mock_delete.assert_not_called()

    def test_stream_response_persistence_override_false(self):
        """Verify stream_response overrides settings to delete when persist_remote_chat=False."""
        client_mock = NotionOpusAPI({"user_id": "u1", "space_id": "s1", "token_v2": "t1"})
        
        # Patch dependencies
        with patch.object(client_mock, "_to_notion_transcript", return_value=[]), \
             patch.object(client_mock, "_resolve_thread_type", return_value="markdown-chat"), \
             patch.object(client_mock, "_resolve_request_profile", return_value={"precreate_thread": True, "create_thread": True, "is_partial_transcript": False, "include_debug_overrides": False}), \
             patch.object(client_mock, "_build_cookie_header", return_value=""), \
             patch.object(client_mock, "delete_thread") as mock_delete, \
             patch.object(client_mock, "_scraper", MagicMock()) as mock_scraper:
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            def mock_parse_stream(res):
                yield {"type": "content", "text": "hello"}

            with patch("app.notion_client.parse_stream", side_effect=mock_parse_stream):
                mock_scraper.post.return_value = mock_response
                
                gen = client_mock.stream_response(
                    transcript=[{"role": "user", "content": "hi"}],
                    thread_id="test-thread-id",
                    persist_remote_chat=False
                )
                list(gen)
                # Should delete thread after stream since persist_remote_chat is False
                mock_delete.assert_called_once_with("test-thread-id")

    def test_route_forwards_persist_remote_chat(self):
        """Verify completions route extracts metadata and forwards persist_remote_chat to stream_response."""
        payload = {
            "model": "claude-sonnet4.6",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": False,
            "metadata": {
                "persist_remote_chat": True
            }
        }
        
        with patch("app.notion_client.NotionOpusAPI.stream_response") as mock_stream:
            mock_stream.return_value = iter([{"type": "final_content", "text": "ok"}])
            resp = self.client.post("/v1/chat/completions", json=payload, headers=self.auth_headers)
            
            self.assertIn(resp.status_code, (200, 503))
            mock_stream.assert_called()
            # Verify it was called with persist_remote_chat=True
            _, kwargs = mock_stream.call_args
            self.assertEqual(kwargs.get("persist_remote_chat"), True)

    def test_stream_parser_safe_yields_unique_thinking(self):
        """Verify stream_parser_safe appends thinking content if it is not duplicate of content."""
        from app.stream_parser_safe import parse_stream
        
        # Mock Response whose iterator yields dicts like _parse_stream would
        mock_response = MagicMock()
        
        # Test case: thinking is unique answer, content is just citation
        mock_items = [
            {"type": "thinking", "text": "This is Kimi's actual detailed answer."},
            {"type": "content", "text": "[1] Sources."}
        ]
        
        with patch("app.stream_parser_safe._parse_stream", return_value=iter(mock_items)):
            res = list(parse_stream(mock_response))
            
            # Should yield both the citation and the unique thinking answer (appended)
            event_types = [item["type"] for item in res]
            self.assertIn("content", event_types)
            
            texts = [item.get("text", "") for item in res if item["type"] == "content"]
            self.assertIn("[1] Sources.", texts)
            self.assertIn("\n\nThis is Kimi's actual detailed answer.", texts)

    def test_stream_parser_safe_suppresses_duplicate_thinking(self):
        """Verify stream_parser_safe suppresses thinking if it is identical to yielded content."""
        from app.stream_parser_safe import parse_stream
        
        mock_response = MagicMock()
        
        # Test case: thinking is duplicated in the content
        mock_items = [
            {"type": "thinking", "text": "This is identical answer."},
            {"type": "content", "text": "This is identical answer."}
        ]
        
        with patch("app.stream_parser_safe._parse_stream", return_value=iter(mock_items)):
            res = list(parse_stream(mock_response))
            
            # Should ONLY yield one content block (the duplicate thinking should be suppressed)
            texts = [item.get("text", "") for item in res if item["type"] == "content"]
            self.assertEqual(len(texts), 1)
            self.assertEqual(texts[0], "This is identical answer.")

if __name__ == '__main__':
    unittest.main()
