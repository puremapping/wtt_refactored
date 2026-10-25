#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""行程路由：生成 / 修改 / 推荐 / 景区列表 / 统计 / 健康检查"""
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.db import connect
from app.routers.deps import current_user_optional
from app.services import analytics as ana
from app.services import conversation as convo_svc
from app.services import itinerary as itin_svc
from app.services import itinerary_flow as flow
from app.services import narrative as nar_svc
from app.services import recommend as rec_svc

router = APIRouter(tags=["itinerary"])


@router.post("/api/recommend")
async def recommend(request: Request):
    """按动机推荐景区

    body 可选 city：限定城市（多城隔离，Phase 2c）；缺省 = 全部城市。
    """
    body = await request.json()
    mot = body.get("motivation") or "探索/新奇"
    intensity = int(body.get("intensity") or 3)
    top_k = int(body.get("top_k") or 8)
    city = body.get("city") or None

    items = rec_svc.recommend(mot, intensity, top_k, city=city)
    return {"motivation": mot, "city": city or "",
            "items": [i.to_dict() for i in items]}


@router.post("/api/itinerary")
async def make_itinerary(request: Request, user=Depends(current_user_optional)):
    """生成行程（显式接口）"""
    body = await request.json()
    sid = body.get("session_id")
    uid = user["id"] if user else None

    if not sid:
        sid = uuid.uuid4().hex[:12]
        if uid:
            with connect() as conn:
                conn.execute(
                    "INSERT INTO sessions "
                    "(id,user_id,created_at,profile,motivations,itinerary) "
                    "VALUES (?,?,?,?,?,?)",
                    (sid, uid, datetime.now().isoformat(), "{}", "{}", "{}"))
        else:
            # 匿名：建内存会话
            conv = convo_svc.Conversation(
                session_id=sid, created_at=datetime.now().isoformat())
            convo_svc._anon_put(conv)

    hours = body.get("hours")
    try:
        hours = int(hours) if hours else None
    except (ValueError, TypeError):
        hours = None

    d = flow.generate_itinerary(sid, hours, user_id=uid)
    d["session_id"] = sid
    ana.track(ana.EV_ITINERARY_GENERATED, sid, uid,
              stops_count=len(d.get("stops", [])),
              motivation=d.get("motivation"))
    return d


@router.post("/api/itinerary/modify")
async def modify_itinerary(request: Request, user=Depends(current_user_optional)):
    """落实行程修改（用户确认后调用）

    body: {session_id, action, target}
    ⚠️ 归属校验：只能改自己的会话
    """
    body = await request.json()
    sid = body.get("session_id")
    action = body.get("action")
    target = body.get("target")
    uid = user["id"] if user else None

    if not sid or not action:
        return JSONResponse({"error": "缺少 session_id 或 action"},
                            status_code=400)

    # 取行程（带归属校验）
    cur = flow.load_itinerary(sid, uid)
    if not cur:
        return JSONResponse({"error": "当前没有行程可修改"}, status_code=400)

    profile = flow.load_profile(sid, uid)
    cand = flow.build_candidates(profile)

    new_it = itin_svc.apply_modification(
        cur, action, target=target, candidates=cand,
        motivation=profile.get("primary") or cur.get("motivation"),
        hours=profile.get("hours") or cur.get("hours"))

    if not new_it:
        return JSONResponse({"error": "无法完成该修改（可能候选不足）"},
                            status_code=400)

    # 重新生成叙述
    try:
        new_it["narrative"] = nar_svc.narrate(
            new_it, new_it.get("motivation", ""), profile=profile)
        new_it["assessment"] = nar_svc.assess(new_it)
    except Exception:
        new_it["narrative"] = cur.get("narrative", "")
        new_it["assessment"] = cur.get("assessment", {})

    new_it["profile"] = profile
    if uid:
        # ⚠️ 加固-1：归属条件补齐 AND user_id=?（项目纪律：所有查询强制 user_id）
        with connect() as conn:
            conn.execute(
                "UPDATE sessions SET itinerary=? WHERE id=? AND user_id=?",
                (json.dumps(new_it, ensure_ascii=False), sid, uid))
    else:
        # ⚠️ BUG-9 修复：匿名会话只存在内存、数据库无此行 ——
        #    原实现只写库，更新落空，下一轮对话 AI 看到的还是旧行程。
        conv = convo_svc._anon_get(sid)
        if conv:
            conv.itinerary = new_it
            convo_svc._anon_put(conv)

    new_it["session_id"] = sid
    return new_it


@router.get("/api/attractions")
def list_attractions(limit: int = 50, district: str = None):
    """景区列表（调试/浏览用）"""
    sql = ("SELECT id,name,level,district,address,lon,lat,ticket_free,"
           "price_high,price_low FROM attractions WHERE 1=1")
    args = []
    if district:
        sql += " AND district LIKE ?"
        args.append(f"%{district}%")
    sql += " LIMIT ?"
    args.append(limit)

    with connect() as conn:
        rows = [dict(r) for r in conn.execute(sql, args)]
    return {"count": len(rows), "items": rows}


@router.get("/api/stats")
def stats():
    """数据统计"""
    with connect() as conn:
        out = {}
        for t in ("attractions", "transport", "crowd_index", "sessions"):
            out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        out["attractions_with_coord"] = conn.execute(
            "SELECT COUNT(*) FROM attractions WHERE lon IS NOT NULL").fetchone()[0]
    return out


@router.get("/api/health")
def health():
    return {"ok": True}
