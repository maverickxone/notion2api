# Notion2API Architecture

## Project Overview / 项目概述

FastAPI reverse-engineered Notion Web API providing OpenAI-compatible interface.
核心特性：流式响应、三层记忆系统、多账号池、Thread ID 持久化。

Core features: Streaming responses, three-tier memory system, multi-account pool, Thread ID persistence.

---

## Architecture / 架构

```
app/
├── server.py              # FastAPI entry point / FastAPI 入口
├── api/chat.py            # Chat Completions API (core) / Chat Completions API（核心）
├── conversation.py        # Memory management: sliding window + compression pool + archive / 记忆管理：滑动窗口+压缩池+归档
├── notion_client.py       # Notion API client (reverse-engineered) / Notion API 客户端（逆向工程）
├── account_pool.py        # Multi-account load balancing / 多账号负载均衡
├── model_registry.py      # Model name mapping / 模型名称映射
└── schemas.py             # Pydantic data models / Pydantic 数据模型
```

---

## Three-Tier Memory System / 三层记忆系统

### Heavy Mode Only / 仅 Heavy 模式

1. **sliding_window table** (8 rounds, core) — user/assistant/thinking, UPSERT writes
   **sliding_window 表**（8轮，核心）— user/assistant/thinking，UPSERT 写入

2. **compressed_summaries table** (medium-term) — Auto-compressed when exceeding 8 rounds
   **compressed_summaries 表**（中期）— 超出8轮自动压缩

3. **full_archive table** (permanent) — Complete archive
   **full_archive 表**（永久）— 完整归档

### Memory Entry Points / 记忆读写入口

`conversation.py`:
- `get_sliding_window()` — Retrieve recent conversation
- `persist_round()` — Save a round of dialogue
- `get_transcript_payload()` — Build transcript for Notion API

---

## Key Behavioral Constraints / 关键行为约束（不得修改）

- **Thread ID Persistence**: Reuse same `thread_id` for entire conversation, stored in `conversations` table
  **Thread ID 持久化**：整个对话复用同一个 thread_id，存储在 conversations 表

- **is_partial_transcript=True**: Must set when reusing thread, otherwise AI loses memory
  **is_partial_transcript=True**：重用 thread 时必须设置，否则 AI 失忆

- **No Thread Deletion**: Auto-deletion logic removed, Notion homepage will accumulate conversations (acceptable)
  **不删除 Thread**：已移除自动删除逻辑，Notion 主页会累积对话（可接受）

- **Forced Sliding Window**: `get_transcript_payload()` no longer falls back to messages table
  **强制滑动窗口**：`get_transcript_payload()` 不再回退到 messages 表

---

## Supported Models / 支持的模型

| External Name / 对外名称 | Notion Internal Code / Notion 内部代号 |
|---|---|
| claude-opus4.6 | avocado-froyo-medium |
| claude-sonnet4.6 | almond-croissant-low |
| gemini-3.1pro | galette-medium-thinking |
| gpt-5.2 | oatmeal-cookie |
| gpt-5.4 | oval-kumquat-medium |

---

## Environment Variables / 环境变量

```env
NOTION_ACCOUNTS=[{"token_v2": "...", "space_id": "...", ...}]
API_KEY=optional
DB_PATH=./data/conversations.db
APP_MODE=standard  # lite / standard / heavy
```

---

## Git Commit Convention / Git 提交规范

`feat` / `fix` / `docs` / `refactor` / `perf` / `test`

---

## Current Status / 当前状态

- **Version**: v2.1.1, core functionality complete and stable
  **版本**：v2.1.1，核心功能完整可用

- **Modes Available**:
  **可用模式**：
  - **Lite**: Single-turn Q&A, no memory, no database
  - **Standard**: Full context, supports thinking & search, no database (recommended)
  - **Heavy**: Full session management with SQLite database

---

## API Endpoints / API 端点

### Main Endpoints
```
POST /v1/chat/completions    # OpenAI-compatible chat endpoint
GET  /v1/models               # List available models
GET  /health                  # Health check
GET  /                        # Web UI (frontend)
```

### Streaming Support
All chat responses support SSE (Server-Sent Events) streaming.

---

## Mode Comparison / 模式对比

| Feature | Lite | Standard | Heavy |
|---------|------|----------|-------|
| **Memory** | ❌ None | ✅ Client-managed | ✅ Server-managed |
| **Database** | ❌ Not needed | ❌ Not needed | ✅ SQLite |
| **Thinking Panel** | ❌ Not needed | ✅ Dedicated panel | ✅ Dedicated panel |
| **Search Results** | ❌ Not needed | ✅ Dedicated panel | ✅ Dedicated panel |
| **Rate Limit** | 30/min | 25/min | 20/min |
| **Use Case** | Simple Q&A | Short-mid conversations | Long-term conversations |

---

## Development Notes / 开发说明

### Thread ID Lifecycle
1. First request: `createThread=true` → New thread created
2. Subsequent requests: `createThread=false, isPartialTranscript=true` → Reuse existing thread
3. Thread never deleted → Accumulates in Notion homepage

### Search Feature
- Enabled via `emitAgentSearchExtractedResults: true` in debugOverrides
- Returns custom SSE event: `search_metadata` containing queries and sources
- Frontend displays in collapsible "Search" panel

### Thinking Feature
- Available for all models
- Returns via `delta.reasoning_content` in SSE stream
- Frontend displays in collapsible "Thinking" panel

---

## Security Considerations / 安全考虑

- **API_KEY**: Optional Bearer token authentication for `/v1/*` endpoints
- **Rate Limiting**: Per-IP rate limits (varies by mode)
- **CORS**: Enabled for all origins (configure for production)
- **SSL**: Use reverse proxy (nginx/caddy) for HTTPS in production

---

## Troubleshooting / 故障排查

### Common Issues

**AI loses memory in conversation**:
- Ensure `is_partial_transcript=True` when reusing threads
- Check thread_id consistency across requests

**Rate limit errors**:
- Reduce request frequency
- Configure multiple accounts in `NOTION_ACCOUNTS`

**Search results not showing**:
- Verify `emitAgentSearchExtractedResults: true` in payload
- Check frontend JavaScript console for SSE events

---

## License

MIT License
