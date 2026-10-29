#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对话策略：意图白名单 / 工具过滤 / 数据边界 / 兜底回复

这一层是服务端对模型行为的「二次把关」—— 每个policy背后都是一次
真实踩坑（v0.3-v0.5），切勿因模型升级而随意删除。
"""
from typing import TYPE_CHECKING

import re

from app.services import cities
from app.services.conversation.profile import _clean_field_value

if TYPE_CHECKING:
    from app.services.conversation.models import Conversation


def _clean_reply(reply: str) -> str:
    """清理回复里的杂质

    实测：模型调工具时，有时会把流式响应碎片（JSON 片段）当正文吐出来，
    形如 `我查一下{"index":0,"finish_reason":"tool_calls","delta":...`
    """
    if not reply:
        return ""
    t = reply.strip()

    # 砍掉从 `{"index"` 开始的流式碎片
    for marker in ('{"index"', '{"id"', '"finish_reason"'):
        i = t.find(marker)
        if i > 0:
            t = t[:i].rstrip()
            break

    # 若是纯 JSON 对象，丢弃（不该当正文）
    if t.startswith("{") and t.endswith("}"):
        return ""

    return t.strip()


def _is_generate_intent(user_text: str) -> bool:
    """判断用户是否真的要生成行程

    实测教训：glm-4-flash 会在用户只是提问时也调 generate_itinerary。
    光靠工具描述里写「不要调用」不够，服务端要二次把关。

    这是**白名单式**判断：只有用户明确表达生成意愿才放行。
    """
    t = (user_text or "").strip()
    if not t:
        return False
    triggers = [
        "生成", "排个", "排一下", "安排", "规划", "出个", "做个",
        "看看行程", "看行程", "出方案", "怎么玩", "怎么安排",
        "换一批", "重新来", "再来一版",
    ]
    if any(k in t for k in triggers):
        return True
    # ⚠️ 「排一天的行程」「排 6 小时」这种最自然的说法不含上面任何整词 ——
    #    实测「北京帮我排一天的行程」被判成没意图，行程永远生成不出来。
    #    用正则补：排 + 可选量词 + 数字/中文数 + 天/小时/日。
    #    不能简单加「排」，否则「排队」「安排」都会误触发。
    if re.search(r"排\s*[个一]?\s*[0-9一二三四五六七八九十两]+\s*(天|日|小时|钟头)", t):
        return True
    if re.search(r"(一天|两天|半天|一日|两日).{0,4}(行程|路线|路线图)", t):
        return True
    return False


def _should_allow_propose(user_text: str) -> bool:
    """判断是否该允许 propose_modify

    实测教训：服务端过滤太严会让该调的也不调。
    场景「最后那个太远了，换一个」应触发 propose —— 不能因为
    它不含「生成」类词就被砍掉。
    """
    t = (user_text or "").strip()
    if not t:
        return False
    # 排除「换一批」这类整条重来的（那该走 generate）
    if any(k in t for k in ("换一批", "重新生成", "重新来", "再来一版",
                            "其他的", "别的")):
        return False
    triggers = [
        "换", "太远", "太赶", "不想去", "去掉", "删", "加一个", "加点",
        "顺序", "倒过来", "调整", "改一下", "改成", "不好", "不合适",
        "有没有别的", "还有其他",
    ]
    return any(k in t for k in triggers)


def _sanitize_tool_calls(tool_calls: list, user_text: str,
                         has_itinerary: bool) -> list:
    """服务端校验 + 过滤工具调用

    过滤规则：
      1. 没有行程时，不允许 propose_modify（工具层面已不给，这里是双保险）
      2. propose 需要「调整意图」，否则丢弃
      3. generate 需要「生成意图」，否则丢弃
      4. 参数非法时丢弃
    """
    out = []
    for tc in tool_calls or []:
        name = tc.get("name")
        args = tc.get("args") or {}

        if name == "propose_modify_itinerary":
            if not has_itinerary:
                continue
            if args.get("action") not in ("replace", "remove", "add", "reorder"):
                continue
            if not _should_allow_propose(user_text):
                continue
            out.append(tc)

        elif name == "generate_itinerary":
            if not _is_generate_intent(user_text):
                continue
            out.append(tc)

    return out


def _is_supported_destination(dest: str) -> bool:
    """判断目的地是否在数据覆盖范围内

    ⚠️ 不再硬编码「北京」—— 从数据库的城市注册表判断（app/services/cities.py）。
       加第二座城市只需导入数据，不用改这里。

    ⚠️ 「未知」「不确定」这类占位词 = 用户没说过目的地 → 视为空（True）。
       不能当成「一个叫未知的城市」。
    """
    d = _clean_field_value(dest)
    if not d:
        return True
    return cities.is_supported(d)


def _substantive_fallback(conv: "Conversation") -> str:
    """正文为空且无工具调用时的兜底 —— 给实质内容，不敷衍

    优先级：有动机 → 顺着动机问最关键的一个缺口；
            没动机 → 问动机（这是产品的核心入口）。
    """
    p = conv.profile or {}
    mot = p.get("primary")
    dest = _clean_field_value(p.get("destination"))
    hours = p.get("hours")

    if not mot:
        return ("我先问最关键的一件事：**你这次出去是为了什么？**\n\n"
                "比如想歇一歇、想陪家人、想找点新鲜感——说法随意，"
                "我按这个来挑地方。")

    if not hours:
        return f"明白，这次是「{mot}」。\n\n那你大概能空出多久？半天还是一整天？"

    if not dest:
        return (f"好，这次是「{mot}」，大概 {hours} 小时。\n\n"
                f"想去哪个城市？我目前有**{cities.supported_description()}**的完整数据。")

    return "我先把条件理一理，你要补充什么随时说。"


def _fallback_reply(tool_calls: list, conv: "Conversation") -> str:
    """模型返回 tool_calls 但 content 为空时的兜底回复

    实测：模型决定调工具时常不写正文，直接给 tool_calls。
    """
    if not tool_calls:
        return _substantive_fallback(conv)

    tc = tool_calls[0]
    name = tc.get("name")
    args = tc.get("args") or {}

    if name == "generate_itinerary":
        return "好，我按你现在说的给你排一条行程。"

    if name == "propose_modify_itinerary":
        act = args.get("action")
        target = args.get("target") or ""
        reason = args.get("reason") or ""
        label = {
            "replace": "换掉", "remove": "去掉", "add": "加一个",
            "reorder": "调整顺序", "regenerate": "重新生成",
        }.get(act, "调整")
        s = f"我建议{label}"
        if target:
            s += f"「{target}」"
        if reason:
            s += f"——{reason}"
        s += "。要改吗？"
        return s

    return "好的，我来处理。"
