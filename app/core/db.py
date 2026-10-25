#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Where to Travel — 数据库层（SQLite）"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from app.core.config import DB_PATH

SCHEMA = """
-- 景点
CREATE TABLE IF NOT EXISTS attractions (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    city        TEXT NOT NULL DEFAULT '北京',   -- ★ 城市（多城时区分同名区）
    level       TEXT,              -- 5A/4A/3A...
    district    TEXT,
    address     TEXT,
    phone       TEXT,
    postcode    TEXT,
    lon         REAL,              -- GCJ-02
    lat         REAL,
    ticket_free INTEGER,           -- 是否免费
    price_high  REAL,              -- 旺季价
    price_low   REAL,              -- 淡季价
    context     TEXT,              -- 用于 embedding 的描述
    embedding   BLOB               -- 向量（可选，后补）
);

-- 交通（来自平台「等级景区交通信息」）
CREATE TABLE IF NOT EXISTS transport (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    attraction_name TEXT NOT NULL,
    district    TEXT,
    level       TEXT,
    metro       TEXT,
    bus         TEXT,
    highway     TEXT,
    branch_road TEXT,
    airport     TEXT,
    railway     TEXT,
    town        TEXT
);

-- 景区饱和指数（实时人流）
CREATE TABLE IF NOT EXISTS crowd_index (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    saturation  REAL,
    ts          TEXT
);

-- ── 用户系统（v0.4）──

-- 注册用户
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    nickname      TEXT,
    created_at    TEXT NOT NULL,
    last_login    TEXT,
    role          TEXT NOT NULL DEFAULT 'person',   -- person | agency
    org_id        TEXT                              -- 文旅局账号关联 teams.id
);

-- 文旅局（团队）：一个文旅局账号归属一个团队，团队下可有成员
CREATE TABLE IF NOT EXISTS teams (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,        -- 如「成都市文化广电旅游局」
    region      TEXT,                 -- 如「成都」
    owner_id    TEXT NOT NULL,        -- 创建者
    space_key   TEXT,                 -- 对应 Coze space（暂空）
    intro       TEXT,
    created_at  TEXT NOT NULL
);

-- 会话（只有登录用户的会落库；匿名会话在内存）
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    user_id     TEXT,              -- 历史遗留会话为 NULL
    created_at  TEXT,
    ended_at    TEXT,
    turn_count  INTEGER DEFAULT 0,
    profile     TEXT,              -- JSON：画像
    motivations TEXT,              -- JSON：动机
    itinerary   TEXT               -- JSON：行程
);

-- 行为事件（长期分析的核心）
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT,
    user_id     TEXT NOT NULL,     -- ★ 匿名事件写不进来（隐私政策的结构约束）
    event_type  TEXT NOT NULL,
    payload     TEXT,              -- JSON
    created_at  TEXT NOT NULL
);


-- 文旅局在自己团队下创建的智能体
CREATE TABLE IF NOT EXISTS agents (
    id          TEXT PRIMARY KEY,
    team_id     TEXT NOT NULL,            -- 归属的文旅局（teams.id）
    creator_id  TEXT NOT NULL,            -- 创建者（用户 id）
    name        TEXT NOT NULL,
    region      TEXT,                     -- 覆盖地区，用于主智能体路由
    description TEXT,
    prompt      TEXT,                     -- 人设 / 话术
    status      TEXT NOT NULL DEFAULT 'draft',   -- draft | published
    external_id TEXT,                     -- 对应 Coze bot_id（暂空）
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_attr_name ON attractions(name);
CREATE INDEX IF NOT EXISTS idx_crowd_name ON crowd_index(name);

-- ── 内容社区 ──────────────────────────────────────────────
-- 帖子：普通图文（content）或 AI 行程分享（inspiration）
CREATE TABLE IF NOT EXISTS posts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT 'content',   -- content | inspiration
    title       TEXT NOT NULL,
    body        TEXT,
    cover_url   TEXT,
    images      TEXT,                              -- JSON 数组
    itinerary   TEXT,                              -- JSON，灵感帖的结构化行程
    motivation  TEXT,                              -- 动机标签（如「恢复/逃离」）
    stops_count INTEGER DEFAULT 0,
    hours       INTEGER DEFAULT 0,
    likes       INTEGER DEFAULT 0,
    views       INTEGER DEFAULT 0,
    is_public   INTEGER DEFAULT 1,
    created_at  TEXT NOT NULL,
    deleted_at  TEXT
);

CREATE TABLE IF NOT EXISTS likes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id    INTEGER NOT NULL,
    user_id    TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(post_id, user_id)
);

CREATE TABLE IF NOT EXISTS comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id    INTEGER NOT NULL,
    user_id    TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL,
    deleted_at TEXT
);

-- 站内消息
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    type       TEXT NOT NULL,       -- like | comment | ai | system
    ref_id     INTEGER,
    content    TEXT NOT NULL,
    is_read    INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

-- 搜索日志与命中（热榜靠这个算）
CREATE TABLE IF NOT EXISTS search_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT,
    keyword    TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS post_search_hits (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id    INTEGER NOT NULL,
    keyword    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

# 索引依赖 sessions.user_id，必须等 _migrate 补列之后再建
INDEXES_AFTER_MIGRATE = """
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(created_at);
CREATE INDEX IF NOT EXISTS idx_posts_user ON posts(user_id);
CREATE INDEX IF NOT EXISTS idx_posts_type ON posts(type, created_at);
CREATE INDEX IF NOT EXISTS idx_likes_post ON likes(post_id);
CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_search_hits_post ON post_search_hits(post_id, created_at);
CREATE INDEX IF NOT EXISTS idx_agents_team ON agents(team_id, status);
"""


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        # 1. 建表（IF NOT EXISTS，已有的跳过）
        conn.executescript(SCHEMA)
        # 2. 补列（给老库加 user_id 等）
        _migrate(conn)
        # 3. 建依赖新列的索引
        conn.executescript(INDEXES_AFTER_MIGRATE)


def _migrate(conn):
    """给已有库补列（SQLite 的 ALTER TABLE ADD COLUMN 是安全操作）"""
    def cols(table):
        return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}

    for name, decl in (
        ("avatar_url", "TEXT"),
        ("city", "TEXT"),
        ("bio", "TEXT"),
        ("role", "TEXT DEFAULT 'person'"),
        ("org_id", "TEXT"),
    ):
        # ⚠️ 实时检查，不用快照 —— 同一批里若重复也不会炸
        if name not in cols("users"):
            conn.execute(f"ALTER TABLE users ADD COLUMN {name} {decl}")

    for name, decl in (
        ("user_id", "TEXT"),
        ("ended_at", "TEXT"),
        ("turn_count", "INTEGER DEFAULT 0"),
    ):
        if name not in cols("sessions"):
            conn.execute(f"ALTER TABLE sessions ADD COLUMN {name} {decl}")

    _migrate_events_notnull(conn)
    _migrate_attractions_city(conn)


def _migrate_attractions_city(conn):
    """给 attractions 补 city 列（多城市支持的基础）

    老库只有 district（16 个北京区），没有城市维度。
    加 city 列后，同名区（如两个城市都有「朝阳区」）才能区分。

    回填策略：
      - 已有数据一律标为 DEFAULT_CITY（当前只有北京）
      - 若 city 列已存在但不为空值，不动
    """
    from app.services.cities import DEFAULT_CITY

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(attractions)")}
    if not cols:
        return                      # 表不存在

    if "city" not in cols:
        conn.execute(
            f"ALTER TABLE attractions ADD COLUMN city TEXT NOT NULL DEFAULT '{DEFAULT_CITY}'")
        return

    # 列已存在但有空值 → 回填
    blank = conn.execute(
        "SELECT COUNT(*) FROM attractions WHERE city IS NULL OR city = ''").fetchone()[0]
    if blank:
        conn.execute(
            "UPDATE attractions SET city=? WHERE city IS NULL OR city = ''",
            (DEFAULT_CITY,))


def _migrate_events_notnull(conn):
    """把 events.user_id 改成 NOT NULL（SQLite 不支持 ALTER COLUMN，要重建表）

    动机：把「匿名不落库」这条隐私政策变成**结构约束**，而不是只靠代码判空。
    ⚠️ 若表里已有 user_id 为空的行，无法加约束 —— 此时不清数据，只跳过并留痕。
    """
    info = list(conn.execute("PRAGMA table_info(events)"))
    if not info:
        return                      # 表不存在，init_db 的建表语句已带 NOT NULL
    ucol = next((r for r in info if r["name"] == "user_id"), None)
    if ucol is None or ucol["notnull"] == 1:
        return                      # 已是 NOT NULL（或列不存在），无需迁移

    bad = conn.execute(
        "SELECT COUNT(*) FROM events WHERE user_id IS NULL OR user_id = ''"
    ).fetchone()[0]
    if bad:
        # 不擅自删数据（数据诚实高于好看）—— 记录问题，跳过迁移
        conn.execute(
            "INSERT INTO events (session_id,user_id,event_type,payload,created_at) "
            "VALUES (NULL, '__migration__', 'migration_skipped', ?, ?)",
            (json.dumps({"reason": "events.user_id 有 %d 行空值" % bad}),
             datetime.now().isoformat()))
        return

    conn.executescript("""
        CREATE TABLE events_new (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT,
            user_id     TEXT NOT NULL,
            event_type  TEXT NOT NULL,
            payload     TEXT,
            created_at  TEXT NOT NULL
        );
        INSERT INTO events_new (id,session_id,user_id,event_type,payload,created_at)
            SELECT id,session_id,user_id,event_type,payload,created_at FROM events;
        DROP TABLE events;
        ALTER TABLE events_new RENAME TO events;
    """)


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"数据库已初始化: {DB_PATH}")
