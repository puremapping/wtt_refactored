#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取成都市 A 级旅游景区名录（四川省文化和旅游厅官方）

## 数据源

  https://wlt.sc.gov.cn/scwlt/c100297/introduce.shtml
  标题：《四川省A级旅游景区名录》
  更新：2026-01-07（页面上写死的，脚本会一并记录）

## 为什么用这个源

市级平台（成都市公共数据开放平台 chengdu.gov.cn/data/oportal）**没有景区数据集**
——2026-10-29 实测翻过它的目录，40 个市级部门里没有文旅局开放的景区数据。
省级文旅厅的名录是能拿到的最权威、最新、且完全公开的结构化数据。

## 产出

  data/raw/chengdu_attractions.csv   103 行，字段：
    seq, name, city, district, level, address

## 用法

  python -m app.scripts.fetch_chengdu
"""
import csv
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

SOURCE_URL = "https://wlt.sc.gov.cn/scwlt/c100297/introduce.shtml"
CITY = "成都"
OUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw"
OUT_CSV = OUT_DIR / "chengdu_attractions.csv"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    raw = urllib.request.urlopen(req, timeout=30).read()
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise RuntimeError("无法解码页面")


def parse_rows(html: str) -> list:
    """解析表格行

    表头：序号 | 名称 | 所在市州 | 所在区县 | 等级 | 地址
    小计行（如「5A级旅游景区」「4A级旅游景区」）只有一个单元格，会被长度判断滤掉。
    """
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) != 6:
            continue
        seq, name, city, district, level, address = cells
        if not name or not city:
            continue
        out.append({
            "seq": seq, "name": name, "city": city,
            "district": district, "level": level, "address": address,
        })
    return out


def main():
    print(f"抓取: {SOURCE_URL}")
    html = fetch_html(SOURCE_URL)

    rows = parse_rows(html)
    print(f"全省景区: {len(rows)} 条")

    cd = [r for r in rows if CITY in r["city"]]
    print(f"{CITY}景区: {len(cd)} 条")

    if not cd:
        print("错误：没解析到成都数据，页面结构可能变了", file=sys.stderr)
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["seq", "name", "city",
                                          "district", "level", "address"])
        w.writeheader()
        w.writerows(cd)

    print(f"\n已写入: {OUT_CSV}")

    from collections import Counter
    dist = Counter(r["level"] for r in cd)
    print("等级分布:", dict(sorted(dist.items())))


if __name__ == "__main__":
    main()
