#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""登录页 + 身份 + 文旅局开发页 端到端"""
import httpx, json, time, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

B = 'http://127.0.0.1:8100'
c = httpx.Client(base_url=B, timeout=60)

print("=" * 74)
print("身份系统 + 文旅局开发页 端到端")
print("=" * 74)

ts = int(time.time())

# ── 1. 个人注册 ──
r = c.post('/api/auth/register', json={
    "email": f"person{ts}@test.com", "password": "pass123456",
    "nickname": "小张", "role": "person"})
print(f"\n[1] 个人注册: {r.status_code}")
u = r.json()['user']
print(f"    role={u['role']} org={u.get('org_name')}")
assert u['role'] == 'person'

r = c.get('/api/auth/me')
print(f"    /me 确认: role={r.json()['user']['role']}")

# ── 2. 个人访问开发页 API 应被拒 ──
r = c.get('/api/agents')
print(f"\n[2] 个人 GET /api/agents: {r.status_code}（期望 403）")
assert r.status_code == 403

# 发帖应可以（个人功能不受限）
r = c.post('/api/posts', json={"title": "个人的帖子", "type": "content"})
print(f"    个人发帖: {r.status_code}（期望 200，个人功能不受限）")

c.post('/api/auth/logout')

# ── 3. 文旅局注册 ──
c2 = httpx.Client(base_url=B, timeout=60)
r = c2.post('/api/auth/register', json={
    "email": f"cd{ts}@test.com", "password": "pass123456",
    "role": "agency", "org_name": "成都市文化广电旅游局", "region": "成都"})
print(f"\n[3] 文旅局注册: {r.status_code}")
u2 = r.json()['user']
print(f"    role={u2['role']} org={u2['org_name']} org_id={u2['org_id'][:8]}...")
assert u2['role'] == 'agency' and u2['org_name']

r = c2.get('/api/auth/me')
print(f"    /me: role={r.json()['user']['role']} org={r.json()['user']['org_name']}")

# ── 4. 文旅局缺机构名应被拒 ──
c3 = httpx.Client(base_url=B, timeout=60)
r = c3.post('/api/auth/register', json={
    "email": f"bad{ts}@test.com", "password": "pass123456", "role": "agency"})
print(f"\n[4] 文旅局不填机构名: {r.status_code}（期望 400）")
print(f"    错误: {r.json().get('error')}")
assert r.status_code == 400

# ── 5. 建智能体 ──
r = c2.get('/api/agents')
print(f"\n[5] 智能体列表: {r.json()['items']}")

r = c2.post('/api/agents', json={
    "name": "成都文旅助手", "region": "成都",
    "description": "带你逛遍成都的慢生活",
    "prompt": "你是成都本地向导，用户想放松时推荐巷子里的茶馆和郊野公园，避开人多网红点。"})
print(f"    创建: {r.status_code} id={r.json().get('id')}")
aid = r.json()['id']

# ── 6. 发布校验（缺字段应拦下）──
r = c2.post('/api/agents', json={"name": "残缺助手", "region": "", "prompt": ""})
aid2 = r.json()['id']
r = c2.post(f'/api/agents/{aid2}/publish')
print(f"\n[6] 发布缺字段的: {r.status_code}（期望 400）")
print(f"    错误: {r.json().get('error')}")
assert r.status_code == 400

# ── 7. 发布 ──
r = c2.post(f'/api/agents/{aid}/publish')
print(f"\n[7] 正常发布: {r.json()}")
assert r.json().get('ok')

r = c2.get('/api/agents')
print(f"    列表:")
for a in r.json()['items']:
    print(f"      - {a['name']} [{a['region']}] {a['status']}")

# ── 8. 跨团队越权 ──
c4 = httpx.Client(base_url=B, timeout=60)
r = c4.post('/api/auth/register', json={
    "email": f"xian{ts}@test.com", "password": "pass123456",
    "role": "agency", "org_name": "西安市文旅局", "region": "西安"})
r = c4.get(f'/api/agents/{aid}')
print(f"\n[8] 西安访问成都的智能体: {r.status_code}（期望 404）")
assert r.status_code == 404
r = c4.delete(f'/api/agents/{aid}')
print(f"    西安删成都的智能体: {r.status_code}（期望 404）")

# ── 9. 路由匹配 ──
from app.services import agents as agent_svc
hit = agent_svc.route_agent_by_region("成都")
print(f"\n[9] 按地区路由:")
print(f"    「成都」 → {hit['name'] if hit else 'None'}")
print(f"    「成都市」→ ", end="")
h2 = agent_svc.route_agent_by_region("成都市")
print(h2['name'] if h2 else 'None')
print(f"    「上海」 → ", end="")
h3 = agent_svc.route_agent_by_region("上海")
print(h3['name'] if h3 else 'None（正确，没发布上海的）')

# ── 10. 个人升级为文旅局 ──
c5 = httpx.Client(base_url=B, timeout=60)
c5.post('/api/auth/register', json={
    "email": f"up{ts}@test.com", "password": "pass123456", "role": "person"})
r = c5.post('/api/auth/upgrade-agency', json={
    "org_name": "杭州市文旅局", "region": "杭州"})
print(f"\n[10] 个人升级为文旅局: {r.json()}")
assert r.json().get('ok')
r = c5.get('/api/auth/me')
print(f"     升级后: role={r.json()['user']['role']} org={r.json()['user']['org_name']}")
# 升级后能建智能体
r = c5.post('/api/agents', json={"name": "杭州助手", "region": "杭州", "prompt": "西湖向导"})
print(f"     建智能体: {r.status_code}")

print()
print("=" * 74)
print("✓ 全部通过")
print("=" * 74)
