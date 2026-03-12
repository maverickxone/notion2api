# Notion2API

> Notion AI to OpenAI-Compatible API Wrapper

🌐 English | [中文](./README.md)

Notion2API wraps Notion AI as an OpenAI-compatible API, supporting direct use with Cherry Studio, Zotero, and other third-party clients, as well as existing frontend pages.

## Features

- **Three Operation Modes** - Lite/Standard/Heavy to meet different needs
- **OpenAI Compatible** - Standard `/v1/chat/completions` endpoint
- **Streaming Response** - SSE real-time output support
- **Thinking Panel** - Reasoning process display for all models
- **Search Feature** - Web search results display
- **Account Pool** - Multi-account load balancing and failover
- **Docker Deployment** - Ready-to-use containerized solution

---

## Mode Comparison

| Feature | Lite | Standard | Heavy |
|---------|------|----------|-------|
| **Memory** | ❌ None | ✅ Client-managed | ✅ Server-managed |
| **Database** | ❌ Not needed | ❌ Not needed | ✅ SQLite |
| **Thinking** | ❌ Not needed | ✅ Dedicated panel | ✅ Dedicated panel |
| **Search Results** | ❌ Not needed | ✅ Dedicated panel | ✅ Dedicated panel |
| **Rate Limit** | 30/min | 25/min | 20/min |
| **Use Case** | Simple Q&A | Short-mid conversations | Long-term conversations |

To switch modes: change the `APP_MODE` variable in `.env`.

---

## Quick Start

### 1. Get Notion Credentials

Open https://www.notion.so/ai and log in, then press `F12` to open DevTools:

**Step 1: Get token_v2**
1. Switch to the **Application** tab
2. Expand **Storage → Cookies → https://www.notion.so** on the left
3. Find `token_v2` and copy its Value

**Step 2: Get other information**
1. Switch to the **Console** tab
2. Copy and paste the code from `scripts/extract_notion_info.js`, then press Enter
3. The script will automatically retrieve `space_id`, `user_id`, and 5 other fields
4. Copy the output, replace `YOUR_TOKEN_V2_HERE` with the token_v2 from Step 1
5. Paste into the `.env` file

### 2. Configure Environment Variables

```bash
# Copy example config
cp .env.example .env

# Edit .env and fill in your credentials
NOTION_ACCOUNTS='[{"token_v2":"your_token","space_id":"your_space","user_id":"your_uid","space_view_id":"your_view","user_name":"your_name","user_email":"your_email"}]'
APP_MODE=standard  # lite / standard / heavy
```

**⚠️ If using Heavy mode**:

Heavy mode requires `SILICONFLOW_API_KEY` (for conversation summary compression):
1. Visit https://siliconflow.cn to register an account (free)
2. Get your API Key
3. Add it to `.env`:
   ```bash
   SILICONFLOW_API_KEY=your_api_key_here
   APP_MODE=heavy
   ```

### 3. Start the Service

#### Docker Deployment (Recommended)

```bash
docker-compose up -d
# Access http://localhost:8000
```

#### Local Run

```bash
pip install -r requirements.txt
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

---

## Supported Models

| Model Name | Description |
|---|---|
| `claude-sonnet4.6` | Best balance of performance and speed! (**Most recommended**, most optimized, most reliable) |
| `claude-opus4.6` | Stronger reasoning, but not recommended for frequent use |
| `gemini-3.1pro` | Google model, currently suspended officially but **still accessible here**, no web search support |
| `gpt-5.2` / `gpt-5.4` | Latest OpenAI models, also great |

View full list: `GET http://localhost:8000/v1/models`

---

## API Usage
This project supports custom API keys with no format requirements.

### Python Example

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="optional_api_key"
)

response = client.chat.completions.create(
    model="claude-sonnet4.6",
    messages=[{"role": "user", "content": "Hello"}],
    stream=True
)

for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")
```

---

## Web UI
(Custom design inspired by Claude style, supports Standard and Heavy modes)

Access `http://localhost:8000` to use the built-in Web UI:

- **Main Content Area** - Displays AI responses
- **Thinking Panel** - Shows reasoning process (collapsible)
- **Search Panel** - Shows search sources (collapsible)
- **Star Feature** - Bookmark valuable conversations to the top

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_MODE` | Operation mode: lite/standard/heavy | `heavy` |
| `NOTION_ACCOUNTS` | Notion credentials JSON array | Required |
| `API_KEY` | Client authentication key | Optional (recommended) |
| `DB_PATH` | SQLite database path | `./data/conversations.db` |
| `HOST_PORT` | Host port | `8000` |
| `SILICONFLOW_API_KEY` | Required for Heavy mode, used for early conversation summary compression | Optional |

---

## Docker Deployment

### Using docker-compose (Recommended)

```bash
# 1. Configure .env file
cp .env.example .env

# 2. Start service
docker-compose up -d

# 3. View logs
docker-compose logs -f

# 4. Stop service
docker-compose down
```

### Custom Port

Modify the `HOST_PORT` variable in `.env`:
```bash
HOST_PORT=8080  # Use port 8080
```

---

## FAQ

### 1. Thinking panel not showing?

Make sure you are using `APP_MODE=standard` or `heavy`. Lite mode does not support Thinking.

### 2. How to switch modes?

Modify `APP_MODE` in `.env`, then restart the service:
```bash
APP_MODE=standard  # Switch to standard
docker-compose restart
```

### 3. How to configure multiple accounts?
(Multiple accounts improve stability, Beta version)

`NOTION_ACCOUNTS` supports array format:
```json
[
  {"token_v2":"token1","space_id":"space1",...},
  {"token_v2":"token2","space_id":"space2",...}
]
```

---

## Compatibility Test
(Note: Due to Notion's own AI call rate, there is usually a ~3 second delay from sending a query to receiving an answer. Clients with high latency requirements, such as Immersive Translate, are not recommended.)

| Client | Status | Notes |
|--------|--------|-------|
| Cherry Studio | ✅ Full support | Recommended |
| Zotero Translation | ✅ Full support | Slightly slow, but sonnet model is accurate |
| Immersive Translate | Not recommended | Very slow |

---

## License

MIT License

---

## Star History

If this project helps you, please give it a Star ⭐

## Notes
This project was built with assistance from Claude Code and Codex.

**Heavy Mode Details**:
- Sliding window: retains the most recent **8 rounds** of conversation (16 messages) by default
- Summary compression: content beyond the window is automatically compressed into a summary
- Full archive: all history is permanently stored in the SQLite database

**Future Improvements**:
- If you need a custom sliding window size (e.g., 10 or 20 rounds), feel free to submit an Issue
- We will add environment variable configuration options based on demand

Issues and suggestions are welcome!
