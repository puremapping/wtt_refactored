"""每轮对话编排测试（FakeLLM，零真调用）

三个历史坑固化为回归测试：
  - v0.3：模型谎称有上海数据 → 服务端硬拦数据边界
  - v0.5：模型想调工具被拦 → reply 与 tool_calls 双空 → 必须去掉 tools 重问
  - v0.5：用户明确要生成但模型没调工具 → 服务端强制补调
"""
import json
from types import SimpleNamespace

import pytest

from app.services import conversation as convo


class FakeLLM:
    """按剧本回话：json_chat 走 extract 脚本，chat_raw 走 replies 队列"""

    def __init__(self, extract=None, replies=None):
        self.extract = extract if extract is not None else {}
        self.replies = list(replies or [])
        self.calls = []                      # (kind, messages, kwargs)

    def json_chat(self, messages, **kw):
        self.calls.append(("extract", messages, kw))
        return self.extract

    def chat_raw(self, messages, **kw):
        self.calls.append(("reply", messages, kw))
        if self.replies:
            return self.replies.pop(0)
        return SimpleNamespace(content="（默认回复）", tool_calls=None)


def text_msg(content):
    return SimpleNamespace(content=content, tool_calls=None)


def tool_msg(name, args=None, content=""):
    return SimpleNamespace(
        content=content,
        tool_calls=[SimpleNamespace(
            function=SimpleNamespace(name=name,
                                     arguments=json.dumps(args or {})))])


@pytest.fixture(autouse=True)
def _clean_anon():
    convo._ANON_SESSIONS.clear()
    yield
    convo._ANON_SESSIONS.clear()


# ── 正常轮 ──

def test_normal_turn_updates_profile(seed_beijing):
    fake = FakeLLM(
        extract={"primary": "恢复/逃离", "primary_intensity": 4},
        replies=[text_msg("听起来你需要好好休息一下。最近工作很累吗？")])
    conv = convo.chat(None, "太累了，想找个地方躺平", llm=fake)

    assert conv.profile["primary"] == "恢复/逃离"
    assert conv.profile["primary_intensity"] == 4
    assert conv.messages[-1]["role"] == "assistant"
    assert "休息" in conv.messages[-1]["content"]
    # 两次独立调用：先抽取后回复
    assert [k for k, _, _ in fake.calls] == ["extract", "reply"]


def test_extract_messages_never_contain_assistant_history(seed_beijing):
    """关键设计：抽取调用绝不喂 assistant 消息（否则模型续写对话而非抽取）"""
    fake = FakeLLM(extract={}, replies=[text_msg("好")])
    convo.chat(None, "想去北京玩", llm=fake)
    _, msgs, _ = fake.calls[0]
    assert all(m["role"] != "assistant" for m in msgs)


def test_two_turns_become_ready(seed_beijing):
    fake1 = FakeLLM(extract={"primary": "恢复/逃离"},
                    replies=[text_msg("明白了，想放松一下。")])
    c1 = convo.chat(None, "太累了想出去走走", llm=fake1)
    assert not c1.ready                    # 第 1 轮只有动机

    fake2 = FakeLLM(extract={"hours": "一天"},
                    replies=[text_msg("好，一天时间。要不要看看行程？")])
    c2 = convo.chat(c1.session_id, "大概能玩一天", llm=fake2)
    assert c2.ready
    assert c2.profile["hours"] == 8


# ── 坑 1：工具被拦后双空 → 去 tools 重问 ──

def test_intercepted_tool_triggers_reask_without_tools(seed_beijing):
    """模型想调工具（无正文），服务端按白名单拦掉（用户没表达生成意图）
    → 必须第二次不带 tools 重问，得到文字回复，而不是空洞兜底"""
    fake = FakeLLM(
        extract={"primary": "成就/完成"},
        replies=[
            tool_msg("generate_itinerary"),          # 被意图白名单拦掉
            text_msg("你现在是想了解故宫的开放信息，还是想让我帮你排行程？"),
        ])
    conv = convo.chat(None, "故宫是谁建的呀", llm=fake)

    assert conv.tool_calls == []
    assert "排行程" in conv.messages[-1]["content"]
    # 三次调用：extract + 带 tools 的回复 + 不带 tools 的重问
    assert [k for k, _, _ in fake.calls] == ["extract", "reply", "reply"]
    assert fake.calls[-1][2].get("tools") is None


def test_tool_call_with_content_keeps_content(seed_beijing):
    """模型给了正文又给了合法工具调用 → 正文保留，工具放行"""
    fake = FakeLLM(
        extract={"primary": "成就/完成", "hours": 8},
        replies=[tool_msg("generate_itinerary", {"hours": 8},
                          content="好，我按北京给你排一条。")])
    conv = convo.chat(None, "帮我排一下行程", llm=fake)

    assert conv.tool_calls and conv.tool_calls[0]["name"] == "generate_itinerary"
    assert conv.messages[-1]["content"].startswith("好")


# ── 坑 2：谎称有上海数据 → 服务端硬拦 ──

def test_unsupported_destination_blocks_generation(seed_beijing):
    fake = FakeLLM(
        extract={"destination": "上海", "primary": "探索/新奇"},
        replies=[text_msg("上海好玩的可多了！")])   # 模型撒谎的正文
    conv = convo.chat(None, "我想去上海玩", llm=fake)

    # 正文被替换为诚实声明
    assert "上海还查不了" in conv.messages[-1]["content"]
    assert "北京" in conv.messages[-1]["content"]     # 告知支持的城市
    assert conv.tool_calls == []


def test_unsupported_destination_blocks_forced_generate(seed_beijing):
    """用户明确要生成 + 目的地不支持 → 绝不能强行给北京行程（静默错误）"""
    fake = FakeLLM(
        extract={"destination": "上海"},
        replies=[text_msg("好的。")])
    conv = convo.chat(None, "帮我排一下上海一日游的行程", llm=fake)

    assert conv.tool_calls == []
    assert "还查不了" in conv.messages[-1]["content"]


def test_placeholder_destination_not_treated_as_city(seed_beijing):
    """「未知」不是城市名 —— 清洗后不得触发边界拦截"""
    fake = FakeLLM(
        extract={"destination": "未知", "primary": "恢复/逃离"},
        replies=[text_msg("好呀，想放松的话有不少选择。")])
    conv = convo.chat(None, "就想放松一下", llm=fake)

    assert "未知" not in str(conv.profile)
    assert conv.messages[-1]["content"] == "好呀，想放松的话有不少选择。"


# ── 坑 3：用户明确要生成但模型没调工具 → 强制补调 ──

def test_forced_generate_when_model_misses_intent(seed_beijing):
    fake = FakeLLM(
        extract={"primary": "成就/完成", "hours": 8},
        replies=[text_msg("好的，知道了。")])       # 模型只顾追问城市，没调工具
    conv = convo.chat(None, "帮我排个行程，就在北京", llm=fake)

    assert len(conv.tool_calls) == 1
    tc = conv.tool_calls[0]
    assert tc["name"] == "generate_itinerary"
    assert tc.get("forced") is True
    assert "排" in conv.messages[-1]["content"]


def test_forced_generate_carries_same_turn_hours(seed_beijing):
    """BUG-11 修复回归：本轮刚说的 hours 必须进强制补调参数"""
    fake = FakeLLM(extract={"hours": 8}, replies=[text_msg("好的，知道了。")])
    conv = convo.chat(None, "帮我排个行程，能玩一天 8 小时", llm=fake)
    assert conv.tool_calls[0]["args"].get("hours") == 8


def test_no_forced_generate_without_intent(seed_beijing):
    fake = FakeLLM(extract={}, replies=[text_msg("你好呀，想去哪玩？")])
    conv = convo.chat(None, "你好", llm=fake)
    assert conv.tool_calls == []


# ── 会话持久化（匿名内存路径）──

def test_anonymous_session_roundtrip_in_memory(seed_beijing):
    fake = FakeLLM(extract={"primary": "美食/感官"}, replies=[text_msg("好，吃的。")])
    c1 = convo.chat(None, "我想吃好吃的", llm=fake)
    sid = c1.session_id

    c2 = convo.load_session(sid)                   # user_id=None → 内存
    assert c2 is not None
    assert c2.profile["primary"] == "美食/感官"


def test_fallback_reply_when_content_empty_and_no_tools(seed_beijing):
    """正文空且无工具 → 兜底要给实质内容（BUG-11 修复回归：兜底能看到本轮抽取）"""
    fake = FakeLLM(extract={}, replies=[text_msg("")])
    c1 = convo.chat(None, "嗯", llm=fake)
    assert "为什么" in c1.messages[-1]["content"] or "出去" in c1.messages[-1]["content"]

    fake2 = FakeLLM(extract={"primary": "恢复/逃离"}, replies=[text_msg("")])
    c2 = convo.chat(c1.session_id, "想放松", llm=fake2)
    assert "多久" in c2.messages[-1]["content"]


def test_stream_fragment_cleaned_from_reply(seed_beijing):
    """模型把流式碎片当正文吐出来 → 清掉"""
    fake = FakeLLM(
        extract={},
        replies=[text_msg('我查一下{"index":0,"finish_reason":"tool_calls"}')])
    conv = convo.chat(None, "你好", llm=fake)
    assert "finish_reason" not in conv.messages[-1]["content"]
