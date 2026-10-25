"""API 层测试（TestClient，不起真服务、不碰真 LLM）

覆盖：注册/登录态、用户数据隔离、帖子权限、未登录拦截。
对话与行程生成接口涉及 LLM，不在本层测（编排层已用 FakeLLM 覆盖）。
"""
import os
import uuid

import pytest
from fastapi.testclient import TestClient

import app.core.db as db_module
from app.main import app


@pytest.fixture()
def client(tmp_db):
    # startup 事件里的 init_db 用的是 db_module.DB_PATH（已被 patch）
    with TestClient(app) as c:
        yield c


def _register(client, email=None, password="secret123", **kw):
    email = email or f"{uuid.uuid4().hex[:10]}@test.com"
    body = {"email": email, "password": password, **kw}
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 200, r.text
    return email, r.json()["user"]


# ── 认证 ──

def test_register_login_me_logout(client):
    email, user = _register(client)
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["user"]["email"] == email

    client.post("/api/auth/logout")
    r = client.get("/api/auth/me")
    assert r.json()["user"] is None

    r = client.post("/api/auth/login", json={"email": email, "password": "secret123"})
    assert r.status_code == 200
    assert client.get("/api/auth/me").json()["user"]["email"] == email


def test_login_wrong_password_401(client):
    email, _ = _register(client)
    r = client.post("/api/auth/login", json={"email": email, "password": "wrong!"})
    assert r.status_code == 401


def test_register_bad_request(client):
    r = client.post("/api/auth/register", json={"email": "bad", "password": "x"})
    assert r.status_code == 400


# ── 未登录拦截 ──

def test_protected_endpoints_require_login(client):
    for method, path in (("GET", "/api/history"), ("GET", "/api/me/memories"),
                         ("GET", "/api/messages")):
        r = getattr(client, method.lower())(path)
        assert r.status_code == 401, path


# ── 用户数据隔离 ──

def test_users_cannot_see_or_delete_others_history(client):
    _, user_a = _register(client)
    email_b, _ = _register(client)

    # A 建一个会话（直接插库，绕过 LLM）
    import sqlite3
    from app.core.config import DB_PATH  # 已被 patch 到临时库 —— 通过 db_module 取
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        "INSERT INTO sessions (id,user_id,created_at,profile,motivations,itinerary) "
        "VALUES ('sess_a1', ?, '2026-10-25T10:00:00', '{}', '{}', '{}')", (user_a["id"],))
    conn.commit()
    conn.close()

    # B（当前登录态是 B，因为 _register 后者是最后注册的）试图读/删 A 的会话
    r = client.get("/api/history/sess_a1")
    assert r.status_code == 404, "B 不得读到 A 的会话"
    r = client.delete("/api/history/sess_a1")
    assert r.status_code == 404, "B 不得删 A 的会话"

    # B 的历史列表里没有 A 的会话
    r = client.get("/api/history")
    assert all(item["id"] != "sess_a1" for item in r.json()["items"])


# ── 帖子权限 ──

def test_post_requires_login_and_respects_ownership(client):
    _, user_a = _register(client)

    r = client.post("/api/posts", json={"title": "A 的帖子"})
    assert r.status_code == 200
    post_id = r.json()["id"]

    # B 登录后删 A 的帖子 → 404
    _register(client)
    r = client.delete(f"/api/posts/{post_id}")
    assert r.status_code == 404

    # 帖子还在
    r = client.get(f"/api/posts/{post_id}")
    assert r.status_code == 200


def test_like_toggle(client):
    _, _ = _register(client)
    r = client.post("/api/posts", json={"title": "点赞测试"})
    post_id = r.json()["id"]

    email_b, _ = _register(client)
    r = client.post(f"/api/posts/{post_id}/like")
    assert r.json() == {"liked": True, "likes": 1}
    r = client.post(f"/api/posts/{post_id}/like")
    assert r.json() == {"liked": False, "likes": 0}


def test_liked_flag_per_viewer(client):
    """BUG-4 修复回归：列表的 liked 按查看者标记（批量查询后行为不变）"""
    email_a, _ = _register(client)                 # A
    r = client.post("/api/posts", json={"title": "标记测试"})
    post_id = r.json()["id"]

    _register(client)                              # 当前登录态 = B
    client.post(f"/api/posts/{post_id}/like")

    items = {i["id"]: i for i in client.get("/api/posts").json()["items"]}
    assert items[post_id]["liked"] is True         # B 点过赞

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": email_a, "password": "secret123"})
    items = {i["id"]: i for i in client.get("/api/posts").json()["items"]}
    assert items[post_id]["liked"] is False        # A 没点过


def test_analytics_token_via_header(client):
    """BUG-6 修复回归：看板凭证走 X-Admin-Token 请求头"""
    real = os.environ.get("ADMIN_TOKEN", "")
    assert real, "测试环境必须配置 ADMIN_TOKEN"
    # 无 token → 403
    r = client.get("/api/analytics/report?days=7")
    assert r.status_code == 403
    # 请求头 → 200
    r = client.get("/api/analytics/report?days=7",
                   headers={"X-Admin-Token": real})
    assert r.status_code == 200
    # 错误 token → 403
    r = client.get("/api/analytics/report?days=7",
                   headers={"X-Admin-Token": "wrong"})
    assert r.status_code == 403
    # 旧式 query 参数仍兼容（仅过渡期）
    r = client.get(f"/api/analytics/report?days=7&token={real}")
    assert r.status_code == 200


def test_inspiration_post_requires_itinerary(client):
    _register(client)
    r = client.post("/api/posts", json={"title": "灵感帖", "type": "inspiration"})
    assert r.status_code == 400
    r = client.post("/api/posts", json={
        "title": "灵感帖", "type": "inspiration",
        "itinerary": {"motivation": "恢复/逃离", "hours": 8, "stops": []}})
    assert r.status_code == 200


def test_anonymous_can_browse_posts(client):
    # 匿名（无 cookie）可看列表和详情
    r = client.get("/api/posts")
    assert r.status_code == 200
    r = client.get("/api/search/hot_keywords")
    assert r.status_code == 200


def test_anonymous_modify_updates_memory_session(client, tmp_db, monkeypatch):
    """BUG-9 修复回归：匿名用户确认修改后，内存会话里的行程必须更新

    （原实现只写库，匿名会话库里无行 → 更新落空，下一轮对话 AI 看到旧行程）
    """
    # 叙述/评估需要真 LLM —— 替换为桩，专注测数据流
    from app.services import narrative as nar_svc
    monkeypatch.setattr(nar_svc, "narrate", lambda d, m, **kw: "（测试叙述）")
    monkeypatch.setattr(nar_svc, "assess", lambda d, **kw: {
        "intensity": "中", "strength": "", "suggestion": ""})

    import sqlite3
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        "INSERT INTO attractions (id,name,city,level,district,lon,lat,ticket_free) "
        "VALUES (1,'故宫博物院','北京','5A','东城区',116.397,39.918,1),"
        "(2,'天坛公园','北京','5A','东城区',116.410,39.882,1),"
        "(3,'景山公园','北京','4A','西城区',116.394,39.925,1)")
    conn.execute("INSERT INTO transport (attraction_name,district,metro) "
                 "VALUES ('故宫博物院','东城区','地铁1号线'),"
                 "('天坛公园','东城区','地铁5号线'),"
                 "('景山公园','西城区','地铁1号线')")
    conn.commit()
    conn.close()

    from app.services import cities as cities_svc
    cities_svc.invalidate()

    # 1. 匿名生成行程（不登录 → 内存会话）
    r = client.post("/api/itinerary", json={"hours": 4})
    assert r.status_code == 200, r.text
    d = r.json()
    sid = d["session_id"]
    assert d["stops"], "测试前提：生成的行程有站点"

    # 2. 匿名确认修改（删掉第一站）
    target = d["stops"][0]["name"]
    r = client.post("/api/itinerary/modify", json={
        "session_id": sid, "action": "remove", "target": target})
    assert r.status_code == 200, r.text
    new_names = [s["name"] for s in r.json()["stops"]]
    assert target not in new_names

    # 3. 关键断言：内存会话里的行程已被更新（BUG-9 修的就是这一步）
    from app.services import conversation as convo
    conv = convo._anon_get(sid)
    assert conv is not None and conv.itinerary
    assert target not in [s["name"] for s in conv.itinerary["stops"]]


# ── 只读接口 ──

def test_stats_and_attractions(client, seed_beijing):
    r = client.get("/api/stats")
    assert r.json()["attractions"] == 5
    r = client.get("/api/attractions")
    assert r.json()["count"] == 5
    r = client.get("/api/attractions", params={"district": "东城"})
    assert r.json()["count"] == 2


def test_recommend_endpoint(client, seed_beijing):
    r = client.post("/api/recommend", json={"motivation": "成就/完成", "intensity": 3})
    assert r.status_code == 200
    items = r.json()["items"]
    assert items and all("name" in i and "score" in i for i in items)
