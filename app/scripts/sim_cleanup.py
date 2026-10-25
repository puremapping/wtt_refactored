#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清除社区模拟机器人的全部痕迹（@sim.local 账号 + 模拟机构 + 其数据）

⚠️ 只删模拟机器人产生的内容，真实用户数据不受影响。
用法：.venv/Scripts/python.exe app/scripts/sim_cleanup.py   （先 --dry-run 预览）
"""
import sqlite3
import sys

DB = "data/wtt.db"


def main(dry_run=True):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row

    bots = [r["id"] for r in c.execute(
        "SELECT id FROM users WHERE email LIKE '%@sim.local'")]
    orgs = [r["id"] for r in c.execute(
        "SELECT id FROM teams WHERE name LIKE '%模拟%'")]
    posts = [r["id"] for r in c.execute(
        f"SELECT id FROM posts WHERE user_id IN ({','.join('?'*len(bots))})",
        bots)] if bots else []
    agents = [r["id"] for r in c.execute(
        f"SELECT id FROM agents WHERE creator_id IN ({','.join('?'*len(bots))})",
        bots)] if bots else []

    print(f"将删除：{len(bots)} 个机器人账号 / {len(orgs)} 个模拟机构 / "
          f"{len(posts)} 个帖子 / {len(agents)} 个智能体及关联数据")
    if dry_run:
        print("(dry-run，加参数 apply 执行)")
        return

    q = ','.join('?' * len(bots))
    for table in ("likes", "comments", "messages"):
        if posts or table == "messages":
            if table == "messages":
                c.execute(f"DELETE FROM {table} WHERE user_id IN ({q})", bots)
                # 机器人给真实用户发的通知（ref 指向将被删的帖子）
                c.execute(f"DELETE FROM {table} WHERE type IN ('like','comment') "
                          f"AND ref_id IN ({','.join('?'*len(posts))})" if posts else "SELECT 1",
                          posts)
            else:
                if posts:
                    c.execute(f"DELETE FROM {table} WHERE post_id IN ({','.join('?'*len(posts))})",
                              posts)
                c.execute(f"DELETE FROM {table} WHERE user_id IN ({q})", bots)
    if posts:
        c.execute(f"DELETE FROM posts WHERE id IN ({','.join('?'*len(posts))})", posts)
        c.execute(f"DELETE FROM post_search_hits WHERE post_id IN ({','.join('?'*len(posts))})", posts)
    if agents:
        c.execute(f"DELETE FROM agents WHERE id IN ({','.join('?'*len(agents))})", agents)
    if bots:
        c.execute(f"DELETE FROM sessions WHERE user_id IN ({q})", bots)
        c.execute(f"DELETE FROM events WHERE user_id IN ({q})", bots)
        c.execute(f"DELETE FROM search_logs WHERE user_id IN ({q})", bots)
        c.execute(f"DELETE FROM users WHERE id IN ({q})", bots)
    if orgs:
        c.execute(f"DELETE FROM teams WHERE id IN ({','.join('?'*len(orgs))})", orgs)
    c.commit()
    print("已清除。")


if __name__ == "__main__":
    main(dry_run="apply" not in sys.argv)
