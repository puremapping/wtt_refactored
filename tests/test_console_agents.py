#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文旅局开发台 /console 的 API（表单对接层）

覆盖：
  - 建两种类型的智能体
  - 鉴权头**不回传明文**（这是安全边界，不是可选优化）
  - 更新时 auth 留空 = 不改
  - 类型创建后不可改
"""
import pytest

from app.services import agents as agent_svc


def _mk_user(role="agency", org_id="t1", uid="u1", token="tok"):
    import sqlite3

    from app.core import db as db_module
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT OR REPLACE INTO users "
        "(id,email,password_hash,nickname,created_at,role,org_id) "
        "VALUES (?,?,?,?,datetime('now'),?,?)",
        (uid, f"{uid}@test.local", "x", "测试", role, org_id))
    conn.commit()
    conn.close()


def _mk_team(team_id="t1", name="成都市文旅局"):
    import sqlite3

    from app.core import db as db_module
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO teams (id,name,region,owner_id,created_at) "
        "VALUES (?,?,?,?,datetime('now'))",
        (team_id, name, "成都", "owner-" + team_id))
    conn.commit()
    conn.close()


@pytest.fixture()
def agency_client(tmp_db, monkeypatch):
    """已登录的文旅局账号"""
    _mk_team()
    _mk_user()

    from app.routers import deps
    from app.main import app
    from fastapi.testclient import TestClient

    fake = {"id": "u1", "role": "agency", "org_id": "t1", "nickname": "测试"}
    # API 路由用 require_user；页面路由（/console）用 current_user_optional
    app.dependency_overrides[deps.require_user] = lambda: fake
    app.dependency_overrides[deps.current_user_optional] = lambda: fake
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


# ──────────────────────────────────────────────────────────────
# 建两种类型
# ──────────────────────────────────────────────────────────────

def test_create_builtin_via_api(agency_client):
    r = agency_client.post("/api/agents", json={
        "name": "成都小助手", "region": "成都",
        "description": "慢生活", "prompt": "热情", "kind": "builtin"})
    assert r.status_code == 200 and r.json()["ok"]

    items = agency_client.get("/api/agents").json()["items"]
    assert len(items) == 1
    assert items[0]["kind"] == "builtin"
    assert items[0]["prompt"] == "热情"


def test_create_external_via_api(agency_client):
    r = agency_client.post("/api/agents", json={
        "name": "上海外站", "region": "上海", "kind": "external",
        "endpoint": "https://x/chat", "auth": "Bearer sk-abc"})
    assert r.status_code == 200

    a = agency_client.get("/api/agents").json()["items"][0]
    assert a["kind"] == "external"
    assert a["endpoint"] == "https://x/chat"
    assert a["has_auth"] is True


def test_create_external_without_endpoint_rejected(agency_client):
    r = agency_client.post("/api/agents", json={
        "name": "x", "region": "上海", "kind": "external"})
    assert r.status_code == 400
    assert "调用地址" in r.json()["error"]


def test_create_unknown_kind_rejected(agency_client):
    r = agency_client.post("/api/agents", json={
        "name": "x", "region": "上海", "kind": "coze", "prompt": "p"})
    assert r.status_code == 400


# ──────────────────────────────────────────────────────────────
# 安全边界：鉴权头不回传明文
# ──────────────────────────────────────────────────────────────

def test_auth_never_returned_in_plaintext(agency_client):
    """⚠️ 这是安全边界，不是可选优化。

    auth 里是 `Bearer sk-xxx` 明文凭证。列表页一旦回传，凭证就散落在
    每个渲染分支、每条日志、每次浏览器缓存里。
    """
    agency_client.post("/api/agents", json={
        "name": "外部", "region": "上海", "kind": "external",
        "endpoint": "https://x/chat", "auth": "Bearer sk-SECRET-123"})

    items = agency_client.get("/api/agents").json()["items"]
    raw = str(items)
    assert "sk-SECRET-123" not in raw, "鉴权头明文泄漏到列表接口"
    assert items[0]["auth"] == ""
    assert items[0]["has_auth"] is True

    one = agency_client.get(f"/api/agents/{items[0]['id']}").json()
    assert "sk-SECRET-123" not in str(one), "鉴权头明文泄漏到详情接口"
    assert one["has_auth"] is True


def test_agent_without_auth_reports_has_auth_false(agency_client):
    agency_client.post("/api/agents", json={
        "name": "无鉴权", "region": "上海", "kind": "external",
        "endpoint": "https://x/chat"})
    a = agency_client.get("/api/agents").json()["items"][0]
    assert a["has_auth"] is False


# ──────────────────────────────────────────────────────────────
# 更新语义
# ──────────────────────────────────────────────────────────────

def test_update_auth_omitted_keeps_original(agency_client):
    """编辑时 auth 留空 = 不改（前端不会回显明文，所以不能靠空值清空）"""
    import sqlite3

    from app.core import db as db_module

    agency_client.post("/api/agents", json={
        "name": "外部", "region": "上海", "kind": "external",
        "endpoint": "https://x/chat", "auth": "Bearer keep-me"})
    aid = agency_client.get("/api/agents").json()["items"][0]["id"]

    # 只改名，不带 auth
    agency_client.post(f"/api/agents/{aid}", json={"name": "改过的名字"})

    conn = sqlite3.connect(db_module.DB_PATH)
    got = conn.execute("SELECT auth, name FROM agents WHERE id=?", (aid,)).fetchone()
    conn.close()
    assert got[0] == "Bearer keep-me", "auth 被空值覆盖了"
    assert got[1] == "改过的名字"


def test_update_auth_replaces_when_provided(agency_client):
    import sqlite3

    from app.core import db as db_module

    agency_client.post("/api/agents", json={
        "name": "外部", "region": "上海", "kind": "external",
        "endpoint": "https://x/chat", "auth": "Bearer old"})
    aid = agency_client.get("/api/agents").json()["items"][0]["id"]

    agency_client.post(f"/api/agents/{aid}", json={"auth": "Bearer new"})

    conn = sqlite3.connect(db_module.DB_PATH)
    got = conn.execute("SELECT auth FROM agents WHERE id=?", (aid,)).fetchone()
    conn.close()
    assert got[0] == "Bearer new"


def test_update_can_change_endpoint(agency_client):
    agency_client.post("/api/agents", json={
        "name": "外部", "region": "上海", "kind": "external",
        "endpoint": "https://old/chat"})
    aid = agency_client.get("/api/agents").json()["items"][0]["id"]

    agency_client.post(f"/api/agents/{aid}",
                       json={"endpoint": "https://new/chat"})
    a = agency_client.get(f"/api/agents/{aid}").json()
    assert a["endpoint"] == "https://new/chat"


def test_auth_can_be_cleared_explicitly(agency_client):
    """⚠️ 三态语义：不传=不改，传非空=覆盖，传空串=清空

    前端不回显明文，所以「留空」不能等同于「清空」—— 否则用户只是改个名字
    就会把鉴权弄丢。要清空必须显式传空字符串（前端有勾选框）。
    """
    import sqlite3

    from app.core import db as db_module

    agency_client.post("/api/agents", json={
        "name": "外部", "region": "上海", "kind": "external",
        "endpoint": "https://x/chat", "auth": "Bearer to-be-removed"})
    aid = agency_client.get("/api/agents").json()["items"][0]["id"]

    agency_client.post(f"/api/agents/{aid}", json={"auth": ""})

    conn = sqlite3.connect(db_module.DB_PATH)
    got = conn.execute("SELECT auth FROM agents WHERE id=?", (aid,)).fetchone()
    conn.close()
    assert got[0] is None, "显式传空串应当清空鉴权"

    a = agency_client.get(f"/api/agents/{aid}").json()
    assert a["has_auth"] is False


def test_switching_kind_after_creation(agency_client):
    import sqlite3

    from app.core import db as db_module

    agency_client.post("/api/agents", json={
        "name": "外部", "region": "上海", "kind": "external",
        "endpoint": "https://x/chat"})
    aid = agency_client.get("/api/agents").json()["items"][0]["id"]

    agency_client.post(f"/api/agents/{aid}", json={"kind": "builtin"})

    conn = sqlite3.connect(db_module.DB_PATH)
    got = conn.execute("SELECT kind FROM agents WHERE id=?", (aid,)).fetchone()
    conn.close()
    assert got[0] == "external"


# ──────────────────────────────────────────────────────────────
# 发布准入：两条轨不同条件（API 层再确认一次）
# ──────────────────────────────────────────────────────────────

def test_publish_external_without_prompt_succeeds(agency_client):
    """外部轨不要求 prompt —— 人设是对方那边的事"""
    agency_client.post("/api/agents", json={
        "name": "外部", "region": "上海", "kind": "external",
        "endpoint": "https://x/chat"})
    aid = agency_client.get("/api/agents").json()["items"][0]["id"]

    r = agency_client.post(f"/api/agents/{aid}/publish")
    assert r.status_code == 200 and r.json()["ok"]


def test_publish_builtin_without_prompt_rejected(agency_client):
    aid = agent_svc.create_agent("t1", "u1", name="内置", region="成都")
    r = agency_client.post(f"/api/agents/{aid}/publish")
    assert r.status_code == 400
    assert "人设" in r.json()["error"]


# ──────────────────────────────────────────────────────────────
# 页面能渲染
# ──────────────────────────────────────────────────────────────

def test_console_page_renders_with_new_fields(agency_client):
    r = agency_client.get("/console")
    assert r.status_code == 200
    html = r.text
    for marker in ("a-kind", "a-endpoint", "a-auth", "fld-builtin", "fld-external"):
        assert marker in html, f"表单缺少 {marker}"
