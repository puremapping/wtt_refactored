#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端接口测试（避开 shell 中文编码问题）"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import httpx

BASE = "http://127.0.0.1:8100"

CASES = [
    ("恢复/逃离", 4, 8),
    ("文化/沉浸", 4, 8),
    ("成就/完成", 5, 8),
]

for mot, intensity, hours in CASES:
    print("=" * 84)
    print(f"【{mot}】强度 {intensity} / {hours} 小时")
    print("=" * 84)
    try:
        r = httpx.post(f"{BASE}/api/itinerary", json={
            "motivation": mot, "intensity": intensity, "hours": hours,
        }, timeout=120)
        d = r.json()
        print(f"{len(d['stops'])} 站 / {d['total_distance_km']} km")
        for s in d["stops"]:
            reasons = "；".join(s["reasons"]) if s["reasons"] else "—"
            print(f"  {s['arrive']}  {s['name']:<24} [{s['level']}] "
                  f"{s['district']:<5} {reasons}")
        if d["stops"]:
            print(f"  时段: {d['stops'][0]['arrive']} → {d['stops'][-1]['arrive']}")
    except Exception as e:
        print(f"  失败: {type(e).__name__}: {e}")
    print()
