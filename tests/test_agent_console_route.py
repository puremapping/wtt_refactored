#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""地区路由的选取规则（多智能体覆盖同一地区时选谁）

2026-10-29 实测踩到的坑：SQL 没 ORDER BY，返回顺序由 SQLite 决定，
结果集群里最新的智能体被旧记录顶掉，表现为「建了新的却没生效」。
"""
import sqlite3

import pytest

from app.services import agents as agent_svc


def _team(conn, team_id):
    conn.execute(
        "INSERT OR REPLACE INTO teams (id,name,region,owner_id,created_at) "
        "VALUES (?,?,?,?,datetime('now'))", (team_id, f"文旅局{team_id}", "成都", "u1"))


def _publish(conn, team_id, name, region, updated_at):
    """直接插一条已发布记录，可控 updated_at"""
    aid = f"id-{name}-{region}"
    conn.execute(
        "INSERT INTO agents (id,team_id,creator_id,name,region,prompt,status,"
        "kind,protocol,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (aid, team_id, "u1", name, region, "人设", "published",
         "builtin", "generic", updated_at, updated_at))
    return aid


@pytest.mark.parametrize("a_updated,b_updated,expect", [
    ("2026-10-01T00:00:00", "2026-10-29T00:00:00", "新"),
    ("2026-10-29T00:00:00", "2026-10-01T00:00:00", "旧"),
])
def test_latest_wins(tmp_db, a_updated, b_updated, expect):
    """同类匹配里，最近更新的那个生效 —— 不能被库里物理顺序左右"""
    conn = sqlite3.connect(tmp_db)
    _team(conn, "t1")
    _publish(conn, "t1", "旧", "成都", a_updated)
    _publish(conn, "t1", "新", "成都", b_updated)
    conn.commit()
    conn.close()

    hit = agent_svc.route_agent_by_region("成都")
    assert hit["name"] == expect


def test_exact_match_beats_fuzzy(tmp_db):
    """精确匹配优先：查「成都」时 region='成都' 赢过 region='成都市'，
    即使后者更新"""
    conn = sqlite3.connect(tmp_db)
    _team(conn, "t1")
    _publish(conn, "t1", "成都市局", "成都市", "2026-10-29T00:00:00")
    _publish(conn, "t1", "成都局", "成都", "2026-10-01T00:00:00")
    conn.commit()
    conn.close()

    hit = agent_svc.route_agent_by_region("成都")
    assert hit["name"] == "成都局"


def test_fuzzy_still_works_when_no_exact(tmp_db):
    """只有「成都市」时，查「成都」应该匹到它"""
    conn = sqlite3.connect(tmp_db)
    _team(conn, "t1")
    _publish(conn, "t1", "成都市局", "成都市", "2026-10-29T00:00:00")
    conn.commit()
    conn.close()

    hit = agent_svc.route_agent_by_region("成都")
    assert hit["name"] == "成都市局"


def test_no_match_returns_none(tmp_db):
    conn = sqlite3.connect(tmp_db)
    _team(conn, "t1")
    _publish(conn, "t1", "成都局", "成都", "2026-10-29T00:00:00")
    conn.commit()
    conn.close()

    assert agent_svc.route_agent_by_region("广州") is None
