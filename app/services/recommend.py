#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推荐引擎：动机 → 景区筛选与排序

评分公式（PRD 3.1 模块二）：
  score = 动机匹配度 × 0.35
        + 多源评价一致性 × 0.20
        + 用户画像匹配度 × 0.15
        + 官方推荐权重 × 0.10
        + 新鲜度 × 0.10
        - 拥挤度 × 0.10

MVP 简化说明：
  - 「多源评价一致性」降级为「等级分」（平台数据无跨源评分）
  - 「新鲜度」用数据更新时间近似，MVP 暂置常量
  - 「官方推荐权重」用景区等级代替（5A>4A>…）
  - 「拥挤度」用平台的「重点景区饱和指数」真实数据
"""
from dataclasses import dataclass, field

from app.core.db import connect

# ---- 动机 → 排序偏好映射（PRD 3.1 模块二）----
# 每项：(标签关键词, 权重调整)
MOTIVATION_RULES = {
    "恢复/逃离": {
        "prefer_level_low": 0.3,      # 偏好低等级/小众
        "crowd_penalty": 0.5,         # 重罚拥挤
        "prefer_free": 0.1,
        "prefer_nature": 0.45,        # 重奖自然类
        "avoid_serious": 0.5,         # 排除严肃场所（纪念馆/烈士等）
        "avoid_indoor": 0.25,         # 略排除室内（博物馆）
    },
    "连接/关系": {
        "prefer_easy_transport": 0.4, # 交通便利（有地铁）
        "prefer_level_high": 0.2,
        "crowd_penalty": 0.1,
    },
    "探索/新奇": {
        "prefer_level_low": 0.3,      # 小众
        "prefer_less_crowd": 0.3,
        "prefer_level_high": -0.15,
    },
    "表达/展示": {
        "prefer_level_high": 0.3,     # 标志性更出片
        "prefer_photo_hint": 0.3,
    },
    "成就/完成": {
        "prefer_level_high": 0.4,     # 5A 优先
        "prefer_free": -0.05,
    },
    "文化/沉浸": {
        "prefer_level_high": 0.2,
        "prefer_culture_hint": 0.35,
    },
    "美食/感官": {
        # P2 修复（2026-11-12）：原规则没有任何美食信号、复用 culture_hint，
        # 导致与「文化/沉浸」top5 完全相同（Jaccard=1.0，jaccard_diag.py 实测）。
        # 现在给真正的美食信号 + 差异化的次级信号（交通便利/不挤/小众）。
        "prefer_food_hint": 0.35,
        "prefer_easy_transport": 0.2,
        "prefer_less_crowd": 0.15,
        "prefer_level_low": 0.1,
    },
}

# 等级 → 基础分。⚠️ P2 修复（2026-11-12）：等级降为「可靠性闸门」而非主分——
# 5A 是便利性认证（GB/T 17775 细则一 950/1000 是厕所/标识/停车/医护），
# 不是「值得去」的认证。原实现 40% 权重（s_level 0.10 + s_profile 0.15·lv）
# 压在等级上，排序实际由「等级是否相同」这种二元信号决定（分数压缩 0.005 级）。
# 现在等级派生分 0.08·lv + (0.05 + 0.08·lv)，动机信号（0.35 档，含连续的
# 拥挤度/交通/线索词）成为主导。
LEVEL_SCORE = {"5A": 1.0, "4A": 0.85, "3A": 0.6, "2A": 0.4, "1A": 0.2}

# avoid 类惩罚（avoid_serious / avoid_indoor）合计上限 —— 软降权（P2 修复）。
# 原实现无上限：故宫（名称含「馆」被判室内）被扣 0.15、抗战馆类被扣 0.45，
# 分数压到 0.099 且 reasons 被清空 → 「无理由的低分」。软降权 = 保留在候选池、
# 扣分有记录（penalties[]）、理由不被抹掉。
AVOID_PENALTY_CAP = 0.20

# 场所气质分类（用于动机匹配的排除项）
# 从名称推断场所类型 —— 平台数据没有类型字段，只能用命名特征。
# ⚠️ P2 修复（2026-11-12）：原实现对任意位置的子串匹配，故宫博物院因含「馆」
# 被判室内博物馆。现在改成「强室内词 + 露天否决」两级判定：
#   - 只有名字里出现**强室内词**才算室内（博物馆/展览馆这类完整词，不再匹配单字「馆」）
#   - 名字里出现露天场所词（公园/故宫/坛/陵/山/湖…）时否决室内判定
#   - data_confidence 里 poi_type 一律标 inferred（是猜的，不是库里的事实）
SERIOUS_HINTS = ["纪念馆", "烈士", "抗战", "革命", "党史", "军事", "国防",
                 "警示", "法制", "禁毒", "消防", "安全"]
INDOOR_STRONG = ["博物馆", "博物院", "纪念馆", "展览馆", "美术馆", "科技馆",
                 "天文馆", "海洋馆", "艺术馆", "陈列馆", "规划馆", "文化馆",
                 "图书馆", "体育馆", "游泳馆", "滑雪馆", "室内"]
OPEN_AIR_HINTS = ["故宫", "公园", "园林", "坛", "陵", "长城", "古城", "遗址",
                  "庄园", "山庄", "苑", "寺", "庙", "塔", "观", "宫",
                  "山", "湖", "谷", "峪", "溪", "岛", "草原", "湿地", "峡",
                  "瀑", "森林", "温泉", "滑雪场", "乐园", "世界", "镇", "村",
                  "街", "广场", "河", "滩", "田", "园"]
NATURE_HINTS = ["公园", "湿地", "森林", "湖", "山", "谷", "峪", "溪",
                "植物园", "花园", "景区", "绿道", "郊野"]

# 名称里的美食线索词（P2 修复：美食/感官规则表此前没有任何美食信号）
FOOD_HINTS = ["美食", "小吃", "夜市", "风味", "名吃", "餐饮", "糕点",
              "老字号", "食府", "食街", "美食街", "街", "巷", "市场", "坊"]

# 名称/描述里的线索词
PHOTO_HINTS = ["景", "公园", "街", "桥", "塔", "长城", "湖", "山", "园"]
CULTURE_HINTS = ["博物", "遗址", "故居", "寺", "庙", "文化", "纪念馆",
                 "故宫", "坛", "陵", "堂"]


def _kind(name: str) -> set:
    """判断场所气质，返回标签集合

    P2 修复（2026-11-12）：室内判定改两级 ——
      1. 只认**强室内词**（完整词，不再拿「馆」单字到处匹配）
      2. 名字含露天场所词时否决室内判定（故宫博物院 → 露天）
    """
    tags = set()
    if any(h in name for h in SERIOUS_HINTS):
        tags.add("serious")
    indoor_hit = any(h in name for h in INDOOR_STRONG)
    open_air = any(h in name for h in OPEN_AIR_HINTS)
    if indoor_hit and not open_air:
        tags.add("indoor")
    if any(h in name for h in NATURE_HINTS):
        tags.add("nature")
    return tags


def _data_confidence(item: "Scored") -> dict:
    """数据可信度标注（P2 契约：界面必须能区分「库里真有的」和「名称猜的」）

    - poi_type / place_kind 永远是 inferred：库里没有类型列，全是名称猜的
    - crowd / metro 缺失标 missing（下游 UI 不得把缺数据画得像确定状态）
    - crowd_missing 标 isolated：拥挤度覆盖率只有 57%（北京 5A 仅 4/10），
      缺数据景点在排序里与「低人流」同待遇 —— 这是本评分器的已知盲区，
      必须显式标注，不能画成确定状态（诊断报告 §5.2 第 2 条纪律）
    """
    conf = {"poi_type": "inferred", "place_kind": "inferred"}
    if item.crowd is None:
        conf["crowd"] = "missing"
        conf["crowd_missing_treated_as"] = "isolated"
    if not item.has_metro:
        conf["metro"] = "missing"
    return conf


@dataclass
class Scored:
    id: int
    name: str
    level: str
    district: str
    address: str
    ticket_free: int | None
    price_high: float | None
    price_low: float | None
    crowd: float | None
    has_metro: bool
    lon: float | None = None
    lat: float | None = None
    city: str = ""
    score: float = 0.0
    reasons: list = field(default_factory=list)
    # ── P2 数据契约（2026-11-12）：把「已在算但没留下来」的东西留下 ──
    # 各分项得分；sum(score_breakdown.values()) == score（可测的一致性判据）
    score_breakdown: dict = field(default_factory=dict)
    # 结构化理由码 [{code,label,evidence,weight}]；机器可判，组件按 code 分派
    match_reasons: list = field(default_factory=list)
    # 被扣的分 [{code,label,amount}]；被排除的原因 exclusion_reason（闸门用）
    penalties: list = field(default_factory=list)
    exclusion_reason: str | None = None
    # 名称推断的场所类型（indoor/nature/serious...）—— 一律 inferred
    poi_type: list = field(default_factory=list)
    # 数据可信度（见 _data_confidence）
    data_confidence: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "level": self.level,
            "district": self.district, "address": self.address,
            "ticket_free": self.ticket_free,
            "price_high": self.price_high, "price_low": self.price_low,
            "crowd": self.crowd, "has_metro": self.has_metro,
            "lon": self.lon, "lat": self.lat, "city": self.city,
            # P2 修复：round(...,3) 把 0.489x/0.485x 压成同值，是诊断里
            # 「分数压缩 0.005 级」在 API 层的二次伤害。保留 4 位。
            "score": round(self.score, 4), "reasons": self.reasons,
            "score_breakdown": self.score_breakdown,
            "match_reasons": self.match_reasons,
            "penalties": self.penalties,
            "exclusion_reason": self.exclusion_reason,
            "poi_type": self.poi_type,
            "data_confidence": self.data_confidence,
        }


def _norm_crowd(crowd):
    """饱和指数归一化到 0-1（值越小越空）。

    实测数据范围：约 0 ~ 100+。用 100 为上限截断。
    """
    if crowd is None:
        return 0.5                       # 无数据取中值
    return min(1.0, max(0.0, crowd / 100.0))


def load_candidates(city: str = None, limit=None):
    """从库里取候选景区（含饱和指数、地铁信息、坐标）

    ⚠️ city（Phase 2c 多城市隔离）：
      - 传入时只取该城市的景区
      - transport / crowd_index 的 join 带 (名称, 城市) 双条件 ——
        两城同名景点的交通与人流数据绝不互相串
    """
    sql = """
        SELECT a.id, a.name, a.level, a.district, a.address,
               a.ticket_free, a.price_high, a.price_low,
               a.lon, a.lat, a.city,
               c.saturation AS crowd,
               t.metro
        FROM attractions a
        LEFT JOIN crowd_index c
               ON c.name = a.name AND c.city = a.city
        LEFT JOIN transport  t
               ON t.attraction_name = a.name AND t.city = a.city
    """
    args = []
    if city:
        sql += " WHERE a.city = ?"
        args.append(city)

    out = []
    with connect() as conn:
        for r in conn.execute(sql, args):
            out.append(Scored(
                id=r["id"], name=r["name"], level=r["level"] or "",
                district=r["district"] or "", address=r["address"] or "",
                ticket_free=r["ticket_free"],
                price_high=r["price_high"], price_low=r["price_low"],
                crowd=r["crowd"],
                has_metro=bool(r["metro"] and str(r["metro"]).strip()),
                lon=r["lon"], lat=r["lat"],
                city=r["city"] or "",
            ))
    return out[:limit] if limit else out


def score_one(item: Scored, motivation: str, intensity: int) -> Scored:
    """按动机给单个景区打分

    P2 修复（2026-11-12）：
      - 等级从主分降为闸门：派生分合计 0.08·lv + (0.05 + 0.08·lv)，
        动机信号（0.35 档）成为排序主导 —— 解「分数压缩 0.005 级」
      - avoid 类从无上限硬扣改软降权（AVOID_PENALTY_CAP 封顶），
        扣分进 penalties[]，不再撤掉已积累的理由 —— 解「故宫 0.099 无理由」
      - 全过程留 score_breakdown / match_reasons / penalties / poi_type /
        data_confidence（数据契约：把已在算的东西留下来）
    """
    rules = MOTIVATION_RULES.get(motivation, {})
    k = intensity / 5.0                  # 强度归一化，最高 1.0
    reasons = []
    match_reasons = []                   # 结构化理由码
    penalties = []                       # 扣分明细

    def _mr(code, label, evidence, weight):
        match_reasons.append({"code": code, "label": label,
                              "evidence": evidence, "weight": round(weight, 4)})

    def _pen(code, label, amount):
        penalties.append({"code": code, "label": label,
                          "amount": round(amount, 4)})

    # --- 1. 等级闸门（原「官方推荐权重 0.10」降权）---
    lv = LEVEL_SCORE.get(item.level, 0.3)
    s_level = lv * 0.08

    # --- 2. 拥挤度（-0.10）用真实饱和指数 ---
    # ⚠️ P2 修复（两处倒挂）：
    #   a) crowd=None 是「缺数据」（data_confidence.crowd=missing），不是
    #      「中等拥挤」。原实现按中值 0.5 照扣，把没数据当惩罚。
    #   b) 反向倒挂：真实数据表明景点很空（cn≈0）时原实现仍扣微量分，
    #      导致「有验证数据且很空」排在「没数据」之后 —— 实测故宫
    #      （饱和指数 1.31）因 0.0001 的惩罚被挤出成就/完成 top5。
    #   现在：惩罚只在人流可感（cn > 0.3）时按超出量计；缺数据不扣。
    cn = _norm_crowd(item.crowd)
    penalty_crowd = 0.0
    if item.crowd is not None and cn > 0.3:
        penalty_crowd = rules.get("crowd_penalty", 0.1) * (cn - 0.3) / 0.7 * 0.10
        _pen("crowd", "当前人流压力", penalty_crowd)
        if cn > 0.6:
            reasons.append(f"当前人流较满（饱和指数 {item.crowd:.1f}）")

    # --- 3. 动机偏好调整（0.35 档，排序主导）---
    s_pref = 0.0
    if rules.get("prefer_level_high"):
        v = rules["prefer_level_high"] * lv * k
        s_pref += v
        if item.level == "5A":
            reasons.append("5A 级标志性景区")
            _mr("level_high", "等级标志性", item.level, v)
    if rules.get("prefer_level_low"):
        v = rules["prefer_level_low"] * (1 - lv) * k
        s_pref += v
        if item.level in ("2A", "3A"):
            reasons.append("非头部景区，相对小众")
            _mr("level_low", "相对小众", item.level, v)
    if rules.get("prefer_less_crowd") and item.crowd is not None:
        v = rules["prefer_less_crowd"] * (1 - cn) * k
        s_pref += v
        _mr("less_crowd", "人流宽松", f"饱和指数 {item.crowd:.1f}", v)
    if rules.get("prefer_easy_transport"):
        if item.has_metro:
            v = rules["prefer_easy_transport"] * k
            s_pref += v
            reasons.append("有地铁直达，交通方便")
            _mr("easy_transport", "交通便利", "有地铁直达", v)
    if rules.get("prefer_free") and item.ticket_free == 1:
        v = rules["prefer_free"] * k
        s_pref += v
        reasons.append("免费开放")
        _mr("free", "免费开放", "ticket_free", v)
    if rules.get("prefer_photo_hint"):
        if any(h in item.name for h in PHOTO_HINTS):
            v = rules["prefer_photo_hint"] * k
            s_pref += v
            reasons.append("视觉景观突出，适合拍摄")
            _mr("photo", "视觉景观突出", "名称线索", v)
    if rules.get("prefer_culture_hint"):
        if any(h in item.name for h in CULTURE_HINTS):
            v = rules["prefer_culture_hint"] * k
            s_pref += v
            reasons.append("历史文化属性突出")
            _mr("culture", "历史文化属性", "名称线索", v)
    if rules.get("prefer_food_hint"):
        if any(h in item.name for h in FOOD_HINTS):
            v = rules["prefer_food_hint"] * k
            s_pref += v
            reasons.append("名称含美食线索，餐饮选择多")
            _mr("food", "美食聚集地", "名称线索", v)

    # --- 3b. 场所气质匹配（软降权 + 扣分留痕，不再撤理由）---
    kind = _kind(item.name)
    poi_type = sorted(kind)
    if rules.get("prefer_nature") and "nature" in kind:
        v = rules["prefer_nature"] * k
        s_pref += v
        reasons.append("自然景观，适合放松")
        _mr("nature", "自然景观", "名称线索", v)

    # avoid 类合计封顶（软降权）：避免「一个词误判扣光全部」
    avoid_total = 0.0
    if rules.get("avoid_serious") and "serious" in kind:
        avoid_total += rules["avoid_serious"] * k
    if rules.get("avoid_indoor") and "indoor" in kind and "nature" not in kind:
        avoid_total += rules["avoid_indoor"] * k
    if avoid_total:
        amount = min(avoid_total, AVOID_PENALTY_CAP)
        s_pref -= amount
        code = ("serious" if rules.get("avoid_serious") and "serious" in kind
                else "indoor")
        _pen(f"avoid_{code}",
             "场所气质与动机冲突（按名称推断，非确切类型）", amount)

    # --- 4. 画像匹配度（原 0.15 → 降权为 0.05 + 0.08·lv）---
    s_profile = 0.05 + 0.08 * lv

    item.score = s_level + s_profile + s_pref - penalty_crowd
    item.score_breakdown = {
        "level": round(s_level, 4),
        "profile": round(s_profile, 4),
        "preference": round(s_pref, 4),      # 净值（含 avoid 扣分）
        "crowd_penalty": round(-penalty_crowd, 4),
    }
    item.reasons = reasons
    item.match_reasons = match_reasons
    item.penalties = penalties
    item.exclusion_reason = None
    item.poi_type = poi_type
    item.data_confidence = _data_confidence(item)
    return item


def recommend(motivation: str, intensity: int = 3, top_k: int = 10,
              city: str = None):
    """主入口：返回按动机排序的景区列表

    city：限定城市（Phase 2c）。None = 全部城市（调试接口用）。
    """
    items = load_candidates(city=city)
    scored = [score_one(i, motivation, intensity) for i in items]
    # 有理由的排前面，再按分数
    scored.sort(key=lambda x: (-x.score, -len(x.reasons)))
    return scored[:top_k]
