#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对话领域模型"""
from dataclasses import dataclass, field


@dataclass
class Conversation:
    """一次多轮对话的状态"""
    session_id: str = ""
    messages: list = field(default_factory=list)      # [{role, content}]
    profile: dict = field(default_factory=dict)       # 累积的画像
    turn: int = 0
    ready: bool = False                               # 信息是否足够生成行程
    created_at: str = ""
    tool_calls: list = field(default_factory=list)    # 本轮 LLM 请求调用的工具
    itinerary: dict = field(default_factory=dict)     # 当前行程（匿名会话需要）

    def to_dict(self):
        return {
            "session_id": self.session_id,
            "messages": self.messages,
            "profile": self.profile,
            "turn": self.turn,
            "ready": self.ready,
            "created_at": self.created_at,
        }
