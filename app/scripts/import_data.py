#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 .research 里下载的北京数据导入 SQLite。

数据源（均来自北京市公共数据开放平台，已实测下载）：
  北京市等级景区信息.csv      →  attractions（基础）
  等级景区门票信息.xlsx        →  attractions（票价）
  等级景区交通信息.xlsx        →  transport
  重点景区饱和指数.xlsx        →  crowd_index

用法: python -m app.scripts.import_data
"""
import csv
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.config import RESEARCH_DIR
from app.core.db import connect, init_db


def read_csv(path):
    for enc in ("utf-8-sig", "gbk"):
        try:
            with open(path, encoding=enc, newline="") as f:
                return [r for r in csv.reader(f) if any(c.strip() for c in r)]
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"无法解码: {path}")


def read_xlsx(path, sheet_marker=None):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = []
    for r in ws.iter_rows(values_only=True):
        if any(c is not None and str(c).strip() for c in r):
            rows.append(["" if c is None else str(c).strip() for c in r])
    wb.close()
    return rows


def import_attractions(conn):
    """景区基础信息 + 票价"""
    f = RESEARCH_DIR / "北京市等级景区信息.csv"
    rows = read_csv(f)
    hdr, body = rows[0], rows[1:]
    print(f"  景区基础: {len(body)} 行")

    # 票价（用 名称 关联）
    price = {}
    pf = RESEARCH_DIR / "等级景区门票信息.xlsx"
    if pf.exists():
        prows = read_xlsx(pf)
        phdr = prows[0]
        # 主键，序号 | 景区名称 | 景区等级 | 门票是否收费 | 旺季价格 | 淡季价格
        for r in prows[1:]:
            if len(r) < 6:
                continue
            name = r[1]
            free = 1 if r[3] in ("否", "免费") else 0
            try:
                ph = float(r[4]) if r[4] not in ("", "None") else None
            except ValueError:
                ph = None
            try:
                pl = float(r[5]) if r[5] not in ("", "None") else None
            except ValueError:
                pl = None
            price[name] = (free, ph, pl)
        print(f"  门票信息: {len(price)} 条")

    n = 0
    for r in body:
        if len(r) < 5:
            continue
        try:
            idx = int(r[0])
        except ValueError:
            continue
        name = r[1].strip()
        free, ph, pl = price.get(name, (None, None, None))
        # context：用于 embedding 的描述
        ctx = f"{name}，位于北京市{r[3]}，等级{r[2]}，地址{r[4]}"
        conn.execute(
            """INSERT OR REPLACE INTO attractions
               (id,name,level,district,address,phone,postcode,
                ticket_free,price_high,price_low,context)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (idx, name, r[2], r[3], r[4],
             r[5] if len(r) > 5 else "", r[6] if len(r) > 6 else "",
             free, ph, pl, ctx))
        n += 1
    print(f"  → 导入 attractions: {n}")
    return n


def import_transport(conn):
    f = RESEARCH_DIR / "等级景区交通信息.xlsx"
    if not f.exists():
        print("  ⚠ 交通信息文件不存在")
        return 0
    rows = read_xlsx(f)
    body = rows[1:]
    print(f"  交通信息: {len(body)} 行")

    n = 0
    for r in body:
        if len(r) < 4:
            continue
        # 主键|景区名称|区域|等级|地铁|公交|高速|支线|机场|火车站|城镇
        vals = (r[1], r[2], r[3],
                r[4] if len(r) > 4 else "", r[5] if len(r) > 5 else "",
                r[6] if len(r) > 6 else "", r[7] if len(r) > 7 else "",
                r[8] if len(r) > 8 else "", r[9] if len(r) > 9 else "",
                r[10] if len(r) > 10 else "")
        conn.execute(
            """INSERT INTO transport
               (attraction_name,district,level,metro,bus,highway,
                branch_road,airport,railway,town)
               VALUES (?,?,?,?,?,?,?,?,?,?)""", vals)
        n += 1
    print(f"  → 导入 transport: {n}")
    return n


def import_crowd(conn, limit=None):
    f = RESEARCH_DIR / "重点景区饱和指数(全市4A级以上景区饱和指数).xlsx"
    if not f.exists():
        print("  ⚠ 饱和指数文件不存在")
        return 0
    print("  读取饱和指数（10万行，稍慢）...")
    rows = read_xlsx(f)
    body = rows[1:]
    if limit:
        body = body[:limit]
    print(f"  饱和指数: {len(body)} 行")

    # 只保留每个景区的最新一条（按数据获取时间）
    latest = {}
    for r in body:
        if len(r) < 3:
            continue
        name, sat, ts = r[0], r[1], r[2]
        if not name:
            continue
        if name not in latest or ts > latest[name][1]:
            try:
                latest[name] = (float(sat), ts)
            except (ValueError, TypeError):
                continue
    print(f"  → 去重后景区数: {len(latest)}")

    n = 0
    for name, (sat, ts) in latest.items():
        conn.execute(
            "INSERT INTO crowd_index (name,saturation,ts) VALUES (?,?,?)",
            (name, sat, ts))
        n += 1
    print(f"  → 导入 crowd_index: {n}")
    return n


def main():
    print("=" * 70)
    print("导入北京数据到 SQLite")
    print("=" * 70)
    init_db()
    with connect() as conn:
        # 清空重灌
        for t in ("attractions", "transport", "crowd_index"):
            conn.execute(f"DELETE FROM {t}")

        print("\n[1] 景区")
        import_attractions(conn)
        print("\n[2] 交通")
        import_transport(conn)
        print("\n[3] 人流")
        import_crowd(conn)

        print("\n" + "=" * 70)
        print("统计")
        print("=" * 70)
        for t in ("attractions", "transport", "crowd_index"):
            c = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t:<16} {c}")
    print("\n导入完成")


if __name__ == "__main__":
    main()
