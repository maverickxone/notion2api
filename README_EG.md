# Notion2API

> Notion AI → OpenAI-Compatible API

🌐 English | [中文](./README.md)

Notion2API reverse-engineers the Notion AI web interface and exposes it as a standard `/v1/chat/completions` endpoint, making it directly usable with Cherry Studio, Zotero, and any other OpenAI-compatible client.

---

## Features

- **OpenAI Compatible** — Standard `/v1/chat/completions` endpoint, streaming (SSE) and non-streaming
- **Three Operation Modes** — Lite / Standard / Heavy to fit different use cases
- **23 AI Models** — Claude (incl. Opus 5), GPT-6 Astra, GPT-5.x, Gemini, Kimi, Grok, DeepSeek, GLM, Fable
- **Thinking Panel** — Reasoning process display for all models
- **Search Panel** — Web search queries and source links
- **Multi-Account Pool** — Round-Robin load balancing with cooldown failover
- **Built-in Web UI** — Minimalist design, ambient animations, dark mode
- **Docker Ready** — One-command deployment

---

## Mode Comparison

| Feature | Lite | Standard | Heavy |
|---------|------|----------|-------|
| **Memory** | ❌ None | ✅ Client-managed | ✅ Server-managed |
| **Database** | ❌ | ❌ | ✅ SQLite |
| **Thinking Panel** | ❌ | ✅ | ✅ |
| **Search Panel** | ❌ | ✅ | ✅ |
| **Rate Limit** | 30/min | 25/min | 20/min |
| **Use Case** | Simple Q&A | Short–mid conversations | Long-term conversations |

> **Recommended**: `standard` — full context, no database required.  
> Switch by setting `APP_MODE` in `.env`.

---

## Quick Start

### 1. Get Notion Credentials

Choose the method that fits your situation:

#### Method A — F12 (if you already have a Notion web session)

1. Open https://www.notion.so/ai and log in
2. Press `F12` → **Application** tab → **Storage → Cookies → https://www.notion.so**
3. Find `token_v2` and copy its Value
4. Switch to the **Console** tab, paste and run `scripts/extract_notion_info.js`
5. The script outputs all required fields — paste the result into `accounts.json`

#### Method B — Browser-Assisted Login (no existing web session needed)

```bash
python login.py
```

This launches a temporary Chrome/Edge window, waits for you to sign in to Notion, then automatically extracts all credentials and writes them to `accounts.json` and `.env`.

```bash
python login.py --check          # verify a saved profile
python login.py --list           # list all saved profiles
python login.py --manual         # paste token_v2 manually if Chrome is unavailable
python login.py --profile work   # save under a named profile
```

Both methods write to `accounts.json`. Multiple accounts are supported — add more entries to the array to enable load balancing.

> ⚠️ `accounts.json` and `.env` contain credentials. Both are git-ignored — keep them private.

---

### 2. Configure `.env`

```bash
cp .env.example .env
```

At minimum, set:

```env
APP_MODE=standard   # lite / standard / heavy
```

If using **Heavy mode**, also add:

```env
SILICONFLOW_API_KEY=your_key_here
```

> Heavy mode uses SiliconFlow's LLM to compress long conversations. Register free at https://siliconflow.cn.

---

### 3. Start the Service

#### Docker (Recommended)

```bash
docker-compose build --no-cache && docker-compose up -d
```

`accounts.json` is mounted as a volume — update accounts without rebuilding:

```bash
# After editing accounts.json:
docker-compose restart
```

#### Local Run

```bash
pip install -r requirements.txt
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

Access the Web UI at `http://localhost:8000`.

---

## Supported Models

| Model Name | Description |
|---|---|
| `claude-sonnet4.6` | Best balance of speed and quality — **most recommended** |
| `claude-sonnet5` | Sonnet 5 |
| `claude-opus4.6` | Stronger reasoning, use sparingly |
| `claude-opus4.7` | Stronger reasoning |
| `claude-opus4.8` | Strong reasoning Claude |
| `claude-opus5` | Newest Claude Opus, strongest reasoning |
| `claude-haiku4.5` | Haiku 4.5 |
| `gpt-6-astra` | GPT-6 Astra |
| `gpt-5.6-sol` | GPT-5.6 Sol |
| `gpt-5.6-terra` | GPT-5.6 Terra |
| `gpt-5.6-luna` | GPT-5.6 Luna |
| `gpt-5.5` | GPT-5.5 |
| `gpt-5.4` | OpenAI model |
| `gemini-3.5flash` | Gemini 3.5 Flash |
| `gemini-3.1pro` | Google's strongest reasoning model |
| `gemini-3flash` | Gemini 3 Flash |
| `kimi-2.7` | Kimi K2.7 Code |
| `grok-4.3` | xAI Grok 4.3 |
| `spacexai-4.5` | SpaceXAI 4.5 |
| `grok-build0.1` | xAI Grok Build 0.1 |
| `deepseek-v4pro` | DeepSeek V4 Pro |
| `glm-5.2` | GLM 5.2 |
| `fable-5` | Fable 5 |

Full list via API: `GET http://localhost:8000/v1/models`

To add or sync a Notion AI model, see [`docs/ADD_MODEL.md`](./docs/ADD_MODEL.md) (checklist of files to update — no need to search the whole repo).

---

## API Usage

This project accepts any string as the API key (no format requirement).

### Python Example

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="any-string"
)

response = client.chat.completions.create(
    model="claude-sonnet4.6",
    messages=[{"role": "user", "content": "Hello"}],
    stream=True
)

for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")
```

### Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/v1/chat/completions` | POST | Chat completions (core) |
| `/v1/models` | GET | List available models |
| `/health` | GET | Health check (account pool status, uptime) |
| `/` | GET | Built-in Web UI |

---

## Web UI

Access `http://localhost:8000` for the built-in **Notion AI Studio** interface:

- **Conversation Management** — Create, rename, delete, star/bookmark
- **Model Selector** — Grouped by provider (Anthropic / OpenAI / Google / Moonshot / xAI / DeepSeek)
- **Thinking Panel** — Collapsible reasoning display with elapsed timer
- **Search Panel** — Collapsible web search queries and source links
- **Ambient Animations** — Weather effects: default / snow / rain / sunny / night
- **Theme** — Light / dark mode toggle
- **Responsive** — Mobile-friendly sidebar

> Thinking and Search panels require `standard` or `heavy` mode.

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `NOTION_ACCOUNTS` | Notion credentials JSON array | **Required** |
| `APP_MODE` | `lite` / `standard` / `heavy` | `heavy` |
| `API_KEY` | Bearer token for client auth | *(none)* |
| `DB_PATH` | SQLite database path | `./data/conversations.db` |
| `HOST` | Bind address | `0.0.0.0` |
| `PORT` | Service port | `8000` |
| `HOST_PORT` | Docker host port | `8000` |
| `ALLOWED_ORIGINS` | CORS allowed origins | `*` |
| `SILICONFLOW_API_KEY` | Required for Heavy mode compression | *(none)* |
| `DISABLE_RATE_LIMIT` | Disable per-IP rate limiting | `false` |
| `NOTION_CLIENT_VERSION` | Override Notion client version header | `23.13.20260228.0625` |
| `NOTION_URL` | Notion site base URL (mirror/proxy) | `https://www.notion.so` |
| `NOTION_DOMAIN` | Cookie domain for login.py | `www.notion.so` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `TZ` | Timezone | `Asia/Shanghai` |

---

## Docker Reference

```bash
# Start
docker-compose up -d

# View logs
docker-compose logs -f --tail=50

# Restart (e.g. after updating accounts.json)
docker-compose restart

# Update code and redeploy
git pull && docker-compose down && docker-compose build --no-cache && docker-compose up -d

# Stop
docker-compose down
```

### Nginx Reverse Proxy (optional)

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 300s;
}
```

---

## FAQ

**Thinking panel not showing?**  
Use `APP_MODE=standard` or `heavy`. Lite mode does not support Thinking or Search panels.

**How do I switch modes?**  
Edit `APP_MODE` in `.env`, then restart: `docker-compose restart`

**How do I add multiple accounts?**  
Edit `accounts.json` as an array — accounts are load-balanced automatically:
```json
[
  {"token_v2": "token1", "space_id": "...", "user_id": "...", "space_view_id": "...", "user_name": "...", "user_email": "..."},
  {"token_v2": "token2", "space_id": "...", "user_id": "...", "space_view_id": "...", "user_name": "...", "user_email": "..."}
]
```

**Getting 429 or Notion AI suspended?**  
Notion may throttle workspaces with unusual request patterns. Adding multiple accounts helps distribute load. Business Trial workspaces are especially prone to this.

**Token expired?**  
Re-run `python login.py` or repeat the F12 steps to refresh credentials.

---

## Compatibility

> Due to Notion's own AI latency, expect ~3 seconds from request to first token.

| Client | Status | Notes |
|---|---|---|
| Cherry Studio | ✅ Full support | Recommended |
| Zotero Translation | ✅ Full support | Slightly slow; sonnet model most accurate |
| Immersive Translate | ⚠️ Not recommended | High latency |
| Claude Code | ❌ Not supported | Uses Anthropic native API format |

---

## License

MIT License

---

If this project helps you, please give it a Star ⭐

*Built with assistance from Claude Code.*
