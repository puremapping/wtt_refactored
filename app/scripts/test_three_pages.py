#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三页式产品端到端测试：注册 → 发帖 → 浏览 → 搜索 → 热榜 → 点赞 → 评论"""
import httpx, json, time

B = 'http://127.0.0.1:8100'
c = httpx.Client(base_url=B, timeout=120)

print("=" * 74)
print("三页式产品 端到端")
print("=" * 74)

# ── 1. 注册 ──
email = f"e2e{int(time.time())}@test.com"
r = c.post('/api/auth/register', json={"email": email, "password": "pass123456",
                                        "nickname": "E2E测试"})
print(f"\n[1] 注册: {r.status_code}")
u = r.json()['user']
print(f"    user_id={u['id'][:12]}... nickname={u['nickname']}")

# ── 2. 发行程灵感帖 ──
itin = {
    "stops": [{"name": "宽窄巷子", "arrive": "09:30"},
              {"name": "锦里", "arrive": "12:00"},
              {"name": "武侯祠", "arrive": "15:00"}],
    "hours": 8,
    "motivation": "恢复/逃离",
    "narrative": "想找个安静地方待一天，避开人潮。",
}
r = c.post('/api/posts', json={
    "title": "成都一日 · 慢生活",
    "body": "想歇一歇，找个人少的地方待着",
    "type": "inspiration",
    "itinerary": itin,
    "motivation": "恢复/逃离",
})
print(f"\n[2] 发行程帖: {r.status_code} → id={r.json().get('id')}")
pid = r.json()['id']

# ── 3. 发普通帖 ──
r = c.post('/api/posts', json={
    "title": "成都的咖啡馆推荐",
    "body": "玉林路那家不错",
    "type": "content",
})
print(f"[3] 发普通帖: {r.status_code} → id={r.json().get('id')}")
pid2 = r.json()['id']

# ── 4. 三个页签 ──
for tab in ('content', 'inspiration', 'hot'):
    r = c.get(f'/api/posts?tab={tab}')
    d = r.json()
    print(f"\n[4] 页签 {tab:12}: {d['total']} 条")
    for it in d['items'][:3]:
        print(f"      - [{it['type']}] {it['title']}")

# ── 5. 搜索（触发热榜）──
r = c.get('/api/posts?tab=content&keyword=成都')
print(f"\n[5] 搜索「成都」: {r.json()['total']} 条命中")

# 再搜两次制造热度
c.get('/api/posts?tab=content&keyword=成都')
c.get('/api/posts?tab=content&keyword=慢生活')

r = c.get('/api/posts?tab=hot')
hot = r.json()
print(f"    热榜: {hot['total']} 条")
for it in hot['items'][:3]:
    print(f"      - {it['title']}")

r = c.get('/api/search/hot_keywords')
print(f"    热门搜索词: {r.json()['items']}")

# ── 6. 详情 ──
r = c.get(f'/api/posts/{pid}')
d = r.json()
print(f"\n[6] 详情: {d['title']}")
print(f"    站数={d['stops_count']} 时长={d['hours']} 动机={d['motivation']}")
print(f"    行程站数校验: {len(d['itinerary']['stops'])} (期望 3)")

# ── 7. 点赞 ──
r = c.post(f'/api/posts/{pid}/like')
print(f"\n[7] 点赞: {r.json()}")
r = c.post(f'/api/posts/{pid}/like')
print(f"    取消: {r.json()}")

# ── 8. 评论 ──
r = c.post(f'/api/posts/{pid}/comments', json={"content": "这条路线收藏了"})
print(f"\n[8] 评论: {r.status_code}")
r = c.get(f'/api/posts/{pid}/comments')
print(f"    评论数: {len(r.json()['items'])}")

# ── 9. 个人主页数据 ──
r = c.get('/api/me/profile')
print(f"\n[9] 个人资料: {r.json().get('nickname')} / {r.json().get('email')}")

r = c.get('/api/me/memories')
print(f"    旅游回忆: {r.json()['total']} 条（未生成行程时应为 0）")

# ── 10. 消息 ──
r = c.get('/api/messages')
print(f"\n[10] 消息: {len(r.json()['items'])} 条")

# ── 11. 匿名浏览（应能看）──
anon = httpx.Client(base_url=B, timeout=30)
r = anon.get('/api/posts?tab=content')
print(f"\n[11] 匿名浏览: {r.status_code}，{r.json()['total']} 条 ✓")

# 匿名发帖应被拒
r = anon.post('/api/posts', json={"title": "匿名test"})
print(f"     匿名发帖: {r.status_code}（期望 401）")

# ── 12. 越权删帖 ──
email2 = f"e2e_b{int(time.time())}@test.com"
u2 = httpx.Client(base_url=B, timeout=30)
u2.post('/api/auth/register', json={"email": email2, "password": "pass123456"})
r = u2.delete(f'/api/posts/{pid}')
print(f"\n[12] 他人删帖: {r.status_code}（期望 404）")
r = c.delete(f'/api/posts/{pid2}')
print(f"     本人删帖: {r.status_code}（期望 200）")

print()
print("=" * 74)
print("测试完成")
print("=" * 74)
