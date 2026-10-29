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
                 prompt: str = "", kind: str = "builtin",
                 endpoint: str = "", auth: str = "") -> str:
    """建智能体。

    kind='builtin'  —— 平台内自建，靠 prompt 调 GLM（默认）
    kind='external' —— 外部注册，靠 endpoint 转发（prompt 可空）
    """
    if not (name or "").strip():
        raise ValueError("智能体名称不能为空")
    if kind not in ("builtin", "external"):
        raise ValueError(f"未知的智能体类型：{kind}")
    if kind == "external" and not (endpoint or "").strip():
        raise ValueError("外部智能体必须填写调用地址")

    aid = uuid.uuid4().hex[:16]
    now = _now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO agents "
            "(id,team_id,creator_id,name,region,description,prompt,status,"
            " kind,endpoint,auth,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (aid, team_id, creator_id, name.strip(), region.strip() or None,
             description.strip() or None, prompt.strip() or None, "draft",
             kind, endpoint.strip() or None, auth.strip() or None, now, now))
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
    """发布。⚠️ 发布前必须过准入检查 —— 否则主智能体没法路由到它，或者路由到了也答不出来

    两条轨的准入条件不同：
      builtin  —— 要 prompt（不然没话术）+ region（不然没法路由）
      external —— 要 endpoint（不然调不动）+ region；prompt 可空（对方自己有人设）
    共同要求：region 必填，这是路由的唯一依据。
    """
    with connect() as conn:
        r = conn.execute(
            "SELECT * FROM agents WHERE id=? AND team_id=? AND deleted_at IS NULL",
            (agent_id, team_id)).fetchone()
        if not r:
            return {"ok": False, "error": "智能体不存在"}
        problems = _publish_problems(dict(r))
        if problems:
            return {"ok": False, "error": "、".join(problems)}

        conn.execute("UPDATE agents SET status='published',updated_at=? "
                     "WHERE id=? AND team_id=?", (_now(), agent_id, team_id))
    return {"ok": True}


def _publish_problems(row: dict) -> list:
    """准入检查（纯函数，不碰库 —— 测试可直接调用）"""
    problems = []
    kind = (row.get("kind") or "builtin").strip().lower()

    if not (row.get("region") or "").strip():
        problems.append("缺少覆盖地区（主智能体靠它路由）")

    if kind == "external":
        if not (row.get("endpoint") or "").strip():
            problems.append("缺少调用地址")
    elif kind == "builtin":
        if not (row.get("prompt") or "").strip():
            problems.append("缺少人设/话术")
    else:
        problems.append(f"未知的智能体类型：{kind}")

    return problems


def delete_agent(agent_id: str, team_id: str) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE agents SET deleted_at=? WHERE id=? AND team_id=? "
            "AND deleted_at IS NULL", (_now(), agent_id, team_id))
        return cur.rowcount > 0


def route_agent_by_region(region: str) -> Optional[dict]:
    """主智能体用：按地区找已发布的智能体（返回数据库原始行）

    匹配：region 完全等于，或互相包含（「成都」能匹到「成都市」）

    ⚠️ 这是**取数据**。要拿来回答问题的，用 `find_region_agent()` ——
    它返回统一抽象 RegionAgent，两条轨对调用方同形。
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


def find_region_agent(region: str, **kwargs):
    """按地区找已发布智能体，返回**统一抽象**（app/services/agent_runtime.RegionAgent）

    与 route_agent_by_region 的区别：
      - 这个给主对话用，返回值可以直接 `.answer(question)`
      - 数据脏（kind 不认识 / 缺地区）时返回 None，不会把坏对象交出去

    kwargs（llm= / opener=）透传给底层实现，供测试注入。
    """
    from app.services.agent_runtime import build_agent

    row = route_agent_by_region(region)
    if not row:
        return None
    return build_agent(row, **kwargs)
