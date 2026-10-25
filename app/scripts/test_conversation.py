#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多轮对话实跑测试（不经 Web，直接调服务层）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.db import init_db
from app.services import conversation as conv

init_db()

# 模拟一段真实对话
SCRIPT = [
    "想去北京玩一天",
    "最近工作太累了，就想找个地方安静待着",
    "一个人去，不想跟人挤",
    "大概一天吧，不用太赶",
]

print("=" * 84)
print("多轮动机对话测试")
print("=" * 84)

sid = None
for i, user_text in enumerate(SCRIPT, 1):
    print(f"\n【第 {i} 轮】用户：{user_text}")
    c = conv.chat(sid, user_text)
    sid = c.session_id
    print(f"  AI：{c.messages[-1]['content']}")
    print(f"  ── 画像：{conv.profile_summary(c.profile)}")
    print(f"  ── ready={c.ready}")

print()
print("=" * 84)
print("最终画像")
print("=" * 84)
import json
print(json.dumps(c.profile, ensure_ascii=False, indent=1))
print()
print(f"会话 ID: {sid}   轮数: {c.turn}   就绪: {c.ready}")

# 验证会话能重新载入
print()
print("=" * 84)
print("会话持久化验证")
print("=" * 84)
reloaded = conv.load_session(sid)
if reloaded:
    print(f"✓ 重新载入成功，轮数={reloaded.turn}，消息数={len(reloaded.messages)}")
    print(f"  画像一致性: {reloaded.profile == c.profile}")
else:
    print("✗ 载入失败")
