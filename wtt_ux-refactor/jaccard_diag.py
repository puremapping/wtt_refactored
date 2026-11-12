#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨画像 Top-5 Jaccard 重合度诊断（可复现）

结论与用法见 wtt_ux-refactor/PLAN.md §P2「诊断结论」。

⚠️ 必须在项目根目录运行：
    .venv/Scripts/python.exe wtt_ux-refactor/jaccard_diag.py
不能在 D:/fs/tmp 下跑 —— 那里的 inspect.py 会遮蔽标准库。
"""
import os
import sys

os.environ.setdefault("SECRET_KEY", "x")
os.environ.setdefault("GLM_API_KEY", "x")
os.environ.setdefault("ADMIN_TOKEN", "x")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.recommend import recommend  # noqa: E402

MOTIVATIONS = [
    "恢复/逃离", "连接/关系", "探索/新奇", "表达/展示",
    "成就/完成", "文化/沉浸", "美食/感官",
]


def jaccard(a, b):
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


def main():
    print(f"{'':16}" + "".join(f"{m[:4]:>8}" for m in MOTIVATIONS))
    print("-" * (16 + 8 * len(MOTIVATIONS)))

    selections = {}
    all_names = set()
    for m in MOTIVATIONS:
        top = recommend(m, intensity=3, top_k=5, city="北京")
        names = [t.name for t in top]
        selections[m] = names
        all_names.update(names)

    for mi in MOTIVATIONS:
        row = f"{mi:<16}"
        for mj in MOTIVATIONS:
            row += f"{jaccard(selections[mi], selections[mj]):>8.1f}"
        print(row)

    print("\n各动机选出的 top-5：")
    for m in MOTIVATIONS:
        print(f"  {m:<8}: {', '.join(selections[m])}")

    first = [selections[m][0] for m in MOTIVATIONS]
    print(f"\n7 种动机第一个推荐去重后 {len(set(first))} 个")
    print(f"全部选中景区去重后 {len(all_names)} 个 / 7×5=35")


if __name__ == "__main__":
    main()
