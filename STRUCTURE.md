# Project Structure

本文档描述 `notion-ai` 当前目录结构、各文件职责，以及建议维护状态。

状态说明：

- `[Core]`：项目运行必不可少的生产级代码或运行时配置。
- `[Tool]`：必要的维护、部署、说明或测试工具。
- `[Deprecated]`：调试残留、备份文件、缓存产物或已过时逻辑，建议删除或移出主仓库。

## Root

| Path | Status | Module | Purpose | Notes |
|---|---|---|---|---|
| `.dockerignore` | `[Tool]` | Container | Docker 构建上下文过滤规则。 | 维护中。 |
| `.env` | `[Core]` | Runtime Config | 本地/部署运行时密钥与环境变量。 | 运行必需；不应提交。 |
| `.env.example` | `[Tool]` | Runtime Config | 环境变量模板。 | 维护中。 |
| `.gitignore` | `[Tool]` | Repo Hygiene | Git 忽略规则。 | 维护中。 |
| `delete_by_threadID.py` | `[Deprecated]` | Debug Script | 早期按 thread ID 删除 Notion 线程的临时脚本。 | 已被后端删除能力与正常流程替代，建议移除。 |
| `deploy.bat` | `[Tool]` | Deployment | Windows 部署辅助脚本。 | 可保留；需和当前 Docker/Compose 命令保持一致。 |
| `deploy.md` | `[Deprecated]` | Docs | 旧版部署说明。 | 与 `DEPLOYMENT.md` 重复，建议合并后删除。 |
| `deploy.sh` | `[Tool]` | Deployment | Linux/macOS 一键部署脚本。 | 可保留；需持续与真实部署方式同步。 |
| `DEPLOYMENT.md` | `[Tool]` | Docs | 当前主要部署文档。 | 维护中。 |
| `docker-compose.yml` | `[Tool]` | Deployment | Docker Compose 运行编排文件。 | 部署必需。 |
| `Dockerfile` | `[Tool]` | Deployment | 容器镜像构建定义。 | 部署必需。 |
| `main.py` | `[Tool]` | CLI | 本地终端交互入口。 | 不是服务主入口，但对调试和手工验证有用。 |
| `manage.sh` | `[Tool]` | Operations | 服务管理脚本，封装启动、日志、备份等命令。 | 维护中。 |
| `opus.py.bak` | `[Deprecated]` | Backup | 历史备份代码文件。 | 明确应删除。 |
| `README.md` | `[Tool]` | Docs | 项目总体说明、API 示例、快速开始。 | 维护中。 |
| `requirements.txt` | `[Core]` | Dependency | Python 运行依赖清单。 | 运行必需。 |
| `test.py` | `[Tool]` | Verification | 面向接口的手工测试脚本。 | 保留价值有限，但仍可用于联调。 |
| `test_strip.py` | `[Deprecated]` | Parser Debug | 针对流式清洗函数的临时试验脚本。 | 偏调试残留，建议删除或迁入正式 tests。 |

## Root Directories

| Path | Status | Purpose | Notes |
|---|---|---|---|
| `.claude/` | `[Tool]` | 本地 AI/协作工具配置目录。 | 非运行核心。 |
| `.git/` | `[Tool]` | Git 元数据。 | 仓库基础设施，不纳入业务代码。 |
| `.venv/` | `[Tool]` | 本地 Python 虚拟环境。 | 本地开发依赖，不应纳入项目结构治理。 |
| `.vscode/` | `[Tool]` | 编辑器工作区配置。 | 非运行核心。 |
| `AI-note/` | `[Deprecated]` | 研发笔记或临时记录。 | 建议移出代码仓库主目录。 |
| `app/` | `[Core]` | 后端主代码。 | 项目核心。 |
| `data/` | `[Core]` | 运行时数据目录。 | 当前用于 SQLite 持久化。 |
| `frontend/` | `[Core]` | 前端单页界面。 | 项目核心。 |
| `__pycache__/` | `[Deprecated]` | 根目录 Python 缓存。 | 生成产物，建议清理。 |

## app/

### app Top Level

| Path | Status | Module | Purpose | Notes |
|---|---|---|---|---|
| `app/__init__.py` | `[Core]` | Package | Python 包标记文件。 | 轻量但必要。 |
| `app/account_pool.py` | `[Core]` | Upstream Resilience | Notion 账号池、轮询选择、失败冷却。 | 核心运行逻辑。 |
| `app/config.py` | `[Core]` | Config | 读取环境变量并构造全局配置。 | 核心运行逻辑。 |
| `app/conversation.py` | `[Core]` | Memory/Storage | SQLite 对话存储、上下文恢复、压缩摘要、召回组装。 | 后端核心模块。 |
| `app/limiter.py` | `[Core]` | API Guard | 全局速率限制器定义。 | 核心安全控制。 |
| `app/logger.py` | `[Core]` | Observability | JSON 结构化日志。 | 核心运行基础设施。 |
| `app/model_registry.py` | `[Core]` | Model Namespace | 标准模型名与 Notion 私有 ID 的映射与展示名称。 | 当前已作为契约边界。 |
| `app/notion_client.py` | `[Core]` | Upstream Client | 与 Notion 私有接口通信，发送 payload、接收流。 | 核心逆向协议实现。 |
| `app/schemas.py` | `[Core]` | API Schema | Pydantic 请求/响应模型。 | 核心接口定义。 |
| `app/server.py` | `[Core]` | App Entry | FastAPI 应用、路由挂载、中间件、健康检查、静态前端。 | 服务主入口。 |
| `app/stream_parser.py` | `[Core]` | Stream Parsing | 解析 Notion NDJSON 流并拆分 content/search/thinking。 | 核心协议解析器。 |
| `app/summarizer.py` | `[Core]` | Memory Compression | 调用外部摘要模型，对旧轮次生成压缩摘要。 | 核心但属于可退化子系统。 |

### app/api/

| Path | Status | Module | Purpose | Notes |
|---|---|---|---|---|
| `app/api/__init__.py` | `[Core]` | Package | API 路由包标记文件。 | 必要。 |
| `app/api/chat.py` | `[Core]` | API Route | `/v1/chat/completions` 与 `/v1/conversations/{id}` 等核心接口。 | API 核心。 |
| `app/api/models.py` | `[Core]` | API Route | `/v1/models` 标准模型列表接口。 | API 核心。 |

### app/__pycache__/ and app/api/__pycache__/

| Path | Status | Purpose | Notes |
|---|---|---|---|
| `app/__pycache__/...` | `[Deprecated]` | Python 编译缓存。 | 生成产物，不应纳入仓库。 |
| `app/api/__pycache__/...` | `[Deprecated]` | Python 编译缓存。 | 生成产物，不应纳入仓库。 |

当前检测到的缓存文件：

- `app/__pycache__/account_pool.cpython-313.pyc`
- `app/__pycache__/config.cpython-313.pyc`
- `app/__pycache__/conversation.cpython-313.pyc`
- `app/__pycache__/limiter.cpython-313.pyc`
- `app/__pycache__/logger.cpython-313.pyc`
- `app/__pycache__/model_registry.cpython-313.pyc`
- `app/__pycache__/notion_client.cpython-313.pyc`
- `app/__pycache__/schemas.cpython-313.pyc`
- `app/__pycache__/server.cpython-313.pyc`
- `app/__pycache__/stream_parser.cpython-313.pyc`
- `app/__pycache__/summarizer.cpython-313.pyc`
- `app/__pycache__/__init__.cpython-313.pyc`
- `app/api/__pycache__/chat.cpython-310.pyc`
- `app/api/__pycache__/chat.cpython-313.pyc`
- `app/api/__pycache__/models.cpython-310.pyc`
- `app/api/__pycache__/models.cpython-313.pyc`
- `app/api/__pycache__/__init__.cpython-310.pyc`
- `app/api/__pycache__/__init__.cpython-313.pyc`

## frontend/

| Path | Status | Module | Purpose | Notes |
|---|---|---|---|---|
| `frontend/index.html` | `[Core]` | Web UI | 单文件前端，包含界面布局、样式、模型选择、SSE 处理、本地会话管理。 | 当前前端全部逻辑都在此文件中，功能完整但耦合度较高。 |

## data/

| Path | Status | Module | Purpose | Notes |
|---|---|---|---|---|
| `data/conversations.db` | `[Core]` | Persistence | SQLite 持久化数据库，保存会话、消息、摘要与归档。 | 运行时核心数据，不应提交真实内容。 |

## Recommended Cleanup Order

优先建议清理以下内容：

1. `[Deprecated]` 备份与调试脚本：`opus.py.bak`、`delete_by_threadID.py`、`test_strip.py`。
2. `[Deprecated]` 重复文档：`deploy.md`。
3. `[Deprecated]` 生成产物：根目录和 `app/` 下所有 `__pycache__` / `*.pyc`。
4. `[Deprecated]` 杂项目录：`AI-note/` 若无持续价值应移出仓库。

## Current Core Runtime Path

生产运行主链路如下：

1. `app/server.py` 启动 FastAPI。
2. `app/api/chat.py` 接收 OpenAI 兼容请求。
3. `app/conversation.py` 管理上下文、SQLite 和摘要。
4. `app/notion_client.py` 将标准模型名转换为 Notion 私有 ID 并发送请求。
5. `app/stream_parser.py` 解析上游流。
6. `frontend/index.html` 提供内置 UI。
