"""
Stream regression checks for protocol compatibility and thinking/content integrity.

Run:
    .\\.venv\\Scripts\\python.exe test_stream_regression.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

from app.config import API_KEY
from app.server import app


@dataclass
class StreamStats:
    status_code: int
    custom_types: list[str]
    content_chunks: int
    reasoning_chunks: int


class FakeUpstreamClient:
    def __init__(self) -> None:
        self.user_id = "fake-user"
        self.space_id = "fake-space"
        self.space_view_id = "fake-view"
        self.user_name = "fake-name"
        self.user_email = "fake@example.com"
        self.account_key = "fake-account"

    def stream_response(self, transcript: list[dict[str, Any]]):  # noqa: ARG002
        yield {
            "type": "search",
            "data": {
                "queries": ["what is 2+2"],
                "sources": [{"title": "Example", "url": "https://example.com"}],
            },
        }
        yield {"type": "thinking", "text": "Reasoning: simple arithmetic. "}
        yield {"type": "content", "text": "2 + 2 = 4."}
        yield {
            "type": "final_content",
            "text": "2 + 2 = 4.",
            "source_type": "text",
            "source_length": 10,
        }


class FakePool:
    def __init__(self) -> None:
        self._client = FakeUpstreamClient()
        self.clients = [self._client]

    def get_client(self) -> FakeUpstreamClient:
        return self._client

    def mark_failed(self, client: FakeUpstreamClient, cooldown_seconds: int = 60) -> None:  # noqa: ARG002
        return


def _collect_stream_stats(web_mode: bool) -> StreamStats:
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    if web_mode:
        headers["X-Client-Type"] = "Web"

    payload = {
        "model": "claude-sonnet4.6",
        "messages": [{"role": "user", "content": "What is 2+2?"}],
        "stream": True,
    }

    custom_types: list[str] = []
    content_chunks = 0
    reasoning_chunks = 0

    with TestClient(app) as client:
        client.app.state.account_pool = FakePool()
        with client.stream("POST", "/v1/chat/completions", headers=headers, json=payload) as resp:
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else str(raw_line)
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    continue

                chunk = json.loads(data)
                custom_type = chunk.get("type")
                if isinstance(custom_type, str):
                    custom_types.append(custom_type)

                choices = chunk.get("choices")
                if not isinstance(choices, list) or not choices:
                    continue
                delta = choices[0].get("delta", {})
                if isinstance(delta.get("content"), str) and delta.get("content"):
                    content_chunks += 1
                if isinstance(delta.get("reasoning_content"), str) and delta.get("reasoning_content"):
                    reasoning_chunks += 1

            return StreamStats(
                status_code=resp.status_code,
                custom_types=custom_types,
                content_chunks=content_chunks,
                reasoning_chunks=reasoning_chunks,
            )


def main() -> None:
    non_web = _collect_stream_stats(web_mode=False)
    web = _collect_stream_stats(web_mode=True)

    assert non_web.status_code == 200, f"non-web status={non_web.status_code}"
    assert web.status_code == 200, f"web status={web.status_code}"

    assert non_web.custom_types == [], f"non-web should not emit custom types: {non_web.custom_types}"
    assert "search_metadata" in web.custom_types, f"web should emit search_metadata: {web.custom_types}"

    assert non_web.content_chunks > 0, "non-web content chunk missing"
    assert non_web.reasoning_chunks > 0, "non-web reasoning chunk missing"
    assert web.content_chunks > 0, "web content chunk missing"
    assert web.reasoning_chunks > 0, "web reasoning chunk missing"

    print("PASS non-web", non_web)
    print("PASS web", web)


if __name__ == "__main__":
    main()
