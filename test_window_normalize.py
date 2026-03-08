"""
测试 _normalize_window_messages 的修复
"""

from app.conversation import ConversationManager


def test_normalize_window_messages():
    """测试消息规范化逻辑"""
    manager = ConversationManager()

    print("=" * 60)
    print("测试场景1：正常的 user → assistant 交替顺序")
    print("=" * 60)

    messages1 = [
        {"role": "user", "content": "问题1"},
        {"role": "assistant", "content": "回答1"},
        {"role": "user", "content": "问题2"},
        {"role": "assistant", "content": "回答2"},
        {"role": "user", "content": "问题3"},
        {"role": "assistant", "content": "回答3"},
    ]

    result1 = manager._normalize_window_messages(messages1)

    print(f"\n输入：{len(messages1)} 条消息")
    print(f"输出：{len(result1)} 条消息")
    print(f"\n结果：")
    for msg in result1:
        print(f"  - {msg['role']}: {msg['content'][:20]}...")

    # 验证
    assert len(result1) == 6, f"期望 6 条消息，实际 {len(result1)}"
    assert all(
        result1[i]["role"] == "user" and result1[i + 1]["role"] == "assistant"
        for i in range(0, len(result1), 2)
    ), "消息应该成对出现"

    print("\n✅ 测试通过：正常的交替顺序")

    print("\n" + "=" * 60)
    print("测试场景2：缺少 assistant 消息")
    print("=" * 60)

    messages2 = [
        {"role": "user", "content": "问题1"},
        {"role": "assistant", "content": "回答1"},
        {"role": "user", "content": "问题2"},
        # 缺少回答2
        {"role": "user", "content": "问题3"},
        {"role": "assistant", "content": "回答3"},
    ]

    result2 = manager._normalize_window_messages(messages2)

    print(f"\n输入：{len(messages2)} 条消息")
    print(f"输出：{len(result2)} 条消息")
    print(f"\n结果：")
    for msg in result2:
        print(f"  - {msg['role']}: {msg['content'][:20]}...")

    # 验证
    assert len(result2) == 4, f"期望 4 条消息（问题1+回答1+问题3+回答3），实际 {len(result2)}"
    assert result2[0]["content"] == "问题1"
    assert result2[1]["content"] == "回答1"
    assert result2[2]["content"] == "问题3"
    assert result2[3]["content"] == "回答3"

    print("\n✅ 测试通过：缺少 assistant 消息时，跳过不成对的 user 消息")

    print("\n" + "=" * 60)
    print("测试场景3：末尾是不完整的 user 消息")
    print("=" * 60)

    messages3 = [
        {"role": "user", "content": "问题1"},
        {"role": "assistant", "content": "回答1"},
        {"role": "user", "content": "问题2"},
        {"role": "assistant", "content": "回答2"},
        {"role": "user", "content": "问题3"},  # 末尾是不完整的 user 消息
    ]

    result3 = manager._normalize_window_messages(messages3)

    print(f"\n输入：{len(messages3)} 条消息")
    print(f"输出：{len(result3)} 条消息")
    print(f"\n结果：")
    for msg in result3:
        print(f"  - {msg['role']}: {msg['content'][:20]}...")

    # 验证
    assert len(result3) == 4, f"期望 4 条消息（问题1+回答1+问题2+回答2），实际 {len(result3)}"
    assert result3[-1]["role"] == "assistant", "最后一条消息应该是 assistant"

    print("\n✅ 测试通过：末尾不完整的 user 消息被移除")

    print("\n" + "=" * 60)
    print("测试场景4：空消息和无效角色")
    print("=" * 60)

    messages4 = [
        {"role": "user", "content": "问题1"},
        {"role": "assistant", "content": "回答1"},
        {"role": "user", "content": ""},  # 空消息
        {"role": "assistant", "content": "   "},  # 空白消息
        {"role": "system", "content": "系统消息"},  # 无效角色
        {"role": "user", "content": "问题2"},
        {"role": "assistant", "content": "回答2"},
    ]

    result4 = manager._normalize_window_messages(messages4)

    print(f"\n输入：{len(messages4)} 条消息")
    print(f"输出：{len(result4)} 条消息")
    print(f"\n结果：")
    for msg in result4:
        print(f"  - {msg['role']}: {msg['content'][:20]}...")

    # 验证
    assert len(result4) == 4, f"期望 4 条消息（过滤掉空消息和无效角色），实际 {len(result4)}"

    print("\n✅ 测试通过：空消息和无效角色被过滤")

    print("\n" + "=" * 60)
    print("🎉 所有测试通过！滑动窗口修复验证成功！")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_normalize_window_messages()
    except AssertionError as e:
        print(f"\n❌ 测试失败：{e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ 发生错误：{e}")
        import traceback
        traceback.print_exc()
        exit(1)
