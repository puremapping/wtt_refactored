"""多城市数据隔离（Phase 2c）

核心保证：接入第二座城市时 ——
  1. 推荐与行程管线按城市过滤，行程绝不混城市
  2. transport / crowd_index 按 (名称, 城市) join，同名景点数据绝不互串
"""
import sqlite3

from app.services import cities as cities_svc
from app.services import itinerary_flow as flow
from app.services import recommend as rec_svc
from app.services.itinerary import build_itinerary


def _add_chengdu(db_file):
    """插入成都测试数据：含一个与北京同名的景点「人民公园」（人流不同）"""
    conn = sqlite3.connect(db_file)
    rows = [
        # (name, district, lon, lat, crowd, metro)
        ("宽窄巷子", "青羊区", 104.053, 30.665, 88.0, "地铁4号线"),
        ("武侯祠", "武侯区", 104.048, 30.644, 65.0, ""),
        ("人民公园", "青羊区", 104.055, 30.662, 12.0, "地铁2号线"),
    ]
    for i, (name, district, lon, lat, crowd, metro) in enumerate(rows, start=100):
        conn.execute(
            "INSERT INTO attractions (id,name,city,level,district,lon,lat,ticket_free) "
            "VALUES (?,?,?,?,?,?,?,1)",
            (i, name, "成都", "4A", district, lon, lat))
        conn.execute(
            "INSERT INTO transport (attraction_name,city,district,metro) VALUES (?,?,?,?)",
            (name, "成都", district, metro))
        conn.execute(
            "INSERT INTO crowd_index (name,city,saturation,ts) VALUES (?,?,?,?)",
            (name, "成都", crowd, "2026-10-25T10:00:00"))
    # 同名景点：北京也有「人民公园」，人流 95（与成都 12 明显不同）
    conn.execute(
        "INSERT INTO attractions (id,name,city,level,district,lon,lat,ticket_free) "
        "VALUES (99,'人民公园','北京','3A','西城区',116.35,39.90,1)")
    conn.execute(
        "INSERT INTO transport (attraction_name,city,district,metro) VALUES "
        "('人民公园','北京','西城区','地铁1号线')")
    conn.execute(
        "INSERT INTO crowd_index (name,city,saturation,ts) VALUES "
        "('人民公园','北京',95.0,'2026-10-25T10:00:00')")
    conn.commit()
    conn.close()
    cities_svc.invalidate()


def test_city_registry_sees_both(seed_beijing, tmp_db):
    _add_chengdu(tmp_db)
    names = cities_svc.city_names()
    assert names == ["北京", "成都"]          # 按景区数排序
    assert "成都（3 个景区）" in cities_svc.supported_description()


def test_recommend_city_filter(seed_beijing, tmp_db):
    _add_chengdu(tmp_db)
    all_items = rec_svc.recommend("成就/完成", 3, 50)
    assert {i.city for i in all_items} == {"北京", "成都"}

    bj = rec_svc.recommend("成就/完成", 3, 50, city="北京")
    assert all(i.city == "北京" for i in bj)
    assert not any("宽窄巷子" in i.name or i.name == "武侯祠" for i in bj)

    cd = rec_svc.recommend("成就/完成", 3, 50, city="成都")
    assert all(i.city == "成都" for i in cd)
    assert {"宽窄巷子", "武侯祠", "人民公园"} <= {i.name for i in cd}


def test_same_name_spot_crowd_not_mixed(seed_beijing, tmp_db):
    """同名景点「人民公园」：北京 95 vs 成都 12，join 必须按城市区分"""
    _add_chengdu(tmp_db)
    bj = {i.name: i for i in rec_svc.load_candidates(city="北京")}
    cd = {i.name: i for i in rec_svc.load_candidates(city="成都")}
    assert bj["人民公园"].crowd == 95.0
    assert cd["人民公园"].crowd == 12.0


def test_same_name_spot_metro_not_mixed(seed_beijing, tmp_db):
    _add_chengdu(tmp_db)
    bj = {i.name: i for i in rec_svc.load_candidates(city="北京")}
    cd = {i.name: i for i in rec_svc.load_candidates(city="成都")}
    assert bj["人民公园"].has_metro           # 地铁1号线
    assert cd["人民公园"].has_metro           # 地铁2号线 —— 各自的数据


def test_build_candidates_resolves_city_from_profile(seed_beijing, tmp_db):
    _add_chengdu(tmp_db)
    # 目的地成都 → 候选全是成都
    cand = flow.build_candidates({"primary": "成就/完成", "destination": "成都"})
    names = [c[0] for c in cand]
    assert names and all(n in ("宽窄巷子", "武侯祠", "人民公园") for n in names)

    # 目的地北京 → 不混入成都
    cand_bj = flow.build_candidates({"primary": "成就/完成", "destination": "北京"})
    bj_names = [c[0] for c in cand_bj]
    assert "宽窄巷子" not in bj_names and "武侯祠" not in bj_names


def test_plan_city_defaults_to_largest_when_unspecified(seed_beijing, tmp_db):
    _add_chengdu(tmp_db)
    # 未指定目的地 → 默认景区最多的城市（北京 6 > 成都 3），防止行程混城市
    assert flow._resolve_plan_city({}) == "北京"
    assert flow._resolve_plan_city({"destination": "成都"}) == "成都"


def test_itinerary_never_mixes_cities(seed_beijing, tmp_db):
    """端到端：双城数据下，成都目的地行程零北京景点，反之亦然"""
    _add_chengdu(tmp_db)

    cd_cand = flow.build_candidates({"primary": "探索/新奇", "destination": "成都"})
    cd_it = build_itinerary(cd_cand, "探索/新奇", hours=4)
    assert cd_it.stops
    assert all(s.name in ("宽窄巷子", "武侯祠", "人民公园") for s in cd_it.stops)

    bj_cand = flow.build_candidates({"primary": "探索/新奇", "destination": "北京"})
    bj_it = build_itinerary(bj_cand, "探索/新奇", hours=4)
    assert bj_it.stops
    assert all(s.name not in ("宽窄巷子", "武侯祠") for s in bj_it.stops)


def test_migration_backfills_city_on_legacy_db(tmp_db):
    """老库补列迁移：city 列存在但有空值 → 回填默认城市，幂等"""
    import sqlite3

    from app.core import db as db_mod

    conn = sqlite3.connect(tmp_db)
    # 模拟迁移前的老数据：去掉 city 值
    conn.execute("UPDATE transport SET city=''")
    conn.execute("UPDATE crowd_index SET city=NULL")
    conn.commit()

    db_mod._migrate_city_columns(conn)
    conn.commit()

    blank_t = conn.execute(
        "SELECT COUNT(*) FROM transport WHERE city IS NULL OR city=''").fetchone()[0]
    blank_c = conn.execute(
        "SELECT COUNT(*) FROM crowd_index WHERE city IS NULL OR city=''").fetchone()[0]
    assert blank_t == 0 and blank_c == 0

    # 幂等：再跑一次不炸
    db_mod._migrate_city_columns(conn)
    conn.commit()
    conn.close()
