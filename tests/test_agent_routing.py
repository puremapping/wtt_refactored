#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主对话 → 地区智能体 的路由接管（P1 第 2 步）

分三层测：
  1. routing.py 的纯判定（不碰库、不调模型）
  2. orchestrator._try_delegate 的接管决策（假 LLM + 假智能体）
  3. routers/chat 的端到端（TestClient + 假 LLM + 真库）

⚠️ 全程零真实 GLM 调用、零真实外网请求。
"""
import pytest

from app.services.conversation.routing import (
    mentioned_region, should_delegate, wants_local_engine,
)


# ──────────────────────────────────────────────────────────────
# 假货
# ──────────────────────────────────────────────────────────────

class FakeAgent:
    """假的地区智能体 —— 只实现契约要求的属性"""

    kind = "builtin"

    def __init__(self, region="成都", text="成都有熊猫基地。",
                 degraded=False, raises=None):
        self.region = region
        self.name = f"{region}小助手"
        self.text = text
        self.degraded = degraded
        self.raises = raises
        self.calls = []

    def answer(self, question, context=None):
        from app.services.agent_runtime import Answer
        self.calls.append((question, context))
        if self.raises:
            raise self.raises
        return Answer(self.text, degraded=self.degraded,
                      reason="" if not self.degraded else "假降级")


# ──────────────────────────────────────────────────────────────
# 一、routing.py 纯判定
# ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("北京有什么好吃的", "北京"),
    ("朝阳区哪里好玩", "北京"),
    ("首都好玩吗", "北京"),
    ("上海外滩", None),
    ("", None),
    ("我想去玩", None),
])
def test_mentioned_region(seed_beijing, text, expected):
    """城市注册表能解析的情况"""
    assert mentioned_region(text) == expected


def test_mentioned_region_falls_back_to_agent_table(seed_beijing):
    """⚠️ 库里只有北京景区数据，但文旅局注册了「成都」智能体 ——
    只认城市注册表的话，成都智能体永远接不到话。
    路由层必须退一步去智能体表里找。
    """
    _seed_published_agent(team_id="t_cd", name="成都小助手", region="成都")
    assert mentioned_region("成都有什么好吃的") == "成都"
    assert mentioned_region("成都市哪里好玩") == "成都"


def test_mentioned_region_agent_fallback_prefers_longer_name(seed_beijing):
    """地区名互相包含时，长的优先

    ⚠️ 用「望京」而不是「海淀区」—— 后者城市注册表就能解析成北京，
       走不到智能体兜底这条路上，测不到想测的东西。
    """
    _seed_published_agent(team_id="t1", name="A", region="望京")
    _seed_published_agent(team_id="t2", name="B", region="望京街道")
    assert mentioned_region("望京街道哪里好") == "望京街道"


@pytest.mark.parametrize("text", [
    "帮我排一天的行程", "生成行程", "换一批", "再加一站", "把这个删掉",
])
def test_wants_local_engine_hits(text):
    assert wants_local_engine(text) is True


@pytest.mark.parametrize("text", [
    "成都有什么好吃的", "北京天气怎么样", "",
])
def test_wants_local_engine_misses(text):
    assert wants_local_engine(text) is False


def test_should_delegate_blocks_itinerary_intent(seed_beijing):
    """「北京帮我排个行程」—— 提到了城市，但本地引擎要干活，不交"""
    assert should_delegate("北京帮我排个行程") is None


def test_should_delegate_allows_pure_qa(seed_beijing):
    assert should_delegate("北京有什么好吃的") == "北京"


# ──────────────────────────────────────────────────────────────
# 二、_try_delegate 决策表
# ──────────────────────────────────────────────────────────────

def test_delegate_takes_over_when_all_conditions_met(seed_beijing):
    from app.services.conversation.models import Conversation
    from app.services.conversation.orchestrator import _try_delegate

    conv = Conversation(session_id="s1", created_at="2026-10-29T00:00:00")
    conv.turn = 1
    agent = FakeAgent(region="北京", text="北京烤鸭必吃。")

    out = _try_delegate(conv, "北京有什么好吃的", "本地回复", [], False, agent)
    assert out is not None
    reply, tool_calls = out
    assert reply == "北京烤鸭必吃。"
    assert tool_calls == []
    assert conv.profile["_delegated_to"] == "北京小助手"


def test_delegate_skipped_without_agent(seed_beijing):
    from app.services.conversation.models import Conversation
    from app.services.conversation.orchestrator import _try_delegate

    conv = Conversation(session_id="s1", created_at="x")
    conv.turn = 1
    assert _try_delegate(conv, "北京有什么好吃的", "本地", [], False, None) is None


def test_delegate_skipped_when_local_engine_has_tool_calls(seed_beijing):
    """本地引擎要排行程 —— 智能体没有行程能力，绝不能抢"""
    from app.services.conversation.models import Conversation
    from app.services.conversation.orchestrator import _try_delegate

    conv = Conversation(session_id="s1", created_at="x")
    conv.turn = 1
    agent = FakeAgent(region="北京")
    tc = [{"name": "generate_itinerary", "args": {}}]

    assert _try_delegate(conv, "北京有什么好吃的", "本地", tc, False, agent) is None


def test_delegate_skipped_when_text_has_no_region(seed_beijing):
    """用户这轮没提城市 —— 智能体没有立足点"""
    from app.services.conversation.models import Conversation
    from app.services.conversation.orchestrator import _try_delegate

    conv = Conversation(session_id="s1", created_at="x")
    conv.turn = 1
    agent = FakeAgent(region="北京")

    assert _try_delegate(conv, "有什么好吃的", "本地", [], False, agent) is None


def test_delegate_skipped_when_region_mismatch(seed_beijing):
    """路由给的是北京智能体，但用户说的是朝阳区以外的城市 —— 不匹配就不接"""
    from app.services.conversation.models import Conversation
    from app.services.conversation.orchestrator import _try_delegate

    conv = Conversation(session_id="s1", created_at="x")
    conv.turn = 1
    agent = FakeAgent(region="成都")     # 用户说的是北京

    assert _try_delegate(conv, "北京有什么好吃的", "本地", [], False, agent) is None


def test_delegate_falls_back_on_degraded_agent(seed_beijing):
    """⚠️ 智能体答不出来时保留本地回复 —— 不能给用户空洞兜底"""
    from app.services.conversation.models import Conversation
    from app.services.conversation.orchestrator import _try_delegate

    conv = Conversation(session_id="s1", created_at="x")
    conv.turn = 1
    agent = FakeAgent(region="北京", text="", degraded=True)

    assert _try_delegate(conv, "北京有什么好吃的", "本地回复", [], False, agent) is None
    assert "_delegated_to" not in conv.profile


def test_delegate_falls_back_on_agent_exception(seed_beijing):
    from app.services.conversation.models import Conversation
    from app.services.conversation.orchestrator import _try_delegate

    conv = Conversation(session_id="s1", created_at="x")
    conv.turn = 1
    agent = FakeAgent(region="北京", raises=RuntimeError("boom"))

    assert _try_delegate(conv, "北京有什么好吃的", "本地回复", [], False, agent) is None


def test_delegate_passes_context_to_agent(seed_beijing):
    from app.services.conversation.models import Conversation
    from app.services.conversation.orchestrator import _try_delegate

    conv = Conversation(session_id="s1", created_at="x")
    conv.turn = 3
    conv.profile = {"destination": "北京"}
    agent = FakeAgent(region="北京")

    _try_delegate(conv, "北京有什么好吃的", "本地", [], False, agent)
    q, ctx = agent.calls[0]
    assert q == "北京有什么好吃的"
    assert ctx["turn"] == 3
    assert ctx["profile"]["destination"] == "北京"


# ──────────────────────────────────────────────────────────────
# 三、端到端：POST /api/chat
# ──────────────────────────────────────────────────────────────

class FakeLLMFull:
    """模拟编排层要的三次调用：json_chat / chat_raw(带 tools) / chat_raw(无 tools)"""

    def __init__(self, reply_text="本地引擎的回复"):
        self.reply_text = reply_text
        self.json_calls = 0
        self.raw_calls = 0

    def json_chat(self, messages, temperature=0.0):
        self.json_calls += 1
        return {}

    def chat_raw(self, messages, temperature=0.3, model=None,
                 tools=None, tool_choice="auto"):
        self.raw_calls += 1

        class Msg:
            content = self.reply_text
            tool_calls = None

        return Msg()


@pytest.fixture()
def client(seed_beijing, monkeypatch):
    import app.services.conversation.orchestrator as orch
    from app.services import llm as llm_mod
    from fastapi.testclient import TestClient

    fake = FakeLLMFull()
    monkeypatch.setattr(llm_mod, "LLM", lambda: fake)

    # orchestrator 里 `llm = llm or LLM()` —— LLM 是模块级导入的，要单独替换
    monkeypatch.setattr(orch, "LLM", lambda: fake)

    from app.main import app
    c = TestClient(app)
    c.fake_llm = fake
    return c


def _seed_published_agent(team_id="t1", name="北京小助手",
                          region="北京", prompt="熟悉北京"):
    from app.services import agents as agent_svc
    import sqlite3
    from app.core import db as db_module

    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute("INSERT INTO teams (id,name,region,owner_id,created_at) "
                 "VALUES (?,?,?,?,datetime('now'))",
                 (team_id, "北京市文旅局", "北京", "owner-" + team_id))
    conn.commit()
    conn.close()

    aid = agent_svc.create_agent(team_id, "u1", name=name, region=region,
                                 prompt=prompt, kind="builtin")
    assert agent_svc.publish_agent(aid, team_id)["ok"] is True
    return aid


def test_api_chat_delegates_to_region_agent(client, monkeypatch):
    """有已发布智能体 + 用户提到该地区 → 回复来自智能体"""
    _seed_published_agent()

    import app.services.agents as agent_svc
    holder = {"ai": 0}

    class CountingAgent(FakeAgent):
        def answer(self, question, context=None):
            holder["ai"] += 1
            return super().answer(question, context)

    monkeypatch.setattr(agent_svc, "find_region_agent",
                        lambda region, **kw: CountingAgent(
                            region=region, text="故宫要提前预约。"))

    r = client.post("/api/chat", json={"text": "北京有什么好玩的"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "故宫要提前预约。"
    assert body["delegated_to"] == "北京小助手"
    assert holder["ai"] == 1


def test_api_chat_keeps_local_reply_without_agent(client):
    """没有已发布智能体 → 本地引擎照常回复"""
    r = client.post("/api/chat", json={"text": "北京有什么好玩的"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "本地引擎的回复"
    assert "delegated_to" not in body


def test_api_chat_keeps_local_reply_when_agent_errors(client, monkeypatch):
    """智能体爆炸 → 不影响对话，兜回本地回复"""
    _seed_published_agent()

    import app.services.agents as agent_svc
    monkeypatch.setattr(
        agent_svc, "find_region_agent",
        lambda region, **kw: FakeAgent(region=region, raises=RuntimeError("炸了")))

    r = client.post("/api/chat", json={"text": "北京有什么好玩的"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "本地引擎的回复"
    assert "delegated_to" not in body


def test_api_chat_skips_agent_for_itinerary_request(client, monkeypatch):
    """用户要排行程 → 不交给智能体"""
    _seed_published_agent()

    import app.services.agents as agent_svc
    called = {"n": 0}

    def spy(region, **kw):
        called["n"] += 1
        return FakeAgent(region=region, text="不该出现")

    monkeypatch.setattr(agent_svc, "find_region_agent", spy)

    client.post("/api/chat", json={"text": "北京帮我排个一天行程"})
    # should_delegate 已经在入口拦掉，find_region_agent 根本不该被调用
    assert called["n"] == 0


def test_api_chat_swallows_agent_lookup_error(client, monkeypatch):
    """查智能体这一步报错 → 不能影响基础对话"""
    import app.services.agents as agent_svc

    def boom(region, **kw):
        raise RuntimeError("库里炸了")

    monkeypatch.setattr(agent_svc, "find_region_agent", boom)

    r = client.post("/api/chat", json={"text": "北京有什么好玩的"})
    assert r.status_code == 200
    assert r.json()["reply"] == "本地引擎的回复"


def test_delegated_to_hidden_from_profile(client, monkeypatch):
    """_delegated_to 是内部字段，不能漏进对外的 profile"""
    _seed_published_agent()
    import app.services.agents as agent_svc
    monkeypatch.setattr(agent_svc, "find_region_agent",
                        lambda region, **kw: FakeAgent(region=region, text="答"))

    r = client.post("/api/chat", json={"text": "北京有什么好玩的"})
    body = r.json()
    assert body["delegated_to"] == "北京小助手"
    assert "_delegated_to" not in body["profile"]


def test_delegated_to_cleared_on_next_turn(client, monkeypatch):
    """⚠️ 接管标记是**每轮结论**，不是会话状态。

    2026-10-29 真实 HTTP 端到端抓到的泄漏：第一轮交给北京智能体后，
    第二轮用户换话题（没提城市），delegated_to 仍然显示北京智能体 ——
    连带把本地引擎的正常回答误标成智能体回答。
    """
    _seed_published_agent()
    import app.services.agents as agent_svc
    monkeypatch.setattr(agent_svc, "find_region_agent",
                        lambda region, **kw: FakeAgent(region=region, text="智能体回答"))

    r1 = client.post("/api/chat", json={"text": "北京有什么好玩的"})
    assert r1.json()["delegated_to"] == "北京小助手"
    sid = r1.json()["session_id"]

    # 第二轮：没提城市 → 本地引擎，不该残留标记
    r2 = client.post("/api/chat", json={"text": "有什么推荐的", "session_id": sid})
    body2 = r2.json()
    assert "delegated_to" not in body2, "上一轮的接管标记泄漏到了这一轮"
    assert body2["reply"] == "本地引擎的回复"


def test_delegated_to_cleared_when_switching_to_itinerary(client, monkeypatch):
    """第一轮交给智能体，第二轮要排行程 → 走本地引擎且不残留标记"""
    _seed_published_agent()
    import app.services.agents as agent_svc
    monkeypatch.setattr(agent_svc, "find_region_agent",
                        lambda region, **kw: FakeAgent(region=region, text="智能体回答"))

    r1 = client.post("/api/chat", json={"text": "北京有什么好玩的"})
    sid = r1.json()["session_id"]
    assert r1.json()["delegated_to"] == "北京小助手"

    r2 = client.post("/api/chat",
                     json={"text": "北京帮我排一天的行程", "session_id": sid})
    assert "delegated_to" not in r2.json()
