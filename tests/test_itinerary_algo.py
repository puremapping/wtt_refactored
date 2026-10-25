"""行程编排算法：聚类 / TSP / 时间预算剪枝 / 修改操作 —— 纯函数，零 DB"""
import pytest

from app.services import itinerary as itin


def cand(name, lon, lat, district="东城区", level="4A", crowd=None, metro="", reasons=None):
    return (name, level, district, "地址" + name, lon, lat, crowd, metro, reasons or [])


# 市中心一组 + 海淀一组（相距 ~15km，8h 阈值 8000m 下分属两簇）
CANDS = [
    cand("故宫博物院", 116.397, 39.918),
    cand("天坛公园", 116.410, 39.882),
    cand("景山公园", 116.394, 39.925),
    cand("颐和园", 116.275, 39.999, district="海淀区"),
    cand("奥林匹克森林公园", 116.393, 40.012, district="朝阳区"),
]


# ── 几何 ──

def test_haversine_sane():
    d = itin.haversine(116.397, 39.918, 116.397, 39.918)
    assert d == 0
    # 故宫→天坛 约 4.2km
    d = itin.haversine(116.397, 39.918, 116.410, 39.882)
    assert 3000 < d < 5500


def test_cluster_groups_nearby():
    pts = [(116.397, 39.918), (116.398, 39.919), (116.275, 39.999)]
    groups = itin.cluster(pts, 1000)
    sizes = sorted(len(g) for g in groups)
    assert sizes == [1, 2]              # 两个近的合一簇，远的单开


# ── TSP ──

def test_tsp_returns_permutation():
    pts = [(116.397, 39.918), (116.410, 39.882), (116.394, 39.925),
           (116.411, 39.883), (116.395, 39.926)]
    order = itin.tsp_order([0, 1, 2, 3, 4], pts)
    assert sorted(order) == [0, 1, 2, 3, 4]


def test_tsp_two_points_trivial():
    assert itin.tsp_order([0, 1], [(0, 0), (1, 1)]) == [0, 1]


# ── 主流程 ──

def test_build_itinerary_basic():
    it = itin.build_itinerary(CANDS, "成就/完成", hours=8)
    assert it.stops, "8 小时 5 个候选必须产出行程"
    names = [s.name for s in it.stops]
    assert len(names) == len(set(names)), "站点不得重复"
    assert [s.order for s in it.stops] == list(range(1, len(it.stops) + 1))
    # 到达时间单调不减
    arrives = [s.arrive for s in it.stops]
    assert arrives == sorted(arrives)


def test_build_itinerary_time_budget():
    hours = 4
    it = itin.build_itinerary(CANDS, "探索/新奇", hours=hours)
    # 4 小时 = 240 分钟，行程总占用（首站停留起算）不得超预算太多
    assert len(it.stops) <= 4
    last = it.stops[-1]
    hh, mm = map(int, last.arrive.split(":"))
    arrive_min = hh * 60 + mm
    # 到达 + 75 分钟停留 ≤ 出发 + 时长 + 60 分钟宽限
    assert arrive_min + itin.STAY_MINUTES <= itin.START_MINUTES + hours * 60 + 60


def test_build_itinerary_excludes():
    it = itin.build_itinerary(CANDS, "成就/完成", hours=8,
                              exclude=["故宫博物院"])
    assert "故宫博物院" not in [s.name for s in it.stops]


def test_build_itinerary_no_coords_filtered():
    bad = [cand("无坐标景点", None, None)]
    it = itin.build_itinerary(bad, "成就/完成", hours=4)
    assert not it.stops
    assert it.risks


def test_more_hours_never_fewer_stops_current_range():
    """1-8 小时档内：时长越长，站数不得减少（9-12h 的缺失档位是 BUG-1，Phase 2a 补测）"""
    counts = {}
    for h in (2, 4, 6, 8):
        it = itin.build_itinerary(CANDS, "成就/完成", hours=h)
        counts[h] = len(it.stops)
    assert counts[4] >= counts[2]
    assert counts[6] >= counts[4]
    assert counts[8] >= counts[6]


# ── 修改操作 ──

def _existing_itin():
    return itin.build_itinerary(CANDS, "成就/完成", hours=8).to_dict()


def test_apply_remove():
    cur = _existing_itin()
    target = cur["stops"][0]["name"]
    new = itin.apply_modification(cur, "remove", target=target,
                                  motivation="成就/完成", hours=8)
    assert new is not None
    assert target not in [s["name"] for s in new["stops"]]
    assert len(new["stops"]) == len(cur["stops"]) - 1


def test_apply_replace_picks_same_district_first():
    cur = _existing_itin()
    target = cur["stops"][0]["name"]
    target_district = cur["stops"][0]["district"]
    pool = CANDS + [cand("备选景点", 116.40, 39.91)]
    new = itin.apply_modification(cur, "replace", target=target,
                                  candidates=pool, motivation="成就/完成", hours=8)
    assert new is not None
    names = [s["name"] for s in new["stops"]]
    assert target not in names
    assert "备选景点" in names


@pytest.mark.xfail(reason="BUG-12: apply_modification 的 not target 检查挡在 add 分支之前，"
                          "而工具定义明说「add 时省略 target」——该操作实际不可用。Phase 2a 修复",
                   strict=True)
def test_apply_add():
    cur = _existing_itin()
    before = len(cur["stops"])
    pool = CANDS + [cand("新增景点", 116.40, 39.91)]
    new = itin.apply_modification(cur, "add", candidates=pool,
                                  motivation="成就/完成", hours=8)
    assert new is not None
    assert len(new["stops"]) == before + 1


def test_apply_reorder_keeps_stops():
    cur = _existing_itin()
    new = itin.apply_modification(cur, "reorder", motivation="成就/完成", hours=8)
    assert new is not None
    assert {s["name"] for s in new["stops"]} == {s["name"] for s in cur["stops"]}


def test_apply_invalid_actions_return_none():
    # 两个站删掉一个后只剩 1 站 → 无法成行
    two = itin.build_itinerary(CANDS[:2], "成就/完成", hours=8).to_dict()
    assert len(two["stops"]) == 2
    assert itin.apply_modification(two, "remove",
                                   target=two["stops"][0]["name"]) is None
    assert itin.apply_modification({}, "remove", target="x") is None
    assert itin.apply_modification(two, "unknown-action", target="x") is None
    # 注：remove 一个不存在的站 = 无操作重建，返回的是重建行程而非 None（现状行为）


def test_apply_regenerate_excludes_current_when_pool_sufficient():
    """池子够时 regenerate 不得把现有站点带回来（池子耗尽的回退是 BUG-2，Phase 2a 补测）"""
    cur = _existing_itin()
    pool = CANDS + [
        cand("替代景点A", 116.40, 39.91),
        cand("替代景点B", 116.41, 39.92),
        cand("替代景点C", 116.42, 39.93),
        cand("替代景点D", 116.43, 39.94),
    ]
    new = itin.apply_modification(cur, "regenerate", candidates=pool,
                                  motivation="成就/完成", hours=8)
    assert new is not None
    old_names = {s["name"] for s in cur["stops"]}
    new_names = {s["name"] for s in new["stops"]}
    assert not (old_names & new_names), "换一批不得出现旧站点"
