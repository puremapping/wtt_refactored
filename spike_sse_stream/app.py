#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SSE 端点原型：FastAPI StreamingResponse + 断线检测 + 一次性补发

跟 stream_core.py 配合演示后端三件事：
  1. 业务层 yield dict，SSE 线格式只在这里拼一次
  2. 心跳（防代理空闲超时）与「首字节快发」（防前端误判挂起）
  3. 断线时 asyncio.CancelledError 会打进来 —— 必须能停掉上游 LLM
"""
from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from spike_sse_stream.stream_core import Emitter, FakeLLM, chat_stream

app = FastAPI()

SESSIONS: dict = {}
# ⚠️ 实测踩到的坑（很隐蔽）：同一个路径注册两次 GET，**先注册的先匹配**。
#    我原来把 mode_get 放在 set_mode 前面，结果所有设置请求都打到只读的那个，
#    返回 {"plan":"tool"}（正是默认值，看起来像成功），实际什么都没写。
#    教训：调试开关实现成「读写在同一个端点」，别开两条同路径路由。
_LLM_PLAN = {"plan": "chat", "fail_at": None}


# ══════════════════════════════════════════════════════════════
# SSE 线格式
# ══════════════════════════════════════════════════════════════

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    # nginx 反代必加，否则缓冲导致「流到最后一次性吐出」
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


def sse_frame(ev: dict, event_id: int | None = None) -> bytes:
    eid = f"id: {event_id}\n" if event_id is not None else ""
    payload = json.dumps(ev, ensure_ascii=False)
    return f"{eid}event: {ev['kind']}\ndata: {payload}\n\n".encode("utf-8")


HEARTBEAT = b": ping\n\n"      # 注释行，EventSource 与手写解析都要忽略
HEARTBEAT_S = 3               # 实测：15s 太粗，一旦卡住 grep 日志像「死机」


async def _guarded(ag, emitter: Emitter, drain_first: bool):
    """把一个可能抛异常的异步生成器包成「一定以终止帧结束、且不会再抛」的流。

    ⚠️ 头已发出后不可能改状态码（HTTP 协议限制）。所以错误只能靠
       终止帧（event: error）传达，前端必须实现这条分支。
    """
    try:
        async for ev in ag:
            yield sse_frame(ev, ev.get("seq"))
        # 兜底：生成器被提前 return（没走 done）也要给终止帧
        if not emitter._buf or emitter._buf[-1]["kind"] not in ("done", "error"):
            yield sse_frame({"kind": "error", "message": "上游无终止帧",
                             "code": "NoTerminalEvent"})
    except asyncio.CancelledError:
        raise                                    # 断线：交给 ASGI 层
    except Exception as e:                       # noqa: BLE001
        yield sse_frame({"kind": "error", "message": str(e),
                         "code": type(e).__name__})


@app.post("/api/chat/stream")
async def chat_stream_endpoint(request: Request):
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        # 参数错在「头发出前」→ 正常 400，前端走 fetch 的 !r.ok 分支
        return JSONResponse({"error": "说点什么吧"}, status_code=400)

    # ——— 断线1：只在头发出前能拒绝 ———
    last_id = request.headers.get("Last-Event-ID")

    queue: asyncio.Queue = asyncio.Queue()
    emitter = Emitter(sink=queue.put_nowait)
    llm = FakeLLM(plan=_LLM_PLAN["plan"], fail_at=_LLM_PLAN["fail_at"])

    task: asyncio.Task | None = None

    async def producer():
        async for ev in chat_stream(text, body.get("session_id"), llm,
                                    emitter, SESSIONS):
            pass                             # 事件全部经 emitter.sink 入队

    async def gen():
        nonlocal task
        # ⚠️ 立刻吐一个 hello，让 fetch 的 response 头尽快返回、
        #    也让前端能区分「连接建立」与「模型还没开始」
        yield sse_frame({"kind": "hello", "seq": 0})
        if last_id:
            for ev in emitter.replay_from(int(last_id)):
                yield sse_frame(ev, ev.get("seq"))

        task = asyncio.create_task(producer())

        # ⚠️ 实测踩到的坑：这个 loop 一抛异常，事件就全没了、前端只看到 hello。
        #    生成器里**任何**未捕获异常都会直接终止流（头已发出，无法改状态码）。
        #    → queue.get() 的 call_later / wait_for 在这里是多余的复杂度，
        #      心跳用固定周期注入更稳（见下方 background heartbeat）。
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_S)
                except asyncio.TimeoutError:
                    yield HEARTBEAT
                    continue
                yield sse_frame(ev, ev.get("seq"))
                if ev["kind"] in ("done", "error"):
                    return
        finally:
            if task and not task.done():
                task.cancel()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers=SSE_HEADERS)


@app.get("/api/chat")
async def chat_sync(request: Request):
    """同步接口用同一个生成器「抽干」事件 —— 逻辑零分叉。"""
    text = request.query_params.get("text", "")
    llm = FakeLLM(plan="chat", chunk_delay=0)
    final = None
    err = None
    async for ev in chat_stream(text, request.query_params.get("session_id"),
                                llm, Emitter(), SESSIONS):
        if ev["kind"] == "done":
            final = ev["result"]
        elif ev["kind"] == "error":
            err = ev
    if err:
        return JSONResponse({"error": err["message"]}, status_code=500)
    return final


@app.get("/api/_mode")
def set_mode(plan: str | None = None, fail_at: str | None = None):
    """读写同一端点：不带 plan 就是查询。"""
    if plan is not None:
        _LLM_PLAN["plan"] = plan
        _LLM_PLAN["fail_at"] = fail_at or None
    return dict(_LLM_PLAN)


@app.get("/spike", response_class=HTMLResponse)
async def page():
    from pathlib import Path
    p = Path(__file__).parent / "spike_client.html"
    return HTMLResponse(p.read_text(encoding="utf-8"))
