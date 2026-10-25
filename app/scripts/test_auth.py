#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""认证 + 事件记录 单元测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.db import init_db, connect
from app.services import auth
from app.services import analytics as ana

init_db()

print("=" * 76)
print("认证服务测试")
print("=" * 76)

# 1. 密码哈希
print("\n[1] 密码哈希")
h = auth.hash_password("test123456")
print(f"  哈希: {h[:40]}...")
print(f"  正确密码验证: {auth.verify_password('test123456', h)}")
print(f"  错误密码验证: {auth.verify_password('wrong', h)}")
assert auth.verify_password("test123456", h)
assert not auth.verify_password("wrong", h)

# 2. Token 签名
print("\n[2] Cookie 签名")
t = auth.make_token("user_abc")
print(f"  token: {t[:50]}...")
print(f"  解析: {auth.parse_token(t)}")
print(f"  篡改后: {auth.parse_token(t[:-4] + '0000')}")
assert auth.parse_token(t) == "user_abc"
assert auth.parse_token(t[:-4] + "0000") is None

# 3. 注册/登录（用唯一邮箱避免冲突）
import time
email = f"test{int(time.time())}@example.com"
print(f"\n[3] 注册登录（{email}）")
u = auth.register(email, "pass123456")
print(f"  注册: {u}")
lu = auth.login(email, "pass123456")
print(f"  登录: {lu}")
assert u["id"] == lu["id"]

try:
    auth.register(email, "pass123456")
    print("  ✗ 重复注册应该失败")
except auth.AuthError as e:
    print(f"  ✓ 重复注册被拒: {e}")

try:
    auth.login(email, "wrongpass")
    print("  ✗ 错误密码应该失败")
except auth.AuthError as e:
    print(f"  ✓ 错误密码被拒: {e}")

try:
    auth.register("notanemail", "pass123456")
    print("  ✗ 非法邮箱应该失败")
except auth.AuthError as e:
    print(f"  ✓ 非法邮箱被拒: {e}")

# 4. 事件记录
print("\n[4] 事件记录")
sid = "sess_" + str(int(time.time()))
ana.track(ana.EV_MESSAGE_SENT, sid, u["id"], turn=1, text_len=15)
ana.track(ana.EV_ITINERARY_GENERATED, sid, u["id"], stops_count=4, hours=8)
ana.track(ana.EV_PROPOSAL_ACCEPTED, sid, u["id"], action="replace")
# 匿名事件应该被跳过
ana.track(ana.EV_MESSAGE_SENT, "anon_sess", None, turn=1)

with connect() as conn:
    n = conn.execute("SELECT COUNT(*) FROM events WHERE session_id=?",
                     (sid,)).fetchone()[0]
    n_anon = conn.execute(
        "SELECT COUNT(*) FROM events WHERE session_id=?", ("anon_sess",)).fetchone()[0]
print(f"  登录用户事件数: {n}（期望 3）")
print(f"  匿名事件数: {n_anon}（期望 0 —— 匿名不落库）")
assert n == 3 and n_anon == 0

# 5. 分析查询
print("\n[5] 分析查询")
rep = ana.report(days=30)
print(f"  overview: {rep['overview']}")
print(f"  funnel:   {rep['funnel']}")
print(f"  events:   {rep['events']}")

print()
print("=" * 76)
print("✓ 全部通过")
print("=" * 76)
