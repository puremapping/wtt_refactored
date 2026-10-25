#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 tool_calls 触发（生成行程 / 提议修改）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.db import init_db
from app.services import conversation as conv

init_db()

FAKE_ITINERARY = {
    "motivation": "恢复/逃离",
    "hours": 8,
    "total_distance_km": 25.7,
    "stops": [
        {"order": 1, "arrive": "09:00", "name": "京都第一瀑景区",
         "level": "3A", "district": "密云区", "crowd": 0},
        {"order": 2, "arrive": "10:16", "name": "北京天门山旅游风景区",
         "level": "3A", "district": "密云区", "crowd": 1},
        {"order": 3, "arrive": "11:37", "name": "捧河湾自然风景区",
         "level": "3A", "district": "密云区", "crowd": 0},
        {"order": 4, "arrive": "14:00", "name": "神堂峪自然风景区",
         "level": "3A", "district": "怀柔区", "crowd": 2},
    ],
    "risks": ["各站点均无地铁直达，建议自驾或打车"],
}


def run(title, session_id, text, itinerary=None):
    c = conv.chat(session_id, text, current_itinerary=itinerary)
    print(f"\n【{title}】")
    print(f"  用户: {text}")
    print(f"  AI  : {c.messages[-1]['content'][:100]}")
    if c.tool_calls:
        for tc in c.tool_calls:
            print(f"  🔧 tool_call: {tc['name']}({tc['args']})")
    else:
        print(f"  （无工具调用）")
    return c


print("=" * 84)
print("tool_calls 触发测试")
print("=" * 84)

# 场景 1：无行程时，用户说「生成行程」
c = run("场景1 生成行程", None, "想去北京玩一天，一个人想安静点")
sid = c.session_id
run("场景1b 明确要求生成", sid, "帮我生成行程吧")

# 场景 2：有行程时，用户说某站太远
c2 = run("场景2 提议修改", sid, "最后那个神堂峪太远了，换一个", FAKE_ITINERARY)

# 场景 3：有行程时，用户说换一批
run("场景3 重新生成", sid, "这几个都不太想去，换一批", FAKE_ITINERARY)

# 场景 4：有行程时，用户只是闲聊（不该触发工具）
run("场景4 不该触发", sid, "这些地方大概几点开门？", FAKE_ITINERARY)
