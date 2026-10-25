"""对话策略：意图白名单 / 工具调用过滤 —— v0.3-v0.5 踩坑的防线"""
from app.services.conversation import (
    _is_generate_intent,
    _sanitize_tool_calls,
    _should_allow_propose,
)


def test_generate_intent_whitelist():
    for t in ("帮我生成行程", "排个行程", "帮我排一下", "出个方案",
              "怎么安排", "看看行程", "换一批", "再来一版"):
        assert _is_generate_intent(t), t


def test_generate_intent_rejects_questions():
    for t in ("故宫几点开门", "远不远", "好玩吗", "北京有什么好吃的",
              "你好", ""):
        assert not _is_generate_intent(t), t


def test_propose_intent():
    assert _should_allow_propose("最后那个太远了，换一个")
    assert _should_allow_propose("这个不想去，去掉")
    assert _should_allow_propose("顺序调整一下")
    # 「换一批」是整条重来 → 走 generate，不放行 propose
    assert not _should_allow_propose("换一批")
    assert not _should_allow_propose("重新生成")
    assert not _should_allow_propose("几点开门")


def test_sanitize_drops_generate_without_intent():
    out = _sanitize_tool_calls(
        [{"name": "generate_itinerary", "args": {}}],
        user_text="故宫几点开门", has_itinerary=False)
    assert out == []


def test_sanitize_drops_propose_without_itinerary():
    out = _sanitize_tool_calls(
        [{"name": "propose_modify_itinerary",
          "args": {"action": "remove", "reason": "太远"}}],
        user_text="去掉故宫", has_itinerary=False)
    assert out == []


def test_sanitize_drops_propose_invalid_action():
    out = _sanitize_tool_calls(
        [{"name": "propose_modify_itinerary",
          "args": {"action": "nuke", "reason": "x"}}],
        user_text="去掉故宫", has_itinerary=True)
    assert out == []


def test_sanitize_keeps_valid_propose():
    tc = [{"name": "propose_modify_itinerary",
           "args": {"action": "remove", "target": "故宫", "reason": "太远"}}]
    out = _sanitize_tool_calls(tc, user_text="故宫太远了，去掉吧", has_itinerary=True)
    assert out == tc


def test_sanitize_keeps_valid_generate():
    tc = [{"name": "generate_itinerary", "args": {"hours": 8}}]
    out = _sanitize_tool_calls(tc, user_text="帮我排一下", has_itinerary=False)
    assert out == tc


def test_sanitize_empty_input():
    assert _sanitize_tool_calls(None, "x", False) == []
    assert _sanitize_tool_calls([], "x", False) == []
