#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
城市注册表 —— 把「哪个城市」从代码里抽出来

背景（2026-10-15 阿哲定）：
  原实现把「北京」「212 个景区」「16 个区名」硬编码在 conversation.py 里，
  加第二座城市要改代码。现在改为从数据库读城市配置。

设计原则：
  - **城市列表来自数据库**（attractions.city 的 distinct 值），不写死在代码里
  - **区名也来自数据库**（该城市下的 district 值），不维护第二份真相
  - 代码里只保留「当前支持哪些城市」这一层，且是从库算出来的

⚠️ 数据库里没有 city 字段时的行为：
   视为单城市模式（全部数据归到 DEFAULT_CITY），保持向后兼容。
"""
from typing import Optional

from app.core.db import connect

# 单城市模式下的默认城市名（老库没有 city 字段时用）
DEFAULT_CITY = "北京"

# 进程内缓存（城市列表变化不频繁，避免每轮对话都查库）
_cache: dict = {}


def _has_city_column() -> bool:
    key = "_has_city_col"
    if key not in _cache:
        with connect() as conn:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(attractions)")}
        _cache[key] = "city" in cols
    return _cache[key]


def invalidate():
    """数据变更后清缓存"""
    _cache.clear()


def list_cities() -> list:
    """当前数据覆盖的城市列表（从库算，不写死）

    返回：[{"city": "北京", "count": 212, "districts": ["东城区", ...]}, ...]
    """
    if "cities" in _cache:
        return _cache["cities"]

    with connect() as conn:
        if _has_city_column():
            rows = conn.execute(
                "SELECT city, COUNT(*) AS n FROM attractions "
                "WHERE city IS NOT NULL AND city != '' "
                "GROUP BY city ORDER BY n DESC").fetchall()
        else:
            rows = [{"city": DEFAULT_CITY,
                     "n": conn.execute("SELECT COUNT(*) FROM attractions").fetchone()[0]}]

        out = []
        for r in rows:
            city = r["city"]
            if _has_city_column():
                drows = conn.execute(
                    "SELECT DISTINCT district FROM attractions "
                    "WHERE city=? AND district IS NOT NULL AND district != ''",
                    (city,)).fetchall()
            else:
                drows = conn.execute(
                    "SELECT DISTINCT district FROM attractions "
                    "WHERE district IS NOT NULL AND district != ''").fetchall()
            out.append({
                "city": city,
                "count": r["n"],
                "districts": [d["district"] for d in drows],
            })

    _cache["cities"] = out
    return out


def city_names() -> list:
    return [c["city"] for c in list_cities()]


def total_count() -> int:
    return sum(c["count"] for c in list_cities())


def _districts_of(city: str) -> list:
    for c in list_cities():
        if c["city"] == city:
            return c["districts"]
    return []


def resolve_city(dest: str) -> Optional[str]:
    """把用户说的目的地解析成「数据里存在的城市」

    返回城市名；无法匹配返回 None。

    匹配顺序：
      1. 完全等于某城市名          「北京」→ 北京
      2. 城市名出现在文本里         「去北京玩」→ 北京
      3. 命中了某城市的区名         「朝阳区」→ 北京
      4. 特殊别名                   「首都」「京」→ 北京（见 CITY_ALIASES）

    ⚠️ 占位词（「未知」等）由调用方先清洗，这里不处理。
    """
    if not dest:
        return None
    d = str(dest).strip()
    if not d:
        return None

    cities = city_names()

    # 1. 完全匹配
    if d in cities:
        return d

    # 2. 城市名包含在文本里（长的优先，避免「南京」被「京」误匹配）
    for c in sorted(cities, key=len, reverse=True):
        if c in d:
            return c

    # 3. 区名匹配
    for c in list_cities():
        for dist in c["districts"]:
            # 去掉「区/县」后缀再比，兼容用户说「朝阳」而非「朝阳区」
            short = dist.rstrip("区县市")
            if dist in d or (short and short in d):
                return c["city"]

    # 4. 别名
    for alias, city in CITY_ALIASES.items():
        if alias in d and city in cities:
            return city

    return None


# 城市别名（不含单字，避免误匹配）
CITY_ALIASES = {
    "首都": "北京",
    "帝都": "北京",
}


def supported_description() -> str:
    """给 prompt 用的一句话描述当前数据覆盖

    例：「北京（212 个景区）」
    例：「北京（212 个景区）、成都（89 个景区）」
    """
    cs = list_cities()
    if not cs:
        return "（暂无数据）"
    return "、".join(f"{c['city']}（{c['count']} 个景区）" for c in cs)


def is_supported(dest: str) -> bool:
    """目的地是否在数据覆盖范围内

    ⚠️ 空值/占位词视为「未指定」→ True（不是「不支持」）
       这一点由调用方用 _clean_field_value 先清洗后传入。
    """
    if not dest:
        return True
    return resolve_city(dest) is not None
