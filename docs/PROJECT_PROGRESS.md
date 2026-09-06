# Notion2API — 项目实时进展文档

> 本文档记录项目的完整状态、架构细节、开发历程和当前进展。  
> 目标：阅读本文档后，即可全面掌握项目最新全貌。  
> 最后更新：2026-09-06（模型列表同步至 23 个，新增 GPT-6 Astra）

---

## 一、项目概述

### 1.1 项目定位

Notion2API 是一个将 **Notion AI** 逆向封装为 **OpenAI 兼容 API** 的开源项目。通过逆向 Notion 的 Web API（`/api/v3/runInferenceTranscript`），将 Notion AI 的能力以标准 `/v1/chat/completions` 接口对外暴露，使得 Cherry Studio、Zotero 等第三方客户端可以直接调用。

### 1.2 核心特性

- **OpenAI 兼容 API**：标准 `/v1/chat/completions` 端点，支持流式（SSE）和非流式响应
- **三种运行模式**：Lite / Standard / Heavy，满足不同场景需求
- **23 个 AI 模型**：Claude（含 Opus 5）、GPT-6 Astra、GPT-5.x、Gemini、Kimi、Grok、DeepSeek、GLM、Fable
- **三层记忆系统**（Heavy 模式）：滑动窗口 + 压缩摘要 + 完整归档
- **多账号负载均衡**：Round-Robin 轮询 + 冷却机制
- **内置 Web UI**：Claude 风格界面，支持 Thinking 面板、Search 面板、对话管理
- **Docker 一键部署**：docker-compose 开箱即用

### 1.3 仓库信息

- **仓库地址**：`git@github.com:maverickxone/notion2api.git`
- **主分支**：`main`
- **许可证**：MIT
- **当前版本**：v2.1.1

---

## 二、技术栈

### 2.1 后端

| 技术 | 用途 |
|------|------|
| Python 3.11 | 运行时 |
| FastAPI | Web 框架 |
| cloudscraper | 绕过 Cloudflare 反爬（Notion API 请求） |
| requests | HTTP 客户端 |
| httpx | 异步 HTTP 客户端（SiliconFlow 摘要服务） |
| SQLite | 数据持久化（Heavy 模式） |
| Pydantic | 数据模型验证 |
| slowapi | 速率限制 |
| python-dotenv | 环境变量管理 |
| uvicorn | ASGI 服务器 |

### 2.2 前端

| 技术 | 用途 |
|------|------|
| 原生 HTML/CSS/JS | 无框架，模块化组织 |
| marked.js（CDN） | Markdown 渲染 |
| DOMPurify（CDN） | XSS 防护 |
| highlight.js（CDN） | 代码高亮 |

### 2.3 部署

| 技术 | 用途 |
|------|------|
| Docker + docker-compose | 容器化部署 |
| Python 3.11-slim 镜像 | 基础镜像 |
| 非 root 用户运行 | 安全加固 |

---

## 三、项目架构

### 3.1 目录结构

```
notion2api/
├── app/                          # 后端核心代码
│   ├── server.py                 # FastAPI 入口、中间件、路由挂载
│   ├── api/
│   │   ├── chat.py               # 核心：/v1/chat/completions 端点 + 结构化错误系统（1700+ 行）
│   │   └── models.py             # /v1/models 端点
│   ├── conversation.py           # 三层记忆系统（1789 行，最大文件）
│   ├── notion_client.py          # Notion API 逆向客户端（370+ 行）
│   ├── stream_parser.py          # NDJSON 流解析器 + 段落注册表（849 行）
│   ├── account_pool.py           # 多账号负载均衡 + 冷却等待（110+ 行）
│   ├── model_registry.py         # 模型名称映射（108 行）
│   ├── summarizer.py             # SiliconFlow LLM 摘要服务（72 行）
│   ├── schemas.py                # Pydantic 数据模型（64 行）
│   ├── config.py                 # 环境变量加载（55 行）
│   ├── limiter.py                # 速率限制器（22 行）
│   └── logger.py                 # JSON 结构化日志（38 行）
├── frontend/                     # 内置 Web UI
│   ├── index.html                # 主页面（1705 行）
│   ├── css/
│   │   ├── main.css              # 主样式（700 行）
│   │   ├── components.css        # 组件样式（351 行）
│   │   ├── markdown.css          # Markdown 渲染样式（150 行）
│   │   └── animations.css        # 动画效果（72 行）
│   └── js/
│       ├── core/
│       │   ├── app.js            # 应用入口 + 事件绑定（412 行）
│       │   ├── constants.js      # 常量定义（131 行）
│       │   └── state.js          # 全局状态管理（69 行）
│       ├── api/
│       │   ├── client.js         # API 通信客户端（86 行）
│       │   ├── models.js         # 模型管理（63 行）
│       │   └── settings.js       # 设置面板（27 行）
│       ├── chat/
│       │   ├── manager.js        # 对话管理（207 行）
│       │   ├── renderer.js       # 消息 DOM 渲染（276 行）
│       │   ├── streaming.js      # SSE 流式处理（235 行）
│       │   └── storage.js        # LocalStorage 持久化（91 行）
│       ├── ui/
│       │   ├── input.js          # 输入框控制（43 行）
│       │   ├── modal.js          # 弹窗组件（33 行）
│       │   ├── sidebar.js        # 侧边栏（24 行）
│       │   └── theme.js          # 主题切换（36 行）
│       └── utils/
│           ├── dom.js            # DOM 工具函数（54 行）
│           ├── markdown.js       # Markdown 安全渲染（29 行）
│           └── validation.js     # 数据校验（88 行）
├── scripts/                      # 部署和管理脚本
│   ├── deploy.sh                 # Linux 部署脚本
│   ├── deploy.bat                # Windows 部署脚本
│   ├── manage.sh                 # 服务管理脚本（start/stop/backup 等）
│   └── extract_notion_info.js    # 浏览器控制台脚本：提取 Notion 凭据（多工作区支持）
├── docs/                         # 文档
│   ├── issues.md                 # 问题排查（中英双语）
│   └── PROJECT_PROGRESS.md       # 本文档（架构 + 进展 + AI 上下文，替代原 ARCHITECTURE.md）
├── data/                         # SQLite 数据库目录
│   └── conversations.db          # 对话数据库（Heavy 模式）
├── response/                     # 调试用：各模型原始响应样本
├── main.py                       # 终端交互入口（调试用）
├── requirements.txt              # Python 依赖
├── Dockerfile                    # Docker 构建文件
├── docker-compose.yml            # Docker Compose 配置
├── .env.example                  # 环境变量模板
├── .gitignore                    # Git 忽略规则
├── .dockerignore                 # Docker 构建忽略规则
├── login.py                      # 浏览器辅助登录脚本（CDP，自动提取 Notion 凭据）
├── README.md                     # 项目说明（中文，默认）
└── README_EG.md                  # 项目说明（英文）
```

### 3.2 代码规模

| 部分 | 文件数 | 总行数 |
|------|--------|--------|
| 后端 Python | 12 | ~4,992 |
| 前端 JS | 13 | ~1,645 |
| 前端 CSS | 4 | ~1,273 |
| 前端 HTML | 1 | ~1,504 |
| **合计** | **30** | **~9,414** |


---

## 四、核心模块详解

### 4.1 三种运行模式

#### Lite 模式
- **特点**：单轮问答，无记忆，无数据库
- **速率限制**：30 次/分钟
- **流程**：提取最后一条 user 消息 → 构建 transcript → 调用 Notion API → 返回结果
- **适用场景**：简单问答、翻译等无需上下文的任务
- **入口函数**：`_handle_lite_request()` in `api/chat.py`

#### Standard 模式（推荐）
- **特点**：客户端管理完整上下文，支持 Thinking 和 Search 面板，无数据库
- **速率限制**：25 次/分钟
- **流程**：接收客户端发送的完整 messages 历史 → 构建 transcript → 调用 Notion API → 返回结果（含 thinking/search 事件）
- **适用场景**：中短对话，第三方客户端使用
- **入口函数**：`_handle_standard_request()` in `api/chat.py`

#### Heavy 模式
- **特点**：服务端管理会话，SQLite 持久化，三层记忆系统
- **速率限制**：20 次/分钟
- **流程**：
  1. 获取/创建 conversation_id
  2. 从滑动窗口获取最近 8 轮对话
  3. 注入压缩摘要（如有）
  4. 构建 transcript 发送给 Notion
  5. 持久化本轮对话到滑动窗口 + 归档
  6. 异步触发压缩（超出窗口的轮次）
- **适用场景**：长期对话、需要服务端记忆的场景
- **入口函数**：`create_chat_completion()` 主函数 in `api/chat.py`

### 4.2 三层记忆系统（Heavy 模式）

```
┌─────────────────────────────────────────────────┐
│                  Notion API                      │
│  (接收 transcript: config + context + 对话历史)   │
└─────────────────────┬───────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────┐
│  get_transcript_payload()                        │
│  组装 transcript：                                │
│  1. config block (模型配置)                       │
│  2. context block (用户/空间信息)                  │
│  3. 压缩摘要 (如有，注入为 system 消息)            │
│  4. 滑动窗口最近 8 轮对话                          │
│  5. 新的 user prompt                              │
└─────────────────────┬───────────────────────────┘
                      │
    ┌─────────────────┼─────────────────┐
    ▼                 ▼                 ▼
┌──────────┐  ┌──────────────┐  ┌──────────────┐
│ sliding   │  │ compressed   │  │ full_archive │
│ _window   │  │ _summaries   │  │              │
│ (8 轮)    │  │ (中期摘要)    │  │ (永久归档)    │
│ 核心层    │  │ 压缩层        │  │ 归档层        │
│ UPSERT   │  │ SiliconFlow  │  │ INSERT OR    │
│ 写入      │  │ LLM 压缩     │  │ IGNORE       │
└──────────┘  └──────────────┘  └──────────────┘
```

**SQLite 表结构**：
- `conversations`：对话元数据（id, title, thread_id, next_round_index）
- `messages`：兼容性消息表（role, content, thinking）
- `sliding_window`：滑动窗口表（round_number, user_content, assistant_content, assistant_thinking, compress_status）
- `compressed_summaries`：压缩摘要表（round_index, user_content, assistant_content, summary, compress_status）
- `full_archive`：完整归档表（round_index, role, content）

**关键行为约束**（不可修改）：
1. **Thread ID 持久化**：整个对话复用同一个 thread_id
2. **is_partial_transcript=True**：重用 thread 时必须设置，否则 AI 失忆
3. **不删除 Thread**：Notion 主页会累积对话（可接受的副作用）
4. **强制滑动窗口**：`get_transcript_payload()` 不回退到 messages 表

### 4.3 Notion API 逆向客户端

**核心端点**：`https://www.notion.so/api/v3/runInferenceTranscript`

**请求流程**：
1. 构建 transcript（config + context + 对话历史）
2. 将外部模型名映射为 Notion 内部代号（如 `claude-sonnet4.6` → `almond-croissant-low`）
3. 根据模型确定 thread type（`workflow` 或 `markdown-chat`）
4. 使用 cloudscraper 绕过 Cloudflare 发送请求
5. 解析 NDJSON 流式响应

**Thread 类型**：
- `workflow`：大多数模型使用，支持 thinking/search
- `markdown-chat`：仅 Gemini 2.5 Flash 使用

**反爬措施**：
- 使用 cloudscraper 模拟浏览器（每个账号复用一个实例，保留 Cloudflare challenge cookie）
- 收到 403 时自动重建 scraper 刷新 Cloudflare challenge
- Cookie 通过 header 字符串传递（绕过 cookie jar 的非 ASCII 编码问题）
- 携带完整的 headers（User-Agent, notion-client-version 等）
- `notion-client-version` 可通过环境变量 `NOTION_CLIENT_VERSION` 覆盖

### 4.4 NDJSON 流解析器（stream_parser.py）

**核心机制——段落注册表（Segment Registry）**：

Notion 的流式响应是 NDJSON 格式，每行是一个 JSON 对象。解析器通过"段落注册表"机制分类内容：

1. `o:"a"` + `path="/s/-"` 的 patch 创建新段落，此时 `v.type` 标注类型
2. 根据 type 分类：`agent-inference` → thinking，`agent-tool-result` → tool，`text` → content
3. 后续 `o:"x"` patch 往已有段落追加文本，查表即可知归属

**输出三种事件**：
- `{"type": "content", "text": "..."}` — 正文
- `{"type": "thinking", "text": "..."}` — 思考过程
- `{"type": "search", "data": {...}}` — 搜索元数据
- `{"type": "final_content", "text": "...", "source_type": "..."}` — 最终确认内容（来自 record-map）

**特殊处理**：
- 清理 Notion 内部 `<lang>` 标签和 `primary="zh-CN"` 属性残片
- 从 record-map 提取最终权威内容（用于修正流式内容）
- 搜索数据提取和去重

### 4.5 多账号负载均衡

**AccountPool** 实现 Round-Robin 轮询：
- 每个账号对应一个 `NotionOpusAPI` 实例（含独立的 cloudscraper 会话）
- 请求失败时标记冷却（默认 3 秒）
- 冷却期间自动跳过该账号，轮询到下一个
- 所有账号都在冷却时，**等待最近的冷却结束**（最多 15 秒），而非直接报错
- 重试次数：`max(3, 账号数)`，单账号也至少重试 3 次
- 429（Notion 限流）也允许重试（换账号后重试）

### 4.6 支持的模型

> **新增 / 同步模型**：按清单操作 → [`docs/ADD_MODEL.md`](./ADD_MODEL.md)（必改 6 处文件 + 自检表，无需全库搜索）。

| 外部名称 | Notion 内部代号 | Thread Type | 说明 |
|----------|-----------------|-------------|------|
| claude-sonnet4.6 | almond-croissant-low | workflow | **推荐**，速度与质量最佳平衡 |
| claude-sonnet5 | angel-cake-high | workflow | Sonnet 5 |
| claude-opus4.6 | avocado-froyo-medium | workflow | 更强推理，不建议频繁使用 |
| claude-opus4.7 | apricot-sorbet-high | workflow | 更强推理 |
| claude-opus4.8 | ambrosia-tart-high | workflow | 强推理 Claude |
| claude-opus5 | agave-flan | workflow | 最新 Claude Opus，最强推理 |
| claude-haiku4.5 | anthropic-haiku-4.5 | workflow | Haiku 4.5 |
| gpt-6-astra | orlando-quinn | workflow | GPT-6 Astra |
| gpt-5.6-sol | orange-mousse | workflow | GPT-5.6 Sol |
| gpt-5.6-terra | orchid-muffin | workflow | GPT-5.6 Terra |
| gpt-5.6-luna | olive-jellyroll | workflow | GPT-5.6 Luna |
| gpt-5.4 | oval-kumquat-medium | workflow | OpenAI 模型 |
| gpt-5.5 | opal-quince-medium | workflow | GPT-5.5 |
| gemini-3.5flash | vertex-gemini-3.5-flash | markdown-chat | Gemini 3.5 Flash |
| gemini-3.1pro | galette-medium-thinking | workflow | Google 最强推理模型 |
| gemini-3flash | gingerbread | workflow | Gemini 3 Flash |
| kimi-2.7 | fireworks-kimi-k2.7 | workflow | Kimi K2.7 Code |
| grok-4.3 | xigua-mochi-medium | workflow | xAI Grok 4.3 |
| spacexai-4.5 | strawberry-whoopiepie | workflow | SpaceXAI 4.5 |
| grok-build0.1 | xinomavro-cake | workflow | xAI Grok Build 0.1 |
| deepseek-v4pro | baseten-deepseek-v4-pro | workflow | DeepSeek V4 Pro |
| glm-5.2 | baseten-glm-5.2 | workflow | GLM 5.2 |
| fable-5 | acai-budino-high | workflow | Fable 5 |

### 4.7 前端 Web UI

**命名**：Notion AI Studio

**架构**：原生 JS 模块化，通过 `window.NotionAI` 命名空间组织

**核心功能**：
- 对话管理：新建、重命名、删除、收藏（Star）
- 模型选择：分组下拉菜单（Anthropic / OpenAI / Google / Moonshot / xAI / DeepSeek）
- 流式渲染：SSE 实时输出，支持 Markdown + 代码高亮
- Thinking 面板：可折叠，显示 AI 推理过程，带计时器
- Search 面板：可折叠，显示搜索查询和来源链接
- 主题切换：亮色/暗色模式
- 环境粒子动画（AmbientEngine）：支持 default/snow/rain/sunny/night 天气效果
- 时段问候语：根据 CST 时间显示不同问候
- 数据持久化：LocalStorage 存储对话历史
- 响应式设计：移动端侧边栏适配

**SSE 协议**（前端与后端约定）：
- `choices[0].delta.content` — 正文内容（标准 OpenAI 格式）
- `choices[0].delta.reasoning_content` — 思考内容（Heavy 模式）
- `{"type": "thinking_chunk", "text": "..."}` — 思考片段（Standard 模式）
- `{"type": "search_metadata", "searches": {...}}` — 搜索结果
- `{"type": "content_replace", "content": "..."}` — 内容替换（Web 客户端专用）
- `{"type": "thinking_replace", "thinking": "..."}` — 思考替换（Web 客户端专用）


---

## 五、API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | 聊天补全（核心端点） |
| `/v1/models` | GET | 列出可用模型 |
| `/v1/conversations/{id}` | DELETE | 删除对话（Heavy 模式） |
| `/health` | GET | 健康检查（返回账号池状态、运行时间） |
| `/` | GET | Web UI 静态页面 |

**认证**：可选 Bearer Token（通过 `API_KEY` 环境变量配置）

**速率限制**：按 IP 限流，可通过 `DISABLE_RATE_LIMIT=True` 关闭

---

## 六、环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `NOTION_ACCOUNTS` | Notion 账号 JSON 数组（必填） | — |
| `APP_MODE` | 运行模式：lite / standard / heavy | `heavy` |
| `API_KEY` | 客户端认证密钥 | 空（不鉴权） |
| `DB_PATH` | SQLite 数据库路径 | `./data/conversations.db` |
| `HOST` | 服务绑定 IP | `0.0.0.0` |
| `PORT` | 服务端口 | `8000` |
| `HOST_PORT` | Docker 宿主机端口 | `8000` |
| `ALLOWED_ORIGINS` | CORS 允许的域名 | `*` |
| `SILICONFLOW_API_KEY` | Heavy 模式摘要压缩服务密钥 | 空 |
| `DISABLE_RATE_LIMIT` | 关闭速率限制 | `false` |
| `NOTION_CLIENT_VERSION` | 覆盖 Notion 客户端版本号 | `23.13.20260228.0625` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `TZ` | 时区 | `Asia/Shanghai` |

**账号配置获取方式**：
1. 登录 https://www.notion.so/ai
2. F12 → Application → Cookies → 复制 `token_v2`
3. F12 → Console → 运行 `scripts/extract_notion_info.js` 获取其余字段

---

## 七、开发历程（Git 提交时间线）

### Phase 1：基础搭建（2026-03-07 ~ 03-08）

| 日期 | 提交 | 内容 |
|------|------|------|
| 03-07 | `8ccc102` | 标准化 OpenAI 协议，改进限流错误消息 |
| 03-07 | `0836e28` | 结构化调整，添加 GEMINI.md |
| 03-08 | `a8b868c` | 修复长回复失忆与双重渲染，升级层级记忆与多账号池 |
| 03-08 | `e98b92a` | Opus/GPT 模型思考区块优化，修复滑动窗口 AI 回复缺失 |
| 03-08 | `2c6dd2e` | 修复 Opus/GPT 模型 thinking 区块和正文混淆 |
| 03-08 | `155ab7f` | 接入 GPT-5.4 (oval-kumquat-medium) |
| 03-08 | `3fc672f` | **关键修复**：修复滑动窗口缺失 AI 回复的严重 bug |
| 03-08 | `520fb2c` | **关键修复**：修复上下文记忆缺失 bug，搭建滑动窗口+压缩池系统 |

### Phase 2：模式扩展与前端重构（2026-03-09 ~ 03-11）

| 日期 | 提交 | 内容 |
|------|------|------|
| 03-09 | `cd0538d` | 添加 CLAUDE.md 项目进展文档 |
| 03-09 | `9f156a1` | 重写 CLAUDE.md 为精简版 |
| 03-09 | `50e5827` | **重构**：前端代码静态资源分离 + JS 模块化 |
| 03-09 | `330d5ab` | 优化前端设计，增加前端功能 |
| 03-09 | `067d571` | 初始化前端应用：核心聊天、UI、模型选择 |
| 03-09 | `d51e43c` | 更新 v0.9 版本 README |
| 03-09 | `8e9f884` | **v1.0**：增加 Lite 模式 |
| 03-11 | `6ab9d00` | 添加 Standard 模式支持（存在已知问题） |
| 03-11 | `40c0b9c` | 部分优化，修改 README |

### Phase 3：文档国际化（2026-03-11 ~ 03-12）

| 日期 | 提交 | 内容 |
|------|------|------|
| 03-11 | `e89d6e1` | 添加英文 README |
| 03-11 | `0dbd301` | 清理调试文件和笔记 |
| 03-12 | `78bf3c1` | 创建中文 README |
| 03-12 | `42e42b1` | 翻译 README 并更新格式 |
| 03-12 | `21c24d1` | 英文化 |

### Phase 4：Bug 修复与安全加固（2026-03-12 ~ 03-13）

| 日期 | 提交 | 内容 |
|------|------|------|
| 03-12 | `17845b1` | 维护 thinking 区块泄露 bug（仍有瑕疵） |
| 03-13 | `e98a6cf` | **PR #1 合并**：修复流式响应中 thinking 区块泄露 |
| 03-13 | `31fd6b0` | **PR #4 合并**：🔒 限制过于宽松的 CORS 策略 |
| 03-13 | `5f0d7e1` | 优化限流逻辑并添加问题排查文档 |

### Phase 5：新模型与前端优化（2026-04-28 ~ 04-29）

| 日期 | 提交 | 内容 |
|------|------|------|
| 04-28 | `423e255` | 同步官方新模型，增加不限流模式 |
| 04-29 | `fe558d4` | 修复 thinking 区块溢出 bug，给新模型增加补丁 |
| 04-29 | `0686550` | 针对前端深度优化，更换简洁的前端界面 |

### Phase 6：错误体系重构与稳定性优化（2026-04-30）

| 日期 | 提交 | 内容 |
|------|------|------|
| 04-30 | `819d7bb` | 补提交前端深度优化的 CSS/JS 模块文件（昨天遗漏） |
| 04-30 | `4bb823f` | **大改版**：结构化错误提示、重试优化、Cloudflare 修复、脚注清理、账号提取脚本重构 |
| 04-30 | `8aa02e9` | 账号提取脚本支持多账号选择（getSpaces API） |
| 04-30 | *(待push)* | 前端优化：Copy 按钮移至消息底部、用户消息 Copy、侧边栏可拖拽调节、暗色模式代码高亮 |

**`4bb823f` 详细改动**：
- **后端错误体系**：统一所有 503/500 为结构化 JSON 响应，含 11 种错误码（NOTION_401/403/429/5XX、NETWORK_TIMEOUT、POOL_COOLING 等）
- **重试优化**：`max_retries` 从 `min(3, 账号数)` 改为 `max(3, 账号数)`；429 改为可重试
- **账号池优化**：冷却时间 10s→3s；冷却期间等待而非直接报错
- **Cloudflare 修复**：cloudscraper 实例复用；403 自动重建；cookie 改为 header 字符串传递（修复中文工作区名导致的编码崩溃）
- **前端错误卡片**：红色主题卡片，显示错误码 + 具体原因 + 建议操作 + 可展开技术详情
- **脚注清理**：Markdown 渲染前移除 `[^1]` 引用和文末脚注定义
- **账号提取脚本重构**：支持多工作区选择、深度字段提取、3 秒延迟弹窗
- **Bug 修复**：`_persist_history_messages` 3 元组解包错误
- **新增文件**：`docs/PROJECT_PROGRESS.md`、`accounts.README.md`
- **新增配置**：`NOTION_CLIENT_VERSION` 环境变量

### Phase 7：新模型同步（2026-05 ~ 06）

| 日期 | 提交 | 内容 |
|------|------|------|
| 05-04 | `6a302ea` | 文档结构重组，README 双语重写 |
| 05-04 | `2991421` | **PR #12 合并**：浏览器辅助登录 `login.py` |
| 05-29 | `0611adb` | 同步官方新模型 Claude Opus 4.8（`ambrosia-tart-high`） |
| 05-29 | `7b4439e` | 修复默认回退 Sonnet 模型的 bug |
| 06-06 | `880357e` | 同步官方新模型 Grok 4.3、Grok Build 0.1、DeepSeek V4 Pro |
| 07-25 | — | 同步官方新模型 Claude Opus 5（`claude-opus5` / `agave-flan`），模型总数 22 |
| 09-06 | — | 新增 GPT-6 Astra（`gpt-6-astra` / `orlando-quinn`，codename 经 `getAvailableModels` 验证，活体调用通过），模型总数 23 |

---

## 八、Git 状态（截至 2026-06）

### 8.1 分支状态

| 分支 | 状态 | 说明 |
|------|------|------|
| `main` | ✅ 当前分支 | 主开发分支 |
| `security-fix-permissive-cors-policy` | ✅ 已合并（PR #4） | CORS 安全修复 |
| `jules-1625553040058672141` | ✅ 已合并（PR #1） | thinking 泄露修复 |
| `Sanity-Cloud:feat/login-cdp` | ✅ 已合并（PR #12） | 浏览器辅助登录 login.py |

### 8.2 最近 commit

| 提交 | 内容 |
|------|------|
| `880357e` | 同步官方新模型 Grok 4.3、Grok Build 0.1、DeepSeek V4 Pro |
| `0611adb` | 同步官方新模型 Claude Opus 4.8 |
| `7b4439e` | 修复默认回退 Sonnet 模型的 bug |
| `6a302ea` | 文档结构重组：合并 issues 双语、删除冗余 md、更新 README |
| PR #12 | feat: 浏览器辅助登录 login.py（CDP），新增 websocket-client 依赖 |

### 8.3 已关闭但内容可参考的分支

以下 PR 已被作者主动关闭（非合并），分支仍存在，内容可按需捡取：

1. **`perf-optimize-migration-n1`** — 优化对话迁移 N+1 查询（2026-03-13）
2. **`fix-remove-unused-import-logger`** — 清理 `app/logger.py` 未使用的 `time` import（2026-03-13）
3. **`testing-improvement-truncate-json`** — 为 `_truncate_json` 添加单元测试（2026-03-13）

---

## 九、已知问题与待改进

### 9.1 已知问题

1. **Thinking 区块泄露**：虽经多次修复（PR #1、`fe558d4`），部分模型在特定场景下仍可能出现 thinking 内容泄露到正文的情况。当前通过 `_trim_redundant_thinking()` 和 `_build_thinking_replacement()` 做后处理裁剪。

2. **Notion 主页 Thread 累积**：为保持对话上下文，不再自动删除 thread，导致 Notion 主页会累积大量对话记录。

3. **无自动化测试**：项目没有测试框架和 CI/CD。仅有一个未合并的分支包含 `_truncate_json` 的单元测试。

4. **CORS 配置**：默认 `ALLOWED_ORIGINS=*`，生产环境需要手动配置。

5. **依赖未锁版本**：`requirements.txt` 中所有依赖都没有指定版本号。

6. **Notion 反代检测风险**：Notion 可能对异常请求模式（大量 thread 创建、服务器 IP 请求等）进行风控，导致工作区 AI 功能被暂停。Business Trial 工作区尤其容易触发。

### 9.2 待改进项

1. **可配置滑动窗口大小**：当前硬编码为 8 轮，README 中提到未来会添加环境变量配置
2. **测试覆盖**：需要建立测试框架
3. **CI/CD**：需要配置自动化构建和测试
4. **依赖版本锁定**：应使用 `pip freeze` 或 `poetry` 锁定版本
5. **前端框架化**：当前原生 JS 模块化方案在复杂度增长后可能难以维护

---

## 十、兼容性

| 客户端 | 状态 | 备注 |
|--------|------|------|
| Cherry Studio | ✅ 完全支持 | 推荐 |
| Zotero 翻译 | ✅ 完全支持 | 稍慢，但 Sonnet 模型翻译准确 |
| 沉浸式翻译 | ❌ 不推荐 | 延迟太高 |
| Claude Code | ❌ 不支持 | 使用 Anthropic 原生 API 格式，不兼容 |

**注意**：由于 Notion AI 本身的调用延迟，从发送请求到收到回答通常有 ~3 秒延迟。

---

## 十一、部署指南

### Docker 部署（推荐）

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 Notion 凭据

# 2. 启动服务
docker-compose up -d

# 3. 查看日志
docker-compose logs -f

# 4. 健康检查
curl http://localhost:8000/health
```

### 本地开发

```bash
pip install -r requirements.txt
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

### 管理脚本

```bash
./scripts/manage.sh start    # 启动
./scripts/manage.sh stop     # 停止
./scripts/manage.sh status   # 状态
./scripts/manage.sh logs     # 日志
./scripts/manage.sh backup   # 备份数据库
./scripts/manage.sh test     # 测试 API
```

---

## 十二、当前工作重点

**截至 2026-07**：

**已完成**：
- ✅ 模型列表已同步至 23 个，新增 GPT-6 Astra（`orlando-quinn`），覆盖最新 Claude Opus 5（`agave-flan`）、GPT-5.6、Gemini、Kimi、GLM、Grok、DeepSeek 与 Fable 模型
- ✅ 合并 PR #12：浏览器辅助登录 `login.py`（CDP，支持 Chrome/Edge，自动写入 accounts.json + .env）
- ✅ 文档结构重组：README 双语重写、issues.md 中英合并、删除冗余 md 文件（ARCHITECTURE.md、DEPLOYMENT.md、accounts.README.md、CLAUDE.md、issues_CN.md）
- ✅ 结构化错误提示系统（11 种错误码，前端红色错误卡片）
- ✅ 重试机制优化（单账号 3 次重试、429 可重试、冷却期等待）
- ✅ Cloudflare 绕过优化（scraper 复用、403 自动重建、cookie 编码修复）
- ✅ 前端优化：极简自研 UI（Notion AI Studio）、环境粒子动画、Copy 按钮、侧边栏拖拽、暗色代码高亮

**待观察**：
- ⏳ Notion 反代检测风控情况
- ⏳ login.py 在不同平台（Windows/Mac/Linux）的兼容性

**下一步计划**：
- 图片/PDF 上传支持（已完成抓包分析，流程已确认）
- 研究降低 Notion 风控触发概率的方法

---

*本文档随每次 git commit 同步更新。*
