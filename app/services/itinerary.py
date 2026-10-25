#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行程生成：把推荐结果排成一日路线

复用 ITINERA 的思路（EMNLP 2024，见 docs/research/itinera-verification.md）：
  1. 按距离阈值聚类（同簇 = 地理相近）
  2. 簇内 TSP 排序（最近邻 + 2-opt 改良）
  3. 簇间按空间连续性串联

与 ITINERA 的差异：
  - 不依赖外部 LLM 做排序（LLM 交给"行程叙述"环节）
  - 用纯 numpy 实现 TSP，不引 pulp/python_tsp
  - 时长 → 景点数量映射沿用其经验表
"""
import math
from dataclasses import dataclass, field

# 时长(小时) → (景点数, 聚类阈值米)   —— 参考 ITINERA 的 TIME2NUM，按北京尺度调整
TIME2PLAN = {
    1: (3, 3000),
    2: (4, 4000),
    3: (5, 5000),
    4: (6, 6000),
    5: (7, 6000),
    6: (8, 7000),
    7: (9, 8000),
    8: (10, 8000),
}
DEFAULT_HOURS = 6

# 平均每站停留时间（分钟），用于估算行程
STAY_MINUTES = 75
TRAVEL_MINUTES_PER_KM = 3.0
START_MINUTES = 9 * 60      # 默认 9:00 出发


@dataclass
class Stop:
    name: str
    level: str
    district: str
    address: str
    lon: float
    lat: float
    crowd: float | None
    metro: str
    reasons: list = field(default_factory=list)
    order: int = 0
    arrive: str = ""
    duration_min: int = STAY_MINUTES


@dataclass
class Itinerary:
    motivation: str
    hours: int
    stops: list = field(default_factory=list)
    total_distance_km: float = 0.0
    risks: list = field(default_factory=list)
    alternatives: list = field(default_factory=list)

    def to_dict(self):
        return {
            "motivation": self.motivation,
            "hours": self.hours,
            "stops": [{
                "order": s.order, "name": s.name, "level": s.level,
                "district": s.district, "address": s.address,
                "lon": s.lon, "lat": s.lat, "crowd": s.crowd,
                "metro": s.metro, "arrive": s.arrive,
                "duration_min": s.duration_min, "reasons": s.reasons,
            } for s in self.stops],
            "total_distance_km": round(self.total_distance_km, 2),
            "risks": self.risks,
            "alternatives": self.alternatives,
        }


# ---------- 几何 ----------

def haversine(lon1, lat1, lon2, lat2):
    """两点球面距离（米）"""
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def dist_matrix(pts):
    n = len(pts)
    d = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            v = haversine(pts[i][0], pts[i][1], pts[j][0], pts[j][1])
            d[i][j] = d[j][i] = v
    return d


# ---------- 聚类（并查集，按距离阈值） ----------

def cluster(pts, thresh):
    n = len(pts)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            if haversine(pts[i][0], pts[i][1], pts[j][0], pts[j][1]) < thresh:
                union(i, j)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


# ---------- TSP：最近邻 + 2-opt ----------

def tsp_order(idx, pts):
    """给定索引列表，返回访问顺序（局部索引）"""
    if len(idx) <= 2:
        return list(range(len(idx)))

    sub = [pts[i] for i in idx]
    n = len(sub)
    # 最近邻
    unvisited = set(range(n))
    cur = 0
    order = [cur]
    unvisited.discard(cur)
    while unvisited:
        nxt = min(unvisited, key=lambda j: haversine(
            sub[cur][0], sub[cur][1], sub[j][0], sub[j][1]))
        order.append(nxt)
        unvisited.discard(nxt)
        cur = nxt

    # 2-opt 改良
    improved = True
    while improved:
        improved = False
        for i in range(1, n - 1):
            for k in range(i + 1, n):
                a, b = order[i - 1], order[i]
                c = order[k]
                d = order[(k + 1) % n]
                if a == c or b == d:
                    continue
                cur_d = (haversine(sub[a][0], sub[a][1], sub[b][0], sub[b][1])
                         + haversine(sub[c][0], sub[c][1], sub[d][0], sub[d][1]))
                new_d = (haversine(sub[a][0], sub[a][1], sub[c][0], sub[c][1])
                         + haversine(sub[b][0], sub[b][1], sub[d][0], sub[d][1]))
                if new_d < cur_d - 1e-6:
                    order[i:k + 1] = reversed(order[i:k + 1])
                    improved = True
    return order


# ---------- 主流程 ----------

def build_itinerary(candidates, motivation, hours=None, exclude=None):
    """candidates: [(name, level, district, address, lon, lat, crowd, metro, reasons), ...]

    exclude: 要排除的景点名列表（用于「换一批」）
    返回 Itinerary
    """
    hours = hours or DEFAULT_HOURS
    n_poi, thresh = TIME2PLAN.get(hours, TIME2PLAN[DEFAULT_HOURS])

    # 过滤：无坐标 / 被排除
    excl = set(exclude or [])
    cand = [c for c in candidates
            if c[4] is not None and c[5] is not None and c[0] not in excl]
    cand = cand[:max(n_poi * 2, n_poi)]     # 多取一些做聚类

    it = Itinerary(motivation=motivation, hours=hours)
    if not cand:
        it.risks.append("没有可用坐标的候选景区")
        return it

    pts = [(c[4], c[5]) for c in cand]
    groups = cluster(pts, thresh)

    # 簇按大小降序，大的优先（内容更丰富）
    groups.sort(key=len, reverse=True)

    # 簇间衔接：按簇心的距离贪心串联
    centroids = []
    for g in groups:
        lon = sum(pts[i][0] for i in g) / len(g)
        lat = sum(pts[i][1] for i in g) / len(g)
        centroids.append((lon, lat))

    used = set()
    chain = []
    cur = 0
    while len(used) < len(groups):
        used.add(cur)
        chain.append(cur)
        nxt, best = None, None
        for gi in range(len(groups)):
            if gi in used:
                continue
            d = haversine(centroids[cur][0], centroids[cur][1],
                          centroids[gi][0], centroids[gi][1])
            if best is None or d < best:
                best, nxt = d, gi
        if nxt is None:
            break
        cur = nxt

    # 逐簇取点，直到凑够 n_poi
    # 改进：不再"每簇都取"，而是按"从起点向外扩散"的顺序，
    # 优先取与已选点同区/邻近的点，避免全城折返。
    picked = []
    for gi in chain:
        g = groups[gi]
        order = tsp_order(g, pts)
        for k in order:
            picked.append(g[k])
            if len(picked) >= n_poi:
                break
        if len(picked) >= n_poi:
            break

    # 追加优化：若选出的点跨区过多，按区做二次收敛
    picked = _tighten_by_district(picked, cand, n_poi)

    # 组装 Stop（带时间预算剪枝：超时就停止加点）
    total_km = 0.0
    prev = None
    clock = START_MINUTES          # 出发时间
    deadline = START_MINUTES + hours * 60
    for i, ci in enumerate(picked):
        c = cand[ci]
        travel_min = 0
        add_km = 0.0
        if prev is not None:
            d = haversine(prev[4], prev[5], c[4], c[5])
            add_km = d / 1000
            travel_min = int(add_km * TRAVEL_MINUTES_PER_KM)

        # 预算检查：到达 + 停留 是否还来得及
        if prev is not None and (clock + travel_min + STAY_MINUTES) > deadline:
            break

        total_km += add_km
        clock += travel_min
        hh, mm = divmod(clock, 60)
        it.stops.append(Stop(
            name=c[0], level=c[1], district=c[2], address=c[3],
            lon=c[4], lat=c[5], crowd=c[6], metro=c[7] or "",
            reasons=c[8] or [], order=len(it.stops) + 1,
            arrive=f"{hh:02d}:{mm:02d}",
        ))
        clock += STAY_MINUTES
        prev = c

    it.total_distance_km = total_km
    it = _assess_risks(it)
    it.alternatives = _suggest_alternatives(cand, picked)
    return it


def apply_modification(itinerary_dict, action, target=None, candidates=None,
                       motivation=None, hours=None):
    """对已有行程执行修改，返回新行程 dict

    action:
      replace    —— 换掉 target 那一站
      remove     —— 删掉 target
      add        —— 加一站（从未入选的候选里挑）
      reorder    —— 重跑 TSP 排序
      regenerate —— 整条重新生成（排除现有站点）

    实现思路：**统一走「重算」** —— 修改站点集合后重新编排时间线，
    避免手工调整导致时间错乱。
    """
    cur = itinerary_dict or {}
    stops = list(cur.get("stops") or [])
    hours = hours or cur.get("hours") or DEFAULT_HOURS
    motivation = motivation or cur.get("motivation") or "探索/新奇"

    if not stops:
        return None

    # 把当前站点转成 cand 元组形式，便于复用构建逻辑
    def to_tuple(s):
        return (s["name"], s.get("level", ""), s.get("district", ""),
                s.get("address", ""), s.get("lon"), s.get("lat"),
                s.get("crowd"), s.get("metro", ""), s.get("reasons") or [])

    base = [to_tuple(s) for s in stops]

    if action == "regenerate":
        # 换一批：排除现有全部站点
        excl = [s["name"] for s in stops]
        pool = [c for c in (candidates or []) if c[0] not in excl]
        return build_itinerary(pool or candidates, motivation, hours).to_dict()

    if action == "reorder":
        return build_itinerary(base, motivation, hours).to_dict()

    if not target:
        return None

    if action == "remove":
        pool = [c for c in base if c[0] != target]
        if len(pool) < 2:
            return None
        return build_itinerary(pool, motivation, hours).to_dict()

    if action == "replace":
        # 从候选里找一个「同区优先、未在行程中」的替换
        used = {s["name"] for s in stops}
        cur_stop = next((s for s in stops if s["name"] == target), None)
        cand_pool = [c for c in (candidates or [])
                     if c[0] not in used and c[4] is not None]
        if not cand_pool:
            return None
        if cur_stop:
            # 同区域的优先
            same = [c for c in cand_pool if c[2] == cur_stop.get("district")]
            pick = (same or cand_pool)[0]
        else:
            pick = cand_pool[0]
        pool = [c if c[0] != target else pick for c in base]
        return build_itinerary(pool, motivation, hours).to_dict()

    if action == "add":
        used = {s["name"] for s in stops}
        cand_pool = [c for c in (candidates or [])
                     if c[0] not in used and c[4] is not None]
        if not cand_pool:
            return None
        pool = base + [cand_pool[0]]
        return build_itinerary(pool, motivation, hours).to_dict()

    return None


def _tighten_by_district(picked, cand, n_poi):
    """按区收敛：优先保留同一片区域的点。

    背景：北京的区很大，跨区往往就是 20+ 公里。
    贪心串联只看了簇心距离，容易选出"东城→朝阳→西城→海淀"这种折返路线。

    做法：
      1. 统计 picked 里的区分布
      2. 保留占比最高的 2 个区
      3. 从其余点里，按与保留点最近的原则补足 n_poi
    """
    if len(picked) <= 3:
        return picked

    from collections import Counter
    districts = Counter(cand[i][2] for i in picked)
    keep = {d for d, _ in districts.most_common(2)}

    kept = [i for i in picked if cand[i][2] in keep]
    dropped = [i for i in picked if cand[i][2] not in keep]

    if len(kept) >= n_poi:
        return kept[:n_poi]

    # 用 dropped 补足（按与 kept 的最小距离排序）
    def min_dist_to_kept(j):
        if not kept:
            return 0
        return min(haversine(cand[j][4], cand[j][5], cand[k][4], cand[k][5])
                   for k in kept)

    dropped.sort(key=min_dist_to_kept)
    kept.extend(dropped[:n_poi - len(kept)])
    return kept


def _assess_risks(it):
    """简单风险评估"""
    for s in it.stops:
        if s.crowd is not None and s.crowd >= 60:
            it.risks.append(f"{s.name} 当前人流较满（饱和指数 {s.crowd:.0f}），建议早到")
    if it.total_distance_km > 60:
        it.risks.append(f"全程约 {it.total_distance_km:.0f} 公里，跨区较多，交通耗时占比高")
    if not any(s.metro for s in it.stops):
        it.risks.append("各站点均无地铁直达，建议自驾或打车")
    if not it.risks:
        it.risks.append("整体强度适中，未发现明显风险")
    return it


def _suggest_alternatives(cand, picked):
    """从候选里挑没被选中的作为备选"""
    out = []
    for i, c in enumerate(cand):
        if i in picked:
            continue
        out.append({"name": c[0], "level": c[1], "district": c[2],
                    "lon": c[4], "lat": c[5]})
        if len(out) >= 3:
            break
    return out
