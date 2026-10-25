#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复现并验证修复：用户报告的那段真实对话"""
import httpx

B = 'http://127.0.0.1:8100'
c = httpx.Client(base_url=B, timeout=180)

# 原样复刻阿哲的对话
TURNS = [
    "我想看看现代建筑",
    "没有，你给我几个推荐",
    "你先随便给我几个",
    "就只看北京",
]

print("=" * 78)
print("复现：现代建筑推荐（阿哲报告的问题）")
print("=" * 78)

sid = None
for i, t in enumerate(TURNS, 1):
    r = c.post('/api/chat', json={"text": t, "session_id": sid}).json()
    sid = r["session_id"]
    prof = r.get("profile") or {}
    print(f"\n【第 {i} 轮】你：{t}")
    print(f"  AI：{r['reply']}")
    print(f"  画像：destination={prof.get('destination')!r}  primary={prof.get('primary')!r}")

    # 检查荒谬输出
    if "未知" in r['reply'] and "查不了" in r['reply']:
        print("  ✗✗ 仍有「未知还查不了」的荒谬输出！")
    if r['reply'].strip() in ("嗯，能再多说说吗？", "嗯，能再多说说吗？"):
        print("  ✗✗ 仍是敷衍兜底！")

print()
print("=" * 78)
print("结束")
print("=" * 78)
