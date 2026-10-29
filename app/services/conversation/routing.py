#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主对话 → 地区智能体 的路由判定

## 职责

一轮对话里，决定「这轮要不要交给某个文旅局智能体回答」。三个条件全满足才交：

  1. 用户这轮明确提到了某个地区（从用户原话里解析，不从画像猜）
  2. 该地区有已发布的智能体（走 app/services/agents.find_region_agent）
  3. 平台的本地引擎这轮没别的事要干（没在等生成行程、没被工具占用）

## 为什么用「用户原话」而不是画像

画像里的 destination 是累积的 —— 用户第三轮才说去成都，但第二轮它就已经
被抽取填上了。若按画像路由，用户还没说目的地时就会被成都智能体接管。
所以路由只认 `resolve_city(user_text)`。

## 为什么不接管到底

文旅局智能体只回答「关于这个地区的问题」，它没有行程生成能力。
用户说「帮我排一天的行程」时，走本地引擎；用户说「成都有什么好吃的」
时，交给成都智能体。判定逻辑在 `should_delegate()` 里，看的是意图。

## ⚠️ 已知数据缺口

2026-10-29 实测：data/wtt.db 的城市注册表只有「北京」，而 agents 表里
6 个已发布智能体中有挂「成都」的。这类智能体路由得到但答不出景点
（它没有景点数据可用）。这是数据缺口不是代码缺陷，别在路由层修。
"""
from __future__ import annotations

from typing import Optional

from app.services import cities

# 这些意图即使提到了城市，也必须走本地引擎 —— 智能体干不了
# （行程生成/修改是平台的核心能力，智能体只有人设和话术）
#
# ⚠️ 用**词根**匹配不整词：用户会说「排一天的行程」「规划两天的」，
#    「排行程」这种整词匹配不上中间插了成分的说法。
_LOCAL_ONLY_VERBS = (
    "生成行程", "排", "安排", "规划", "换一批", "换一个",
    "再加一站", "删掉", "去掉",
)


def mentioned_region(user_text: str) -> Optional[str]:
    """从用户原话里解析出提到的城市（解析不到返回 None）

    复用 cities.resolve_city —— 它已经处理了：
      - 「成都市」→ 成都
      - 「朝阳区」→ 按景区数多的城市（同名区消歧）
      - 「首都」→ 北京

    ⚠️ 解析不出时，退一步去智能体表里找（见 `_match_agent_region`）。
       原因：城市注册表来自 attractions 数据，而文旅局可以在我们还没有景区
       数据的城市注册智能体。若只认注册表，成都智能体永远接不到话。
       这是路由层该兜的事 —— 数据缺口不该变成代码死路。
    """
    if not user_text:
        return None
    text = user_text.strip()
    city = cities.resolve_city(text)
    if city:
        return city
    return _match_agent_region(text)


def _match_agent_region(text: str) -> Optional[str]:
    """在城市注册表之外，用智能体表的 region 再试一次

    返回命中智能体的 region 原值（不是标准城市名）——
    因为调用方要拿它去查智能体，得能对得上。
    """
    try:
        from app.services import agents as agent_svc

        candidates = agent_svc.published_regions()
    except Exception:
        return None

    # 长的优先，避免「京」这种短名吃掉别的城市
    for region in sorted(candidates, key=len, reverse=True):
        if region and region in text:
            return region
    return None


def wants_local_engine(user_text: str) -> bool:
    """这轮是不是要平台自己干活（排行程/改行程）

    命中就不交给智能体 —— 智能体没有行程能力，交过去等于答非所问。
    """
    t = (user_text or "").strip()
    if not t:
        return False
    return any(v in t for v in _LOCAL_ONLY_VERBS)


def should_delegate(user_text: str) -> Optional[str]:
    """返回应当交给的地区名；不交返回 None

    只做判定，不碰数据库 —— 查智能体是调用方的事。
    """
    if wants_local_engine(user_text):
        return None
    return mentioned_region(user_text)
