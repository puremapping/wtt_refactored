#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每轮对话编排：用户说话 → 抽取 → 合并画像 → 回复 → 策略执行 → 存会话

关键设计（每条背后都是实测教训）：
  - **生成回复**与**抽取画像**是两次独立调用。
    实测教训：合成一次调用时，多轮历史会让模型「学样」回自然语言，
    忽略 JSON 格式要求（即使是 glm-4-flash 开了 response_format）。
  - **画像合并在回复生成之前**（BUG-11）：否则回复上下文、强制补调
    参数、兜底回复、数据边界检查读到的都是上一轮画像。
  - **current_itinerary** 让 AI「看得见」右侧行程，用户说「最后那个太远」
    时它知道指哪。
  - **user_id**：为空 = 匿名（会话只存内存，刷新即丢）
"""
import json
import uuid
from datetime import datetime
from typing import Optional

from app.services import cities
from app.services.conversation.models import Conversation
from app.services.conversation.profile import (
    _all_user_text,
    _clean_field_value,
    _has_evidence,
    _FIELD_EVIDENCE,
    _is_ready,
    _merge_profile,
)
from app.services.conversation.prompts import (
    _build_extract_messages,
    _build_reply_messages,
)
from app.services.conversation.policies import (
    _clean_reply,
    _fallback_reply,
    _is_generate_intent,
    _is_supported_destination,
    _sanitize_tool_calls,
)
from app.services.conversation.store import load_session, save_session
from app.services.llm import LLM
from app.services.tools import get_tools


def chat(session_id: Optional[str], user_text: str,
         llm: Optional[LLM] = None,
         current_itinerary: dict = None,
         user_id: str = None,
         region_agent: Optional[object] = None) -> Conversation:
    """处理一轮对话：用户说话 → AI 回复 + 更新画像 + 可能的工具调用

    `region_agent`：本轮的文旅局智能体（已由调用方按地区找好）。
      传了才会尝试接管 —— 编排层不查库，查库是 routers/chat.py 的事。
      接管判定见 `_try_delegate()`：本地引擎有事要干时不接管。
    """
    llm = llm or LLM()

    # 1. 取或建会话
    conv = load_session(session_id, user_id) if session_id else None
    if conv is None:
        conv = Conversation(
            session_id=uuid.uuid4().hex[:12],
            created_at=datetime.now().isoformat(),
        )
    if not conv.created_at:
        conv.created_at = datetime.now().isoformat()

    # 2. 追加用户消息
    conv.messages.append({"role": "user", "content": user_text})
    conv.turn += 1

    # 3. 抽取画像（独立调用，强制 JSON）
    new_profile = {}
    extract_error = None
    try:
        extracted = llm.json_chat(_build_extract_messages(conv), temperature=0.0)
        if isinstance(extracted, dict):
            new_profile = extracted
        else:
            extract_error = f"抽取返回非 dict: {type(extracted).__name__}"
    except Exception as e:
        extract_error = f"{type(e).__name__}: {e}"

    # 4. 合并画像（先做证据校验，拦掉模型瞎补的字段）
    # ⚠️ BUG-11 修复：合并必须发生在回复生成之前 —— 否则回复上下文、
    #    强制补调参数、兜底回复、数据边界检查读到的都是上一轮画像，
    #    用户本轮刚说的话对它们全部不可见（与 v0.6 数据边界时序问题同族）。
    user_text_all = _all_user_text(conv)
    filtered = {}
    for k, v in (new_profile or {}).items():
        if k in _FIELD_EVIDENCE and not _has_evidence(k, user_text_all):
            continue          # 用户没说，拒绝这个字段
        # 清洗：占位词（「未知」「不确定」「无」…）不该进画像
        if isinstance(v, str):
            v = _clean_field_value(v)
            if not v:
                continue
        elif isinstance(v, list):
            v = [x for x in (_clean_field_value(i) for i in v) if x]
            if not v:
                continue
        filtered[k] = v
    conv.profile = _merge_profile(conv.profile, filtered)

    if extract_error:
        conv.profile["_extract_error"] = extract_error
    # 记录轮数（供 ready 判据用；不对外暴露）
    conv.profile["_turns"] = conv.turn

    # 5. 服务端判据（不信 LLM 自报）
    conv.ready = _is_ready(conv.profile)

    # 6. 生成回复（独立调用，带 tools，可能返回 tool_calls）
    reply = ""
    tool_calls = []
    try:
        msg = llm.chat_raw(
            _build_reply_messages(conv, itinerary=current_itinerary),
            temperature=0.6,
            tools=get_tools(has_itinerary=bool(current_itinerary)),
        )
        reply = (msg.content or "").strip().strip('"').strip("'").strip()
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({
                    "name": tc.function.name,
                    "args": args,
                })
    except Exception as e:
        if not reply:
            reply = f"（回复生成异常：{e}）"

    # 清理：模型有时把工具参数当正文吐出来（流式碎片）
    reply = _clean_reply(reply)

    # 服务端校验 tool_calls（防误触发）
    has_itin = bool(current_itinerary)
    _raw_count = len(tool_calls)
    tool_calls = _sanitize_tool_calls(tool_calls, user_text, has_itin)
    # ⚠️ 关键补救：模型本打算调工具（所以没写正文），但服务端把工具拦掉了
    #    → 此刻 reply 和 tool_calls 双空，用户会收到空洞兜底。
    #    正确做法：**重新让模型用文字回答**（去掉 tools 再问一次），
    #    而不是套模板 —— 模板不看用户说了什么，必然答非所问。
    if not reply and not tool_calls and _raw_count > 0:
        try:
            msg2 = llm.chat_raw(
                _build_reply_messages(conv, itinerary=current_itinerary),
                temperature=0.6,
                tools=None,          # ← 不给工具，逼它说话
            )
            reply = _clean_reply((msg2.content or "").strip())
        except Exception:
            pass

    # ⚠️ 数据边界拦截：只有数据覆盖的城市
    # 实测教训：模型会声称「我有上海的数据」并给出北京行程（静默错误）。
    # 光靠 prompt 告知无效，必须服务端硬拦。
    # ⚠️ 画像已在第 4 步合并，conv.profile 里就是本轮最新目的地（含占位词清洗）。
    dest = _clean_field_value(conv.profile.get("destination"))
    blocked = bool(dest) and not _is_supported_destination(dest)

    # ── 文旅局智能体接管（P1 第 2 步）────────────────────────────
    # ⚠️ 先清掉上一轮的接管标记 —— 它是每轮结论，不是会话状态。
    #    不清的话，用户第二轮没提城市时前端还会显示「由北京文旅局回答」，
    #    那是纯泄漏（2026-10-29 实测抓到）。
    conv.profile.pop("_delegated_to", None)
    #
    # 时机在这里是有讲究的：
    #   - 放在 tool_calls 校验之后：本地引擎这轮要排行程时不接管（tool_calls 非空）
    #   - 放在「反向补齐」之前：补齐逻辑只看用户有没有生成意图，与接管无关
    #   - 放在数据边界拦截之前：智能体自己负责说清它的覆盖范围，
    #     不该被本地引擎的「我只有北京数据」话术覆盖掉
    delegated = _try_delegate(conv, user_text, reply, tool_calls,
                              blocked, region_agent)
    reply_source = None
    if delegated is not None:
        reply, tool_calls, reply_source = delegated

    # 反向补齐：用户明确要求生成，但模型没调工具 → 强制补上
    # 实测教训：加了 destination 字段后，模型会优先追问「去哪个城市」
    # 而忽略用户明确的「生成行程」指令。光靠 prompt 纠正不可靠。
    # ⚠️ 若目的地不支持，不能补 —— 否则强行生成北京行程给上海需求（静默错误）
    if (not tool_calls and not has_itin and not blocked
            and _is_generate_intent(user_text)):
        tool_calls = [{
            "name": "generate_itinerary",
            "args": {"hours": conv.profile.get("hours")} if conv.profile.get("hours") else {},
            "forced": True,
        }]
        if reply and "生成行程" not in reply and "排" not in reply:
            reply = f"好，我先按{cities.city_names()[0]}给你排一条，要换城市随时说。"

    # ⚠️ 数据边界拦截：只有数据覆盖的城市
    if blocked:
        tool_calls = [t for t in tool_calls if t["name"] != "generate_itinerary"]
        supported = cities.supported_description()
        if not any(c in reply for c in cities.city_names()):
            reply = (f"我目前只有**{supported}**的景点数据，"
                     f"{dest}还查不了。\n\n"
                     f"要不要先看看这几个城市的安排？或者等我们接入{dest}的数据。")

    if not reply:
        # 模型返回 tool_calls 时 content 常为空 —— 不能直接兜底成「能再多说说吗」
        reply = _fallback_reply(tool_calls, conv)

    conv.messages.append({"role": "assistant", "content": reply})
    # 来源跟着消息走，历史会话载入时才能还原「谁答的」
    if reply_source:
        conv.messages[-1]["source"] = reply_source
    conv.tool_calls = tool_calls          # 供上层执行
    save_session(conv, user_id)
    return conv


# ──────────────────────────────────────────────────────────────
# 文旅局智能体接管
# ──────────────────────────────────────────────────────────────


def _try_delegate(conv: Conversation, user_text: str, reply: str,
                  tool_calls: list, blocked: bool,
                  region_agent) -> Optional[tuple]:
    """让地区智能体接管这轮回复

    返回 (reply, tool_calls)；不该接管返回 None（调用方保持原样）。

    接管的四个前提（全满足才接）：
      1. 有智能体 —— 调用方按地区查好传进来的
      2. 本地引擎这轮没活干 —— tool_calls 空（要排行程就别抢）
      3. 目的地没被本地数据边界拦下 —— 拦下了说明用户问的是平台管不到的城市，
         此时智能体（若有）反而更该回答，所以这条不拦，只记录
      4. 智能体自己答得出来 —— answer() 没降级

    ⚠️ 智能体答不出来（超时/报错/空回）时**不接管**，保留本地引擎的原回复。
       宁可回答得平庸，也不能给用户一句空洞的兜底 —— 那是本产品反复踩过的坑。
    """
    if region_agent is None:
        return None
    if tool_calls:
        return None                      # 本地引擎要排行程/改行程，别抢

    from app.services.conversation.routing import mentioned_region, wants_local_engine

    # 双保险：路由判定在这里再跑一次。
    # 调用方已经判过，但编排层是最后一道闸 —— 用户原话若不含城市（比如
    # 「有什么好吃的」），智能体没有立足点，不接。
    if wants_local_engine(user_text):
        return None
    region = mentioned_region(user_text)
    if not region or region != getattr(region_agent, "region", None):
        return None

    try:
        res = region_agent.answer(
            user_text,
            context={"profile": conv.profile, "turn": conv.turn},
        )
    except Exception:
        return None                      # 智能体炸了，兜回本地回复

    if getattr(res, "degraded", False) or not getattr(res, "text", ""):
        return None                      # 答不出来就别硬塞

    # 接管：回复换成智能体的，工具调用清空（智能体没有行程能力）
    # 画像仍然保留 —— 用户说的话一样进了画像，下一轮本地引擎照常能用
    #
    # ⚠️ 存结构而不是光存名字：界面上要让用户看出来「现在谁在答、是哪个机构的」。
    #    只存名字的话，同名智能体（多个文旅局都叫「文旅助手」）就分不清了。
    conv.profile["_delegated_to"] = {
        "name": getattr(region_agent, "name", "") or "",
        "team": getattr(region_agent, "team_name", "") or "",
        "region": getattr(region_agent, "region", "") or "",
        "kind": getattr(region_agent, "kind", "") or "",
    }

    # ⚠️ 来源要跟着**消息**走，不能只挂在本轮结果上 ——
    #    否则载入历史会话时每条回复都退化成无身份的气泡。
    #    由调用方在 append assistant 消息时取用（见 chat() 末尾）。
    pending_source = dict(conv.profile["_delegated_to"])
    return (res.text.strip(), [], pending_source)
