#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""行程生成管线（Phase 2b 自 main.py 迁入）

此前这些函数写在路由文件里，换任何入口（如将来的 Agent 平台调用）
都无法复用。路由层现在只做参数校验 + 调这里的服务函数。
"""
import json

from app.core.db import connect
from app.services import cities as cities_svc
from app.services import conversation as convo_svc
from app.services import itinerary as itin_svc
from app.services import narrative as nar_svc
from app.services import recommend as rec_svc

# 「换一批」语义关键词 —— 用户不想再看到现有站点中的任何一个
REGEN_KEYWORDS = ("换一批", "重新生成", "重新来", "再来一版",
                  "这几个都不想去", "都不想去", "换几个")


def regen_exclude(user_text, args, current_itinerary):
    """「换一批」语义 → 返回要排除的现有站点名列表（BUG-2）

    触发条件（其一）：
      - 模型按工具定义填了 reuse_existing=true
      - 用户话里带「换一批」类关键词（模型漏填 flag 的双保险）

    无现有行程或非重生成语义 → None（正常生成，不排除）。
    """
    if not current_itinerary or not current_itinerary.get("stops"):
        return None
    wants_new = (args.get("reuse_existing")
                 or any(k in (user_text or "") for k in REGEN_KEYWORDS))
    if not wants_new:
        return None
    return [s["name"] for s in current_itinerary["stops"]]


def load_profile(sid, user_id=None):
    """从会话取画像"""
    if not sid:
        return {}
    conv = convo_svc.load_session(sid, user_id)
    return convo_svc.public_profile(conv.profile) if conv else {}


def build_candidates(profile, city=None):
    """按画像构造候选景区列表（推荐 + 排除 avoid + 必去置顶）

    ⚠️ city（Phase 2c 多城市隔离）：传入时只取该城市的景区；
    未传时从画像目的地解析（解析不出默认景区最多的城市），
    多城数据下行程候选绝不混城市。
    """
    if city is None:
        city = _resolve_plan_city(profile)
    mot = profile.get("primary") or "探索/新奇"
    try:
        intensity = int(profile.get("primary_intensity") or 3)
    except (ValueError, TypeError):
        intensity = 3

    items = rec_svc.recommend(mot, intensity, top_k=25, city=city)

    avoid = [str(a) for a in (profile.get("avoid") or [])]
    must = [str(m) for m in (profile.get("must_see") or [])]
    if avoid:
        items = [i for i in items
                 if not any(a in i.name or i.name in a for a in avoid)]
    if must:
        def _is_must(item):
            return any(m in item.name or item.name in m for m in must)
        items.sort(key=lambda x: (not _is_must(x), -x.score))

    with connect() as conn:
        sql = "SELECT attraction_name, metro FROM transport"
        args = []
        if city:
            sql += " WHERE city=?"
            args.append(city)
        metro_map = {r["attraction_name"]: r["metro"] or ""
                     for r in conn.execute(sql, args)}

    return [(i.name, i.level, i.district, i.address, i.lon, i.lat,
             i.crowd, metro_map.get(i.name, ""), i.reasons) for i in items]


def _resolve_plan_city(profile):
    """画像目的地 → 计划城市（Phase 2c）

    解析不出时默认景区最多的城市 —— 多城数据下行程绝不能混城市。
    （对话层已拦掉不支持的城市，能走到这里的目的地要么空要么可解析。）
    """
    dest = (profile.get("destination") or "").strip()
    city = cities_svc.resolve_city(dest) if dest else None
    if city is None:
        names = cities_svc.city_names()
        city = names[0] if names else None
    return city


def generate_itinerary(sid, hours_override=None, exclude=None, user_id=None):
    """生成行程并存入会话，返回行程 dict

    ⚠️ user_id 为空 = 匿名 → 只更新内存会话，不写库
    """
    profile = load_profile(sid, user_id)
    mot = profile.get("primary") or "探索/新奇"
    hours = hours_override or profile.get("hours")
    city = _resolve_plan_city(profile)

    cand = build_candidates(profile, city=city)
    it = itin_svc.build_itinerary(cand, mot, hours, exclude=exclude)
    d = it.to_dict()
    d["city"] = city or ""

    try:
        d["narrative"] = nar_svc.narrate(d, mot, profile=profile)
        d["assessment"] = nar_svc.assess(d)
    except Exception as e:
        d["narrative"] = ""
        d["assessment"] = {"intensity": "中", "strength": "",
                           "suggestion": f"（叙述生成失败: {e}）"}

    d["profile"] = profile
    if sid:
        if user_id:
            with connect() as conn:
                conn.execute("UPDATE sessions SET itinerary=? WHERE id=? AND user_id=?",
                             (json.dumps(d, ensure_ascii=False), sid, user_id))
        else:
            # 匿名：行程存内存会话
            conv = convo_svc._anon_get(sid)
            if conv:
                conv.itinerary = d
                convo_svc._anon_put(conv)
    return d


def load_itinerary(sid, user_id=None):
    """取会话当前行程（含匿名内存路径）"""
    if not sid:
        return None
    if user_id:
        with connect() as conn:
            row = conn.execute(
                "SELECT itinerary FROM sessions WHERE id=? AND user_id=?",
                (sid, user_id)).fetchone()
        if row and row["itinerary"]:
            try:
                return json.loads(row["itinerary"])
            except json.JSONDecodeError:
                return None
        return None
    conv = convo_svc._anon_get(sid)
    return conv.itinerary if conv and conv.itinerary else None
