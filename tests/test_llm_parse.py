"""LLM 封装的健壮 JSON 解析 + 叙述防幻觉校验"""
import pytest

from app.services.llm import parse_json
from app.services.narrative import _verify_narrative


# ── parse_json ──

def test_parse_plain_json():
    assert parse_json('{"a":1}') == {"a": 1}
    assert parse_json('[1,2,3]') == [1, 2, 3]


def test_parse_markdown_wrapped():
    assert parse_json('```json\n{"a":1}\n```') == {"a": 1}
    assert parse_json('```\n{"a":1}\n```') == {"a": 1}


def test_parse_with_surrounding_text():
    assert parse_json('好的，结果如下：{"a":1} 请查收') == {"a": 1}


def test_parse_garbage_returns_none():
    assert parse_json("") is None
    assert parse_json(None) is None
    assert parse_json("这不是JSON") is None
    assert parse_json("{broken") is None


# ── 防幻觉校验 ──

STOPS = [{"name": "故宫博物院"}, {"name": "天坛公园"}]


def test_verify_clean_narrative():
    """BUG-10 修复回归：真实站点的叙述不得误报（含上下文粘连的情况）"""
    ok, suspects = _verify_narrative(
        "上午九点到达故宫博物院，之后前往天坛公园。", STOPS)
    assert ok
    assert suspects == []


def test_verify_real_spot_short_name():
    """「故宫」「天坛」是真实站点的合理简称，不得误报"""
    ok, _ = _verify_narrative("先到故宫，再到天坛公园。", STOPS)
    assert ok


def test_verify_detects_hallucinated_spot():
    # 「中山公园」不在站点里且名字以景点后缀结尾 → 必须被识破
    ok, suspects = _verify_narrative(
        "下午顺路去中山公园散步。", STOPS)
    assert not ok
    assert any("中山" in s for s in suspects)


# ⚠️ 已知误报（BUG-10，Phase 2a 修复后补测试）：
# 正则 {2,10} 前缀会把上下文一起抓进去（如「到达故宫博物院」→「到达故宫」），
# 「宫」在后缀表里导致几乎每条真叙述都被判为幻觉、总是触发重写。
# 且「杭州西湖」这类无后缀幻觉反而漏检。当前实现下无法写出「干净叙述通过」的测试。


def test_verify_empty_text():
    assert _verify_narrative("", STOPS) == (True, [])
