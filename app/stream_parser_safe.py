"""Safe stream parser wrapper.

This module keeps Notion's parser output compatible with the local UI while
preventing full assistant answers from being displayed in the Thinking panel.
"""

from __future__ import annotations

from typing import Any, Generator

import requests

from app.stream_parser import parse_stream as _parse_stream


def parse_stream(response: requests.Response) -> Generator[dict[str, Any], None, None]:
    """Yield content/search/final events while suppressing streamed thinking.

    Some Notion responses put the answer body in an ``agent-inference`` segment.
    The lower-level parser historically maps that segment to ``thinking`` so the
    frontend renders a complete answer under a visible Thinking card. This wrapper
    buffers thinking chunks and only falls them back to normal content if no real
    content/final event arrives.
    """
    buffered_thinking: list[str] = []
    visible_content_seen = False

    for item in _parse_stream(response):
        if not isinstance(item, dict):
            yield item
            continue

        item_type = str(item.get("type", "") or "").lower()
        if item_type == "thinking":
            text = str(item.get("text", "") or "")
            if text:
                buffered_thinking.append(text)
            continue

        if item_type in {"content", "final_content"} and str(item.get("text", "") or "").strip():
            visible_content_seen = True

        yield item

    if not visible_content_seen and buffered_thinking:
        fallback_text = "".join(buffered_thinking).strip()
        if fallback_text:
            yield {"type": "content", "text": fallback_text}
