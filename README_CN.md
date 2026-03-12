# Notion2API

> Notion AI 转 OpenAI 兼容 API 封装

🌐 [English](./README.md) | 中文

Notion2API 将 Notion AI 封装为 OpenAI 兼容的 API 接口，支持 Cherry Studio、Zotero第三方客户端直接使用，也可直接使用已有的前端页面。

## 特性

- **三种运行模式** - Lite/Standard/Heavy 满足不同场景需求
- **OpenAI 兼容** - 标准的 `/v1/chat/completions` 接口
- **流式响应** - 支持 SSE 实时输出
- **Thinking 面板** - 支持 所有模型 推理过程展示
- **搜索功能** - 支持 Web 搜索结果展示
- **账号池** - 多账号负载均衡与故障转移
- **Docker 部署** - 开箱即用的容器化方案

---

## 三种模式对比

| 特性 | Lite | Standard | Heavy |
|------|------|----------|-------|
| **记忆管理** | ❌ 无记忆 | ✅ 客户端管理 | ✅ 服务器管理 |
| **数据库** | ❌ 不需要 | ❌ 不需要 | ✅ SQLite |
| **Thinking** | ❌ 不需要 | ✅ 专用面板 | ✅ 专用面板 |
| **搜索结果** | ❌ 不需要 | ✅ 专用面板 | ✅ 专用面板 |
| **速率限制** | 30/min | 25/min | 20/min |
| **适用场景** | 简单问答 | 中短对话 | 长期对话 |

选择模式：修改 `.env` 中的 `APP_MODE` 变量即可。

---

## 快速开始

### 1. 获取 Notion 凭据

打开 https://www.notion.so/ai 并登录，然后按 `F12` 打开开发者工具：

**步骤 1：获取 token_v2**
1. 切换到 **Application** 标签
2. 左侧展开 **Storage → Cookies → https://www.notion.so**
3. 找到 `token_v2`，复制其 Value

**步骤 2：获取其他信息**
1. 切换到 **Console** 标签
2. 复制并粘贴 `scripts/extract_notion_info.js` 中的代码，回车运行
3. 脚本会自动获取 `space_id`、`user_id` 等其他 5 个字段
4. 复制输出的内容，将 `YOUR_TOKEN_V2_HERE` 替换为步骤 1 获取的 token_v2
5. 粘贴到 `.env` 文件

### 2. 配置环境变量

```bash
# 复制示例配置
cp .env.example .env

# 编辑 .env，填入你的凭据
NOTION_ACCOUNTS='[{"token_v2":"your_token","space_id":"your_space","user_id":"your_uid","space_view_id":"your_view","user_name":"your_name","user_email":"your_email"}]'
APP_MODE=standard  # lite / standard / heavy
```

**⚠️ 如果使用 Heavy 模式**：

Heavy 模式需要配置 `SILICONFLOW_API_KEY`（用于对话摘要压缩）：
1. 访问 https://siliconflow.cn 注册账号（免费）
2. 获取 API Key
3. 添加到 `.env` 文件：
   ```bash
   SILICONFLOW_API_KEY=your_api_key_here
   APP_MODE=heavy
   ```

### 3. 启动服务

#### Docker 部署（推荐）

```bash
docker-compose up -d
# 访问 http://localhost:8000
```

#### 本地运行

```bash
pip install -r requirements.txt
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

---

## 支持的模型

| 模型名称 | 说明 |
|---|---|
| `claude-sonnet4.6` | 均衡性能与速度的绝佳选择！（**最推荐**，优化最多，最稳定可靠） |
| `claude-opus4.6` | 推理能力较强，但不建议频繁使用 |
| `gemini-3.1pro` | Google 模型，目前官方暂停使用，这里**还可访问**，但不支持联网搜索 |
| `gpt-5.2` / `gpt-5.4` | OpenAI 最新模型，也不错 |

查看完整列表：`GET http://localhost:8000/v1/models`

---

## API 使用
本项目支持自定义API key，无格式要求。

### Python 示例

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="optional_api_key"
)

response = client.chat.completions.create(
    model="claude-sonnet4.6",
    messages=[{"role": "user", "content": "你好"}],
    stream=True
)

for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")
```

---

## 前端界面
（自设计，仿照 Claude 风格，支持 Standard 和 Heavy 模式）

访问 `http://localhost:8000` 可使用内置的 Web UI：

- **主内容区** - 显示 AI 回复
- **Thinking 面板** - 显示推理过程（可折叠）
- **搜索面板** - 显示搜索来源（可折叠）
- **Star功能** - 收藏置顶有价值的对话

---

## 环境变量说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `APP_MODE` | 运行模式：lite/standard/heavy | `heavy` |
| `NOTION_ACCOUNTS` | Notion 凭据 JSON 数组 | 必填 |
| `API_KEY` | 客户端鉴权密钥 | 可选（建议自设定） |
| `DB_PATH` | SQLite 数据库路径 | `./data/conversations.db` |
| `HOST_PORT` | 宿主机端口 | `8000` |
| `SILICONFLOW_API_KEY` | Heavy 模式必需，用于对早期对话进行摘要压缩 | 可选 |

---

## Docker 部署

### 使用 docker-compose（推荐）

```bash
# 1. 配置 .env 文件
cp .env.example .env

# 2. 启动服务
docker-compose up -d

# 3. 查看日志
docker-compose logs -f

# 4. 停止服务
docker-compose down
```

### 自定义端口

修改 `.env` 文件中的 `HOST_PORT` 变量：
```bash
HOST_PORT=8080  # 使用 8080 端口
```

---

## 常见问题

### 1. Thinking 面板不显示？

确保使用 `APP_MODE=standard` 或 `heavy`，Lite 模式不支持 Thinking。

### 2. 如何切换模式？

修改 `.env` 中的 `APP_MODE`，然后重启服务：
```bash
APP_MODE=standard  # 改为 standard
docker-compose restart
```

### 3. 多账号如何配置？
（多账号增加稳定性，Beta版本）

`NOTION_ACCOUNTS` 支持数组格式：
```json
[
  {"token_v2":"token1","space_id":"space1",...},
  {"token_v2":"token2","space_id":"space2",...}
]
```

---

## 兼容性测试
（注意，由于notion本身调用AI的速率，通常从发出问答到给出答案有3秒延迟，因此不建议使用对延迟有高要求的客户端，如沉浸式翻译）

| 客户端 | 状态 | 备注 |
|--------|------|------|
| Cherry Studio | ✅ 完美支持 | 推荐 |
| Zotero 翻译 | ✅ 完美支持 | 速度略慢，但sonnet模型准确 |
| 沉浸式翻译 | 不推荐 | 速度很慢 |

---

## 许可证

MIT License

---

## Star History

如果这个项目对你有帮助，请给个 Star ⭐

## 其他
本项目使用 Claude Code 和 Codex 辅助完成

**Heavy 模式说明**：
- 滑动窗口：默认保留最近 **8 轮**对话（16 条消息）
- 压缩摘要：超出窗口的部分自动压缩为摘要
- 完整归档：所有历史永久存储在 SQLite 数据库

**未来改进**：
- 如果您需要自定义滑动窗口大小（如 10 轮、20 轮），欢迎提交 Issue
- 根据需求我们会添加环境变量配置选项

欢迎 Issue 反馈问题和建议！