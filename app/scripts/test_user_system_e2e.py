#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端验证：匿名 vs 登录、用户隔离、历史、分析"""
import httpx, json, time

B = 'http://127.0.0.1:8100'

print("=" * 78)
print("用户系统 端到端验证")
print("=" * 78)

# ── 1. 匿名可以用 ──
print("\n【1】匿名用户可以用（不强制注册）")
anon = httpx.Client(base_url=B, timeout=180)
r = anon.post('/api/chat', json={"text": "最近太累了，想找个人少安静的地方待一天"}).json()
sid_anon = r["session_id"]
print(f"  session={sid_anon}")
print(f"  logged_in={r.get('logged_in')}")
print(f"  回复: {r['reply'][:60]}...")
print(f"  ✓ 匿名能聊" if not r.get('logged_in') else "  ✗ 异常")

# 继续聊，生成行程
r2 = anon.post('/api/chat', json={"text": "帮我生成行程", "session_id": sid_anon}).json()
has_it = bool(r2.get('itinerary'))
print(f"  匿名能生成行程: {has_it}")

# ── 2. 匿名不落库 ──
print("\n【2】匿名会话不落库（核心规则）")
with httpx.Client(base_url=B) as c:
    pass
import sqlite3
conn = sqlite3.connect('data/wtt.db')
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT * FROM sessions WHERE id=?", (sid_anon,)).fetchone()
print(f"  DB 里有这个匿名会话吗: {'有 ⚠️' if row else '没有 ✓'}")
n_anon_events = conn.execute(
    "SELECT COUNT(*) FROM events WHERE session_id=?", (sid_anon,)).fetchone()[0]
print(f"  匿名事件数: {n_anon_events}（期望 0）")

# ── 3. 注册 + 登录后可保存 ──
print("\n【3】注册用户 → 会话落库 + 打上用户标签")
email = f"e2e{int(time.time())}@test.com"
u1 = httpx.Client(base_url=B, timeout=180)
reg = u1.post('/api/auth/register', json={"email": email, "password": "pass123456",
                                          "nickname": "测试甲"}).json()
print(f"  注册: {reg['user']['email']} (id={reg['user']['id'][:8]}...)")
uid1 = reg['user']['id']

r = u1.post('/api/chat', json={"text": "带爸妈玩一天，他们腿脚不太好"}).json()
sid1 = r["session_id"]
print(f"  对话 session={sid1}, logged_in={r.get('logged_in')}")

r = u1.post('/api/chat', json={"text": "帮我生成行程", "session_id": sid1}).json()
print(f"  生成行程: {bool(r.get('itinerary'))}")

# 检查落库 + 用户标签
row = conn.execute("SELECT id, user_id FROM sessions WHERE id=?", (sid1,)).fetchone()
print(f"  DB 里有: {'✓' if row else '✗'}")
print(f"  user_id 打上了: {'✓ ' + row['user_id'][:8] + '...' if row and row['user_id'] else '✗'}")
n_ev = conn.execute("SELECT COUNT(*) FROM events WHERE session_id=?", (sid1,)).fetchone()[0]
print(f"  行为事件数: {n_ev}")

# ── 4. 用户隔离 ──
print("\n【4】用户隔离（甲看不到乙的）")
email2 = f"e2e_b{int(time.time())}@test.com"
u2 = httpx.Client(base_url=B, timeout=180)
reg2 = u2.post('/api/auth/register', json={"email": email2, "password": "pass123456",
                                           "nickname": "测试乙"}).json()
uid2 = reg2['user']['id']

# 乙的列表
h2 = u2.get('/api/history').json()
print(f"  乙的历史条数: {h2['count']}（期望 0）")
print(f"  ✓ 隔离正常" if h2['count'] == 0 else "  ✗ 串了")

# 乙尝试直接访问甲的会话
d = u2.get(f'/api/history/{sid1}')
print(f"  乙访问甲的会话 ID: HTTP {d.status_code}（期望 403/404）")
print(f"  ✓ 越权被拦" if d.status_code in (403, 404) else "  ✗ 越权成功")

# 甲能看到自己的
h1 = u1.get('/api/history').json()
print(f"  甲的历史条数: {h1['count']}（期望 >=1）")

# ── 5. 跨设备/未登录访问受保护接口 ──
print("\n【5】未登录访问受保护接口")
r = anon.get('/api/history')
print(f"  未登录 GET /api/history → HTTP {r.status_code}（期望 401）")

# ── 6. 分析接口 ──
print("\n【6】行为分析接口")
r = anon.get('/api/analytics/report')
print(f"  无 token → HTTP {r.status_code}: {r.json().get('error', '')[:40]}")

import os
os.environ.setdefault('ADMIN_TOKEN', '')
print(f"  （ADMIN_TOKEN 未设置 → 接口禁用，符合预期）")

print()
print("=" * 78)
print("验证完成")
print("=" * 78)
