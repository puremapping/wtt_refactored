#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智能体查库取事实（app/services/agent_facts.py）

核心：模型不能自由发挥，只能用官方名录里有的地方。
"""
import pytest

from app.services.agent_facts import (
    MAX_FACTS, district_of, fetch_facts, format_facts,
)


def _seed(conn, rows):
    """rows: [(name, level, district)]"""
    for i, (name, level, district) in enumerate(rows, start=1):
        conn.execute(
            "INSERT INTO attractions (name, level, district, city) "
            "VALUES (?,?,?,?)", (name, level, district, "成都"))


@pytest.fixture()
def cd_db(tmp_db):
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    _seed(conn, [
        ("青城山--都江堰旅游景区", "5A", "都江堰市"),
        ("安仁古镇景区", "5A", "大邑县"),
        ("宽窄巷子", "3A", "青羊区"),
        ("文殊院", "4A", "青羊区"),
        ("杜甫草堂博物馆", "4A", "青羊区"),
        ("熊猫基地", "4A", "成华区"),
        ("东郊记忆", "4A", "成华区"),
    ])
    conn.commit()
    conn.close()
    return tmp_db


# ──────────────────────────────────────────────────────────────
# 区县识别
# ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("青羊区有什么好玩的", "青羊区"),
    ("我在成华", "成华区"),            # 去后缀也能认
    ("都江堰那边怎么样", "都江堰市"),
    ("成都有什么", None),
    ("", None),
])
def test_district_of(cd_db, text, expected):
    assert district_of(text, "成都") == expected


def test_district_of_ignores_other_city(cd_db):
    """北京没有青羊区，别把成都的区名套到北京上"""
    assert district_of("青羊区有什么", "北京") is None


# ──────────────────────────────────────────────────────────────
# 取事实
# ──────────────────────────────────────────────────────────────

def test_fetch_facts_by_district(cd_db):
    facts = fetch_facts("成都", "青羊区有什么好玩的")
    names = [f["name"] for f in facts]
    assert set(names) == {"宽窄巷子", "文殊院", "杜甫草堂博物馆"}
    assert all(f["district"] == "青羊区" for f in facts)


def test_fetch_facts_citywide_when_no_district(cd_db):
    facts = fetch_facts("成都", "成都有什么好玩的")
    assert len(facts) == 7
    # 等级高的排前面
    assert facts[0]["level"] == "5A"


def test_fetch_facts_respects_limit(cd_db):
    facts = fetch_facts("成都", "成都有什么", limit=3)
    assert len(facts) == 3


def test_fetch_facts_falls_back_to_city_when_district_empty(tmp_db):
    """用户提到的区县在库里一个 5A/4A 都没有 → 退回全市，别给空答复"""
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    _seed(conn, [("杜甫草堂博物馆", "4A", "青羊区")])
    conn.commit()
    conn.close()

    facts = fetch_facts("成都", "龙泉驿区有什么")
    assert [f["name"] for f in facts] == ["杜甫草堂博物馆"]


def test_fetch_facts_unknown_city_returns_empty(tmp_db):
    assert fetch_facts("火星", "有什么") == []


def test_fetch_facts_empty_city(tmp_db):
    assert fetch_facts("", "有什么") == []


def test_fetch_facts_no_cross_city_leak(tmp_db):
    """⚠️ 多城市隔离：成都的景区不能出现在北京的清单里"""
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    conn.execute("INSERT INTO attractions (name,level,district,city) "
                 "VALUES ('故宫','5A','东城区','北京')")
    conn.execute("INSERT INTO attractions (name,level,district,city) "
                 "VALUES ('宽窄巷子','3A','青羊区','成都')")
    conn.commit()
    conn.close()

    bj = [f["name"] for f in fetch_facts("北京", "有什么")]
    cd = [f["name"] for f in fetch_facts("成都", "有什么")]
    assert bj == ["故宫"]
    assert cd == ["宽窄巷子"]


# ──────────────────────────────────────────────────────────────
# 格式化：必须带「只能用这些」的约束
# ──────────────────────────────────────────────────────────────

def test_format_facts_lists_names(cd_db):
    text = format_facts(fetch_facts("成都", "青羊区有什么"))
    assert "宽窄巷子" in text
    assert "文殊院" in text
    assert "官方" in text          # 标注数据来源，模型才知道这是权威清单


def test_format_facts_empty_returns_empty_string():
    assert format_facts([]) == ""


def test_format_facts_marks_free_tickets(tmp_db):
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    conn.execute("INSERT INTO attractions (name,level,district,city,ticket_free) "
                 "VALUES ('人民公园','3A','青羊区','成都',1)")
    conn.execute("INSERT INTO attractions (name,level,district,city,ticket_free) "
                 "VALUES ('武侯祠','4A','武侯区','成都',0)")
    conn.commit()
    conn.close()

    text = format_facts(fetch_facts("成都", "有什么"))
    assert "免费" in text
    assert "收费" in text


# ──────────────────────────────────────────────────────────────
# 接进 BuiltinAgent：模型收到的 prompt 里有事实
# ──────────────────────────────────────────────────────────────

class FakeLLM:
    def __init__(self, reply="好"):
        self.reply = reply
        self.calls = []

    def chat(self, messages, temperature=0.3, model=None, force_json=False):
        self.calls.append(messages)
        return self.reply


def test_builtin_agent_prompt_contains_db_facts(cd_db):
    from app.services.agent_runtime import build_agent

    llm = FakeLLM("宽窄巷子不错。")
    agent = build_agent({
        "id": "a1", "team_id": "t1", "team_name": "成都市文旅局",
        "name": "成都小助手", "region": "成都", "prompt": "热情",
        "status": "published", "kind": "builtin",
    }, llm=llm)

    agent.answer("青羊区有什么好玩的")

    system = llm.calls[0][0]["content"]
    assert "宽窄巷子" in system, "景点清单没进 prompt"
    assert "文殊院" in system
    assert "只能用上面清单" in system, "缺防幻觉约束"


def test_builtin_agent_without_data_still_answers(tmp_db):
    """库里没数据时退化成自由发挥，不能崩"""
    from app.services.agent_runtime import build_agent

    llm = FakeLLM("随便答。")
    agent = build_agent({
        "id": "a1", "team_id": "t1", "team_name": "火星文旅局",
        "name": "火星助手", "region": "火星", "prompt": "热情",
        "status": "published", "kind": "builtin",
    }, llm=llm)

    res = agent.answer("火星有什么")
    assert res.degraded is False
    assert res.text == "随便答。"
    # 没有事实块，不该出现「只能用这些」的硬约束
    assert "只能用上面清单" not in llm.calls[0][0]["content"]


def test_builtin_agent_survives_facts_db_error(cd_db, monkeypatch):
    """查库炸了 → 退化成自由发挥，不能让整个回答失败"""
    import app.services.agent_facts as facts_mod
    from app.services.agent_runtime import build_agent

    def boom(*a, **kw):
        raise RuntimeError("库里炸了")

    monkeypatch.setattr(facts_mod, "fetch_facts", boom)

    llm = FakeLLM("还是能答。")
    agent = build_agent({
        "id": "a1", "team_id": "t1", "team_name": "成都市文旅局",
        "name": "成都小助手", "region": "成都", "prompt": "热情",
        "status": "published", "kind": "builtin",
    }, llm=llm)

    res = agent.answer("成都有什么")
    assert res.degraded is False
    assert res.text == "还是能答。"


def test_external_agent_unaffected(cd_db):
    """外部轨自己管自己的数据，平台不喂事实"""
    from app.services.agent_runtime import build_agent

    captured = []

    def opener(url, payload, headers, timeout):
        captured.append(payload)
        return '{"answer": "外部答的"}'

    agent = build_agent({
        "id": "a2", "team_id": "t2", "team_name": "上海文旅局",
        "name": "上海外站", "region": "上海", "prompt": None,
        "status": "published", "kind": "external",
        "endpoint": "https://x/chat",
    }, opener=opener)

    res = agent.answer("上海有什么")
    assert res.text == "外部答的"
    # 外部协议里没有 facts 字段，不该给它们塞
    assert "facts" not in captured[0]
