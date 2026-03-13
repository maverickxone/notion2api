# 问题排查指南

> 常见错误和解决方案

---

## Q1: 503 Service Unavailable - "请求过多"

**错误信息:**
```
503 Service Unavailable: Notion 账号被限流
```

**原因:**
- Notion AI 有请求频率限制（为了保护你的账号），连续快速提问会触发 Notion 返回 429
- 之前冷却时间过长（60秒），导致频繁出现 503
- 已修复：现在冷却时间仅为 10 秒

**解决方案:**

1. **等待几秒后重试**（推荐）
   - Notion 的限流通常在 10-30 秒后恢复

2. **如果配置了多账号**，系统会自动切换到其他账号
   ```bash
   # 在 .env 中添加更多账号以提高稳定性
   NOTION_ACCOUNTS='[{"token_v2":"..."}, {"token_v2":"..."}]'
   ```

3. **降低请求频率**
   - Lite 模式：最多 30 次/分钟
   - Standard 模式：最多 25 次/分钟
   - Heavy 模式：最多 20 次/分钟

**预防建议:**
- 避免连续快速发送请求
- 使用 Standard 模式以获得更好的稳定性
- 如有可能，配置多个账号

---

## Q2: 405 Method Not Allowed - "方法不被允许"

**错误信息:**
```
API Error: 405 Method Not Allowed
```

**原因:**
- 请求的端点不支持使用的 HTTP 方法
- 常见原因：Claude Code 或其他工具使用了错误的端点或方法

**Notion2API 支持的端点:**

| 端点 | 方法 | 描述 |
|------|------|------|
| `/v1/chat/completions` | POST | 聊天接口（主要端点） |
| `/v1/models` | GET | 获取可用模型列表 |
| `/v1/conversations/{id}` | DELETE | 删除对话（Heavy 模式） |
| `/health` | GET | 健康检查 |

**解决方案:**

1. **检查端点 URL**
   - 确保使用 `/v1/chat/completions`（带 `/v1` 前缀）
   - 而不是 `/chat/completions`（没有前缀）

2. **检查 HTTP 方法**
   - 聊天接口只支持 **POST** 方法
   - 不要在 `/v1/chat/completions` 上使用 GET、PUT、DELETE

3. **关于 Claude Code**
   - Claude Code 使用 Anthropic 原生 API 格式，与 Notion2API **不兼容**
   - Notion2API 只提供 OpenAI 兼容的文本聊天功能
   - 它无法读取文件、执行命令或使用工具
   - **不支持 Claude Code** - 请使用 OpenCode 或其他兼容工具

---

## Q3: 401 Unauthorized - "认证失败"

**错误信息:**
```
401 Unauthorized: Notion upstream returned HTTP 401
```

**原因:**
- 你的 `token_v2` 已过期或失效
- Notion 账号已退出登录
- Notion 更新了认证方式

**解决方案:**

1. **重新获取 token_v2**（推荐）
   - 打开 https://www.notion.so/ai 并确保已登录
   - 按 `F12` 打开开发者工具
   - 切换到 **Application** 标签
   - 左侧找到 **Storage → Cookies → https://www.notion.so**
   - 找到 `token_v2`，复制其 **Value**
   - 更新 `.env` 文件中的 `token_v2`
   - 重启服务

2. **检查 Notion 账号状态**
   - 在浏览器中打开 https://www.notion.so/ai
   - 确保已登录
   - 尝试手动使用 Notion AI

**预防建议:**
- 定期刷新 token_v2
- 服务运行时不要退出 Notion 账号登录

---

## 更多问题待续...

---

*最后更新: 2026-03-13*
