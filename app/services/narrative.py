#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行程叙述 + 可解释推荐

把结构化的行程数据交给 LLM，生成：
  1. 行程叙述（人话）
  2. 每条推荐的可解释理由（自然语言）
  3. 整体评估（强度、风险、建议）

设计参考 ITINERA 的 Prompt 范式（docs/research/arxiv-findings.md）：
  - 角色设定 + 任务概述 + 输出规范
  - 强制 JSON 输出，禁止多余解释
"""
from app.services.llm import LLM

NARRATIVE_PROMPT = """你是旅行规划助手。用户告诉我这次旅行的动机和行程安排，你负责把它讲成一段自然、有画面感的叙述。

## ⚠️ 硬性约束（必须遵守）
**只能提到下面「行程安排」里列出的景点。**
- 不要添加任何未列出的景点、地标、街道、餐厅
- 不要编造营业时间、票价、具体地址等你不知道的信息
- 不确定的事就不要说，宁可少说

## 写作要求
1. 用第二人称"你"，像朋友在给建议
2. 结合动机解释"为什么这条路线适合你"
3. 提到具体的景点名和到达时间
4. 指出需要注意的地方（人流、交通）
5. 150-250 字，纯文本，不要 Markdown 标记

只返回叙述文本，不要任何前缀或解释。
"""


def _verify_narrative(text: str, stops: list) -> tuple:
    """校验叙述里有没有幻觉景点

    返回 (是否通过, 可疑提及列表)

    做法：从叙述里找出「看起来像景点名」的词（含「景区/公园/博物馆/寺/宫/园」
    等后缀），检查是否都在实际站点里。不在的就是疑似幻觉。
    """
    import re
    if not text:
        return True, []

    real = {s["name"] for s in stops if s.get("name")}
    # 真实景点的简称（去掉后缀）也认
    real_short = set()
    for n in real:
        real_short.add(n)
        for suf in ("景区", "风景区", "公园", "博物馆", "纪念馆", "旅游区"):
            if n.endswith(suf):
                real_short.add(n[:-len(suf)])

    # 找出叙述里带景点特征后缀的词
    pattern = (r"[\u4e00-\u9fa5]{2,10}"
               r"(?:景区|风景区|公园|博物馆|纪念馆|寺|宫|园|塔|桥|长城|"
               r"胡同|大街|广场|大学|美术馆|艺术区)")
    suspects = []
    for m in re.finditer(pattern, text):
        word = m.group(0)
        # 命中真实的就跳过
        if any(word in r or r in word for r in real_short):
            continue
        suspects.append(word)

    return (len(suspects) == 0), suspects[:5]

ASSESS_PROMPT = """你是旅行规划助手。根据给出的行程，给出简短评估。

只返回 JSON，格式：
{"intensity":"低/中/高","strength":"整体强度一句话","suggestion":"一条最实用的建议"}

不要任何解释。"""


def narrate(itinerary_dict: dict, motivation: str, llm=None,
            profile: dict = None) -> str:
    """生成行程叙述

    profile：完整画像（可选）。带上它能让叙述更贴合用户的具体约束，
    比如同伴是父母就少提"暴走"，提到人流少就强调安静。
    """
    llm = llm or LLM()

    stops_desc = "\n".join(
        f"{s['arrive']} {s['name']}（{s['level']}，{s['district']}）"
        + (f"，人流指数 {s['crowd']:.0f}" if s.get("crowd") is not None else "")
        for s in itinerary_dict["stops"]
    )

    risks = "；".join(itinerary_dict.get("risks", [])) or "无明显风险"

    # 画像细节
    extra = ""
    if profile:
        bits = []
        if profile.get("companions"):
            bits.append(f"同伴：{profile['companions']}")
        if profile.get("pace"):
            bits.append(f"希望的节奏：{profile['pace']}")
        if profile.get("interests"):
            bits.append("兴趣：" + "、".join(profile["interests"][:4]))
        if profile.get("avoid"):
            bits.append("想避开：" + "、".join(profile["avoid"][:3]))
        if profile.get("secondary"):
            bits.append("次要动机：" + "、".join(profile["secondary"]))
        if bits:
            extra = "\n补充信息：" + "；".join(bits) + "\n"

    user = f"""旅行动机：{motivation}{extra}
行程时长：{itinerary_dict['hours']} 小时
总距离：{itinerary_dict['total_distance_km']} 公里

行程安排：
{stops_desc}

风险提示：{risks}

请把这条行程讲给用户听。"""

    text = llm.chat([
        {"role": "system", "content": NARRATIVE_PROMPT},
        {"role": "user", "content": user},
    ], temperature=0.7).strip()

    # 防幻觉校验：提到不存在的景点就重写一次
    ok, suspects = _verify_narrative(text, itinerary_dict.get("stops", []))
    if not ok:
        retry_user = (user
                      + f"\n\n⚠️ 上一次回答里提到了不在行程中的地点："
                        f"{'、'.join(suspects)}。"
                        f"请重写，**只准提到上面列出的景点**。")
        text2 = llm.chat([
            {"role": "system", "content": NARRATIVE_PROMPT},
            {"role": "user", "content": retry_user},
        ], temperature=0.5).strip()
        ok2, _ = _verify_narrative(text2, itinerary_dict.get("stops", []))
        if ok2 or not text2:
            text = text2 or text
        # 若重写仍不合格，保留原文但标注（宁可如实告知，不假装没问题）

    return text


def assess(itinerary_dict: dict, llm=None) -> dict:
    """行程强度评估"""
    llm = llm or LLM()
    n = len(itinerary_dict["stops"])
    km = itinerary_dict["total_distance_km"]
    hours = itinerary_dict["hours"]

    user = (f"行程共 {n} 个景点，{hours} 小时，总距离 {km} 公里。"
            f"站点：{'、'.join(s['name'] for s in itinerary_dict['stops'])}")

    d = llm.json_chat([
        {"role": "system", "content": ASSESS_PROMPT},
        {"role": "user", "content": user},
    ])
    if isinstance(d, dict):
        return {
            "intensity": d.get("intensity", "中"),
            "strength": d.get("strength", ""),
            "suggestion": d.get("suggestion", ""),
        }
    return {"intensity": "中", "strength": "", "suggestion": ""}


EXPLAIN_PROMPT = """你是推荐解释助手。用户有明确的旅行动机，系统推荐了这些景点。

你的任务：为每个景点写一句推荐理由，说明它为什么契合用户动机。

要求：
1. 每条不超过 40 字
2. 结合动机，不要泛泛而谈
3. 如果已知人流数据，可以提及

只返回 JSON 数组，格式：["理由1","理由2",...]
不要任何解释。"""


def explain(pois: list, motivation: str, llm=None) -> list:
    """为一批景点生成可解释理由"""
    llm = llm or LLM()
    if not pois:
        return []

    lines = "\n".join(
        f"{i+1}. {p['name']}（{p.get('level','')}，{p.get('district','')}）"
        for i, p in enumerate(pois)
    )

    d = llm.json_chat([
        {"role": "system", "content": EXPLAIN_PROMPT},
        {"role": "user", "content": f"用户动机：{motivation}\n\n推荐景点：\n{lines}"},
    ])
    if isinstance(d, list):
        return [str(x) for x in d][:len(pois)]
    return [p.get("reasons", [""])[0] if p.get("reasons") else "" for p in pois]
