#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双轨智能体抽象（app/services/agent_runtime.py）

核心验收点：**两条轨对调用方完全同形**。
所以这里大量测试是「同一个断言，两个实现都过」。
全程零真实 LLM 调用、零真实网络请求 —— llm / opener 都是注入的假货。
"""
import json
import urllib.error

import pytest

from app.services import agents as agent_svc
from app.services.agent_runtime import (
    Answer, BuiltinAgent, ExternalAgent, build_agent,
)


# ──────────────────────────────────────────────────────────────
# 假货
# ──────────────────────────────────────────────────────────────

class FakeLLM:
    """记录收到的 messages，返回预设文本"""

    def __init__(self, reply="成都有熊猫基地和宽窄巷子。", raises=None):
        self.reply = reply
        self.raises = raises
        self.calls = []

    def chat(self, messages, temperature=0.3, model=None, force_json=False):
        self.calls.append(messages)
        if self.raises:
            raise self.raises
        return self.reply


def fake_opener_factory(response, captured=None, raises=None):
    """返回一个假的 HTTP 打开器，记录 (url, payload, headers, timeout)"""

    def opener(url, payload, headers, timeout):
        if captured is not None:
            captured.append({"url": url, "payload": payload,
                             "headers": headers, "timeout": timeout})
        if raises:
            raise raises
        if isinstance(response, bytes):
            return response
        return response.encode("utf-8")

    return opener


def row_builtin(**over):
    base = {
        "id": "a1", "team_id": "t1", "team_name": "成都市文旅局",
        "name": "成都小助手", "region": "成都",
        "description": "", "prompt": "热情好客，熟悉成都美食",
        "status": "published", "kind": "builtin",
        "endpoint": None, "auth": None, "external_id": None,
    }
    base.update(over)
    return base


def row_external(**over):
    base = row_builtin(id="a2", team_id="t2", team_name="上海文旅局",
                       name="上海小助手", region="上海",
                       prompt=None, kind="external",
                       endpoint="https://example.com/chat")
    base.update(over)
    return base


# ──────────────────────────────────────────────────────────────
# 一、工厂：把行变成对象
# ──────────────────────────────────────────────────────────────

def test_build_builtin():
    a = build_agent(row_builtin(), llm=FakeLLM())
    assert isinstance(a, BuiltinAgent)
    assert a.kind == "builtin"
    assert a.region == "成都"
    assert a.team_name == "成都市文旅局"


def test_build_external():
    a = build_agent(row_external(), opener=fake_opener_factory("{}"))
    assert isinstance(a, ExternalAgent)
    assert a.kind == "external"
    assert a.endpoint == "https://example.com/chat"


def test_build_skips_missing_region():
    """没有地区就没法路由 —— 宁可跳过，也不要把路由不了的对象交出去"""
    assert build_agent(row_builtin(region=None)) is None
    assert build_agent(row_builtin(region="   ")) is None


def test_build_skips_missing_id():
    assert build_agent(row_builtin(id="")) is None
    assert build_agent({}) is None
    assert build_agent(None) is None


def test_build_skips_unknown_kind():
    """数据脏了（比如手工改了库）不能瞎猜成 builtin"""
    assert build_agent(row_builtin(kind="coze")) is None


def test_build_defaults_to_builtin():
    """老库 ALTER 前的行 kind 可能是 None —— 按 builtin 处理"""
    assert isinstance(build_agent(row_builtin(kind=None), llm=FakeLLM()),
                      BuiltinAgent)


# ──────────────────────────────────────────────────────────────
# 二、两条轨同形（这是第 1 步的核心验收）
# ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("make_agent", [
    lambda: build_agent(row_builtin(), llm=FakeLLM("成都很巴适。")),
    lambda: build_agent(row_external(region="成都"),
                        opener=fake_opener_factory('{"answer": "成都很巴适。"}')),
], ids=["builtin", "external"])
def test_both_kinds_have_same_contract(make_agent):
    """调用方不需要知道是哪种轨 —— 属性一样、方法一样、返回类型一样"""
    a = make_agent()
    for attr in ("id", "name", "region", "team_id", "team_name", "kind"):
        assert hasattr(a, attr), attr
    assert callable(a.answer)

    res = a.answer("成都有什么好玩的？")
    assert isinstance(res, Answer)
    assert res.text == "成都很巴适。"
    assert res.degraded is False


@pytest.mark.parametrize("make_agent", [
    lambda: build_agent(row_builtin(), llm=FakeLLM("x")),
    lambda: build_agent(row_external(), opener=fake_opener_factory("x")),
], ids=["builtin", "external"])
def test_both_kinds_handle_empty_question(make_agent):
    res = make_agent().answer("   ")
    assert res.degraded is True
    assert res.reason


# ──────────────────────────────────────────────────────────────
# 三、builtin 轨
# ──────────────────────────────────────────────────────────────

def test_builtin_passes_prompt_into_system_message():
    llm = FakeLLM("答")
    a = build_agent(row_builtin(), llm=llm)
    a.answer("有什么好吃的？")

    msgs = llm.calls[0]
    assert msgs[0]["role"] == "system"
    assert "热情好客，熟悉成都美食" in msgs[0]["content"]   # 人设进来了
    assert "成都小助手" in msgs[0]["content"]               # 名字进来了
    assert "成都市文旅局" in msgs[0]["content"]             # 机构进来了
    assert msgs[1] == {"role": "user", "content": "有什么好吃的？"}


def test_builtin_llm_error_degrades_not_raises():
    """模型挂了不该拖垮主对话 —— 降级返回，reasons 里留痕"""
    a = build_agent(row_builtin(), llm=FakeLLM(raises=RuntimeError("额度用完")))
    res = a.answer("你好")
    assert res.degraded is True
    assert "额度用完" in res.reason


def test_builtin_empty_reply_degrades():
    a = build_agent(row_builtin(), llm=FakeLLM("   "))
    res = a.answer("你好")
    assert res.degraded is True
    assert res.reason == "模型返回空"


def test_builtin_without_prompt_degrades():
    """发布时会被拦，但万一数据是手改的，运行期也要兜住"""
    a = build_agent(row_builtin(prompt=None), llm=FakeLLM("答"))
    res = a.answer("你好")
    assert res.degraded is True
    assert "人设" in res.reason


# ──────────────────────────────────────────────────────────────
# 四、external 轨
# ──────────────────────────────────────────────────────────────

def test_external_posts_expected_payload():
    cap = []
    a = build_agent(row_external(), opener=fake_opener_factory("{}", cap))
    a.answer("外滩怎么去？", context={"city": "上海"})

    assert len(cap) == 1
    got = cap[0]
    assert got["url"] == "https://example.com/chat"
    assert got["payload"] == {"question": "外滩怎么去？", "region": "上海",
                              "context": {"city": "上海"}}
    assert got["headers"]["Content-Type"] == "application/json"
    assert got["timeout"] == ExternalAgent.TIMEOUT


def test_external_sends_auth_header_when_set():
    cap = []
    a = build_agent(row_external(auth="Bearer sk-xxx"),
                    opener=fake_opener_factory("{}", cap))
    a.answer("你好")
    assert cap[0]["headers"]["Authorization"] == "Bearer sk-xxx"


def test_external_omits_auth_header_when_empty():
    cap = []
    a = build_agent(row_external(auth=None),
                    opener=fake_opener_factory("{}", cap))
    a.answer("你好")
    assert "Authorization" not in cap[0]["headers"]


@pytest.mark.parametrize("raw,expected", [
    ('{"answer": "熊猫基地必去"}', "熊猫基地必去"),
    ('{"text": "熊猫基地必去"}', "熊猫基地必去"),
    ('{"content": "熊猫基地必去"}', "熊猫基地必去"),
    ('{"reply": "熊猫基地必去"}', "熊猫基地必去"),
    ('"熊猫基地必去"', "熊猫基地必去"),
    ("熊猫基地必去", "熊猫基地必去"),           # 纯文本
    ("  熊猫基地必去  ", "熊猫基地必去"),       # 去空白
], ids=["answer", "text", "content", "reply", "json-string", "plain", "space"])
def test_external_parses_common_response_shapes(raw, expected):
    """外面的人写的东西不可控 —— 常见几种返回都得吃得下"""
    a = build_agent(row_external(), opener=fake_opener_factory(raw))
    res = a.answer("去哪玩")
    assert res.text == expected
    assert res.degraded is False


def test_external_empty_answer_field_falls_through_to_text():
    """{"answer": ""} 这种半残返回，别直接判死，退到原始文本"""
    a = build_agent(row_external(), opener=fake_opener_factory('{"answer": ""}'))
    res = a.answer("去哪玩")
    assert res.degraded is False
    assert res.text == '{"answer": ""}'


def test_external_timeout_degrades():
    a = build_agent(row_external(),
                    opener=fake_opener_factory("", raises=TimeoutError("timed out")))
    res = a.answer("你好")
    assert res.degraded is True
    assert "失败" in res.reason


def test_external_http_error_degrades_with_code():
    err = urllib.error.HTTPError("https://example.com", 502, "Bad Gateway", {}, None)
    a = build_agent(row_external(), opener=fake_opener_factory("", raises=err))
    res = a.answer("你好")
    assert res.degraded is True
    assert "502" in res.reason


def test_external_empty_body_degrades():
    a = build_agent(row_external(), opener=fake_opener_factory("   "))
    res = a.answer("你好")
    assert res.degraded is True


def test_external_without_endpoint_degrades():
    """发布时会被拦，但运行期要兜住"""
    a = build_agent(row_external(endpoint=None), opener=fake_opener_factory("x"))
    res = a.answer("你好")
    assert res.degraded is True
    assert "调用地址" in res.reason


# ──────────────────────────────────────────────────────────────
# 五、准入检查（publish 分流）
# ──────────────────────────────────────────────────────────────

def test_publish_check_builtin_needs_prompt_and_region():
    assert agent_svc._publish_problems(
        {"kind": "builtin", "region": "成都", "prompt": "人设"}) == []

    p = agent_svc._publish_problems({"kind": "builtin", "region": "", "prompt": "人设"})
    assert any("覆盖地区" in x for x in p)

    p = agent_svc._publish_problems({"kind": "builtin", "region": "成都", "prompt": ""})
    assert any("人设" in x for x in p)


def test_publish_check_external_needs_endpoint_not_prompt():
    """外部轨不要求 prompt —— 人设是对方那边的事"""
    assert agent_svc._publish_problems(
        {"kind": "external", "region": "上海", "prompt": None,
         "endpoint": "https://x/y"}) == []

    p = agent_svc._publish_problems(
        {"kind": "external", "region": "上海", "endpoint": ""})
    assert any("调用地址" in x for x in p)


def test_publish_check_external_still_needs_region():
    p = agent_svc._publish_problems(
        {"kind": "external", "region": "", "endpoint": "https://x/y"})
    assert any("覆盖地区" in x for x in p)


def test_publish_check_rejects_unknown_kind():
    p = agent_svc._publish_problems(
        {"kind": "coze", "region": "上海", "prompt": "x", "endpoint": "https://x/y"})
    assert any("未知" in x for x in p)


# ──────────────────────────────────────────────────────────────
# 六、落库：建 → 发布 → 取出来是可调对象（真库，tmp_db）
# ──────────────────────────────────────────────────────────────

def _seed_team(conn, team_id="t1", name="成都市文旅局"):
    conn.execute(
        "INSERT INTO teams (id, name, region, owner_id, created_at) "
        "VALUES (?,?,?,?,datetime('now'))",
        (team_id, name, "成都", f"owner-{team_id}"))


def test_migration_adds_kind_columns(tmp_db):
    """tmp_db 走的是 init_db() —— 新库应当是新建表而非 ALTER，三列都在"""
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(agents)")}
    conn.close()
    assert {"kind", "endpoint", "auth"} <= cols


def test_create_and_route_builtin_end_to_end(tmp_db):
    """建 → 发布 → find_region_agent 拿到可调用对象 → answer() 走得通"""
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    _seed_team(conn)
    conn.commit()
    conn.close()

    aid = agent_svc.create_agent(
        "t1", "u1", name="成都小助手", region="成都",
        prompt="熟悉成都美食", kind="builtin")
    assert agent_svc.publish_agent(aid, "t1")["ok"] is True

    agent = agent_svc.find_region_agent("成都市", llm=FakeLLM("宽窄巷子不错。"))
    assert agent is not None
    assert agent.kind == "builtin"
    assert agent.answer("去哪玩").text == "宽窄巷子不错。"


def test_create_and_route_external_end_to_end(tmp_db):
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    _seed_team(conn, "t2", "上海文旅局")
    conn.commit()
    conn.close()

    aid = agent_svc.create_agent(
        "t2", "u2", name="上海小助手", region="上海",
        kind="external", endpoint="https://example.com/chat",
        auth="Bearer k")
    assert agent_svc.publish_agent(aid, "t2")["ok"] is True

    agent = agent_svc.find_region_agent(
        "上海", opener=fake_opener_factory('{"answer": "外滩夜景别错过。"}'))
    assert agent is not None
    assert agent.kind == "external"
    assert agent.answer("去哪玩").text == "外滩夜景别错过。"


def test_create_external_without_endpoint_raises(tmp_db):
    with pytest.raises(ValueError, match="调用地址"):
        agent_svc.create_agent("t1", "u1", name="x", region="上海", kind="external")


def test_create_rejects_unknown_kind(tmp_db):
    with pytest.raises(ValueError, match="未知"):
        agent_svc.create_agent("t1", "u1", name="x", region="上海", kind="coze")


def test_publish_rejects_unroutable_agent(tmp_db):
    """没地区就发布不了 —— 这正是「发布按钮是摆设」的一半原因"""
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    _seed_team(conn)
    conn.commit()
    conn.close()

    aid = agent_svc.create_agent("t1", "u1", name="无名", prompt="人设")
    r = agent_svc.publish_agent(aid, "t1")
    assert r["ok"] is False
    assert "覆盖地区" in r["error"]


def test_find_region_agent_returns_none_when_no_match(tmp_db):
    assert agent_svc.find_region_agent("广州") is None


def test_find_region_agent_skips_draft(tmp_db):
    """draft 不该被路由到"""
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    _seed_team(conn)
    conn.commit()
    conn.close()

    agent_svc.create_agent("t1", "u1", name="成都小助手", region="成都",
                           prompt="人设")
    assert agent_svc.find_region_agent("成都", llm=FakeLLM("x")) is None
