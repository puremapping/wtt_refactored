"""画像合并 / 占位词清洗 / 时长归一 / ready 判据 —— 纯逻辑，零依赖"""
from app.services.conversation import (
    MOTIVATIONS,
    _clean_field_value,
    _has_evidence,
    _is_ready,
    _merge_profile,
    _norm_hours,
)


# ── 占位词清洗 ──

def test_placeholder_words_cleaned_to_empty():
    for w in ("未知", "不确定", "待定", "无", "没有", "随便", "-", "?", "null", "N/A"):
        assert _clean_field_value(w) == "", w


def test_real_value_kept():
    assert _clean_field_value("北京") == "北京"
    assert _clean_field_value("  上海  ") == "上海"


def test_none_and_whitespace():
    assert _clean_field_value(None) == ""
    assert _clean_field_value("   ") == ""
    assert _clean_field_value("。-") == ""


# ── 时长归一 ──

def test_norm_hours_chinese():
    assert _norm_hours("一天") == 8
    assert _norm_hours("半天") == 4
    assert _norm_hours("一天半") == 12
    assert _norm_hours("两小时") == 2
    assert _norm_hours("3小时") == 3
    assert _norm_hours("一下午") == 4
    assert _norm_hours("晚上") == 3


def test_norm_hours_numeric_and_bounds():
    assert _norm_hours(8) == 8
    assert _norm_hours(8.0) == 8
    assert _norm_hours("8") == 8
    assert _norm_hours(0) is None
    assert _norm_hours(13) is None
    assert _norm_hours("随便说说") is None
    assert _norm_hours(None) is None


# ── 画像合并 ──

def test_merge_scalar_overrides():
    old = {"destination": "北京", "hours": 8}
    new = {"hours": 4}
    out = _merge_profile(old, new)
    assert out["hours"] == 4
    assert out["destination"] == "北京"


def test_merge_list_dedup_append():
    out = _merge_profile({"interests": ["博物馆"]}, {"interests": ["博物馆", "咖啡馆"]})
    assert out["interests"] == ["博物馆", "咖啡馆"]


def test_merge_remove_key_deletes():
    out = _merge_profile(
        {"interests": ["博物馆", "咖啡馆"]},
        {"interests": ["咖啡馆"], "interests_remove": ["博物馆"]})
    assert out["interests"] == ["咖啡馆"]


def test_merge_remove_must_see():
    out = _merge_profile({"must_see": ["故宫"]}, {"must_see_remove": ["故宫"]})
    assert "must_see" not in out or out["must_see"] == []


def test_merge_intensity_clamped():
    assert _merge_profile({}, {"primary_intensity": 9})["primary_intensity"] == 5
    assert _merge_profile({}, {"primary_intensity": 0})["primary_intensity"] == 1
    assert _merge_profile({}, {"primary_intensity": "abc"}).get("primary_intensity") is None


def test_merge_primary_only_from_seven():
    out = _merge_profile({}, {"primary": "胡编的动机"})
    assert "primary" not in out
    for m in MOTIVATIONS:
        assert _merge_profile({}, {"primary": m})["primary"] == m


def test_merge_hours_normalized():
    assert _merge_profile({}, {"hours": "一天"})["hours"] == 8
    assert _merge_profile({}, {"hours": 99}).get("hours") is None


def test_merge_empty_and_none_skipped():
    out = _merge_profile({"destination": "北京"}, {"destination": "", "companions": None})
    assert out["destination"] == "北京"
    assert "companions" not in out


# ── 证据校验（模型瞎补字段的代码层拦截）──

def test_evidence_companions():
    assert _has_evidence("companions", "我和朋友一起去")
    assert _has_evidence("companions", "陪爸妈逛逛")
    assert not _has_evidence("companions", "想去北京玩")


def test_evidence_pace():
    assert _has_evidence("pace", "不想太赶")
    assert not _has_evidence("pace", "想去北京玩")


def test_evidence_unknown_field_always_true():
    assert _has_evidence("destination", "任意文本")


# ── ready 判据 ──

def test_ready_requires_two_turns():
    p = {"primary": "恢复/逃离", "hours": 8, "_turns": 1}
    assert not _is_ready(p)
    p["_turns"] = 2
    assert _is_ready(p)


def test_ready_requires_motive_and_context():
    assert not _is_ready({"_turns": 2})
    assert not _is_ready({"_turns": 2, "primary": "恢复/逃离"})
    assert not _is_ready({"_turns": 2, "hours": 8})
    assert _is_ready({"_turns": 2, "primary": "恢复/逃离", "hours": 8})
    assert _is_ready({"_turns": 3, "primary": "恢复/逃离", "companions": "朋友"})
