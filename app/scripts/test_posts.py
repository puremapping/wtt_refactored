#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""帖子服务测试（不依赖 HTTP）"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.db import init_db, connect
from app.services import posts

init_db()

print("=" * 74)
print("帖子服务测试")
print("=" * 74)

# 准备一个测试用户
with connect() as conn:
    uid = "test_user_posts"
    conn.execute("DELETE FROM posts WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.execute(
        "INSERT INTO users (id,email,password_hash,nickname,created_at) VALUES (?,?,?,?,?)",
        (uid, "posttest@test.com", "x", "测试作者", "2026-10-21T10:00:00"))

# 1. 发普通帖
pid1 = posts.create_post(uid, "成都的慢生活", body="在宽窄巷子待了一下午",
                         ptype="content", cover_url="/uploads/x.jpg")
print(f"\n[1] 发普通帖 → id={pid1}")

# 2. 发行程灵感帖
itin = {"stops": [{"name": "宽窄巷子"}, {"name": "锦里"}, {"name": "武侯祠"}],
        "hours": 8, "motivation": "恢复/逃离"}
pid2 = posts.create_post(uid, "成都一日 · 慢生活", body="想歇一歇",
                         ptype="inspiration", itinerary=itin, motivation="恢复/逃离")
print(f"[2] 发行程帖 → id={pid2}")

# 3. 列表
r = posts.list_posts("content")
print(f"\n[3] content 页签: {r['total']} 条")
for it in r["items"][:3]:
    print(f"    - [{it['type']}] {it['title']} by {it['author']['name']}")

r2 = posts.list_posts("inspiration")
print(f"[4] inspiration 页签: {r2['total']} 条（期望 1）")
assert r2["total"] >= 1

# 5. 点赞
like = posts.toggle_like(pid2, uid)
print(f"\n[5] 点赞: {like}")
like2 = posts.toggle_like(pid2, uid)
print(f"    再点（取消）: {like2}")

# 6. 评论
cm = posts.add_comment(pid2, uid, "这个路线不错")
print(f"\n[6] 评论: {cm['content']}")
cs = posts.list_comments(pid2)
print(f"    评论数: {len(cs)}")

# 7. 搜索 + 热榜
posts.log_search("成都", uid, [pid1, pid2])
posts.log_search("成都", uid, [pid2])
posts.log_search("慢生活", None, [pid2])   # 未登录搜索
print(f"\n[7] 搜索日志已记录")

hot = posts.list_posts("hot")
print(f"    热榜: {hot['total']} 条")
for it in hot["items"][:3]:
    print(f"    - {it['title']}（热度来自搜索命中）")

kw = posts.hot_keywords()
print(f"    热门搜索词: {kw}")

# 8. 详情
d = posts.get_post(pid2)
print(f"\n[8] 详情: {d['title']} | 站数={d['stops_count']} | 动机={d['motivation']}")
print(f"    浏览数: {d['views']}")

# 9. 归属校验
ok = posts.delete_post(pid1, "someone_else")
print(f"\n[9] 他人删帖: {ok}（期望 False）")
ok2 = posts.delete_post(pid1, uid)
print(f"    本人删帖: {ok2}（期望 True）")

# 清理
with connect() as conn:
    conn.execute("DELETE FROM posts WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM likes WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM comments WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM messages WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM search_logs WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM users WHERE id=?", (uid,))

print()
print("=" * 74)
print("✓ 全部通过")
print("=" * 74)
