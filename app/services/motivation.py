#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动机挖掘（Travel for What）

PRD 核心差异化：先搞清楚"为什么去"，再推荐"去哪"。
七类动机：恢复/逃离、连接/关系、探索/新奇、表达/展示、
          成就/完成、文化/沉浸、美食/感官
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from app.services.llm import LLM

MOTIVATIONS = {
    "恢复/逃离": "低强度、自然、人少、慢节奏",
    "连接/关系": "互动性强、老少皆宜、节奏宽松",
    "探索/新奇": "小众、新开、非典型景点",
    "表达/展示": "出片率高、视觉冲击强、网红机位",
    "成就/完成": "标志性景点、打卡式、效率优先",
    "文化/沉浸": "深度讲解、在地体验、非游客区",
    "美食/感官": "餐饮驱动、市场、街巷、老字号",
}

MOTIVATION_PROMPT = """你是旅行需求分析助手。用户会用自然语言描述这次旅行的想法。

你的任务：判断用户的主要动机，并给出强度。

可选动机（只能从这七个里选）：
- 恢复/逃离：想放松、逃离日常、需要休息
- 连接/关系：和家人朋友一起、增进感情
- 探索/新奇：想看没见过的东西、尝鲜
- 表达/展示：想拍照、出片、分享
- 成就/完成：想打卡、完成心愿清单
- 文化/沉浸：想深入了解历史文化
- 美食/感官：冲着吃去的

规则：
1. 主动机只能选 1 个，必须是上述七个之一
2. 可选出 0-2 个次要动机
3. 强度为 1-5 的整数

约束抽取（重要，严格按此规范）：
- hours：**必须是 1-12 的整数，单位是小时**。"一天"≈8，"半天"≈4，"一天半"≈12。
  用户没明确说时长就填 null。**不要填字符串，不要带单位。**
- companions：同伴类型，如"父母"/"朋友"/"独自"/"情侣"/"带娃"。没说填 null
- note：其他约束（如"不要太累"、"预算有限"），没则填空字符串

只返回 JSON，不要任何解释。格式：
{"primary":"动机名","primary_intensity":3,"secondary":[],"constraints":{"hours":null,"companions":null,"note":""}}
"""


@dataclass
class Motivation:
    primary: str = ""
    primary_intensity: int = 3
    secondary: list = field(default_factory=list)
    constraints: dict = field(default_factory=dict)
    raw_input: str = ""

    def to_dict(self):
        return {
            "primary": self.primary,
            "primary_intensity": self.primary_intensity,
            "secondary": self.secondary,
            "constraints": self.constraints,
            "raw_input": self.raw_input,
        }

    def summary(self) -> str:
        parts = [f"{self.primary}（强度 {self.primary_intensity}/5）"]
        if self.secondary:
            parts.append("次要：" + "、".join(self.secondary))
        c = self.constraints or {}
        cs = []
        if c.get("hours"):
            cs.append(f"时长 {c['hours']} 小时")
        if c.get("companions"):
            cs.append(f"同伴 {c['companions']}")
        if c.get("note"):
            cs.append(str(c["note"]))
        if cs:
            parts.append("约束：" + "，".join(cs))
        return "；".join(parts)


def analyze(text: str, llm: Optional[LLM] = None) -> Motivation:
    """从自然语言里挖动机"""
    llm = llm or LLM()
    data = llm.json_chat([
        {"role": "system", "content": MOTIVATION_PROMPT},
        {"role": "user", "content": text},
    ])

    m = Motivation(raw_input=text)
    if not isinstance(data, dict):
        m.primary = "探索/新奇"     # 兜底
        return m

    primary = data.get("primary", "")
    # 校验：必须在预设七类里
    if primary in MOTIVATIONS:
        m.primary = primary
    else:
        # 尝试模糊匹配
        for k in MOTIVATIONS:
            if k in str(primary) or str(primary) in k:
                m.primary = k
                break
        else:
            m.primary = "探索/新奇"

    try:
        m.primary_intensity = max(1, min(5, int(data.get("primary_intensity", 3))))
    except (ValueError, TypeError):
        m.primary_intensity = 3

    sec = data.get("secondary") or []
    m.secondary = [s for s in sec if s in MOTIVATIONS and s != m.primary][:2]

    c = data.get("constraints") or {}
    if isinstance(c, dict):
        m.constraints = _normalize_constraints(c)

    return m


def _normalize_constraints(c: dict) -> dict:
    """规范化约束字段。

    LLM 常把 hours 填成 '1 day' / '一天' / '8小时' 这类，
    这里统一转成 1-12 的整数（小时），无法解析则置 None。
    """
    out = {
        "hours": None,
        "companions": None,
        "note": "",
    }

    # --- hours ---
    h = c.get("hours")
    if h is not None:
        if isinstance(h, (int, float)):
            iv = int(h)
            out["hours"] = iv if 1 <= iv <= 12 else None
        else:
            s = str(h).strip().lower()
            num = None
            # 中文数字映射（"一天"里的一要认得）
            cn_num = {"半": 0.5, "一": 1, "两": 2, "二": 2, "三": 3,
                      "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
                      "九": 9, "十": 10}
            # 一天半 / 半天 先处理（含"半"的组合）
            if "一天半" in s or "1.5" in s:
                num = 1.5
            elif "半天" in s:
                num = 0.5
            # 口语时段词（"一下午"这类没有数字）
            elif "上午" in s or "早上" in s:
                num = 4
            elif "下午" in s:
                num = 4
            elif "晚上" in s:
                num = 3
            elif "中午" in s:
                num = 2
            else:
                # 阿拉伯数字优先
                mth = re.search(r"(\d+(?:\.\d+)?)", s)
                if mth:
                    num = float(mth.group(1))
                else:
                    # 中文数字
                    for ch, v in cn_num.items():
                        if ch in s:
                            num = v
                            break
            # 天/日 → ×8
            if num is not None:
                if "day" in s or "天" in s or "日" in s:
                    num *= 8
                iv = int(round(num))
                out["hours"] = iv if 1 <= iv <= 12 else None

    # --- companions ---
    comp = c.get("companions")
    if comp and str(comp).strip().lower() not in ("null", "none", ""):
        out["companions"] = str(comp).strip()

    # --- note ---
    note = c.get("note")
    if note and str(note).strip().lower() not in ("null", "none"):
        out["note"] = str(note).strip()

    return out
