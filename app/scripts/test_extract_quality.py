#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""动机抽取质量测试 —— 批量跑真实场景，看判得准不准

判据：期望的主动机是否被抽出来。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.db import init_db
from app.services import conversation as conv

init_db()

# (用户说的话, 期望的主动机或 None)
CASES = [
    ("最近工作太累了，想找个人少的地方待着", "恢复/逃离"),
    ("想找个安静的地方放空一下", "恢复/逃离"),
    ("带爸妈出去走走，他们年纪大了走不快", "连接/关系"),
    ("想和女朋友过个安静的周末", "连接/关系"),
    ("想看看没去过的地方，最好小众一点", "探索/新奇"),
    ("想拍点好看的照片，要那种特别出片的机位", "表达/展示"),
    ("想把故宫长城这些必去的都打卡一遍", "成就/完成"),
    ("想认真了解一下北京的历史文化，最好有讲解", "文化/沉浸"),
    ("特别喜欢吃，想找老字号和小吃街", "美食/感官"),
    ("想去北京玩一天", None),                       # 信息不足，不该猜
]

print("=" * 88)
print("动机抽取质量测试")
print("=" * 88)

ok = wrong = miss = 0
for text, expect in CASES:
    c = conv.chat(None, text)
    got = c.profile.get("primary")
    if expect is None:
        status = "✓" if got is None else f"✗ 多判({got})"
        if got is None:
            ok += 1
        else:
            wrong += 1
    elif got == expect:
        status = "✓"
        ok += 1
    elif got is None:
        status = "○ 未判出"
        miss += 1
    else:
        status = f"✗ 判成({got})"
        wrong += 1

    print(f"{status:<16} 「{text[:34]}」")
    if got:
        print(f"{'':<16} → primary={got} intensity={c.profile.get('primary_intensity')}"
              + (f" companions={c.profile.get('companions')}" if c.profile.get('companions') else ""))
    print()

total = len(CASES)
print("=" * 88)
print(f"结果：正确 {ok}/{total}   错误 {wrong}   未判出 {miss}")
print("=" * 88)
