#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行为事件记录 + 分析查询

设计原则：
  - **只记登录用户的事件**（匿名会话不落库，也就没有事件）
  - 事件是 append-only 的原始数据，分析靠查询而非预聚合
  - **不记对话原文**，只记结构化字段（长度、类型、数量）

事件类型见 docs/DESIGN-user-system.md §3.3
"""
import json
from datetime import datetime, timedelta
from typing import Optional

from app.core.db import connect

# 事件类型常量（避免拼写错误）
EV_SESSION_START = "session_start"
EV_USER_REGISTER = "user_register"
EV_USER_LOGIN = "user_login"
EV_MESSAGE_SENT = "message_sent"
EV_PROFILE_UPDATED = "profile_updated"
EV_ITINERARY_GENERATED = "itinerary_generated"
EV_ITINERARY_MODIFIED = "itinerary_modified"
EV_PROPOSAL_ACCEPTED = "proposal_accepted"
EV_PROPOSAL_REJECTED = "proposal_rejected"
EV_SESSION_END = "session_end"


def track(event_type: str, session_id: str = None, user_id: str = None,
          **payload):
    """记录一个事件

    ⚠️ 只记登录用户。匿名（user_id 为空）直接跳过 —— 匿名数据不落库。
    """
    if not user_id:
        return
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO events (session_id,user_id,event_type,payload,created_at) "
                "VALUES (?,?,?,?,?)",
                (session_id, user_id, event_type,
                 json.dumps(payload, ensure_ascii=False) if payload else None,
                 datetime.now().isoformat()))
    except Exception:
        # 事件记录失败不能影响主流程
        pass


# ────────────────────── 分析查询 ──────────────────────

def overview(days: int = 30) -> dict:
    """整体概览（最近 N 天）"""
    since = (datetime.now() - timedelta(days=days)).isoformat()
    with connect() as conn:
        total_users = conn.execute(
            "SELECT COUNT(*) FROM users").fetchone()[0]
        new_users = conn.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?",
            (since,)).fetchone()[0]
        active = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM events WHERE created_at >= ?",
            (since,)).fetchone()[0]
        sessions = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE created_at >= ?",
            (since,)).fetchone()[0]
        avg_turns = conn.execute(
            "SELECT AVG(turn_count) FROM sessions WHERE created_at >= ?",
            (since,)).fetchone()[0]
    return {
        "days": days,
        "total_users": total_users,
        "new_users": new_users,
        "active_users": active,
        "sessions": sessions,
        "avg_turns": round(avg_turns, 1) if avg_turns else 0,
    }


def motivation_dist(days: int = 30) -> list:
    """动机分布"""
    since = (datetime.now() - timedelta(days=days)).isoformat()
    with connect() as conn:
        rows = conn.execute("""
            SELECT json_extract(profile, '$.primary') AS motivation,
                   COUNT(*) AS n
            FROM sessions
            WHERE created_at >= ? AND profile IS NOT NULL
            GROUP BY motivation
            HAVING motivation IS NOT NULL
            ORDER BY n DESC
        """, (since,)).fetchall()
    return [dict(r) for r in rows]


def funnel(days: int = 30) -> dict:
    """核心转化漏斗：注册 → 对话 → 生成行程 → 采纳修改"""
    since = (datetime.now() - timedelta(days=days)).isoformat()

    def uniq(evt):
        with connect() as conn:
            return conn.execute(
                "SELECT COUNT(DISTINCT session_id) FROM events "
                "WHERE event_type=? AND created_at>=?",
                (evt, since)).fetchone()[0]

    talked = uniq(EV_MESSAGE_SENT)
    gen = uniq(EV_ITINERARY_GENERATED)
    accepted = uniq(EV_PROPOSAL_ACCEPTED)
    rejected = uniq(EV_PROPOSAL_REJECTED)

    return {
        "sessions_with_message": talked,
        "generated": gen,
        "proposal_accepted": accepted,
        "proposal_rejected": rejected,
        "gen_rate": round(gen / talked * 100, 1) if talked else 0,
        "accept_rate": round(accepted / (accepted + rejected) * 100, 1)
                       if (accepted + rejected) else 0,
    }


def event_counts(days: int = 30) -> list:
    """各事件出现次数"""
    since = (datetime.now() - timedelta(days=days)).isoformat()
    with connect() as conn:
        rows = conn.execute("""
            SELECT event_type, COUNT(*) AS n
            FROM events WHERE created_at >= ?
            GROUP BY event_type ORDER BY n DESC
        """, (since,)).fetchall()
    return [dict(r) for r in rows]


def user_activity(days: int = 30, limit: int = 20) -> list:
    """用户活跃度排行"""
    since = (datetime.now() - timedelta(days=days)).isoformat()
    with connect() as conn:
        rows = conn.execute("""
            SELECT u.email,
                   COUNT(DISTINCT e.session_id) AS sessions,
                   COUNT(*) AS events,
                   MAX(e.created_at) AS last_active
            FROM events e JOIN users u ON u.id = e.user_id
            WHERE e.created_at >= ?
            GROUP BY e.user_id
            ORDER BY events DESC
            LIMIT ?
        """, (since, limit)).fetchall()
    return [dict(r) for r in rows]


def modification_stats(days: int = 30) -> list:
    """行程修改行为分布（用户都在改什么）"""
    since = (datetime.now() - timedelta(days=days)).isoformat()
    with connect() as conn:
        rows = conn.execute("""
            SELECT event_type,
                   json_extract(payload, '$.action') AS action,
                   COUNT(*) AS n
            FROM events
            WHERE created_at >= ?
              AND event_type IN ('itinerary_modified','proposal_accepted','proposal_rejected')
            GROUP BY event_type, action
            ORDER BY n DESC
        """, (since,)).fetchall()
    return [dict(r) for r in rows]


def report(days: int = 30) -> dict:
    """一次性产出完整报告"""
    return {
        "overview": overview(days),
        "motivations": motivation_dist(days),
        "funnel": funnel(days),
        "events": event_counts(days),
        "top_users": user_activity(days),
        "modifications": modification_stats(days),
    }
