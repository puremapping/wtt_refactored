#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导入成都景区数据（官方名录 + 高德补坐标）

## 前置

  python -m app.scripts.fetch_chengdu     # 先有 data/raw/chengdu_attractions.csv

## 数据构成

  attractions  ← 四川省文旅厅 A 级景区名录（名称/等级/区县/地址）
                 + 高德地理编码补 lon/lat（名录本身没有坐标）

  ⚠️ 成都**没有** transport / crowd_index 数据：
     市级开放平台未开放景区交通与人流数据集，第三方转载源不合规。
     这两张表在成都是空的 —— 行程生成会退化为「只按距离和等级排」。
     这是已知缺口，不是 bug。见 .pms.yml 的数据缺口条目。

## 幂等

  按 (name, city) 判重，重复跑不会产生重复行。坐标已存在就跳过，不浪费高德配额。

## 用法

  python -m app.scripts.import_chengdu            # 全量导入
  python -m app.scripts.import_chengdu --geocode  # 只补缺失坐标
"""
import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.db import connect, init_db

CITY = "成都"
CSV_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "raw" / "chengdu_attractions.csv"


def read_csv(path: Path) -> list:
    for enc in ("utf-8-sig", "gbk"):
        try:
            with open(path, encoding=enc, newline="") as f:
                return [r for r in csv.DictReader(f) if r.get("name")]
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"无法解码: {path}")


def import_attractions(conn, rows: list) -> int:
    """写 attractions。按 (name, city) 判重，不覆盖已存在的坐标。"""
    n = 0
    for r in rows:
        name = r["name"].strip()
        district = (r.get("district") or "").strip()
        level = (r.get("level") or "").strip()
        address = (r.get("address") or "").strip()

        ctx = f"{name}，位于{CITY}市{district}，等级{level}，地址{address}"

        exists = conn.execute(
            "SELECT id FROM attractions WHERE name=? AND city=?",
            (name, CITY)).fetchone()

        if exists:
            # 只更新文本字段，不动 lon/lat（避免把已补的坐标冲掉）
            conn.execute(
                "UPDATE attractions SET level=?, district=?, address=?, context=? "
                "WHERE id=?",
                (level, district, address, ctx, exists["id"]))
        else:
            conn.execute(
                "INSERT INTO attractions "
                "(name,level,district,address,context,city,ticket_free) "
                "VALUES (?,?,?,?,?,?,NULL)",
                (name, level, district, address, ctx, CITY))
        n += 1
    return n


def geocode(address: str, city: str = CITY, retries: int = 2):
    """高德地理编码。遇到 QPS 超限自动重试 —— 那是限流不是「地址不存在」，
    混为一谈会让数据永久缺一条。"""
    import httpx

    from app.core.config import AMAP_KEY

    last_info = "?"
    for attempt in range(retries + 1):
        r = httpx.get("https://restapi.amap.com/v3/geocode/geo", params={
            "address": address, "city": city, "key": AMAP_KEY,
        }, timeout=15)
        d = r.json()
        if d.get("status") == "1" and d.get("geocodes"):
            loc = d["geocodes"][0].get("location", "")
            if "," in loc:
                lon, lat = loc.split(",")
                return float(lon), float(lat), d["geocodes"][0].get("level", "")
            return None, None, "location 字段格式异常"

        last_info = d.get("info", "?")
        if "QPS" in last_info or "EXCEEDED" in last_info.upper():
            time.sleep(1.0 * (attempt + 1))      # 退避后重试
            continue
        return None, None, last_info             # 真的解析不出来，别重试
    return None, None, last_info


def fill_coords(conn, limit: int = None) -> tuple:
    """给缺坐标的成都景区补经纬度

    ⚠️ 优先用完整地址；地址失败则退回「成都+区县+名称」重试一次。
       实测名录里的地址是景区自身地址，比纯名称命中率高。
    """
    from app.core.config import AMAP_KEY

    if not AMAP_KEY:
        print("  ⚠ 未设置 AMAP_KEY，跳过补坐标")
        return 0, 0

    rows = conn.execute(
        "SELECT id, name, district, address FROM attractions "
        "WHERE city=? AND (lon IS NULL OR lat IS NULL) ORDER BY id",
        (CITY,)).fetchall()

    if limit:
        rows = rows[:limit]

    print(f"  待补坐标: {len(rows)}")
    ok = fail = 0
    failures = []
    coords = []       # 收集起来，循环外统一写库，避免长事务

    for i, row in enumerate(rows, 1):
        addr = row["address"] or f"{CITY}市{row['district'] or ''}{row['name']}"
        lon, lat, info = geocode(addr)
        if lon is None and row["address"]:
            # 名录地址可能带「成都市xx区」前缀，换一种写法再试
            lon, lat, info = geocode(f"四川省{CITY}市{row['name']}")

        if lon is None:
            fail += 1
            failures.append((row["name"], info))
        else:
            coords.append((lon, lat, row["id"]))
            ok += 1

        if i % 20 == 0:
            print(f"    {i}/{len(rows)}  成功 {ok} 失败 {fail}")
        # ⚠️ 个人认证 QPS 限制实测约 3 次/秒。0.12 秒间隔会触发
        #    CUQPS_HAS_EXCEEDED_THE_LIMIT，失败的要重跑一遍很浪费，
        #    所以宁可慢：0.4 秒 ≈ 2.5 次/秒，留余量。
        time.sleep(0.4)

    for lon, lat, rid in coords:
        conn.execute("UPDATE attractions SET lon=?, lat=? WHERE id=?",
                     (lon, lat, rid))

    print(f"  → 补坐标完成: 成功 {ok}，失败 {fail}")
    if failures:
        print("  失败清单（前 10）:")
        for name, info in failures[:10]:
            print(f"    {name}: {info}")
    return ok, fail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geocode", action="store_true",
                    help="只补缺失坐标，不重新导入名录")
    args = ap.parse_args()

    init_db()

    with connect() as conn:
        if not args.geocode:
            if not CSV_PATH.exists():
                print(f"错误：找不到 {CSV_PATH}\n"
                      f"先跑：python -m app.scripts.fetch_chengdu", file=sys.stderr)
                sys.exit(2)

            rows = read_csv(CSV_PATH)
            print(f"[1] 导入景区名录: {len(rows)} 条")
            n = import_attractions(conn, rows)
            print(f"  → 写入 attractions: {n}")

        print("\n[2] 补经纬度（高德）")
        fill_coords(conn)

        print("\n" + "=" * 60)
        total = conn.execute(
            "SELECT COUNT(*) FROM attractions WHERE city=?", (CITY,)).fetchone()[0]
        withcoord = conn.execute(
            "SELECT COUNT(*) FROM attractions WHERE city=? "
            "AND lon IS NOT NULL AND lat IS NOT NULL", (CITY,)).fetchone()[0]
        print(f"{CITY} 景区总数: {total}")
        print(f"有坐标: {withcoord}  ({withcoord * 100 // max(total, 1)}%)")
        print(f"无坐标: {total - withcoord}")

        from collections import Counter
        levels = conn.execute(
            "SELECT level, COUNT(*) c FROM attractions WHERE city=? "
            "GROUP BY level ORDER BY level DESC", (CITY,)).fetchall()
        print("等级分布:", {r["level"]: r["c"] for r in levels})


if __name__ == "__main__":
    main()
