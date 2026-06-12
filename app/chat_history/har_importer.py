from __future__ import annotations

import base64
import binascii
import json
from collections import Counter
from typing import Any
from urllib.parse import urlparse

from app.chat_history.extractor import merge_records_into_bundle


def _json_loads(text: str | None, encoding: str | None = None) -> Any:
    if not text:
        return None
    if encoding == "base64":
        try:
            text = base64.b64decode(text).decode("utf-8", errors="replace")
        except (binascii.Error, UnicodeDecodeError):
            return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _endpoint(entry: dict[str, Any]) -> str:
    try:
        path = urlparse(entry["request"]["url"]).path
    except (KeyError, TypeError, ValueError):
        return ""
    if not path.startswith("/api/v3/"):
        return ""
    return path.removeprefix("/api/v3")


def _request_json(entry: dict[str, Any]) -> Any:
    post_data = entry.get("request", {}).get("postData", {})
    return _json_loads(post_data.get("text"), post_data.get("encoding"))


def _response_json(entry: dict[str, Any]) -> Any:
    content = entry.get("response", {}).get("content", {})
    return _json_loads(content.get("text"), content.get("encoding"))


def import_chat_object(obj: Any) -> dict[str, Any]:
    bundle = {"threads": {}, "messages": {}, "endpoint_counts": {}}
    merge_records_into_bundle(bundle, obj)
    return bundle


def import_har_object(har: dict[str, Any]) -> dict[str, Any]:
    bundle = {"threads": {}, "messages": {}, "endpoint_counts": {}}
    counts: Counter[str] = Counter()
    entries = har.get("log", {}).get("entries", [])
    if not isinstance(entries, list):
        return bundle
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        endpoint = _endpoint(entry)
        if not endpoint:
            continue
        counts[endpoint] += 1
        merge_records_into_bundle(bundle, _request_json(entry))
        merge_records_into_bundle(bundle, _response_json(entry))
    bundle["endpoint_counts"] = dict(counts)
    return bundle
