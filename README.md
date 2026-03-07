# Notion AI API Wrapper

一个基于 FastAPI 的 Notion AI API 封装服务，通过逆向工程 Notion Web API 实现，提供与 OpenAI 兼容的接口。

## 特性

- 🔄 **OpenAI 兼容接口** - 支持标准的 Chat Completion API 格式
- 💬 **流式响应** - 实时流式输出，支持 SSE (Server-Sent Events)
- 🧠 **智能记忆系统** - 分层对话历史管理，自动压缩长对话
- 🔍 **记忆召回** - 支持自然语言检索历史对话内容
- 👥 **账号池管理** - 支持多个 Notion 账号负载均衡和故障转移
- 🔐 **API Key 鉴权** - 可选的 API 密钥验证
- ⚡ **速率限制** - 内置请求频率控制
- 🎨 **Web 界面** - 内置简洁的聊天界面
- 🐳 **Docker 支持** - 提供完整的容器化部署方案

## 技术栈

- **后端**: FastAPI + Uvicorn
- **数据库**: SQLite3 (对话历史存储)
- **HTTP 客户端**: httpx, cloudscraper (绕过 Cloudflare)
- **前端**: 原生 HTML + Tailwind CSS + Marked.js
- **部署**: Docker + Docker Compose

## 项目结构

```
notion-ai/
├── app/                    # 应用核心代码
│   ├── api/               # API 路由
│   │   ├── chat.py        # 聊天完成接口
│   │   └── models.py      # 模型列表接口
│   ├── account_pool.py    # 账号池管理
│   ├── config.py          # 配置加载
│   ├── conversation.py    # 对话历史管理
│   ├── logger.py          # 日志系统
│   ├── limiter.py         # 速率限制
│   ├── notion_client.py   # Notion API 客户端
│   ├── schemas.py         # Pydantic 数据模型
│   └── server.py          # FastAPI 服务器
├── frontend/              # 前端界面
│   └── index.html         # 单页面聊天应用
├── data/                  # 数据目录
│   └── conversations.db   # SQLite 数据库
├── .env.example           # 环境变量示例
├── requirements.txt       # Python 依赖
├── Dockerfile            # Docker 镜像构建
├── docker-compose.yml    # Docker Compose 配置
└── README.md             # 本文件
```

## 快速开始

### 1. 环境准备

确保已安装 Python 3.10+：

```bash
python --version
```

### 2. 安装依赖

```bash
# 创建虚拟环境（推荐）
python -m venv .venv

# 激活虚拟环境
# Windows PowerShell:
.venv\Scripts\activate.ps1
# Windows CMD:
.venv\Scripts\activate.bat
# Mac/Linux:
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# Notion 账号配置（JSON 格式，支持多个账号）
NOTION_ACCOUNTS=[{
  "token_v2": "你的token_v2",
  "space_id": "你的space_id",
  "user_id": "你的user_id",
  "space_view_id": "你的space_view_id",
  "user_name": "用户名",
  "user_email": "邮箱"
}]

# API Key（可选，留空则不验证）
API_KEY=your-api-key-here

# 服务配置
HOST=0.0.0.0
PORT=8000

# 数据库路径（可选，默认 ./data/conversations.db）
DB_PATH=./data/conversations.db
```

### 4. 获取 Notion 账号信息

1. 打开 https://www.notion.so/ai
2. 按 `F12` 打开开发者工具
3. 进入 **Network** 标签
4. 发送一条消息
5. 查找 `runInferenceTranscript` 的 POST 请求
6. 从 Request Headers 和 Cookies 中提取所需信息：
   - `token_v2`: Cookie 中的 token_v2 值
   - `space_id`: Request Header 中的 x-notion-space-id
   - `user_id`: Request Header 中的 x-notion-active-user-header
   - `space_view_id`: Request Payload 中的 spaceViewId
   - `user_name` / `user_email`: 你的 Notion 账户信息

### 5. 启动服务

```bash
# 开发模式
uvicorn app.server:app --reload --host 0.0.0.0 --port 8000

# 生产模式
uvicorn app.server:app --host 0.0.0.0 --port 8000 --workers 4
```

服务启动后，访问：
- Web 界面: http://localhost:8000
- API 文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health

## Docker 部署

### 使用 Docker Compose（推荐）

```bash
# 构建并启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 手动 Docker 部署

```bash
# 构建镜像
docker build -t notion-ai-wrapper .

# 运行容器
docker run -d \
  --name notion-ai \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  notion-ai-wrapper
```

## API 使用示例

### Chat Completion API

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "model": "claude-opus4.6",
    "messages": [
      {"role": "user", "content": "你好，请介绍一下你自己"}
    ],
    "stream": true
  }'
```

### 支持的模型

- `claude-opus4.6` - Claude Opus 4.6
- `claude-sonnet4.6` - Claude Sonnet 4.6
- `gemini-3.1pro` - Gemini 3.1 Pro
- `gpt-5.2` - GPT-5.2

### Python 示例

```python
import requests

url = "http://localhost:8000/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer your-api-key"
}

data = {
    "model": "claude-opus4.6",
    "messages": [
        {"role": "user", "content": "解释一下量子计算"}
    ],
    "stream": False
}

response = requests.post(url, json=data, headers=headers)
print(response.json())
```

### 流式响应示例

```python
import requests

url = "http://localhost:8000/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer your-api-key"
}

data = {
    "model": "claude-opus4.6",
    "messages": [
        {"role": "user", "content": "写一首关于春天的诗"}
    ],
    "stream": True
}

response = requests.post(url, json=data, headers=headers, stream=True)

for line in response.iter_lines():
    if line:
        line = line.decode('utf-8')
        if line.startswith('data: '):
            data_str = line[6:]  # 移除 "data: " 前缀
            if data_str == '[DONE]':
                break
            print(data_str)
```

## 功能说明

### 记忆召回功能

当用户的问题包含召回意图关键词（如"之前"、"上次"、"还记得"等）时，系统会自动搜索相关历史对话并在上下文中注入。

支持的关键词：
- 中文：之前、上次、以前、你还记得、我们之前、之前说过、历史记录、找一下、搜索记忆
- 英文：earlier、before、recall、remember

示例：
```
用户: "我们之前讨论过什么关于机器学习的内容？"
系统: 自动检索相关历史对话并注入到上下文中
```

### 对话历史管理

- **短时记忆**: 保存最近 10 轮对话的完整内容
- **中期记忆**: 当对话超过 15 轮时，自动压缩早期对话为摘要
- **长期记忆**: 所有对话内容都会归档到 full_archive 表中
- **自动清理**: Notion 主页的对话记录会自动删除（通过后台线程）

### 账号池管理

- 支持配置多个 Notion 账号实现负载均衡
- 自动故障转移：某个账号失败时自动切换到其他账号
- 冷却机制：失败��账号会暂时进入冷却状态
- 状态监控：通过 `/health` 端点查看账号池状态

### 速率限制

- 默认限制：每 IP 每分钟 10 次请求
- 超出限制返回 429 状态码
- 可在 `app/limiter.py` 中自定义限制规则

## 高级配置

### 自定义速率限制

编辑 `app/limiter.py`：

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
```

在路由中应用：

```python
@router.post("/chat/completions")
@limiter.limit("20/minute")  # 修改为每分钟 20 次
async def create_chat_completion(...):
    ...
```

### 数据库迁移

项目使用 SQLite，数据库文件位于 `data/conversations.db`。如需迁移或备份：

```bash
# 备份数据库
cp data/conversations.db data/conversations.db.backup

# 查看数据库内容
sqlite3 data/conversations.db
.tables
SELECT * FROM conversations;
```

## 故障排查

### 常见问题

1. **账号配置错误**
   - 检查 `.env` 文件中的 `NOTION_ACCOUNTS` 格式是否正确
   - 确认所有必需字段都已填写

2. **API 请求失败**
   - 验证 token_v2 是否有效（可能需要重新获取）
   - 检查网络连接是否正常

3. **流式响应中断**
   - 查看服务端日志获取详细错误信息
   - 检查账号池状态：`curl http://localhost:8000/health`

4. **Docker 部署问题**
   - 确认 `.env` 文件在项目根目录
   - 检查数据目录权限：`chmod -R 755 data/`

## 注意事项

⚠️ **安全警告**
- 不要分享你的 `token_v2`，它等同于你的 Notion 账号密码
- 建议在生产环境中使用 API Key 鉴权
- 定期更新 token_v2 以避免过期

⚠️ **使用限制**
- 本项目仅用于学习和研究目的
- 请遵守 Notion 的服务条款
- 避免频繁请求以免触发 Notion 的限流机制

## 开发

### 运行测试

```bash
# 安装测试依赖
pip install pytest pytest-asyncio httpx

# 运行测试
pytest tests/
```

### 代码风格

项目遵循 PEP 8 代码规范，建议使用 black 格式化代码：

```bash
pip install black
black app/
```

## 许可证

本项目仅供学习交流使用。请遵守 Notion 的服务条款和相关法律法规。

## 贡献

欢迎提交 Issue 和 Pull Request！

## 更新日志

### v1.0.0 (2025-03-06)
- 初始版本发布
- 支持 OpenAI 兼容的 Chat Completion API
- 实现流式响应
- 添加对话历史管理
- 支持记忆召回功能
- 实现账号池管理
- 添加 Docker 部署支持
