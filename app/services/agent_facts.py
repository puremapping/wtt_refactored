#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给文旅局智能体提供「本地景点事实」的检索层

## 为什么需要这一层

BuiltinAgent 只会把 prompt（人设）和用户问题发给模型。模型对景点的知识
来自它自己的训练数据 —— 可能过时、可能编造、可能推荐已经关停或根本不存在的地方。

**平台手上有官方名录（四川省文旅厅 A 级景区，103 个成都景区），
就该把它喂给模型，而不是让模型自由发挥。**

## 检索策略（刻意简单）

不做向量检索 —— 景区名和区县名都是短词，LIKE 匹配足够，而且结果可解释。
问「锦江区有什么」就查锦江区的；问「成都有什么」就按等级取头部若干。

## 与推荐引擎的区别

`recommend.py` 按**用户动机**打分排序，是行程生成用的。
这里是给对话喂事实，不排序，只提供「这个城市/区县有哪些地方」的清单。
两者用同一张表但目的不同，不要合并。
"""
from __future__ import annotations

from typing import Optional

from app.core.db import connect

# 喂给模型的景点条数上限。太多会污染 prompt、稀释重点；
# 太少又不足以覆盖。6-10 是客服类问答的常见量级。
MAX_FACTS = 12


def district_of(text: str, city: str) -> Optional[str]:
    """从用户原话里找出他指的是哪个区县

    只在该城市已知的区县名单里找，避免「朝阳」这种跨城市的歧义。
    """
    if not text or not city:
        return None
    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT district FROM attractions "
            "WHERE city=? AND district IS NOT NULL AND district != ''",
            (city,)).fetchall()

    districts = [r["district"] for r in rows]
    # 长的优先：「都江堰市」不能被「都江堰」以外的短名吃掉
    for d in sorted(districts, key=len, reverse=True):
        if d in text:
            return d
        short = d.rstrip("区县市")
        if short and len(short) >= 2 and short in text:
            return d
    return None


def fetch_facts(city: str, question: str = "",
                district: Optional[str] = None,
                limit: int = MAX_FACTS) -> list:
    """取该城市的景点事实，优先取用户提到的区县

    返回 [{"name","level","district","address","ticket_free"}, ...]
    """
    if not city:
        return []

    if district is None:
        district = district_of(question, city)

    sql = ("SELECT name, level, district, address, ticket_free "
           "FROM attractions WHERE city=?")
    args = [city]

    if district:
        sql += " AND district=?"
        args.append(district)

    # 等级高的优先（5A > 4A > ...），同名按 id 稳定排序
    sql += " ORDER BY level DESC, id LIMIT ?"
    args.append(limit)

    with connect() as conn:
        rows = conn.execute(sql, args).fetchall()

    # 该区县为空时退回全市（比如用户问的区县确实没有 A 级景区）
    if not rows and district:
        return fetch_facts(city, question, district="", limit=limit)

    return [{
        "name": r["name"],
        "level": r["level"] or "",
        "district": r["district"] or "",
        "address": r["address"] or "",
        "ticket_free": r["ticket_free"],
    } for r in rows]


def format_facts(facts: list) -> str:
    """把事实清单格式化成给模型看的文本

    ⚠️ 明确告诉模型「只能用这个清单里的地方」—— 这是防幻觉的关键。
       光给数据不说约束，模型照样会补它自己知道的。
    """
    if not facts:
        return ""
    lines = ["【本地景区名录（官方 A 级景区数据，只能用这些）】"]
    for f in facts:
        free = ""
        # ⚠️ SQLite 取出的 1/0 是 int，`1 is True` 为 False —— 必须按值比
        tf = f["ticket_free"]
        if tf == 1:
            free = "，免费"
        elif tf == 0:
            free = "，收费"
        lines.append(f"- {f['name']}（{f['level']}，{f['district']}{free}）")
    return "\n".join(lines)
