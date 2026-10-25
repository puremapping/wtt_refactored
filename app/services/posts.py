#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内容社区服务：帖子 / 点赞 / 评论 / 搜索

设计要点：
  - **浏览开放**（匿名可看），**互动需登录**（点赞/评论/发布）
  - 「今日热榜」按**搜索命中次数**排序，不是浏览或点赞（阿哲定）
  - 图片只存相对路径，文件落在 data/uploads/（不进 git）
"""
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from app.core.db import connect

# 页签 → 排序
TAB_CONTENT = "content"
TAB_INSPIRATION = "inspiration"
TAB_HOT = "hot"


def _row_to_post(r, viewer_id: str = None) -> dict:
    """DB 行 → 对外的帖子 dict"""
    imgs = []
    if r["images"]:
        try:
            imgs = json.loads(r["images"])
        except json.JSONDecodeError:
            imgs = []

    itin = None
    if r["itinerary"]:
        try:
            itin = json.loads(r["itinerary"])
        except json.JSONDecodeError:
            itin = None

    liked = False
    if viewer_id:
        with connect() as conn:
            liked = conn.execute(
                "SELECT 1 FROM likes WHERE post_id=? AND user_id=?",
                (r["id"], viewer_id)).fetchone() is not None

    return {
        "id": r["id"],
        "type": r["type"],
        "title": r["title"],
        "body": r["body"],
        "cover_url": r["cover_url"],
        "images": imgs,
        "motivation": r["motivation"],
        "stops_count": r["stops_count"],
        "hours": r["hours"],
        "likes": r["likes"],
        "views": r["views"],
        "created_at": r["created_at"],
        "author": {
            "id": r["user_id"],
            "name": r["author_name"] or "旅行者",
            "avatar": r["author_avatar"],
        },
        "liked": liked,
        "itinerary": itin,
    }


def list_posts(tab: str = TAB_CONTENT, page: int = 1, size: int = 20,
               keyword: str = None, viewer_id: str = None) -> dict:
    """帖子列表

    tab:
      content     → 按时间倒序（全部）
      inspiration → 只看 type='inspiration'，按时间倒序
      hot         → 近 24 小时**被搜索命中最多**的帖子

    ⚠️ 匿名也能看（viewer_id 为空时 liked 一律 false）
    """
    offset = max(0, (page - 1) * size)

    with connect() as conn:
        if tab == TAB_HOT:
            # 热榜：近 24h 搜索命中次数排序
            since = (datetime.now() - timedelta(hours=24)).isoformat()
            sql = """
                SELECT p.*, u.nickname AS author_name, u.avatar_url AS author_avatar,
                       COUNT(h.id) AS hit_count
                FROM posts p
                LEFT JOIN users u ON u.id = p.user_id
                LEFT JOIN post_search_hits h
                       ON h.post_id = p.id AND h.created_at >= ?
                WHERE p.deleted_at IS NULL AND p.is_public = 1
                GROUP BY p.id
                HAVING hit_count > 0
                ORDER BY hit_count DESC, p.created_at DESC
                LIMIT ? OFFSET ?
            """
            rows = conn.execute(sql, (since, size, offset)).fetchall()
            total = conn.execute("""
                SELECT COUNT(DISTINCT p.id) FROM posts p
                JOIN post_search_hits h ON h.post_id = p.id AND h.created_at >= ?
                WHERE p.deleted_at IS NULL AND p.is_public = 1
            """, (since,)).fetchone()[0]
        else:
            sql = """
                SELECT p.*, u.nickname AS author_name, u.avatar_url AS author_avatar
                FROM posts p
                LEFT JOIN users u ON u.id = p.user_id
                WHERE p.deleted_at IS NULL AND p.is_public = 1
            """
            args = []
            if tab == TAB_INSPIRATION:
                sql += " AND p.type = 'inspiration'"
            if keyword:
                sql += " AND (p.title LIKE ? OR p.body LIKE ? OR p.motivation LIKE ?)"
                kw = f"%{keyword}%"
                args += [kw, kw, kw]
            sql += " ORDER BY p.created_at DESC LIMIT ? OFFSET ?"
            rows = conn.execute(sql, (*args, size, offset)).fetchall()

            count_sql = sql.split("ORDER BY")[0].replace(
                "SELECT p.*, u.nickname AS author_name, u.avatar_url AS author_avatar",
                "SELECT COUNT(*)")
            total = conn.execute(count_sql, args).fetchone()[0]

    items = [_row_to_post(r, viewer_id) for r in rows]
    return {"items": items, "page": page, "size": size, "total": total,
            "has_more": offset + len(items) < total}


def get_post(post_id: int, viewer_id: str = None) -> Optional[dict]:
    with connect() as conn:
        r = conn.execute("""
            SELECT p.*, u.nickname AS author_name, u.avatar_url AS author_avatar
            FROM posts p LEFT JOIN users u ON u.id = p.user_id
            WHERE p.id = ? AND p.deleted_at IS NULL
        """, (post_id,)).fetchone()
        if not r:
            return None
        conn.execute("UPDATE posts SET views = views + 1 WHERE id = ?", (post_id,))
    return _row_to_post(r, viewer_id)


def create_post(user_id: str, title: str, body: str = "", ptype: str = "content",
                cover_url: str = None, images: list = None,
                itinerary: dict = None, motivation: str = None) -> int:
    """发帖

    ⚠️ type='inspiration' 时必须带 itinerary（来自对话页的行程）
    """
    itin_json = json.dumps(itinerary, ensure_ascii=False) if itinerary else None
    stops = len(itinerary.get("stops", [])) if itinerary else 0
    hours = itinerary.get("hours") if itinerary else 0

    with connect() as conn:
        cur = conn.execute("""
            INSERT INTO posts
              (user_id, type, title, body, cover_url, images,
               itinerary, motivation, stops_count, hours, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (user_id, ptype, title, body, cover_url,
              json.dumps(images, ensure_ascii=False) if images else None,
              itin_json, motivation, stops, hours or 0,
              datetime.now().isoformat()))
        return cur.lastrowid


def delete_post(post_id: int, user_id: str) -> bool:
    """删帖 —— ⚠️ 必须校验归属，不能靠前端"""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE posts SET deleted_at=? WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (datetime.now().isoformat(), post_id, user_id))
        return cur.rowcount > 0


def toggle_like(post_id: int, user_id: str) -> dict:
    """点赞 / 取消。返回 {liked, likes}"""
    with connect() as conn:
        exist = conn.execute(
            "SELECT id FROM likes WHERE post_id=? AND user_id=?",
            (post_id, user_id)).fetchone()

        if exist:
            conn.execute("DELETE FROM likes WHERE post_id=? AND user_id=?",
                         (post_id, user_id))
            conn.execute("UPDATE posts SET likes = MAX(0, likes - 1) WHERE id=?",
                         (post_id,))
            liked = False
        else:
            conn.execute(
                "INSERT INTO likes (post_id, user_id, created_at) VALUES (?,?,?)",
                (post_id, user_id, datetime.now().isoformat()))
            conn.execute("UPDATE posts SET likes = likes + 1 WHERE id=?", (post_id,))
            liked = True

            # 给作者发通知（不给自己发）
            owner = conn.execute("SELECT user_id FROM posts WHERE id=?",
                                 (post_id,)).fetchone()
            if owner and owner["user_id"] != user_id:
                _notify(conn, owner["user_id"], "like", post_id, "有人赞了你的帖子")

        likes = conn.execute("SELECT likes FROM posts WHERE id=?",
                             (post_id,)).fetchone()
    return {"liked": liked, "likes": likes["likes"] if likes else 0}


def add_comment(post_id: int, user_id: str, content: str) -> dict:
    now = datetime.now().isoformat()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO comments (post_id, user_id, content, created_at) VALUES (?,?,?,?)",
            (post_id, user_id, content, now))
        owner = conn.execute("SELECT user_id FROM posts WHERE id=?",
                             (post_id,)).fetchone()
        if owner and owner["user_id"] != user_id:
            _notify(conn, owner["user_id"], "comment", post_id, f"评论：{content[:30]}")
    return {"id": cur.lastrowid, "content": content, "created_at": now}


def list_comments(post_id: int) -> list:
    with connect() as conn:
        rows = conn.execute("""
            SELECT c.*, u.nickname AS author_name, u.avatar_url AS author_avatar
            FROM comments c LEFT JOIN users u ON u.id = c.user_id
            WHERE c.post_id=? AND c.deleted_at IS NULL
            ORDER BY c.created_at ASC
        """, (post_id,)).fetchall()
    return [{
        "id": r["id"], "content": r["content"], "created_at": r["created_at"],
        "author": {"id": r["user_id"], "name": r["author_name"] or "旅行者",
                   "avatar": r["author_avatar"]},
    } for r in rows]


# ── 搜索（热榜的数据来源）──

def log_search(keyword: str, user_id: str = None, matched_posts: list = None):
    """记录一次搜索，并给命中的帖子打点（供热榜统计）

    ⚠️ 未登录也能搜，所以 user_id 可空
    """
    if not keyword or not keyword.strip():
        return
    kw = keyword.strip()
    now = datetime.now().isoformat()
    with connect() as conn:
        conn.execute(
            "INSERT INTO search_logs (user_id, keyword, created_at) VALUES (?,?,?)",
            (user_id, kw, now))
        for pid in (matched_posts or []):
            conn.execute(
                "INSERT INTO post_search_hits (post_id, keyword, created_at) VALUES (?,?,?)",
                (pid, kw, now))


def hot_keywords(limit: int = 10, hours: int = 24) -> list:
    """热门搜索词（可作为搜索框下方推荐）"""
    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    with connect() as conn:
        rows = conn.execute("""
            SELECT keyword, COUNT(*) AS n FROM search_logs
            WHERE created_at >= ? GROUP BY keyword
            ORDER BY n DESC LIMIT ?
        """, (since, limit)).fetchall()
    return [{"keyword": r["keyword"], "count": r["n"]} for r in rows]


# ── 消息 ──

def _notify(conn, user_id: str, mtype: str, ref_id: int, content: str):
    conn.execute(
        "INSERT INTO messages (user_id, type, ref_id, content, created_at) VALUES (?,?,?,?,?)",
        (user_id, mtype, ref_id, content, datetime.now().isoformat()))


def list_messages(user_id: str, limit: int = 50) -> dict:
    with connect() as conn:
        rows = conn.execute("""
            SELECT * FROM messages WHERE user_id=?
            ORDER BY created_at DESC LIMIT ?
        """, (user_id, limit)).fetchall()
        unread = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id=? AND is_read=0",
            (user_id,)).fetchone()[0]
    return {"items": [dict(r) for r in rows], "unread": unread}


def mark_read(user_id: str, message_id: int = None) -> int:
    with connect() as conn:
        if message_id:
            cur = conn.execute(
                "UPDATE messages SET is_read=1 WHERE id=? AND user_id=?",
                (message_id, user_id))
        else:
            cur = conn.execute(
                "UPDATE messages SET is_read=1 WHERE user_id=? AND is_read=0",
                (user_id,))
        return cur.rowcount
