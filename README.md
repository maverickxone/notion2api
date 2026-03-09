# Notion2API

Notion2API 是一个基于 FastAPI 的逆向工程项目，将 Notion AI 封装为与 OpenAI 兼容的 API 接口。

## 核心特性

- 接口兼容：支持标准 OpenAI Chat Completions API 格式。
- 流式响应：支持 Server-Sent Events (SSE) 流式输出。
- 三层记忆系统：通过滑动窗口、压缩摘要及完整归档实现高效的上下文管理。
- 账号池：支持多账号负载均衡与自动故障转移。
- 身份验证：可选的 API Key 鉴权机制。
- 容器化：提供完整的 Docker 部署支持。

## 快速开始

### 1. 环境准备

确保已安装 Python 3.10+。

```bash
git clone https://github.com/your-repo/notion-ai.git
cd notion-ai
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件并参考以下配置：

```env
NOTION_ACCOUNTS=[{"token_v2": "...", "space_id": "...", "user_id": "...", "space_view_id": "..."}]
API_KEY=your_optional_api_key
DB_PATH=./data/conversations.db
```

### 3. 启动服务

```bash
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

访问 `http://localhost:8000/docs` 查看交互式 API 文档。

## 支持的模型

| 模型名称 | Notion 内部代号 |
|---|---|
| claude-opus4.6 | avocado-froyo-medium |
| claude-sonnet4.6 | almond-croissant-low |
| gemini-3.1pro | galette-medium-thinking |
| gpt-5.2 | oatmeal-cookie |
| gpt-5.4 | oval-kumquat-medium |

## API 使用示例

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "model": "claude-opus4.6",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": true
  }'
```

## 三层记忆系统说明

1. 滑动窗口 (sliding_window)：保存最近 8 轮对话内容。
2. 压缩摘要 (compressed_summaries)：超出滑动窗口的内容自动触发压缩。
3. 完整归档 (full_archive)：永久保存所有历史记录。

## Docker 部署

```bash
docker-compose up -d
```

## 许可证

本项目仅供学习研究使用，请遵守 Notion 相关服务条款。
