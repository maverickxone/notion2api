import json
import re
from typing import Any, Generator

import requests

from app.logger import logger

# 清理 Notion 内部语言/格式标记的正则集合
# 1. 完整的 <lang ...>...</lang> 块，替换时只保留内部文本（_strip_lang_tags 的兜底）
_RE_LANG_FULL = re.compile(r"<lang\b[^>]*>(.*?)</lang>", re.DOTALL)
# 2. 残留的 <lang ...> 孤立开标签（无对应内容或截断后留下的）
_RE_LANG_OPEN = re.compile(r"<lang\b[^>]*>")
# 3. 残留的 </lang> 闭标签
_RE_LANG_CLOSE = re.compile(r"</lang>")
# 4. Notion 语言属性残片：如 primary="zh-CN" 或 primary="zh" 或 primary="en"
#    可能带或不带引号，出现在文本开头或任意位置
_RE_PRIMARY_ATTR = re.compile(r'\bprimary="[a-zA-Z\-]{1,15}"\s*')
# 5. 剩余的 > 或 "> 残片（由截断的开标签留下的属性尾巴，如 -CN"> ）
_RE_ATTR_TAIL = re.compile(r'^-?[a-zA-Z]{0,4}"\s*>\s*')
_RE_PRIMARY_START = re.compile(r"\bprimary\b", re.IGNORECASE)

SEARCH_PATH_KEYWORDS = ("search", "web", "query", "source", "citation", "tool")
SEARCH_TYPE_KEYWORDS = ("search", "web", "tool", "citation")
LINE_DEBUG_KEYWORDS = ("queries", "category", "sources", "citations", "questions")
SEARCH_VALUE_KEYS = (
    "queries",
    "query",
    "questions",
    "category",
    "sources",
    "citations",
    "results",
    "url",
    "urls",
    "href",
    "search",
    "web",
    "tool",
    "toolname",
    "tooltype",
    "internal",
)

# ---- 段落分类：根据 Notion o:"a" patch 的 v.type 判断 ----
# 思考类 type 关键词
_THINKING_TYPES = ("agent-inference", "thinking", "reasoning", "inference")
# 工具/搜索类 type 关键词
_TOOL_TYPES = ("agent-tool-result", "tool_use", "tool", "search", "web", "citation")

# 段落角色常量
SEG_THINKING = "thinking"
SEG_TOOL = "tool"
SEG_CONTENT = "content"
SEG_META = "meta"

FINAL_STEP_PRIORITIES: dict[str, int] = {
    "markdown-chat": 400,
    "text": 350,
    "agent-inference": 300,
    "title": 50,
}


def _strip_lang_tags(text: str, in_tag: list[bool]) -> str:
    """Strip Notion internal <lang ...> tags, including cross-chunk broken tags."""
    result = []
    i = 0
    while i < len(text):
        if in_tag[0]:
            end = text.find(">", i)
            if end == -1:
                break
            in_tag[0] = False
            i = end + 1
            continue

        lang_start = text.find("<lang", i)
        close_start = text.find("</lang>", i)
        candidates = [(pos, typ) for pos, typ in [(lang_start, "open"), (close_start, "close")] if pos != -1]
        if not candidates:
            result.append(text[i:])
            break

        next_pos, typ = min(candidates, key=lambda x: x[0])
        result.append(text[i:next_pos])

        if typ == "close":
            i = next_pos + len("</lang>")
            continue

        end = text.find(">", next_pos)
        if end == -1:
            in_tag[0] = True
            break
        i = end + 1

    return "".join(result)


def _clean_notion_markup(text: str) -> str:
    """
    二次清理：移除 _strip_lang_tags 可能遗漏的 Notion 内部标记残片。

    处理以下场景：
    1. 完整 <lang ...>内容</lang>（_strip_lang_tags 兜底，保留内容只剥标签）
    2. 孤立的 </lang> 闭标签
    3. 孤立的 <lang ...> 开标签（内容已被 _strip_lang_tags 保留，只剩空壳）
    4. primary="zh-CN" 属性残片（跨块截断后留下的属性文本）
    5. 属性尾部残片，如 -CN"> 或 en"> 出现在文本开头
    """
    # 完整 <lang ...>内容</lang>：保留内容，剥掉标签
    text = _RE_LANG_FULL.sub(r"\1", text)
    # 移除孤立的 </lang>
    text = _RE_LANG_CLOSE.sub("", text)
    # 移除孤立的 <lang ...> 开标签
    text = _RE_LANG_OPEN.sub("", text)
    # 移除 primary="zh-CN" 之类的属性残片
    text = _RE_PRIMARY_ATTR.sub("", text)
    # 移除行首的属性尾巴残片，如 -CN"> 或 "> 或 en">
    text = _RE_ATTR_TAIL.sub("", text)
    return text



def _strip_primary_attr_fragments(text: str, in_primary_attr: list[bool]) -> str:
    """Strip fragmented `primary=...` attribute pieces leaked by stream chunks."""
    out: list[str] = []
    i = 0

    while i < len(text):
        if in_primary_attr[0]:
            ch = text[i]
            if ch in ">\r\n":
                in_primary_attr[0] = False
                i += 1
                continue
            if ch.isalpha() or ch in '-_="\'/: ':
                i += 1
                continue
            in_primary_attr[0] = False
            continue

        m = _RE_PRIMARY_START.search(text, i)
        if not m:
            out.append(text[i:])
            break

        start = m.start()
        out.append(text[i:start])

        j = m.end()
        while j < len(text) and text[j].isspace():
            j += 1

        if j < len(text) and text[j] not in ("=", "\"", "'"):
            out.append(text[start:m.end()])
            i = m.end()
            continue

        if j < len(text) and text[j] == "=":
            j += 1
            while j < len(text) and text[j].isspace():
                j += 1

        if j < len(text) and text[j] in ("\"", "'"):
            quote = text[j]
            j += 1
            while j < len(text) and (text[j].isalpha() or text[j] in "-_"):
                j += 1
            if j < len(text) and text[j] == quote:
                j += 1
        else:
            while j < len(text) and (text[j].isalpha() or text[j] in "-_"):
                j += 1

        while j < len(text) and text[j] in " />":
            j += 1

        if j >= len(text):
            in_primary_attr[0] = True
            break

        i = j

    return "".join(out)

def _normalize_path(patch: dict[str, Any]) -> str:
    for key in ("path", "p", "pointer", "at"):
        if key not in patch:
            continue
        raw = patch.get(key)
        if isinstance(raw, (list, tuple)):
            return "/".join(str(part) for part in raw)
        return str(raw)
    return ""


def _extract_segment_index(path: str) -> int | None:
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2 or parts[0] != "s":
        return None
    try:
        return int(parts[1])
    except Exception:
        return None


def _extract_value_index(path: str) -> int | None:
    """从 /s/N/value/M/... 形式的 path 中提取 value block 序号 M。"""
    parts = [p for p in path.split("/") if p]
    for i, part in enumerate(parts):
        if part == "value" and i + 1 < len(parts):
            try:
                return int(parts[i + 1])
            except ValueError:
                return None
    return None


def _extract_value_add_index(path: str) -> int | None:
    """
    从 `o:"a"` 的 `/s/N/value/<idx|->` 路径中提取新 value block 序号。
    仅匹配 value block 本身，不匹配 `/content` 等子路径。
    """
    parts = [p for p in path.split("/") if p]
    if len(parts) != 4:
        return None
    if parts[0] != "s" or parts[2] != "value":
        return None
    idx_raw = parts[3]
    if idx_raw == "-":
        return -1
    try:
        return int(idx_raw)
    except ValueError:
        return None


def _truncate_json(value: Any, max_len: int = 2000) -> str:
    try:
        raw = json.dumps(value, ensure_ascii=False)
    except Exception:
        raw = str(value)
    if len(raw) <= max_len:
        return raw
    return raw[:max_len] + "...(truncated)"


def _contains_search_keys(value: Any) -> bool:
    if isinstance(value, dict):
        for key, val in value.items():
            key_lower = str(key).lower()
            if any(token in key_lower for token in SEARCH_VALUE_KEYS):
                return True
            if _contains_search_keys(val):
                return True
        return False

    if isinstance(value, list):
        return any(_contains_search_keys(item) for item in value)

    return False


def _append_query(out: dict[str, Any], query: str) -> None:
    q = query.strip()
    if q:
        out.setdefault("queries", []).append(q)


def _append_source(out: dict[str, Any], source: dict[str, Any]) -> None:
    title = str(source.get("title", "") or "").strip()
    url = str(source.get("url", "") or "").strip()
    snippet = str(source.get("snippet", "") or "").strip()
    if not title and not url:
        return

    entry: dict[str, str] = {}
    if title:
        entry["title"] = title
    if url:
        entry["url"] = url
    if snippet:
        entry["snippet"] = snippet
    out.setdefault("sources", []).append(entry)


def _collect_search_metadata(value: Any, out: dict[str, Any]) -> None:
    if isinstance(value, dict):
        lowered = {str(k).lower(): v for k, v in value.items()}

        if isinstance(lowered.get("queries"), list):
            for item in lowered["queries"]:
                if isinstance(item, str):
                    _append_query(out, item)

        if isinstance(lowered.get("questions"), list):
            for item in lowered["questions"]:
                if isinstance(item, str):
                    _append_query(out, item)

        for single_query_key in ("query", "search_query", "searchquery"):
            query_val = lowered.get(single_query_key)
            if isinstance(query_val, str):
                _append_query(out, query_val)

        category = lowered.get("category")
        if isinstance(category, str) and category.strip():
            out.setdefault("categories", []).append(category.strip())

        for source_key in ("sources", "citations", "results"):
            source_items = lowered.get(source_key)
            if not isinstance(source_items, list):
                continue
            for item in source_items:
                if isinstance(item, dict):
                    _append_source(
                        out,
                        {
                            "title": item.get("title") or item.get("name") or item.get("sourceTitle") or "",
                            "url": item.get("url") or item.get("href") or item.get("link") or item.get("sourceUrl") or "",
                            "snippet": item.get("snippet") or item.get("summary") or item.get("description") or "",
                        },
                    )
                elif isinstance(item, str):
                    _append_source(out, {"title": item, "url": item})

        if isinstance(lowered.get("urls"), list):
            for url_item in lowered["urls"]:
                if isinstance(url_item, str) and url_item.strip():
                    _append_source(out, {"title": url_item.strip(), "url": url_item.strip()})

        url_val = lowered.get("url") or lowered.get("href") or lowered.get("link")
        if isinstance(url_val, str):
            _append_source(
                out,
                {
                    "title": lowered.get("title") or lowered.get("name") or url_val,
                    "url": url_val,
                    "snippet": lowered.get("snippet") or lowered.get("summary") or "",
                },
            )

        for nested in value.values():
            _collect_search_metadata(nested, out)
        return

    if isinstance(value, list):
        for item in value:
            _collect_search_metadata(item, out)


def _dedupe_search_data(data: dict[str, Any]) -> dict[str, Any]:
    queries = data.get("queries", [])
    sources = data.get("sources", [])
    categories = data.get("categories", [])

    deduped_queries: list[str] = []
    for query in queries:
        if query not in deduped_queries:
            deduped_queries.append(query)

    deduped_sources: list[dict[str, str]] = []
    seen_sources: set[tuple[str, str]] = set()
    for source in sources:
        title = str(source.get("title", "") or "")
        url = str(source.get("url", "") or "")
        key = (title, url)
        if key in seen_sources:
            continue
        seen_sources.add(key)
        deduped_sources.append(source)

    deduped_categories: list[str] = []
    for category in categories:
        if category not in deduped_categories:
            deduped_categories.append(category)

    out: dict[str, Any] = {}
    if deduped_queries:
        out["queries"] = deduped_queries
    if deduped_sources:
        out["sources"] = deduped_sources
    if deduped_categories:
        out["categories"] = deduped_categories
    return out


def _looks_like_search_patch(patch: dict[str, Any]) -> bool:
    patch_type = str(patch.get("type", "") or "").lower()
    patch_v = patch.get("v")
    nested_type = ""
    if isinstance(patch_v, dict):
        nested_type = str(patch_v.get("type", "") or "").lower()

    effective_type = patch_type or nested_type
    if effective_type and effective_type != "text" and any(token in effective_type for token in SEARCH_TYPE_KEYWORDS):
        return True

    path = _normalize_path(patch).lower()
    if any(token in path for token in SEARCH_PATH_KEYWORDS):
        return True

    if _contains_search_keys(patch.get("v")):
        return True

    return False


def _extract_search_data_from_patch(patch: dict[str, Any]) -> dict[str, Any]:
    extracted: dict[str, Any] = {"queries": [], "sources": [], "categories": []}
    _collect_search_metadata(patch, extracted)
    return _dedupe_search_data(extracted)


def _extract_text_from_patch(patch: dict[str, Any]) -> str:
    content = ""
    patch_op = patch.get("o")

    if patch_op == "a":
        patch_v = patch.get("v", {})
        if isinstance(patch_v, dict) and "value" in patch_v:
            val = patch_v["value"]
            if isinstance(val, list):
                text_parts = []
                for item in val:
                    if isinstance(item, dict) and isinstance(item.get("content"), str):
                        text_parts.append(str(item.get("content", "")))
                content = "".join(text_parts)

    elif patch_op == "x" and "v" in patch:
        content = patch["v"] if isinstance(patch["v"], str) else ""
    
    elif patch_op == "p" and "v" in patch:
        # 路径替换有时也携带文本内容
        path = _normalize_path(patch)
        if "/content" in path or "/text" in path:
            content = patch["v"] if isinstance(patch["v"], str) else ""

    return content


def _looks_like_search_json_fragment(text: str) -> bool:
    stripped = text.strip().lower()
    if not stripped.startswith("{"):
        return False

    if '"default"' in stripped and ('"questions"' in stripped or '"queries"' in stripped):
        return True

    return (
        '"queries"' in stripped
        or '"web"' in stripped
        or '"sources"' in stripped
        or '"citations"' in stripped
        or '"internal"' in stripped
        or '"questions"' in stripped
        or '"urls"' in stripped
    )


def _extract_search_data_from_json_text(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except Exception:
        return {}

    extracted: dict[str, Any] = {"queries": [], "sources": [], "categories": []}
    _collect_search_metadata(parsed, extracted)
    return _dedupe_search_data(extracted)


def _clean_extracted_text(text: str) -> str:
    if not text:
        return ""
    in_lang_tag = [False]
    in_primary_attr = [False]
    cleaned = _strip_lang_tags(text, in_lang_tag)
    cleaned = _strip_primary_attr_fragments(cleaned, in_primary_attr)
    cleaned = _clean_notion_markup(cleaned)
    return cleaned.strip()


def _extract_text_from_value_items(value_items: Any) -> str:
    if not isinstance(value_items, list):
        return ""

    parts: list[str] = []
    for item in value_items:
        if not isinstance(item, dict):
            continue
        if str(item.get("type", "") or "").lower() != "text":
            continue
        content = item.get("content")
        if isinstance(content, str) and content:
            parts.append(content)
    return "".join(parts)


def _extract_markdown_chat_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type", "") or "").lower()
            if item_type == "text" and isinstance(item.get("content"), str):
                parts.append(str(item.get("content", "")))
                continue
            nested_value = item.get("value")
            if nested_value is not None:
                nested_text = _extract_markdown_chat_text(nested_value)
                if nested_text:
                    parts.append(nested_text)
        return "".join(parts)
    if isinstance(value, dict):
        for key in ("value", "content", "text"):
            if key in value:
                nested_text = _extract_markdown_chat_text(value.get(key))
                if nested_text:
                    return nested_text
    return ""


def _extract_markdown_chat_patch_text(patch: dict[str, Any]) -> tuple[str, str] | None:
    patch_op = str(patch.get("o", "") or "")
    patch_v = patch.get("v")

    if (
        patch_op == "a"
        and isinstance(patch_v, dict)
        and str(patch_v.get("type", "") or "").lower() == "markdown-chat"
    ):
        cleaned = _clean_extracted_text(_extract_markdown_chat_text(patch_v.get("value")))
        if cleaned:
            return ("final_content", cleaned)

    return None


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _extract_final_content_from_record_map(data: dict[str, Any]) -> dict[str, Any] | None:
    record_map = data.get("recordMap")
    if not isinstance(record_map, dict):
        return None

    thread_messages = record_map.get("thread_message")
    if not isinstance(thread_messages, dict):
        return None

    candidates: list[dict[str, Any]] = []

    for msg_id, msg_data in thread_messages.items():
        if not isinstance(msg_data, dict):
            continue

        outer_value = msg_data.get("value")
        if not isinstance(outer_value, dict):
            continue
        inner_value = outer_value.get("value")
        if not isinstance(inner_value, dict):
            continue
        step = inner_value.get("step")
        if not isinstance(step, dict):
            continue

        step_type = str(step.get("type", "") or "").lower()
        content = ""

        if step_type == "markdown-chat":
            content = _extract_markdown_chat_text(step.get("value"))
        elif step_type == "agent-inference":
            content = _extract_text_from_value_items(step.get("value"))
        elif step_type in {"text", "title"}:
            raw_value = step.get("value")
            if isinstance(raw_value, str):
                content = raw_value

        cleaned = _clean_extracted_text(content)
        if cleaned:
            candidates.append(
                {
                    "message_id": str(msg_id),
                    "step_type": step_type or "unknown",
                    "priority": FINAL_STEP_PRIORITIES.get(step_type, 100),
                    "created_at": _safe_int(outer_value.get("created_time")),
                    "edited_at": _safe_int(outer_value.get("last_edited_time")),
                    "length": len(cleaned),
                    "text": cleaned,
                }
            )

    # 智能过滤：如果同时存在高优先级的 text/markdown-chat，则忽略 agent-inference
    # 这可以避免 Opus/GPT 模型将所有内容都放在 agent-inference 中导致的重复显示问题
    high_priority_types = {"text", "markdown-chat"}
    has_high_priority = any(c["step_type"] in high_priority_types for c in candidates)

    if has_high_priority:
        original_count = len(candidates)
        candidates = [c for c in candidates if c["step_type"] in high_priority_types]
        logger.debug(
            "Final content filtered",
            extra={
                "request_info": {
                    "event": "final_content_filtered",
                    "original_count": original_count,
                    "filtered_count": len(candidates),
                    "removed_types": [c["step_type"] for c in candidates if c["step_type"] not in high_priority_types],
                }
            },
        )

    if not candidates:
        return None

    best = max(
        candidates,
        key=lambda candidate: (
            int(candidate.get("priority", 0)),
            int(candidate.get("edited_at", 0)),
            int(candidate.get("created_at", 0)),
            int(candidate.get("length", 0)),
        ),
    )

    logger.debug(
        "Final content selected",
        extra={
            "request_info": {
                "event": "final_content_selected",
                "step_type": best.get("step_type", "unknown"),
                "priority": best.get("priority", 0),
                "length": len(best.get("text", "")),
                "message_id": best.get("message_id", ""),
            }
        },
    )

    return {
        "text": str(best.get("text", "") or ""),
        "source_type": str(best.get("step_type", "") or "unknown"),
        "source_message_id": str(best.get("message_id", "") or ""),
        "source_length": int(best.get("length", 0)),
    }


def _classify_segment_type(effective_type: str) -> str:
    """
    根据 o:"a" patch 的 type 字段判断新段落的角色。
    这是整个分类逻辑的唯一入口——只依赖 Notion 自己标注的 type。
    """
    if not effective_type:
        return SEG_CONTENT
    if effective_type == "text":
        return SEG_CONTENT
    if effective_type == "title":
        return SEG_META
    if any(kw in effective_type for kw in _THINKING_TYPES):
        return SEG_THINKING
    if any(kw in effective_type for kw in _TOOL_TYPES):
        return SEG_TOOL
    # 未知类型默认归正文，保证不丢内容
    return SEG_CONTENT


def parse_stream(response: requests.Response) -> Generator[dict[str, Any], None, None]:
    """
    解析 Notion NDJSON 流，输出三种结构化事件：
      - {"type": "content",  "text": "..."}   正文
      - {"type": "search",   "data": {...}}    搜索元数据
      - {"type": "thinking", "text": "..."}    思考过程

    核心机制——段落注册表（Segment Registry）：
      Notion 流中每个 o:"a" + path="/s/-" 的 patch 创建一个新的顶层段落，
      此时 v.type 明确标注了类型（agent-inference / agent-tool-result / text 等）。
      我们在此刻分配递增序号并记录类型。
      后续 o:"x" + path="/s/N/..." 只是往已有段落追加文本，查表即可知归属。
      不需要关键词猜测、不需要状态机。
    """
    in_lang_tag: list[bool] = [False]
    in_primary_attr: list[bool] = [False]
    search_json_buffer = ""
    search_json_depth = 0

    # ---- 段落注册表 ----
    segment_types: dict[int, str] = {}          # seg_index → SEG_THINKING / SEG_TOOL / SEG_CONTENT
    value_types: dict[tuple[int, int], str] = {}  # (seg_index, val_index) → 类型
    next_seg_id = 0                             # /s/- 追加时分配的递增序号
    next_val_id: dict[int, int] = {}            # seg_index → 下一个 value block 序号

    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="ignore")

        # 调试日志：含搜索关键词的行
        lowered_line = line.lower()
        if any(token in lowered_line for token in LINE_DEBUG_KEYWORDS):
            logger.debug(
                "NDJSON debug line",
                extra={"request_info": {"event": "notion_ndjson_debug_line", "line": line[:4000]}},
            )

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        data_type = str(data.get("type", "") or "").lower()

        if data_type == "record-map":
            final_payload = _extract_final_content_from_record_map(data)
            if final_payload and final_payload.get("text"):
                yield {"type": "final_content", **final_payload}
            continue

        if data_type == "markdown-chat":
            cleaned = _clean_extracted_text(_extract_markdown_chat_text(data.get("value")))
            if cleaned:
                yield {"type": "final_content", "text": cleaned, "source_type": "markdown-chat-event"}
            continue

        if data_type != "patch":
            continue

        patches = data.get("v", [])
        if not isinstance(patches, list):
            continue

        for patch in patches:
            if not isinstance(patch, dict):
                continue

            patch_op = str(patch.get("o", "") or "")
            patch_v = patch.get("v")
            patch_path = _normalize_path(patch)
            patch_seg = _extract_segment_index(patch_path)

            markdown_chat_patch = _extract_markdown_chat_patch_text(patch)
            if markdown_chat_patch is not None:
                event_type, event_text = markdown_chat_patch
                if event_type == "final_content":
                    yield {"type": event_type, "text": event_text, "source_type": "markdown-chat-patch"}
                else:
                    yield {"type": event_type, "text": event_text}
                continue

            # 提取 effective type（优先 patch.type，其次 v.type）
            patch_type = str(patch.get("type", "") or "").lower()
            nested_type = ""
            if isinstance(patch_v, dict):
                nested_type = str(patch_v.get("type", "") or "").lower()
            effective_type = patch_type or nested_type

            # ========== 段落注册：o:"a" 创建新段落 ==========
            path_stripped = patch_path.strip("/")
            is_new_toplevel_segment = (patch_op == "a" and path_stripped == "s/-")

            # 本 patch 的角色（注册时确定，用于当前 patch 的分类）
            patch_role: str | None = None

            if is_new_toplevel_segment:
                # 分配序号，记录类型
                seg_idx = next_seg_id
                next_seg_id += 1
                seg_class = _classify_segment_type(effective_type)
                segment_types[seg_idx] = seg_class
                # value[0] 继承段落类型
                value_types[(seg_idx, 0)] = seg_class
                next_val_id[seg_idx] = 1
                # 本 patch 后续处理使用此 seg_idx
                patch_seg = seg_idx
                patch_role = seg_class

                logger.debug(
                    "Segment registered",
                    extra={
                        "request_info": {
                            "event": "segment_registered",
                            "seg_idx": seg_idx,
                            "seg_class": seg_class,
                            "effective_type": effective_type,
                            "patch": _truncate_json(patch, 500),
                        }
                    },
                )
            elif patch_op == "a" and patch_seg is not None:
                # o:"a" 但 path 不是 /s/-（如 /s/2/value/-），属于已有段落的子追加
                if patch_seg >= next_seg_id:
                    next_seg_id = patch_seg + 1
                if patch_seg not in segment_types:
                    segment_types[patch_seg] = _classify_segment_type(effective_type)

                # 关键：检测 /s/N/value/<idx|-> 子块追加
                # 某些模型会发送显式索引（/value/1）而不是 /value/-。
                value_add_idx = _extract_value_add_index(patch_path)
                if value_add_idx is not None:
                    vid = next_val_id.get(patch_seg, 0) if value_add_idx < 0 else value_add_idx
                    next_val_id[patch_seg] = max(next_val_id.get(patch_seg, 0), vid + 1)
                    val_class = _classify_segment_type(effective_type)
                    value_types[(patch_seg, vid)] = val_class
                    patch_role = val_class
                    in_lang_tag[0] = False
                    in_primary_attr[0] = False

                    logger.debug(
                        "Value block registered",
                        extra={
                            "request_info": {
                                "event": "value_block_registered",
                                "seg_idx": patch_seg,
                                "val_idx": vid,
                                "val_class": val_class,
                                "effective_type": effective_type,
                            }
                        },
                    )

            # ========== 确定当前 patch 所属的角色 ==========
            if patch_role is not None:
                # 刚注册的 patch，直接用注册时的角色
                seg_owner = patch_role
            else:
                # o:"x" 追加文本：先查 value block 表，再查 segment 表
                val_idx = _extract_value_index(patch_path)
                if val_idx is not None and patch_seg is not None and (patch_seg, val_idx) in value_types:
                    seg_owner = value_types[(patch_seg, val_idx)]
                elif patch_seg is not None and patch_seg in segment_types:
                    seg_owner = segment_types[patch_seg]
                else:
                    seg_owner = SEG_CONTENT

            # ========== 搜索元数据（与段落角色无关，始终提取） ==========
            is_search_patch = _looks_like_search_patch(patch)
            if is_search_patch:
                search_data = _extract_search_data_from_patch(patch)
                if search_data:
                    yield {"type": "search", "data": search_data}

            # ========== 提取文本 ==========
            # /content replace patch can finalize broken lang attributes.
            # Reset state here to avoid swallowing following normal text.
            if patch_op == "p" and "/content" in patch_path and isinstance(patch_v, str):
                if ">" in patch_v or "\n" in patch_v or "\r" in patch_v or not patch_v.strip():
                    in_lang_tag[0] = False
                    in_primary_attr[0] = False

            content = _extract_text_from_patch(patch)
            if not content:
                continue

            cleaned = _strip_lang_tags(content, in_lang_tag)
            cleaned = _strip_primary_attr_fragments(cleaned, in_primary_attr)
            cleaned = _clean_notion_markup(cleaned)
            if not cleaned:
                continue

            # ========== 搜索 JSON 片段检测 ==========
            stripped = cleaned.strip()
            if stripped and (search_json_depth > 0 or _looks_like_search_json_fragment(stripped)):
                search_json_buffer += cleaned
                search_json_depth += stripped.count("{") - stripped.count("}")
                if search_json_depth <= 0:
                    sd = _extract_search_data_from_json_text(search_json_buffer)
                    if sd:
                        yield {"type": "search", "data": sd}
                    search_json_buffer = ""
                    search_json_depth = 0
                continue

            # 已被 search patch 处理的结构化数据不重复输出
            if is_search_patch:
                continue

            # ========== 按段落角色输出 ==========
            if seg_owner == SEG_META:
                continue
            if seg_owner in (SEG_THINKING, SEG_TOOL):
                yield {"type": "thinking", "text": cleaned}
            else:
                yield {"type": "content", "text": cleaned}




