#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 对话路由：多轮对话入口 + 会话取回（含限流）"""
import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.ratelimit import SlidingWindowLimiter
from app.routers.deps import current_user_optional
from app.services import agents as agent_svc
from app.services import analytics as ana
from app.services import conversation as convo_svc
from app.services import itinerary_flow as flow
from app.services.conversation.routing import should_delegate

router = APIRouter(tags=["chat"])

# 限流器（BUG-7）：匿名严、登录宽；阈值可从 .env 调整
_anon_limiter = SlidingWindowLimiter(
    int(os.environ.get("RATE_LIMIT_ANON_PER_MIN", "20")), 60)
_user_limiter = SlidingWindowLimiter(
    int(os.environ.get("RATE_LIMIT_USER_PER_MIN", "60")), 60)


@router.post("/api/chat")
async def chat(request: Request, user=Depends(current_user_optional)):
    """多轮对话入口

    用户说一句 → 返回 AI 回复 + 更新后的画像 + 可能的工具调用。
    AI 可以请求生成行程或提议修改，真正的执行由服务端做。

    ⚠️ 匿名（未登录）会话不落库，刷新即丢。
    ⚠️ 限流（BUG-7）：每次对话真实消耗 GLM 费用，超配额返回 429。
       阈值可用 .env 的 RATE_LIMIT_ANON_PER_MIN / RATE_LIMIT_USER_PER_MIN 调整。
    """
    # 限流（先于任何 LLM 调用）
    limiter = _user_limiter if user else _anon_limiter
    limit_key = user["id"] if user else (
        request.client.host if request.client else "unknown")
    if not limiter.allow(limit_key):
        return JSONResponse({"error": "请求太频繁，请稍后再试"}, status_code=429)

    body = await request.json()
    text = (body.get("text") or "").strip()
    sid = body.get("session_id") or None
    if not text:
        return JSONResponse({"error": "说点什么吧"}, status_code=400)

    uid = user["id"] if user else None

    # 取当前行程（让 AI 看得见右侧）
    # chat 内部会从对应存储（DB / 内存）载入 conv，但也需要单独传给 LLM
    current_itinerary = flow.load_itinerary(sid, uid) if sid else None

    # 找本轮的文旅局智能体（P1 第 2 步）
    # ⚠️ 这里只做「按地区查」+ 容错。要不要交给它由编排层的 _try_delegate 决定。
    # 任何异常都吞掉 —— 智能体是增强功能，挂了不能影响基础对话。
    region_agent = None
    region = should_delegate(text)
    if region:
        try:
            region_agent = agent_svc.find_region_agent(region)
        except Exception:
            region_agent = None

    try:
        conv = convo_svc.chat(sid, text, current_itinerary=current_itinerary,
                              user_id=uid, region_agent=region_agent)
    except Exception as e:
        return JSONResponse({"error": f"对话失败: {e}"}, status_code=500)

    sid = conv.session_id

    # 记录行为事件（登录用户才记）
    ana.track(ana.EV_MESSAGE_SENT, sid, uid,
              turn=conv.turn, text_len=len(text))
    if conv.turn == 1:
        ana.track(ana.EV_SESSION_START, sid, uid)

    result = {
        "session_id": sid,
        "reply": conv.messages[-1]["content"],
        "profile": convo_svc.public_profile(conv.profile),
        "summary": convo_svc.profile_summary(conv.profile),
        "turn": conv.turn,
        "ready": conv.ready,
        "tool_calls": conv.tool_calls,
        "logged_in": bool(uid),
    }

    # 本轮是否由文旅局智能体回答（前端可据此显示来源）
    delegated_to = conv.profile.get("_delegated_to")
    if delegated_to:
        result["delegated_to"] = delegated_to

    # 处理工具调用
    for tc in conv.tool_calls:
        name = tc.get("name")
        args = tc.get("args") or {}

        if name == "generate_itinerary":
            try:
                exclude = flow.regen_exclude(user_text, args, current_itinerary)
                d = flow.generate_itinerary(sid, args.get("hours"),
                                            exclude=exclude, user_id=uid)
                result["itinerary"] = d
                result["action"] = "generate"
                ana.track(ana.EV_ITINERARY_GENERATED, sid, uid,
                          stops_count=len(d.get("stops", [])),
                          motivation=d.get("motivation"),
                          hours=d.get("hours"))
            except Exception as e:
                result["action_error"] = f"生成失败: {e}"

        elif name == "propose_modify_itinerary":
            # 只是提议 → 前端展示确认按钮，等用户点
            result["proposal"] = {
                "action": args.get("action"),
                "target": args.get("target"),
                "reason": args.get("reason"),
            }

    return result


@router.get("/api/session/{session_id}")
def get_session(session_id: str):
    """取回会话（刷新页面后续聊）

    ⚠️ 只读匿名内存会话，不触达数据库会话 —— 无越权面（加固-2 复核记录）。
    """
    conv = convo_svc.load_session(session_id)
    if not conv:
        return JSONResponse({"error": "会话不存在"}, status_code=404)
    return {
        "session_id": conv.session_id,
        "messages": conv.messages,
        "profile": convo_svc.public_profile(conv.profile),
        "summary": convo_svc.profile_summary(conv.profile),
        "turn": conv.turn,
        "ready": conv.ready,
    }
