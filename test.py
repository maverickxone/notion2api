"""
API 测试脚本 —— 测试 notion-ai 服务的 /v1/chat/completions 接口
模型: claude-sonnet4.6
"""

import requests
import json

# =====================
# 配置区：按需修改
# =====================
BASE_URL = "http://localhost:8000"
API_KEY  = "ustc-mav-20260306"       # 与 .env 中 API_KEY 保持一致；若未设置 API_KEY 可留空
MODEL    = "claude-sonnet4.6"           # 标准 API 模型名，见 app/model_registry.py

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}


# =====================
# 测试 1：非流式请求
# =====================
def test_non_stream():
    print("=" * 50)
    print("【测试 1】非流式请求")
    print("=" * 50)

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "你好，用一句话介绍一下你自己。"}
        ],
        "stream": False,
    }

    resp = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        headers=HEADERS,
        json=payload,
        timeout=60,
    )

    print(f"状态码: {resp.status_code}")
    if resp.ok:
        data = resp.json()
        reply = data["choices"][0]["message"]["content"]
        print(f"回复内容: {reply}")
    else:
        print(f"错误: {resp.text}")
    print()


# =====================
# 测试 2：流式请求（SSE）
# =====================
def test_stream():
    print("=" * 50)
    print("【测试 2】流式请求（SSE）")
    print("=" * 50)

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "请用 5 句话简要介绍 Claude Code。"}
        ],
        "stream": True,
    }

    with requests.post(
        f"{BASE_URL}/v1/chat/completions",
        headers=HEADERS,
        json=payload,
        stream=True,
        timeout=60,
    ) as resp:
        print(f"状态码: {resp.status_code}")
        if not resp.ok:
            print(f"错误: {resp.text}")
            return

        print("流式输出：", end="", flush=True)
        for line in resp.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if text.startswith("data: "):
                data_str = text[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if content:
                        print(content, end="", flush=True)
                except json.JSONDecodeError:
                    pass
        print("\n")


# =====================
# 测试 3：多轮对话
# =====================
def test_multi_turn():
    print("=" * 50)
    print("【测试 3】多轮对话")
    print("=" * 50)

    messages = [
        {"role": "user",      "content": "1+1等于几？"},
        {"role": "assistant", "content": "1+1等于2。"},
        {"role": "user",      "content": "那再加1呢？"},
    ]

    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
    }

    resp = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        headers=HEADERS,
        json=payload,
        timeout=60,
    )

    print(f"状态码: {resp.status_code}")
    if resp.ok:
        data = resp.json()
        reply = data["choices"][0]["message"]["content"]
        print(f"回复内容: {reply}")
    else:
        print(f"错误: {resp.text}")
    print()


# =====================
# 测试 4：模型列表
# =====================
def test_models():
    print("=" * 50)
    print("【测试 4】获取可用模型列表")
    print("=" * 50)

    resp = requests.get(
        f"{BASE_URL}/v1/models",
        headers=HEADERS,
        timeout=10,
    )

    print(f"状态码: {resp.status_code}")
    if resp.ok:
        data = resp.json()
        for m in data.get("data", []):
            print(f"  - {m.get('id', m)}")
    else:
        print(f"错误: {resp.text}")
    print()


if __name__ == "__main__":
    test_models()
    test_non_stream()
    test_stream()
    test_multi_turn()
