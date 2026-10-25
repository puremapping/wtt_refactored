#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量为景区补经纬度坐标（高德地理编码）

配额：地理编码 5000/日（个人认证），本次约 212 次。
这是行程生成的必需前置——平台数据有地址无坐标。

用法: python -m app.scripts.geocode_all
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import httpx

from app.core.config import AMAP_KEY
from app.core.db import connect

AMAP_URL = "https://restapi.amap.com/v3/geocode/geo"


def geocode(address, city="北京"):
    r = httpx.get(AMAP_URL, params={
        "address": address, "city": city, "key": AMAP_KEY,
    }, timeout=15)
    d = r.json()
    if d.get("status") == "1" and d.get("geocodes"):
        g = d["geocodes"][0]
        loc = g.get("location", "")
        if "," in loc:
            lon, lat = loc.split(",")
            return float(lon), float(lat), g.get("level", "")
    return None, None, d.get("info", "?")


def main():
    if not AMAP_KEY:
        print("错误：未设置 AMAP_KEY", file=sys.stderr)
        sys.exit(2)

    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name, district, address FROM attractions "
            "WHERE lon IS NULL OR lat IS NULL ORDER BY id"
        ).fetchall()

    print(f"待编码: {len(rows)} 个景区")
    print("=" * 78)

    ok = fail = 0
    failures = []

    for i, row in enumerate(rows, 1):
        addr = row["address"] or f"北京市{row['district']}{row['name']}"
        lon, lat, info = geocode(addr)

        if lon is None:
            # 回退：用区+名称再试一次
            lon, lat, info = geocode(f"北京市{row['district']}{row['name']}")

        if lon is not None:
            with connect() as conn:
                conn.execute(
                    "UPDATE attractions SET lon=?, lat=? WHERE id=?",
                    (lon, lat, row["id"]))
            ok += 1
        else:
            fail += 1
            failures.append((row["name"], info))

        if i % 20 == 0 or i == len(rows):
            print(f"  [{i:>3}/{len(rows)}]  成功 {ok}  失败 {fail}")
        time.sleep(0.25)      # 限速，避开 10004 频率限制

    print("=" * 78)
    print(f"完成：成功 {ok} / 失败 {fail} / 共 {len(rows)}")

    if failures:
        print("\n失败清单:")
        for name, info in failures[:20]:
            print(f"  ✗ {name}  ({info})")

    # 统计
    with connect() as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM attractions WHERE lon IS NOT NULL"
        ).fetchone()[0]
    print(f"\n库中有坐标的景区: {n}")


if __name__ == "__main__":
    main()
