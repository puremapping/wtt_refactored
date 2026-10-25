"""API 层测试（TestClient，不起真服务、不碰真 LLM）

覆盖：注册/登录态、用户数据隔离、帖子权限、未登录拦截。
对话与行程生成接口涉及 LLM，不在本层测（编排层已用 FakeLLM 覆盖）。
"""
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
