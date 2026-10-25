#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""会话持久化：登录走库，匿名走进程内存 TTL

核心规则（阿哲定的产品硬约束）：**匿名会话不落库**。
user_id 为空时只更新内存里的匿名会话，不写数据库。
"""
import json
import threading
import time
from datetime import datetime
from typing import Optional

from app.core.db import connect
from app.services.conversation.models import Conversation

# ── 匿名会话：进程内存储，带 TTL ──
# 设计：匿名不落库，刷新即丢；服务端只是暂存，避免一轮请求之间状态丢失
_ANON_SESSIONS: dict = {}
_ANON_LOCK = threading.Lock()
ANON_TTL = 3600          # 1 小时没访问就清


def _anon_put(conv: Conversation):
    with _ANON_LOCK:
        _ANON_SESSIONS[conv.session_id] = (conv, time.time())


def _anon_get(session_id: str) -> Optional[Conversation]:
    with _ANON_LOCK:
        item = _ANON_SESSIONS.get(session_id)
        if not item:
            return None
        conv, _ = item
        _ANON_SESSIONS[session_id] = (conv, time.time())
        return conv


def _anon_cleanup():
    """清理过期匿名会话（由后台线程定期调用）"""
    now = time.time()
    with _ANON_LOCK:
        dead = [k for k, (_, ts) in _ANON_SESSIONS.items()
                if now - ts > ANON_TTL]
        for k in dead:
            del _ANON_SESSIONS[k]
    return len(dead)


def save_session(conv: Conversation, user_id: str = None):
    """保存会话

    ⚠️ 核心规则：**匿名会话不落库**（阿哲定）。
    user_id 为空时只更新内存里的匿名会话，不写数据库。
    """
    if not user_id:
        _anon_put(conv)
        return
    with connect() as conn:
        conn.execute(
            """INSERT INTO sessions
                 (id, user_id, created_at, turn_count, profile, motivations, itinerary)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 profile     = excluded.profile,
                 motivations = excluded.motivations,
                 turn_count  = excluded.turn_count""",
            (conv.session_id, user_id, conv.created_at, conv.turn,
             json.dumps({
                 "profile": conv.profile,
                 "messages": conv.messages,
                 "turn": conv.turn,
                 "ready": conv.ready,
             }, ensure_ascii=False),
             json.dumps(conv.profile, ensure_ascii=False),
             "{}"))


def load_session(session_id: str, user_id: str = None) -> Optional[Conversation]:
    """载入会话

    user_id 为空 → 从匿名内存取；否则从 DB 取（且必须是该用户的）

    ⚠️ 匿名路径只触达进程内存，不查数据库 —— 无越权面（加固-2 复核记录）。
    """
    if not user_id:
        return _anon_get(session_id)

    with connect() as conn:
        row = conn.execute(
            "SELECT id, created_at, profile FROM sessions "
            "WHERE id=? AND user_id=?",
            (session_id, user_id)).fetchone()
    if not row:
        return None
    payload = json.loads(row["profile"] or "{}")
    return Conversation(
        session_id=row["id"],
        created_at=row["created_at"],
        profile=payload.get("profile", {}),
        messages=payload.get("messages", []),
        turn=payload.get("turn", 0),
        ready=payload.get("ready", False),
    )
