#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""行程生成路径的端到端回归（/api/chat 里的 generate_itinerary 分支）

## 为什么单独测这条

`user_text` 未定义这种 NameError 在 routers/chat.py 里被
`except Exception as e: result["action_error"] = f"生成失败: {e}"` 吞掉 ——
接口照样 200，只是多一个 action_error 字段。现象是「点了生成按钮，卡片不出来」，
而单测和 type checker 都看不见。

所以这里显式断言 action_error 不存在、itinerary 真的出来了。
"""
import pytest


class FakeLLMForItinerary:
    """第一轮就要求生成行程的模型"""

    def __init__(self):
        self.calls = 0

    def json_chat(self, messages, temperature=0.0):
        return {"destination": "北京", "hours": 6}

    def chat_raw(self, messages, temperature=0.3, model=None,
                 tools=None, tool_choice="auto"):
        self.calls += 1

        class Msg:
            content = ""
            tool_calls = None

        # 第一次：模拟模型直接请求生成行程
        if self.calls == 1:
            class TC:
                class function:
                    name = "generate_itinerary"
                    arguments = '{"hours": 6}'
            m = Msg()
            m.tool_calls = [TC()]
            return m
        return Msg()


@pytest.fixture()
def client(seed_beijing, monkeypatch):
    import app.services.conversation.orchestrator as orch
    import app.services.llm as llm_mod
    from fastapi.testclient import TestClient

    fake = FakeLLMForItinerary()
    monkeypatch.setattr(llm_mod, "LLM", lambda: fake)
    monkeypatch.setattr(orch, "LLM", lambda: fake)

    from app.main import app
    c = TestClient(app)
    c.fake = fake
    yield c


def test_generate_itinerary_has_no_action_error(client):
    """⚠️ 回归：曾经因为用了未定义的 user_text 变量，这里永远走异常分支"""
    r = client.post("/api/chat", json={"text": "北京帮我排一天的行程"})
    assert r.status_code == 200
    body = r.json()

    assert "action_error" not in body, \
        f"生成行程走了异常分支：{body.get('action_error')}"
    assert body.get("action") == "generate", "没有真的生成行程"
    assert body.get("itinerary"), "itinerary 字段缺失"
    stops = body["itinerary"].get("stops") or []
    assert stops, "行程没有任何站点"


def test_generate_itinerary_attractions_are_in_db(client):
    """生成的站点必须是库里真实存在的景区"""
    import sqlite3

    from app.core import db as db_module

    r = client.post("/api/chat", json={"text": "北京帮我排一天的行程"})
    body = r.json()
    stops = body.get("itinerary", {}).get("stops") or []

    conn = sqlite3.connect(db_module.DB_PATH)
    db_names = {row[0] for row in conn.execute("SELECT name FROM attractions")}
    conn.close()

    for s in stops:
        assert s["name"] in db_names, f"行程里有库中不存在的景区：{s['name']}"


def test_itinerary_not_delegated_to_agent(seed_beijing, monkeypatch):
    """生成行程时不该被地区智能体接管（智能体没有行程能力）"""
    import app.services.agents as agent_svc
    import app.services.conversation.orchestrator as orch
    import app.services.llm as llm_mod
    from fastapi.testclient import TestClient

    fake = FakeLLMForItinerary()
    monkeypatch.setattr(llm_mod, "LLM", lambda: fake)
    monkeypatch.setattr(orch, "LLM", lambda: fake)

    called = {"n": 0}

    class FakeAgent:
        region = "北京"
        name = "北京小助手"
        kind = "builtin"

        def answer(self, q, context=None):
            called["n"] += 1
            from app.services.agent_runtime import Answer
            return Answer("不该出现")

    monkeypatch.setattr(agent_svc, "find_region_agent",
                        lambda region, **kw: FakeAgent())

    from app.main import app
    c = TestClient(app)
    r = c.post("/api/chat", json={"text": "北京帮我排一天的行程"})
    body = r.json()

    assert called["n"] == 0, "排行程时智能体被调用了"
    assert body["delegated_to"]["kind"] == "local"
    assert body.get("itinerary"), "行程没生成"


# ──────────────────────────────────────────────────────────────
# 意图判定：「排一天的行程」这种自然说法必须被认出来
# ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "北京帮我排一天的行程",
    "帮我排一天的行程",
    "排个两天的",
    "排 6 小时",
    "一天行程怎么走",
    "生成行程",
])
def test_generate_intent_accepts_natural_phrasing(text):
    """⚠️ 回归：白名单只有「排个」「排一下」，不含「排一天的行程」，
    导致最自然的中文请求被判成没意图，行程永远生成不出来。"""
    from app.services.conversation.policies import _is_generate_intent
    assert _is_generate_intent(text) is True


@pytest.mark.parametrize("text", [
    "北京有什么好玩的",
    "排队要多久",          # 「排」不能单独当触发词
    "我想去故宫",
    "成都有什么好吃的",
])
def test_generate_intent_rejects_non_generate(text):
    from app.services.conversation.policies import _is_generate_intent
    assert _is_generate_intent(text) is False
