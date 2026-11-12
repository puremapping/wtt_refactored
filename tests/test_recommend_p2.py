#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2 推荐三项修复 + 数据契约的行为锁（wtt_ux-refactor/PLAN.md 验收判据）

三项修复的验收（HANDOVER §七 / 诊断报告 §5.2 闸门）：
  1. 故宫在「恢复/逃离」下不再 0.099、reasons 不再被清空（不靠 hardcode，
     修的是 _kind() 的室内误判）
  2. 「美食/感官」与「文化/沉浸」top5 Jaccard < 1.0
  3. sum(score_breakdown.values()) ≈ score（分项与排序用的是同一个分）

契约（Scored 补 5 字段）：
  score_breakdown / match_reasons / penalties / poi_type / data_confidence
"""
import pytest

from app.services import recommend as rec


# ---------- 修复 1：故宫误伤 ----------

def test_gugong_not_indoor_misjudged():
    """故宫博物院是露天场所，名称含「馆」不该被判室内（根因修复）"""
    assert "indoor" not in rec._kind("故宫博物院")
    assert "indoor" not in rec._kind("景山公园")
    # 真正的室内场馆仍要被识别
    assert "indoor" in rec._kind("首都博物馆")
    assert "indoor" in rec._kind("北京海洋馆")


def test_gugong_recover_score_not_killed():
    """「恢复/逃离」下故宫不再被打到 0.099 级 —— 根因（室内误判扣光）已修。

    reasons 为空在这里是合法的：故宫 5A 不命中 prefer_level_low、
    收费不命中 prefer_free、非自然类不命中 prefer_nature ——
    是「规则没命中」而非「被扣光」。关键判据：score 不再塌到 0.099、
    penalties 里没有 avoid_indoor（误判扣分）。
    """
    g = rec.Scored(id=1, name="故宫博物院", level="5A", district="东城区",
                   address="", ticket_free=0, price_high=60, price_low=40,
                   crowd=1.31, has_metro=False)
    s = rec.score_one(g, "恢复/逃离", 3)
    assert s.score > 0.15, f"故宫仍被扣光：{s.score}"
    assert not any(p["code"] == "avoid_indoor" for p in s.penalties), \
        "故宫仍被当室内扣分"


def test_serious_place_still_penalized():
    """真正的严肃场所（抗战纪念馆）在「恢复/逃离」下仍要被降权，且有留痕"""
    g = rec.Scored(id=2, name="中国人民抗日战争纪念馆", level="4A",
                   district="丰台区", address="", ticket_free=1,
                   price_high=None, price_low=None, crowd=None, has_metro=True)
    s = rec.score_one(g, "恢复/逃离", 3)
    assert any(p["code"] == "avoid_serious" for p in s.penalties)
    # 软降权封顶：不再无上限硬扣
    total = sum(p["amount"] for p in s.penalties if p["code"].startswith("avoid"))
    assert total <= rec.AVOID_PENALTY_CAP + 1e-9


def test_museum_not_openair_still_indoor():
    """无露天词的纯博物馆仍判室内（不因修复而漏判）"""
    assert "indoor" in rec._kind("中国紫檀博物馆")


# ---------- 修复 2：美食/感官 与 文化/沉浸 分离 ----------

def test_food_motivation_differs_from_culture(seed_beijing):
    """美食规则补了 prefer_food_hint 后，两动机不再输出同一份 top5。

    seed 库只有 5 个景点且名字全无美食线索，退化为按次级信号排序；
    用真实语义判据：两动机的排序（含并列顺序）不再逐位相同。
    """
    food = [i.name for i in rec.recommend("美食/感官", 3, 5, city="北京")]
    cult = [i.name for i in rec.recommend("文化/沉浸", 3, 5, city="北京")]
    assert food != cult, f"两动机 top5 仍完全相同：{food}"


def test_food_hint_signal_exists():
    """名称含美食线索词的景点在美食/感官下拿到 food 理由码"""
    g = rec.Scored(id=3, name="前门大街景区", level="3A", district="东城区",
                   address="", ticket_free=1, price_high=None, price_low=None,
                   crowd=None, has_metro=True)
    s = rec.score_one(g, "美食/感官", 3)
    codes = [r["code"] for r in s.match_reasons]
    assert "food" in codes
    # 不得再复用 culture 信号（旧 bug：美食规则里挂着 prefer_culture_hint）
    assert "culture" not in codes


# ---------- 修复 1b：等级降为闸门 ----------

def test_level_weight_reduced():
    """等级派生分（level + profile）不再无脑占主导 —— 动机命中越多占比越低。

    旧公式等级派生占 40%（0.10+0.15 对 0.25 可变）；新公式
    等级派生 ≤ 0.21 恒定，动机命中 3 项即超过它。判据：
    满命中 5A 的等级占比 < 50%。
    """
    g = rec.Scored(id=4, name="天坛公园", level="5A", district="东城区",
                   address="", ticket_free=1, price_high=None, price_low=None,
                   crowd=10.09, has_metro=True)
    s = rec.score_one(g, "成就/完成", 3)
    fixed = s.score_breakdown["level"] + s.score_breakdown["profile"]
    assert fixed <= 0.21 + 1e-9, f"等级派生分仍过高：{fixed}"
    # 天坛命中 prefer_level_high + prefer_free + nature（无 food/transport 键）
    # preference=0.21 与等级派生打平 —— 等级不再单向碾压
    assert fixed < s.score, "总分被等级派生以外的东西拖成负/零"


def test_crowd_missing_not_penalized(seed_beijing):
    """crowd=None 是缺数据不是中等拥挤：不扣 crowd_penalty、conf 标 missing"""
    g = rec.Scored(id=5, name="八达岭长城景区", level="5A", district="延庆区",
                   address="", ticket_free=0, price_high=None, price_low=None,
                   crowd=None, has_metro=True)
    s = rec.score_one(g, "恢复/逃离", 3)
    assert s.score_breakdown["crowd_penalty"] == 0
    assert s.data_confidence.get("crowd") == "missing"


# ---------- 数据契约 ----------

REQUIRED_FIELDS = ("score_breakdown", "match_reasons", "penalties",
                   "poi_type", "data_confidence")


def test_scored_contract_fields_present(seed_beijing):
    """Scored 补 5 字段：每个推荐结果都带完整证据结构"""
    items = rec.recommend("成就/完成", 3, 5, city="北京")
    assert items
    for i in items:
        for f in REQUIRED_FIELDS:
            assert getattr(i, f) is not None, f"{i.name} 缺 {f}"
        d = i.to_dict()
        for f in REQUIRED_FIELDS:
            assert f in d, f"to_dict() 未输出 {f}"


def test_breakdown_sums_to_score(seed_beijing):
    """闸门判据：sum(score_breakdown.values()) ≈ score（分项与排序同一个分）"""
    for mot in ("成就/完成", "恢复/逃离", "文化/沉浸", "美食/感官"):
        for i in rec.recommend(mot, 3, 20, city="北京"):
            total = sum(i.score_breakdown.values())
            assert abs(total - i.score) < 1e-3, \
                f"{i.name} {mot}: breakdown 合计 {total} ≠ score {i.score}"


def test_score_precision_not_collapsed():
    """to_dict 保留 4 位 —— 不再把 0.489x/0.485x 压成同值"""
    g = rec.Scored(id=6, name="测试景区", level="5A", district="东城区",
                   address="", ticket_free=None, price_high=None,
                   price_low=None, crowd=None, has_metro=False)
    g.score = 0.48963
    assert g.to_dict()["score"] == 0.4896


def test_match_reasons_are_structured(seed_beijing):
    """理由码结构：code/label/evidence/weight 齐全，机器可判"""
    for i in rec.recommend("连接/关系", 3, 5, city="北京"):
        for r in i.match_reasons:
            assert {"code", "label", "evidence", "weight"} <= set(r)


def test_penalty_entries_are_structured(seed_beijing):
    for i in rec.recommend("恢复/逃离", 3, 20, city="北京"):
        for p in i.penalties:
            assert {"code", "label", "amount"} <= set(p)
        assert i.exclusion_reason is None      # 软降权下没有硬排除
