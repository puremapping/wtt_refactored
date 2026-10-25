#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文旅局智能体管理（开发页的后端）

设计要点：
  - 智能体**归属团队**（team_id），不是归属个人 —— 一个文旅局多人协作时共享
  - 所有查询强制带 team_id（越权防护，与 sessions 同一套纪律）
  - 暂不接 Coze：external_id 留空。将来接的时候只需填这个字段 + 加同步函数
"""
import uuid
from datetime import datetime
from typing import Optional

from app.core.db import connect


def _now():
    return datetime.now().isoformat()


def list_agents(team_id: str) -> list:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM agents WHERE team_id=? AND deleted_at IS NULL "
            "ORDER BY created_at DESC", (team_id,)).fetchall()
    return [dict(r) for r in rows]


def get_agent(agent_id: str, team_id: str) -> Optional[dict]:
    """⚠️ 必须校验归属 —— 不能只按 id 查"""
    with connect() as conn:
        r = conn.execute(
            "SELECT * FROM agents WHERE id=? AND team_id=? AND deleted_at IS NULL",
            (agent_id, team_id)).fetchone()
    return dict(r) if r else None


def create_agent(team_id: str, creator_id: str, name: str,
                 region: str = "", description: str = "",
                 prompt: str = "") -> str:
    if not (name or "").strip():
        raise ValueError("智能体名称不能为空")
    aid = uuid.uuid4().hex[:16]
    now = _now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO agents "
            "(id,team_id,creator_id,name,region,description,prompt,status,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (aid, team_id, creator_id, name.strip(), region.strip() or None,
             description.strip() or None, prompt.strip() or None, "draft", now, now))
    return aid


def update_agent(agent_id: str, team_id: str, **fields) -> bool:
    """更新，只允许改这几个字段"""
    allowed = ("name", "region", "description", "prompt")
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return False
    args = list(sets.values()) + [_now(), agent_id, team_id]
    with connect() as conn:
        cur = conn.execute(
            "UPDATE agents SET " + ",".join(f"{k}=?" for k in sets) +
            ",updated_at=? WHERE id=? AND team_id=? AND deleted_at IS NULL",
            args)
        return cur.rowcount > 0


def publish_agent(agent_id: str, team_id: str) -> dict:
    """发布。⚠️ 发布前必须有 prompt 和 region —— 否则主智能体没法路由到它"""
    with connect() as conn:
        r = conn.execute(
            "SELECT * FROM agents WHERE id=? AND team_id=? AND deleted_at IS NULL",
            (agent_id, team_id)).fetchone()
        if not r:
            return {"ok": False, "error": "智能体不存在"}
        problems = []
        if not r["prompt"]:
            problems.append("缺少人设/话术")
        if not r["region"]:
            problems.append("缺少覆盖地区（主智能体靠它路由）")
        if problems:
            return {"ok": False, "error": "、".join(problems)}

        conn.execute("UPDATE agents SET status='published',updated_at=? "
                     "WHERE id=? AND team_id=?", (_now(), agent_id, team_id))
    return {"ok": True}


def delete_agent(agent_id: str, team_id: str) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE agents SET deleted_at=? WHERE id=? AND team_id=? "
            "AND deleted_at IS NULL", (_now(), agent_id, team_id))
        return cur.rowcount > 0


def route_agent_by_region(region: str) -> Optional[dict]:
    """主智能体用：按地区找已发布的智能体

    匹配：region 完全等于，或互相包含（「成都」能匹到「成都市」）
    """
    if not region:
        return None
    with connect() as conn:
        rows = conn.execute(
            "SELECT a.*, t.name AS team_name FROM agents a "
            "JOIN teams t ON t.id = a.team_id "
            "WHERE a.status='published' AND a.deleted_at IS NULL").fetchall()

    key = region.strip()
    for r in rows:
        rr = (r["region"] or "").strip()
        if not rr:
            continue
        if rr == key or rr in key or key in rr:
            return dict(r)
    return None
