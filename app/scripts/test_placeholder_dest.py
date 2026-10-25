#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复现「未知」bug：模型把 destination 填成占位词，触发了数据边界拦截"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.services.conversation import _is_supported_destination

print("=" * 76)
print("_is_supported_destination 对占位词的处理（当前行为）")
print("=" * 76)

cases = [
    ("北京", True),
    ("朝阳区", True),
    ("上海", False),
    ("", True),
    # ⚠️ 以下这些是模型可能填进来的「占位词」
    ("未知", "?"),
    ("不清楚", "?"),
    ("待定", "?"),
    ("无", "?"),
    ("不确定", "?"),
    ("未提及", "?"),
    ("-", "?"),
    ("null", "?"),
    ("None", "?"),
    ("未指定", "?"),
    ("未提供", "?"),
    ("不限", "?"),
    ("都可以", "?"),
]

for dest, expected in cases:
    got = _is_supported_destination(dest)
    if expected == "?":
        mark = "⚠️ 应为 True（占位词=没填）" if not got else "✓"
        print(f"  {dest!r:14} → {got}   {mark}")
    else:
        ok = "✓" if got == expected else "✗ 错"
        print(f"  {dest!r:14} → {got}   {ok}（期望 {expected}）")
