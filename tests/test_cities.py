"""城市解析 —— 城市列表必须从库里算，不写死"""
from app.services import cities


def test_supported_from_db(seed_beijing):
    assert cities.city_names() == ["北京"]
    desc = cities.supported_description()
    assert "北京" in desc and "5" in desc  # 5 个景区


def test_resolve_exact(seed_beijing):
    assert cities.resolve_city("北京") == "北京"


def test_resolve_in_text(seed_beijing):
    assert cities.resolve_city("去北京玩") == "北京"
    assert cities.resolve_city("我想看看北京的现代建筑") == "北京"


def test_resolve_by_district(seed_beijing):
    assert cities.resolve_city("东城区") == "北京"
    # 简称（去「区」后缀）
    assert cities.resolve_city("在海淀那边") == "北京"


def test_resolve_by_alias(seed_beijing):
    assert cities.resolve_city("首都") == "北京"
    assert cities.resolve_city("帝都") == "北京"


def test_resolve_unsupported(seed_beijing):
    assert cities.resolve_city("上海") is None
    assert cities.resolve_city("南京") is None


def test_resolve_empty(seed_beijing):
    assert cities.resolve_city("") is None
    assert cities.resolve_city(None) is None


def test_is_supported_empty_means_unspecified(seed_beijing):
    # 空 = 未指定 = 视为支持（不是「不支持」）
    assert cities.is_supported("") is True
    assert cities.is_supported("北京") is True
    assert cities.is_supported("上海") is False


def test_no_city_column_falls_back_to_default(tmp_db):
    # 老库没有 city 列时按单城市模式（DEFAULT_CITY）——向后兼容
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    conn.execute("DROP TABLE attractions")
    conn.execute("""CREATE TABLE attractions (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, level TEXT, district TEXT,
        address TEXT, phone TEXT, postcode TEXT, lon REAL, lat REAL,
        ticket_free INTEGER, price_high REAL, price_low REAL,
        context TEXT, embedding BLOB)""")
    conn.execute("INSERT INTO attractions (id,name) VALUES (1,'测试景区')")
    conn.commit()
    conn.close()

    from app.services import cities as c
    c.invalidate()
    assert c.city_names() == [c.DEFAULT_CITY]
    c.invalidate()
