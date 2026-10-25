#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""个人主页路由：资料 / 旅游回忆"""
import json

from fastapi import APIRouter, Depends, Request

from app.core.db import connect
from app.routers.deps import require_user

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("/profile")
def api_me_profile(user=Depends(require_user)):
    with connect() as conn:
        r = conn.execute("SELECT id,email,nickname,avatar_url,city,bio,created_at "
                         "FROM users WHERE id=?", (user["id"],)).fetchone()
    return dict(r) if r else {}


@router.post("/profile")
async def api_update_profile(request: Request, user=Depends(require_user)):
    body = await request.json()
    fields, args = [], []
    for k in ("nickname", "avatar_url", "city", "bio"):
        if k in body:
            fields.append(f"{k}=?")
            args.append(body[k])
    if not fields:
        return {"ok": True, "updated": 0}
    args.append(user["id"])
    with connect() as conn:
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id=?", args)
    return {"ok": True}


@router.get("/memories")
def api_me_memories(user=Depends(require_user)):
    """我的旅游回忆 —— 有行程的会话"""
    with connect() as conn:
        rows = conn.execute("""
            SELECT id, created_at, turn_count,
                   json_extract(profile,'$.primary') AS motivation,
                   itinerary
            FROM sessions
            WHERE user_id=? AND itinerary IS NOT NULL
              AND itinerary != '' AND itinerary != '{}'
            ORDER BY created_at DESC LIMIT 50
        """, (user["id"],)).fetchall()

    items = []
    for r in rows:
        try:
            it = json.loads(r["itinerary"])
        except (json.JSONDecodeError, TypeError):
            continue
        items.append({
            "session_id": r["id"],
            "created_at": r["created_at"],
            "motivation": r["motivation"],
            "stops_count": len(it.get("stops", [])),
            "hours": it.get("hours"),
            "narrative": (it.get("narrative") or "")[:120],
        })
    return {"items": items, "total": len(items)}
