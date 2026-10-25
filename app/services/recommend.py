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
        "prefer_culture_hint": 0.15,
        "prefer_level_low": 0.1,
    },
}

# 等级 → 基础分
LEVEL_SCORE = {"5A": 1.0, "4A": 0.8, "3A": 0.6, "2A": 0.4, "1A": 0.2}

# 场所气质分类（用于动机匹配的排除项）
# 从名称推断场所类型 —— 平台数据没有类型字段，只能用命名特征
SERIOUS_HINTS = ["纪念馆", "烈士", "抗战", "革命", "党史", "军事", "国防",
                 "警示", "法制", "禁毒", "消防", "安全"]
INDOOR_HINTS = ["博物", "馆", "展", "厅", "中心"]
NATURE_HINTS = ["公园", "湿地", "森林", "湖", "山", "谷", "峪", "溪",
                "植物园", "花园", "景区", "绿道", "郊野"]

# 名称/描述里的线索词
PHOTO_HINTS = ["景", "公园", "街", "桥", "塔", "长城", "湖", "山", "园"]
CULTURE_HINTS = ["博物", "遗址", "故居", "寺", "庙", "文化", "纪念馆",
                 "故宫", "坛", "陵", "馆", "堂"]


def _kind(name: str) -> set:
    """判断场所气质，返回标签集合"""
    tags = set()
    if any(h in name for h in SERIOUS_HINTS):
        tags.add("serious")
    if any(h in name for h in INDOOR_HINTS):
        tags.add("indoor")
    if any(h in name for h in NATURE_HINTS):
        tags.add("nature")
    return tags


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
    score: float = 0.0
    reasons: list = field(default_factory=list)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "level": self.level,
            "district": self.district, "address": self.address,
            "ticket_free": self.ticket_free,
            "price_high": self.price_high, "price_low": self.price_low,
            "crowd": self.crowd, "has_metro": self.has_metro,
            "lon": self.lon, "lat": self.lat,
            "score": round(self.score, 3), "reasons": self.reasons,
        }


def _norm_crowd(crowd):
    """饱和指数归一化到 0-1（值越小越空）。

    实测数据范围：约 0 ~ 100+。用 100 为上限截断。
    """
    if crowd is None:
        return 0.5                       # 无数据取中值
    return min(1.0, max(0.0, crowd / 100.0))


def load_candidates(limit=None):
    """从库里取候选景区（含饱和指数、地铁信息、坐标）"""
    sql = """
        SELECT a.id, a.name, a.level, a.district, a.address,
               a.ticket_free, a.price_high, a.price_low,
               a.lon, a.lat,
               c.saturation AS crowd,
               t.metro
        FROM attractions a
        LEFT JOIN crowd_index c ON c.name = a.name
        LEFT JOIN transport  t ON t.attraction_name = a.name
    """
    out = []
    with connect() as conn:
        for r in conn.execute(sql):
            out.append(Scored(
                id=r["id"], name=r["name"], level=r["level"] or "",
                district=r["district"] or "", address=r["address"] or "",
                ticket_free=r["ticket_free"],
                price_high=r["price_high"], price_low=r["price_low"],
                crowd=r["crowd"],
                has_metro=bool(r["metro"] and str(r["metro"]).strip()),
                lon=r["lon"], lat=r["lat"],
            ))
    return out[:limit] if limit else out


def score_one(item: Scored, motivation: str, intensity: int) -> Scored:
    """按动机给单个景区打分"""
    rules = MOTIVATION_RULES.get(motivation, {})
    k = intensity / 5.0                  # 强度归一化，最高 1.0
    reasons = []

    # --- 1. 官方推荐权重（0.10）用等级近似 ---
    lv = LEVEL_SCORE.get(item.level, 0.3)
    s_level = lv * 0.10

    # --- 2. 拥挤度（-0.10）用真实饱和指数 ---
    cn = _norm_crowd(item.crowd)
    penalty = rules.get("crowd_penalty", 0.1) * cn * 0.10
    if item.crowd is not None and cn > 0.6:
        reasons.append(f"当前人流较满（饱和指数 {item.crowd:.1f}）")

    # --- 3. 动机偏好调整（0.35 档） ---
    s_pref = 0.0
    if rules.get("prefer_level_high"):
        s_pref += rules["prefer_level_high"] * lv * k
        if item.level == "5A":
            reasons.append("5A 级标志性景区")
    if rules.get("prefer_level_low"):
        s_pref += rules["prefer_level_low"] * (1 - lv) * k
        if item.level in ("2A", "3A"):
            reasons.append("非头部景区，相对小众")
    if rules.get("prefer_less_crowd") and item.crowd is not None:
        s_pref += rules["prefer_less_crowd"] * (1 - cn) * k
    if rules.get("prefer_easy_transport"):
        if item.has_metro:
            s_pref += rules["prefer_easy_transport"] * k
            reasons.append("有地铁直达，交通方便")
    if rules.get("prefer_free") and item.ticket_free == 1:
        s_pref += rules["prefer_free"] * k
        reasons.append("免费开放")
    if rules.get("prefer_photo_hint"):
        if any(h in item.name for h in PHOTO_HINTS):
            s_pref += rules["prefer_photo_hint"] * k
            reasons.append("视觉景观突出，适合拍摄")
    if rules.get("prefer_culture_hint"):
        if any(h in item.name for h in CULTURE_HINTS):
            s_pref += rules["prefer_culture_hint"] * k
            reasons.append("历史文化属性突出")

    # --- 3b. 场所气质匹配 ---
    kind = _kind(item.name)
    if rules.get("prefer_nature") and "nature" in kind:
        s_pref += rules["prefer_nature"] * k
        reasons.append("自然景观，适合放松")
    if rules.get("avoid_serious") and "serious" in kind:
        s_pref -= rules["avoid_serious"] * k
        reasons[:] = [r for r in reasons if "历史" not in r]   # 撤掉冲突理由
    if rules.get("avoid_indoor") and "indoor" in kind and "nature" not in kind:
        s_pref -= rules["avoid_indoor"] * k

    # --- 4. 画像匹配度（0.15）MVP 用等级+免费组合近似 ---
    s_profile = 0.15 * lv

    item.score = s_level + s_profile + s_pref - penalty
    item.reasons = reasons
    return item


def recommend(motivation: str, intensity: int = 3, top_k: int = 10):
    """主入口：返回按动机排序的景区列表"""
    items = load_candidates()
    scored = [score_one(i, motivation, intensity) for i in items]
    # 有理由的排前面，再按分数
    scored.sort(key=lambda x: (-x.score, -len(x.reasons)))
    return scored[:top_k]
