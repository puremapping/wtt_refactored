"""pytest 全局夹具

要点：
  - SECRET_KEY 必须在 app.core.config 被 import 前注入（config 在 import 时读取）
  - 数据库重定向：patch app.core.db.DB_PATH（connect/init_db 都查该模块全局）
  - cities._cache 是进程级缓存，每次换库必须清，否则上一块测试库的城市列表串场
  - conversation 的匿名会话是进程内存，测试间要清
"""
import os
import sys
from pathlib import Path

# 必须最先做：config 在 import 时读 SECRET_KEY
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
# 测试环境不该真调 LLM；config 只在显式构造 LLM() 时才检查 key
os.environ.setdefault("GLM_API_KEY", "test-key-not-real")
os.environ.setdefault("ADMIN_TOKEN", "test-admin-token")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """临时数据库：init_db 建表，测试结束即弃。不碰 data/wtt.db。"""
    import app.core.db as db_module
    from app.services import cities as cities_svc
    from app.services import conversation as convo

    db_file = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_file)
    db_module.init_db()
    cities_svc.invalidate()

    yield db_file

    cities_svc.invalidate()
    convo._ANON_SESSIONS.clear()


@pytest.fixture()
def seed_beijing(tmp_db):
    """插入少量北京景区（带坐标），并注册交通/人流。

    编排测试需要 city_names() 非空；城市解析测试需要区名可命中。
    """
    import sqlite3

    from app.services import cities as cities_svc

    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    rows = [
        # (name, level, district, lon, lat)
        ("故宫博物院", "5A", "东城区", 116.397, 39.918),
        ("天坛公园", "5A", "东城区", 116.410, 39.882),
        ("景山公园", "4A", "西城区", 116.394, 39.925),
        ("颐和园", "5A", "海淀区", 116.275, 39.999),
        ("奥林匹克森林公园", "4A", "朝阳区", 116.393, 40.012),
    ]
    for i, (name, level, district, lon, lat) in enumerate(rows, start=1):
        conn.execute(
            "INSERT INTO attractions (id,name,city,level,district,lon,lat,ticket_free) "
            "VALUES (?,?,?,?,?,?,?,1)",
            (i, name, "北京", level, district, lon, lat))
        conn.execute(
            "INSERT INTO transport (attraction_name,district,metro) VALUES (?,?,?)",
            (name, district, "地铁4号线" if i % 2 else ""))
        conn.execute(
            "INSERT INTO crowd_index (name,saturation,ts) VALUES (?,?,?)",
            (name, 30.0 + i * 5, "2026-10-25T10:00:00"))
    conn.commit()
    conn.close()
    cities_svc.invalidate()
    return tmp_db
