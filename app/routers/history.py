#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户历史路由（登录用户，全部强制归属校验）"""
import json

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.db import connect
from app.routers.deps import require_user
from app.services import conversation as convo_svc

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
def history(user=Depends(require_user)):
    """我的会话列表（从 DB 查，只返回该用户的）"""
    with connect() as conn:
        rows = conn.execute("""
            SELECT id, created_at, turn_count,
                   json_extract(profile, '$.primary') AS motivation,
                   CASE WHEN itinerary IS NOT NULL AND itinerary != '' AND itinerary != '{}'
                        THEN 1 ELSE 0 END AS has_itinerary
            FROM sessions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 50
        """, (user["id"],)).fetchall()
    return {"count": len(rows), "items": [dict(r) for r in rows]}


@router.get("/{session_id}")
def history_detail(session_id: str, user=Depends(require_user)):
    """查看某个历史会话（归属校验）"""
    with connect() as conn:
        row = conn.execute(
            "SELECT id, created_at, profile, itinerary FROM sessions "
            "WHERE id=? AND user_id=?",
            (session_id, user["id"])).fetchone()
    if not row:
        return JSONResponse({"error": "会话不存在"}, status_code=404)

    payload = json.loads(row["profile"] or "{}")
    return {
        "session_id": row["id"],
        "created_at": row["created_at"],
        "profile": convo_svc.public_profile(payload.get("profile", {})),
        "messages": payload.get("messages", []),
        "itinerary": json.loads(row["itinerary"]) if row["itinerary"] else None,
    }


@router.delete("/{session_id}")
def delete_history(session_id: str, user=Depends(require_user)):
    """删除自己的某个会话"""
    with connect() as conn:
        cur = conn.execute("DELETE FROM sessions WHERE id=? AND user_id=?",
                           (session_id, user["id"]))
    if cur.rowcount == 0:
        return JSONResponse({"error": "会话不存在"}, status_code=404)
    return {"ok": True}
