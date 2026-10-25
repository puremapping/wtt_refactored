#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具定义（Function Calling）

设计要点：
  - 工具名 `propose_modify_itinerary` 带 `propose` 前缀 ——
    用命名约束模型「这是提议，需用户确认」，比靠 prompt 说更可靠。
  - `generate_itinerary` 则直接执行 —— 用户说「生成行程」就是要看结果。
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generate_itinerary",
            "description": (
                "为用户生成一日行程。"
                "**调用条件（必须满足其一）：**\n"
                "1. 用户明确要求生成行程 —— 如「生成行程」「看看行程」"
                "「给我排一下」「出个方案」「帮我安排」\n"
                "2. 用户明确说「换一批」「重新生成」「这几个都不想去」——"
                "此时用 regenerate 语义（也调本工具，系统会自动排除现有站点）\n\n"
                "**不要调用的情况：**\n"
                "- 用户只是提问（如「几点开门」「远不远」「好玩吗」）→ 直接回答\n"
                "- 用户还在描述需求 → 继续对话了解\n"
                "- 用户只是闲聊或感叹\n"
                "- 当前已有行程且用户没提要新的 → 直接回答即可\n\n"
                "判断不准时**不要调用**，宁可多聊一轮。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": {
                        "type": "integer",
                        "description": "行程时长（小时），1-12。已从对话得知则填写，否则省略。",
                    },
                    "reuse_existing": {
                        "type": "boolean",
                        "description": (
                            "已有行程时：true=重新生成一条全新的（排除现有站点）；"
                            "false 或不填=首次生成"
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_modify_itinerary",
            "description": (
                "提议修改**当前已有**的行程。"
                "**调用条件：** 用户对现有行程表达不满或提出调整要求 —— "
                "如「最后那个太远了」「这个不想去」「加一个吃饭的地方」"
                "「顺序不太顺」「换掉XX」。\n\n"
                "**不要调用的情况：**\n"
                "- 当前没有行程 → 不要调用（用户可能是在要求生成）\n"
                "- 用户只是问行程相关的问题（如「这几点开门」）→ 直接回答\n"
                "- 用户要求「换一批」「重新生成」→ 那应该调 generate_itinerary\n\n"
                "**这只是提议，系统会等用户确认后才执行。**"
                "调用后你应在回复里说明改什么、为什么，并询问是否要改。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["replace", "remove", "add", "reorder"],
                        "description": (
                            "replace=换掉某一站；remove=删除某一站；"
                            "add=增加一站；reorder=调整游览顺序。"
                            "注意：整条重来请用 generate_itinerary，不要用这个。"
                        ),
                    },
                    "target": {
                        "type": "string",
                        "description": "操作对象（景点名称）。add 时省略。",
                    },
                    "reason": {
                        "type": "string",
                        "description": "修改原因（一句话，会被展示给用户）",
                    },
                },
                "required": ["action", "reason"],
            },
        },
    },
]


def get_tools(has_itinerary: bool = False):
    """返回可用的工具集

    has_itinerary：当前是否已有行程。有行程时 propose_modify 才有意义。
    """
    if has_itinerary:
        return TOOLS
    # 没有行程时不给 propose_modify —— 从工具层面杜绝误调用
    return [t for t in TOOLS
            if t["function"]["name"] != "propose_modify_itinerary"]
