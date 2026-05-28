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
    yielded_content_parts: list[str] = []
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

        if item_type in {"content", "final_content"}:
            text = str(item.get("text", "") or "")
            if text.strip():
                visible_content_seen = True
                yielded_content_parts.append(text)

        yield item

    if buffered_thinking:
        thinking_text = "".join(buffered_thinking).strip()
        if thinking_text:
            yielded_text = "".join(yielded_content_parts).strip()
            if not yielded_text:
                yield {"type": "content", "text": thinking_text}
            else:
                # Normalize whitespace and lowercase to compare content
                norm_thinking = " ".join(thinking_text.split()).lower()
                norm_yielded = " ".join(yielded_text.split()).lower()
                
                is_duplicate = False
                if norm_thinking in norm_yielded:
                    is_duplicate = True
                else:
                    from difflib import SequenceMatcher
                    ratio = SequenceMatcher(None, norm_thinking, norm_yielded).ratio()
                    if ratio > 0.75:
                        is_duplicate = True
                
                if not is_duplicate:
                    # Append unique thinking text if it is not a duplication of already yielded content
                    yield {"type": "content", "text": "\n\n" + thinking_text}
