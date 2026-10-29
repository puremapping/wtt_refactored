#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对话里的「谁在答」标识

2026-10-29 阿哲指出：界面上完全看不出这句回复是哪个智能体说的。
同一句问话，本地引擎答和文旅局智能体答，性质完全不同
（前者是平台推荐，后者是官方口径），用户得能分辨。

这里验证后端把身份信息给全了：名字、机构、地区、类型。
"""
import pytest


class FakeLLM:
    def json_chat(self, messages, temperature=0.0):
        return {}

    def chat_raw(self, messages, temperature=0.3, model=None,
                 tools=None, tool_choice="auto"):
        class Msg:
            content = "本地引擎的回复"
            tool_calls = None
        return Msg()


@pytest.fixture()
def client(seed_beijing, monkeypatch):
    import app.services.conversation.orchestrator as orch
    import app.services.llm as llm_mod
    from fastapi.testclient import TestClient

    fake = FakeLLM()
    monkeypatch.setattr(llm_mod, "LLM", lambda: fake)
    monkeypatch.setattr(orch, "LLM", lambda: fake)

    from app.main import app
    return TestClient(app)


def _agent(region="北京", name="北京文旅bot", team="北京市文旅局",
           kind="builtin"):
    class A:
        pass

    a = A()
    a.region = region
    a.name = name
    a.team_name = team
    a.kind = kind
    a.id = "a1"
    a.description = ""

    def answer(q, context=None):
        from app.services.agent_runtime import Answer
        return Answer("智能体的回答")

    a.answer = answer
    return a


# ──────────────────────────────────────────────────────────────
# 本地引擎也有身份
# ──────────────────────────────────────────────────────────────

def test_local_engine_has_identity(client):
    """⚠️ 不能只在走到智能体时才给身份 ——
    本地引擎答的时候如果不标，用户就以为那也是平台在答，
    或者反过来，以为那句话是某家文旅局说的。"""
    r = client.post("/api/chat", json={"text": "随便聊聊"})
    src = r.json()["delegated_to"]

    assert src["kind"] == "local"
    assert src["name"] == "平台助手"
    assert src["team"] == "Where to Travel"


# ──────────────────────────────────────────────────────────────
# 智能体的身份字段齐全
# ──────────────────────────────────────────────────────────────

def test_delegated_identity_has_all_fields(client, monkeypatch):
    import app.services.agents as agent_svc
    monkeypatch.setattr(agent_svc, "find_region_agent",
                        lambda region, **kw: _agent(region=region))

    r = client.post("/api/chat", json={"text": "北京有什么好玩的"})
    src = r.json()["delegated_to"]

    assert src["name"] == "北京文旅bot"
    assert src["team"] == "北京市文旅局", "机构名不能丢 —— 用户要靠它判断可信度"
    assert src["region"] == "北京"
    assert src["kind"] == "builtin"


def test_external_agent_identity_keeps_kind(client, monkeypatch):
    """外部智能体要标成 external，前端据此用不同颜色 ——
    它是「外部系统在答」，跟平台自建的 builtin 性质不同"""
    import app.services.agents as agent_svc
    monkeypatch.setattr(
        agent_svc, "find_region_agent",
        lambda region, **kw: _agent(region="北京", name="北京Dify外站",
                                    team="北京市文旅局", kind="external"))

    r = client.post("/api/chat", json={"text": "北京有什么好玩的"})
    assert r.json()["delegated_to"]["kind"] == "external"


# ──────────────────────────────────────────────────────────────
# 来源跟着消息走（历史会话要能还原）
# ──────────────────────────────────────────────────────────────

def test_source_attached_to_message(client, monkeypatch):
    """⚠️ 只挂在本轮响应上是不够的 ——
    载入历史会话时走的是 /api/session/{id}，读的是 messages 数组。
    来源不写进消息里，历史对话就全变成无身份气泡。"""
    import app.services.agents as agent_svc
    import app.services.conversation.orchestrator as orch
    monkeypatch.setattr(agent_svc, "find_region_agent",
                        lambda region, **kw: _agent(region=region))

    conv = orch.chat("s-src", "北京有什么好玩的", llm=FakeLLM(),
                     current_itinerary=None, user_id=None,
                     region_agent=_agent())

    last = conv.messages[-1]
    assert last["role"] == "assistant"
    assert "source" in last, "来源没写进消息"
    assert last["source"]["name"] == "北京文旅bot"


def test_local_message_has_no_source(client):
    """本地引擎的回答不写 source —— 前端按默认（local）渲染即可，
    不必给每条消息都塞一份重复的「平台助手」"""
    import app.services.conversation.orchestrator as orch
    conv = orch.chat("s-local", "随便聊聊", llm=FakeLLM(),
                     current_itinerary=None, user_id=None, region_agent=None)

    assert "source" not in conv.messages[-1]


# ──────────────────────────────────────────────────────────────
# 不泄漏内部字段
# ──────────────────────────────────────────────────────────────

def test_delegated_marker_not_in_public_profile(client, monkeypatch):
    import app.services.agents as agent_svc
    monkeypatch.setattr(agent_svc, "find_region_agent",
                        lambda region, **kw: _agent(region=region))

    r = client.post("/api/chat", json={"text": "北京有什么好玩的"})
    assert "_delegated_to" not in r.json()["profile"]
