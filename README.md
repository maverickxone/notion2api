# Notion2API

> Notion AI → OpenAI 兼容 API

🌐 [English](./README_EG.md) | 中文

Notion2API 对 Notion AI 网页接口进行逆向工程，将其封装为标准的 `/v1/chat/completions` 端点，可直接用于 Cherry Studio、Zotero 以及任何兼容 OpenAI 的客户端。

2026.09.06：模型列表已同步至 23 个，新增 GPT-6 Astra（`orlando-quinn`）。

---

## 特性

- **OpenAI 兼容** — 标准 `/v1/chat/completions` 端点，支持流式（SSE）和非流式响应
- **三种运行模式** — Lite / Standard / Heavy，满足不同使用场景
- **23 个 AI 模型** — Claude（含 Opus 5）、GPT-6 Astra、GPT-5.x、Gemini、Kimi、Grok、DeepSeek、GLM、Fable
- **Thinking 面板** — 所有模型均支持推理过程展示
- **Search 面板** — 展示 Web 搜索查询和来源链接
- **多账号池** — Round-Robin 负载均衡，带冷却故障转移
- **内置 Web UI** — 极简设计，环境粒子动画，深色模式
- **Docker 一键部署**

---

## 三种模式对比

| 特性 | Lite | Standard | Heavy |
|------|------|----------|-------|
| **记忆** | ❌ 无 | ✅ 客户端管理 | ✅ 服务端管理 |
| **数据库** | ❌ | ❌ | ✅ SQLite |
| **Thinking 面板** | ❌ | ✅ | ✅ |
| **Search 面板** | ❌ | ✅ | ✅ |
| **速率限制** | 30/分钟 | 25/分钟 | 20/分钟 |
| **适用场景** | 简单问答 | 中短对话 | 长期对话 |

> **推荐**：`standard` — 完整上下文，无需数据库。  
> 修改 `.env` 中的 `APP_MODE` 即可切换。

---

## 快速开始

### 1. 获取 Notion 凭据

根据你的情况选择适合的方式：

#### 方式 A — F12（已有 Notion 网页登录时推荐）

1. 打开 https://www.notion.so/ai 并登录
2. 按 `F12` → **Application** 标签 → **Storage → Cookies → https://www.notion.so**
3. 找到 `token_v2`，复制其 Value
4. 切换到 **Console** 标签，粘贴并运行 `scripts/extract_notion_info.js`
5. 脚本会输出所有必要字段 — 将结果粘贴到 `accounts.json`

#### 方式 B — 浏览器辅助登录（只有Notion桌面应用，没有网页登录时）

```bash
python login.py
```

会启动一个临时的 Chrome/Edge 窗口，等待你登录 Notion 后，自动提取所有凭据并写入 `accounts.json` 和 `.env`。

```bash
python login.py --check          # 验证已保存的 profile
python login.py --list           # 列出所有已保存的 profile
python login.py --manual         # Chrome 不可用时手动粘贴 token_v2
python login.py --profile work   # 以指定名称保存 profile
```

两种方式都写入 `accounts.json`。支持多账号 — 在数组中添加更多条目即可启用负载均衡。

> ⚠️ `accounts.json` 和 `.env` 包含凭据，两者均已被 git 忽略 — 请妥善保管。

---

### 2. 配置 `.env`

```bash
cp .env.example .env
```

至少需要设置：

```env
APP_MODE=standard   # lite / standard / heavy
```

如果使用 **Heavy 模式**，还需添加：

```env
SILICONFLOW_API_KEY=your_key_here
```

> Heavy 模式使用 SiliconFlow 的 LLM 来压缩长对话。前往 https://siliconflow.cn 免费注册。

---

### 3. 启动服务

#### Docker（推荐）

```bash
docker-compose build --no-cache && docker-compose up -d
```

`accounts.json` 通过 volume 挂载 — 更新账号无需重新构建：

```bash
# 编辑 accounts.json 后：
docker-compose restart
```

#### 本地运行

```bash
pip install -r requirements.txt
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

访问 `http://localhost:8000` 即可使用 Web UI。

---

## 支持的模型

| 模型名称 | 说明 |
|---|---|
| `claude-sonnet4.6` | 速度与质量的最佳平衡 — **最推荐** |
| `claude-sonnet5` | 最新 Sonnet，推理与 agent 能力更强 |
| `claude-opus4.6` | 推理能力更强，建议适量使用 |
| `claude-opus4.7` | 更强推理能力 |
| `claude-opus4.8` | 强推理 Claude |
| `claude-opus5` | 最新 Claude Opus，推理能力最强 |
| `claude-haiku4.5` | Haiku 4.5 |
| `gpt-6-astra` | GPT-6 Astra |
| `gpt-5.6-sol` | GPT-5.6 Sol |
| `gpt-5.6-terra` | GPT-5.6 Terra |
| `gpt-5.6-luna` | GPT-5.6 Luna |
| `gpt-5.5` | GPT-5.5 |
| `gpt-5.4` | OpenAI 模型 |
| `gemini-3.5flash` | Gemini 3.5 Flash |
| `gemini-3.1pro` | Google 最强推理模型 |
| `gemini-3flash` | Gemini 3 Flash |
| `kimi-2.7` | Kimi K2.7 Code |
| `grok-4.3` | xAI Grok 4.3 |
| `spacexai-4.5` | SpaceXAI 4.5 |
| `grok-build0.1` | xAI Grok Build 0.1 |
| `deepseek-v4pro` | DeepSeek V4 Pro |
| `glm-5.2` | GLM 5.2 |
| `fable-5` | Fable 5 |

完整列表：`GET http://localhost:8000/v1/models`

如需新增或同步 Notion AI 模型，请阅读 [`docs/ADD_MODEL.md`](./docs/ADD_MODEL.md)（必改文件清单，无需全库搜索）。

---

## API 使用

本项目接受任意字符串作为 API key，无格式要求。

### Python 示例

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="any-string"
)

response = client.chat.completions.create(
    model="claude-sonnet4.6",
    messages=[{"role": "user", "content": "你好"}],
    stream=True
)

for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")
```

### 端点

| 端点 | 方法 | 说明 |
|---|---|---|
| `/v1/chat/completions` | POST | 聊天补全（核心） |
| `/v1/models` | GET | 列出可用模型 |
| `/health` | GET | 健康检查（账号池状态、运行时间） |
| `/` | GET | 内置 Web UI |

---

## Web UI

访问 `http://localhost:8000`，使用内置的 **Notion AI Studio** 界面：

- **对话管理** — 新建、重命名、删除、收藏/置顶
- **模型选择器** — 按服务商分组（Anthropic / OpenAI / Google / Moonshot / xAI / DeepSeek / Zhipu / Notion）
- **Thinking 面板** — 可折叠的推理过程展示，带计时器
- **Search 面板** — 可折叠的搜索查询和来源链接
- **环境粒子动画** — 天气效果：默认 / 雪 / 雨 / 晴天 / 夜晚
- **主题** — 亮色/暗色模式切换
- **响应式** — 移动端侧边栏适配

> Thinking 和 Search 面板需要 `standard` 或 `heavy` 模式。

---

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `NOTION_ACCOUNTS` | Notion 凭据 JSON 数组 | **必填** |
| `APP_MODE` | `lite` / `standard` / `heavy` | `heavy` |
| `API_KEY` | 客户端认证 Bearer Token | *(无)* |
| `DB_PATH` | SQLite 数据库路径 | `./data/conversations.db` |
| `HOST` | 服务绑定地址 | `0.0.0.0` |
| `PORT` | 服务端口 | `8000` |
| `HOST_PORT` | Docker 宿主机端口 | `8000` |
| `ALLOWED_ORIGINS` | CORS 允许的域名 | `*` |
| `SILICONFLOW_API_KEY` | Heavy 模式压缩服务密钥 | *(无)* |
| `DISABLE_RATE_LIMIT` | 关闭按 IP 速率限制 | `false` |
| `NOTION_CLIENT_VERSION` | 覆盖 Notion 客户端版本号 | `23.13.20260228.0625` |
| `NOTION_URL` | Notion 站点根地址（镜像/反代） | `https://www.notion.so` |
| `NOTION_DOMAIN` | login.py cookie domain | `www.notion.so` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `TZ` | 时区 | `Asia/Shanghai` |

---

## Docker 参考

```bash
# 启动
docker-compose up -d

# 查看日志
docker-compose logs -f --tail=50

# 重启（如更新 accounts.json 后）
docker-compose restart

# 更新代码并重新部署
git pull && docker-compose down && docker-compose build --no-cache && docker-compose up -d

# 停止
docker-compose down
```

### Nginx 反向代理（可选）

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

## 常见问题

**Thinking 面板不显示？**  
请使用 `APP_MODE=standard` 或 `heavy`，Lite 模式不支持 Thinking 和 Search 面板。

**如何切换模式？**  
修改 `.env` 中的 `APP_MODE`，然后重启：`docker-compose restart`

**如何添加多账号？**  
将 `accounts.json` 编辑为数组格式 — 账号会自动进行负载均衡：
```json
[
  {"token_v2": "token1", "space_id": "...", "user_id": "...", "space_view_id": "...", "user_name": "...", "user_email": "..."},
  {"token_v2": "token2", "space_id": "...", "user_id": "...", "space_view_id": "...", "user_name": "...", "user_email": "..."}
]
```

**收到 429 或 Notion AI 功能被暂停？**  
Notion 可能会对请求模式异常的工作区进行限流。添加多账号有助于分散负载，Business Trial 工作区尤其容易触发。

**Token 过期了？**  
重新运行 `python login.py` 或重复 F12 步骤刷新凭据。

---

## 兼容性

> 由于 Notion AI 本身的调用延迟，从发出请求到收到第一个 token 通常需要约 3 秒。

| 客户端 | 状态 | 备注 |
|---|---|---|
| Cherry Studio | ✅ 完全支持 | 推荐 |
| Zotero 翻译 | ✅ 完全支持 | 速度略慢，sonnet 模型最准确 |
| 沉浸式翻译 | ⚠️ 不推荐 | 延迟过高 |
| Claude Code | ❌ 不支持 | 使用 Anthropic 原生 API 格式 |

---

## 许可证

MIT License

---

如果这个项目对你有帮助，请给个 Star ⭐

*本项目使用 Claude Code 辅助完成。*

## Star History

<a href="https://www.star-history.com/?repos=maverickxone%2Fnotion2api&type=date&legend=bottom-right">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=maverickxone/notion2api&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=maverickxone/notion2api&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=maverickxone/notion2api&type=date&legend=top-left" />
 </picture>
</a>
