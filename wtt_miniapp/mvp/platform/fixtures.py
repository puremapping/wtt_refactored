#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""演示账号（MVP fixtures，非真实用户数据）

三个账号分别暴露画像的三种状态：
  - 完整：字段齐全，含用户原话 summary
  - 稀薄：只有动机，其余未知 —— 验证「注入必须能什么都不注入」
  - 含占位词：destination 被模型填成「未知」——验证主项目的占位词清洗
"""
from __future__ import annotations

# 演示账号共用的密码（本地 MVP 演示专用，不是任何真实凭证；
# 运行时用主项目 auth.hash_password / verify_password 做 constant-time 校验）
DEMO_PASSWORD = "wtt-mvp-demo"

DEMO_USERS = {
    "wenhua@example.com": {
        "id": "u_wenhua",
        "nickname": "文化沉浸型游客",
        "hint": "带父母、慢节奏、爱古建筑 —— 讲解应走深度文化版",
        "profile": {
            "destination": "苏州",
            "primary": "文化/沉浸",
            "primary_intensity": 5,
            "secondary": ["连接/关系"],
            "hours": 4,
            "companions": "父母",
            "pace": "松散",
            "interests": ["古建筑", "园林造园技艺", "碑刻"],
            "avoid": ["网红打卡点", "排队"],
            "must_see": ["假山迷宫"],
            "summary": "想陪爸妈慢慢逛，听点造园的门道，别去人挤人的地方",
            "_turns": 5,
        },
        "itinerary": {
            "motivation": "文化/沉浸",
            "hours": 4,
            "stops": [
                {"order": 1, "name": "假山迷宫", "district": "姑苏区", "arrive": "09:30"},
                {"order": 2, "name": "燕誉堂", "district": "姑苏区", "arrive": "10:40"},
                {"order": 3, "name": "指柏轩", "district": "姑苏区", "arrive": "11:50"},
            ],
            "total_distance_km": 0.8,
            "risks": [],
        },
    },

    "xbo@example.com": {
        "id": "u_xbo",
        "nickname": "稀薄画像游客",
        "hint": "只说了「想放松」，其余全未知 —— 讲解应退回通用版",
        "profile": {
            "destination": "苏州",
            "primary": "恢复/逃离",
            "primary_intensity": 3,
            "_turns": 2,
        },
        "itinerary": {},
    },

    "placeholder@example.com": {
        "id": "u_placeholder",
        "nickname": "含占位词游客",
        "hint": "destination 被模型填成「未知」—— 验证占位词清洗",
        "profile": {
            "destination": "未知",          # ⚠️ 主项目 _clean_field_value 会拦
            "primary": "探索/新奇",
            "companions": "未知",
            "summary": "想看点没见过的",
            "_turns": 3,
        },
        "itinerary": {},
    },
}
