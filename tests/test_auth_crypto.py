"""认证加密原语：pbkdf2 密码 + HMAC 签名 cookie"""
import time

import pytest

from app.services import auth as auth_svc


# ── 密码 ──

def test_password_roundtrip():
    h = auth_svc.hash_password("secret123")
    assert ":" in h                      # salt:dk 结构
    assert auth_svc.verify_password("secret123", h)


def test_password_wrong_rejected():
    h = auth_svc.hash_password("secret123")
    assert not auth_svc.verify_password("wrong", h)
    assert not auth_svc.verify_password("", h)


def test_password_salt_unique():
    assert auth_svc.hash_password("same") != auth_svc.hash_password("same")


def test_password_malformed_stored():
    assert not auth_svc.verify_password("x", "not-a-valid-hash")
    assert not auth_svc.verify_password("x", "")


# ── token 签名 ──

def test_token_roundtrip():
    tok = auth_svc.make_token("user_abc")
    assert auth_svc.parse_token(tok) == "user_abc"


def test_token_expired():
    uid = "user_abc"
    ts = str(int(time.time()) - auth_svc.COOKIE_MAX_AGE - 10)
    msg = f"{uid}.{ts}"
    import hashlib, hmac as hmac_mod
    from app.core.config import SECRET_KEY
    sig = hmac_mod.new(SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()
    assert auth_svc.parse_token(f"{msg}.{sig}") is None


def test_token_tampered():
    tok = auth_svc.make_token("user_abc")
    uid, ts, sig = tok.split(".")
    bad_sig = ("0" if sig[0] != "0" else "1") + sig[1:]
    assert auth_svc.parse_token(f"{uid}.{ts}.{bad_sig}") is None


def test_token_garbage():
    assert auth_svc.parse_token("") is None
    assert auth_svc.parse_token("not-a-token") is None
    assert auth_svc.parse_token(None) is None


# ── 用户 CRUD（临时库）──

def test_register_login_roundtrip(tmp_db):
    u = auth_svc.register("a@test.com", "secret123", "小A")
    assert u["role"] == "person"
    logged = auth_svc.login("a@test.com", "secret123")
    assert logged["id"] == u["id"]
    assert logged["nickname"] == "小A"


def test_register_agency_creates_team(tmp_db):
    u = auth_svc.register("gov@test.com", "secret123", role="agency",
                          org_name="北京市文旅局", region="北京")
    assert u["role"] == "agency"
    assert u["org_id"]
    got = auth_svc.get_user(u["id"])
    assert got["org_name"] == "北京市文旅局"
    assert got["org_region"] == "北京"


def test_register_validation(tmp_db):
    with pytest.raises(auth_svc.AuthError):
        auth_svc.register("bad-email", "secret123")
    with pytest.raises(auth_svc.AuthError):
        auth_svc.register("a@test.com", "123")            # 密码太短
    with pytest.raises(auth_svc.AuthError):
        auth_svc.register("a@test.com", "secret123", role="hacker")
    auth_svc.register("a@test.com", "secret123")
    with pytest.raises(auth_svc.AuthError):
        auth_svc.register("a@test.com", "secret123")      # 重复邮箱
    with pytest.raises(auth_svc.AuthError):
        auth_svc.register("b@test.com", "secret123", role="agency")  # 机构名缺失


def test_login_wrong_password(tmp_db):
    auth_svc.register("a@test.com", "secret123")
    with pytest.raises(auth_svc.AuthError):
        auth_svc.login("a@test.com", "wrong!")


def test_delete_user_cascades(tmp_db):
    u = auth_svc.register("a@test.com", "secret123")
    auth_svc.delete_user(u["id"], "secret123")
    assert auth_svc.get_user(u["id"]) is None
    with pytest.raises(auth_svc.AuthError):
        auth_svc.delete_user(u["id"], "secret123")        # 已不存在
    auth_svc.register("a@test.com", "secret123")
    with pytest.raises(auth_svc.AuthError):
        auth_svc.delete_user(u["id"], "wrong!")           # 密码不对不删
