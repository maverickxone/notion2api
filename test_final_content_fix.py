"""
Final Content 修复验证测试

测试场景：模拟 Opus/GPT 模型同时返回 agent-inference 和 text 的情况
验证：text 类型应该被优先选择，agent-inference 应该被过滤
"""

from __future__ import annotations

import json
from app.stream_parser import _extract_final_content_from_record_map


def test_opus_scenario():
    """
    Opus 场景：同时存在 agent-inference 和 text
    期望：应该选择 text，过滤掉 agent-inference
    """
    print("=" * 60)
    print("测试场景：Opus/GPT 模型（同时存在 agent-inference 和 text）")
    print("=" * 60)

    data = {
        "recordMap": {
            "thread_message": {
                "msg-inference": {
                    "value": {
                        "value": {
                            "step": {
                                "type": "agent-inference",
                                "value": [
                                    {"type": "text", "content": "这是思考内容，应该被过滤"}
                                ]
                            }
                        },
                        "created_time": 1000,
                        "last_edited_time": 2000,
                    }
                },
                "msg-text": {
                    "value": {
                        "value": {
                            "step": {
                                "type": "text",
                                "value": "这是正文内容，应该被选中"
                            }
                        },
                        "created_time": 1000,
                        "last_edited_time": 2000,
                    }
                },
            }
        }
    }

    result = _extract_final_content_from_record_map(data)

    print(f"\n✓ 结果：")
    print(f"  - 选中类型: {result['source_type']}")
    print(f"  - 内��长度: {result['source_length']}")
    print(f"  - 内容: {result['text'][:50]}...")

    # 验证
    assert result['source_type'] == 'text', f"期望选择 'text'，实际选择了 '{result['source_type']}'"
    assert '应该被选中' in result['text'], f"期望内容包含'应该被选中'，实际内容: {result['text']}"

    print("\n✅ 测试通过：text 类型被正确选择，agent-inference 被正确过滤")


def test_sonnet_scenario():
    """
    Sonnet 场景：只有 text 类型
    期望：应该直接选择 text
    """
    print("\n" + "=" * 60)
    print("测试场景：Sonnet 模型（只有 text 类型）")
    print("=" * 60)

    data = {
        "recordMap": {
            "thread_message": {
                "msg-text": {
                    "value": {
                        "value": {
                            "step": {
                                "type": "text",
                                "value": "这是 Sonnet 的正文内容"
                            }
                        },
                        "created_time": 1000,
                        "last_edited_time": 2000,
                    }
                },
            }
        }
    }

    result = _extract_final_content_from_record_map(data)

    print(f"\n✓ 结果：")
    print(f"  - 选中类型: {result['source_type']}")
    print(f"  - 内容长度: {result['source_length']}")
    print(f"  - 内容: {result['text'][:50]}...")

    # 验证
    assert result['source_type'] == 'text', f"期望选择 'text'，实际选择了 '{result['source_type']}'"
    assert 'Sonnet' in result['text'], f"期望内容包含'Sonnet'，实际内容: {result['text']}"

    print("\n✅ 测试通过：text 类型被正确选择")


def test_agent_inference_only():
    """
    只有 agent-inference 的情况（边界情况）
    期望：应该选择 agent-inference
    """
    print("\n" + "=" * 60)
    print("测试场景：只有 agent-inference（边界情况）")
    print("=" * 60)

    data = {
        "recordMap": {
            "thread_message": {
                "msg-inference": {
                    "value": {
                        "value": {
                            "step": {
                                "type": "agent-inference",
                                "value": [
                                    {"type": "text", "content": "这是唯一的内容"}
                                ]
                            }
                        },
                        "created_time": 1000,
                        "last_edited_time": 2000,
                    }
                },
            }
        }
    }

    result = _extract_final_content_from_record_map(data)

    print(f"\n✓ 结果：")
    print(f"  - 选中类型: {result['source_type']}")
    print(f"  - 内容长度: {result['source_length']}")
    print(f"  - 内容: {result['text'][:50]}...")

    # 验证
    assert result['source_type'] == 'agent-inference', f"期望选择 'agent-inference'，实际选择了 '{result['source_type']}'"
    assert '唯一的内容' in result['text'], f"期望内容包含'唯一的内容'，实际内容: {result['text']}"

    print("\n✅ 测试通过：agent-inference 被正确选择（无其他选项时）")


def test_markdown_chat():
    """
    Gemini 场景：markdown-chat 类型
    期望：应该选择 markdown-chat（优先级最高）
    """
    print("\n" + "=" * 60)
    print("测试场景：Gemini 模型（markdown-chat）")
    print("=" * 60)

    data = {
        "recordMap": {
            "thread_message": {
                "msg-markdown": {
                    "value": {
                        "value": {
                            "step": {
                                "type": "markdown-chat",
                                "value": "这是 Gemini 的 markdown-chat 内容"
                            }
                        },
                        "created_time": 1000,
                        "last_edited_time": 2000,
                    }
                },
            }
        }
    }

    result = _extract_final_content_from_record_map(data)

    print(f"\n✓ 结果：")
    print(f"  - 选中类型: {result['source_type']}")
    print(f"  - 内容长度: {result['source_length']}")
    print(f"  - 内容: {result['text'][:50]}...")

    # 验证
    assert result['source_type'] == 'markdown-chat', f"期望选择 'markdown-chat'，实际选择了 '{result['source_type']}'"
    assert 'Gemini' in result['text'], f"期望内容包含'Gemini'，实际内容: {result['text']}"

    print("\n✅ 测试通过：markdown-chat 被正确选择")


def test_priority_order():
    """
    测试优先级顺序
    期望：markdown-chat > text > agent-inference > title
    """
    print("\n" + "=" * 60)
    print("测试场景：优先级顺序")
    print("=" * 60)

    from app.stream_parser import FINAL_STEP_PRIORITIES

    print("\n✓ 优先级顺序：")
    for step_type, priority in sorted(FINAL_STEP_PRIORITIES.items(), key=lambda x: -x[1]):
        print(f"  - {step_type}: {priority}")

    # 验证优先级顺序
    assert FINAL_STEP_PRIORITIES['markdown-chat'] == 400
    assert FINAL_STEP_PRIORITIES['text'] == 350  # 修改后应该是 350
    assert FINAL_STEP_PRIORITIES['agent-inference'] == 300
    assert FINAL_STEP_PRIORITIES['title'] == 50

    # 验证 text > agent-inference
    assert FINAL_STEP_PRIORITIES['text'] > FINAL_STEP_PRIORITIES['agent-inference'], \
        "text 的优先级应该高于 agent-inference"

    print("\n✅ 测试通过：优先级顺序正确")


if __name__ == "__main__":
    try:
        test_priority_order()
        test_sonnet_scenario()
        test_opus_scenario()
        test_agent_inference_only()
        test_markdown_chat()

        print("\n" + "=" * 60)
        print("🎉 所有测试通过！修复方案验证成功！")
        print("=" * 60)
        print("\n总结：")
        print("1. ✅ text 优先级已提高到 350（高于 agent-inference 的 300）")
        print("2. ✅ 同时存在 text 和 agent-inference 时，text 被正确选择")
        print("3. ✅ 只有 agent-inference 时，依然能正确选择（不丢失内容）")
        print("4. ✅ markdown-chat 优先级最高，不受影响")
        print("5. ✅ Sonnet 模型（只有 text）行为不变")
        print("\n这个修复方案应该能够解决 Opus/GPT 模型的 thinking/content 分流问题！")

    except AssertionError as e:
        print(f"\n❌ 测试失败：{e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ 发生错误：{e}")
        import traceback
        traceback.print_exc()
        exit(1)
