#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""流式对话原型：同步 chat() → 生成器 chat_stream() 的重构模板

设计目标（三条硬约束）：
  1. **不复制业务逻辑**。同步路径 chat() 保留为 chat_stream() 的消费器，
     逻辑只有一份，两套接口天然不分叉。
  2. **事件在设计层扁平**。进程内 yield 的是 dict 事件，序列化成 bytes 只在
     ASGI 边界做一次（见 app.py 的 _encode），业务层不关心 SSE 线格式。
  3. **最后一帧自描述**。done 事件携带与老 /api/chat 完全同构的 result，
     前端可以「流式只用于过程展示，最终态照旧靠 done」。

跑法：.venv/Scripts/python.exe -m uvicorn spike_sse_stream.app:app --port 8077
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, AsyncIterator, Dict, Iterable, Iterator, Optional

# ══════════════════════════════════════════════════════════════
# 一、事件总线：把「进度」和「结果」解耦
# ══════════════════════════════════════════════════════════════

MILESTONE_STEPS = {"extract", "reply", "tools", "itinerary"}


class Emitter:
    """一次请求的事件出口。

    - emit() 非阻塞：无订阅者时静默丢弃（同步调用方白拿一个空对象）
    - 环形缓冲保留最后 N 条：SSE 断线重连时补发，不用重跑 LLM
    """

    def __init__(self, sink=None, cap: int = 512):
        self._sink = sink
        self._buf: list[dict] = []
        self.cap = cap
        self.seq = 0
        self._t0 = time.monotonic()

    def emit(self, kind: str, **data: Any) -> None:
        # ⚠️ 实测踩到的坑：`emit("decision", kind=d["kind"])` —— 业务字段名和
        #    签名参数撞车 → TypeError: got multiple values for argument 'kind'。
        #    这个异常被外层兜底吞成 error 帧，面板上只显示「出错了」，
        #    日志里也看不出是**发事件的那一行**炸的（堆栈指向外层 except）。
        #    规避：事件类型用位置参数，payload 字段禁用同名键。
        if "kind" in data:
            raise ValueError("payload 字段不能用 'kind'（与事件类型冲突）")
        self.seq += 1
        ev = {"kind": kind, "seq": self.seq,
              "t": round((time.monotonic() - self._t0) * 1000), **data}
        self._buf.append(ev)
        if len(self._buf) > self.cap:
            del self._buf[0]
        if self._sink is not None:
            self._sink(ev)

    def replay_from(self, seq: int) -> list[dict]:
        return [e for e in self._buf if e["seq"] > seq]


# ══════════════════════════════════════════════════════════════
# 二、假 LLM：真碎片、真延迟，能复现「转圈」和「中途中止」
# ══════════════════════════════════════════════════════════════

class FakeMsg:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Fn:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _TC:
    def __init__(self, name, arguments):
        self.function = _Fn(name, arguments)


class FakeLLM:
    """故意做成「慢 + 会抛」的可控替身。

    ⚠️ 真实 GLM 实测（spike_openai_tools.py）：工具意图那一次 content 是空的，
       正文一个字都不给。所以「工具轮没有正文可流」是常态，不是 bug。
    """

    def __init__(self, plan="chat", fail_at=None, chunk_delay=0.03):
        self.plan = plan
        self.fail_at = fail_at
        self._forked = False
        self.chunk_delay = chunk_delay
        self.json_calls = 0
        self.raw_calls = 0

    # ── 同步版（给现有 chat() 用，接口与现 LLM.chat_raw 同签名 + on_token）──
    def chat_raw(self, messages, temperature=0.3, model=None, tools=None,
                 tool_choice="auto", on_token=None):
        use_tool = self.plan == "tool" and not self._forked
        self._forked = True
        time.sleep(0.02)                      # 同步阻塞，线程里跑
        if use_tool and tools:
            return FakeMsg("", [_TC("generate_itinerary", '{"hours": 4}')])
        text = "好，我先按北京给你排一条。" if use_tool else ("后海周边人少，傍晚光线好；" * 4)
        if on_token:
            for ch in text:
                on_token(ch)
                time.sleep(0.002)
        return FakeMsg(text)

    def json_chat(self, messages, temperature=0.0, on_token=None):
        time.sleep(0.05)
        if on_token:
            on_token('{"destination": "北京", "primary": "散心"}')
        return {"destination": "北京", "primary": "散心", "hours": 4}

    async def json_chat_async(self, messages, on_token=None,
                              temperature=0.0):
        self.json_calls += 1
        await asyncio.sleep(0.4)
        if self.fail_at == "extract":
            raise RuntimeError("抽取调用超时（模拟）")
        if on_token:
            await on_token('{"destination": "北京", "primary": "散心"}')
        return {"destination": "北京", "primary": "散心", "hours": 4}

    async def chat_raw_async(self, messages, on_token=None, tools=None,
                             temperature=0.6):
        self.raw_calls += 1
        await asyncio.sleep(0.3)
        if self.fail_at == "reply":
            raise RuntimeError("回复生成 502（模拟上游）")

        # 工具轮：第一次调用走工具，第二次（去掉 tools 的兜底）给正文
        use_tool = self.plan == "tool" and not self._forked
        self._forked = True
        if use_tool:
            # 工具意图：正文为空（与真实 GLM 一致）
            if tools:
                return FakeMsg("", [_TC("generate_itinerary", '{"hours": 4}')])
            return FakeMsg("好，我先按北京给你排一条。")

        text = ("后海周边人少，傍晚光线好；" * 4)
        if on_token:
            for i, ch in enumerate(text):
                await on_token(ch)
                if i == 8 and self.fail_at == "midway":
                    raise RuntimeError("上游在第 9 个 token 后断开（模拟）")
                await asyncio.sleep(self.chunk_delay)
        return FakeMsg(text)


# ══════════════════════════════════════════════════════════════
# 三、核心：同步 chat() 变成 chat_stream() 的生成器
# ══════════════════════════════════════════════════════════════

def _public(state: dict) -> dict:
    """把内部状态压成对外 result —— 形状必须与老 /api/chat 完全一致"""
    return {
        "session_id": state["session_id"],
        "reply": state["reply"],
        "profile": state["profile"],
        "turn": state["turn"],
        "ready": state["ready"],
        "tool_calls": state["tool_calls"],
        "action": state.get("action"),
        "itinerary": state.get("itinerary"),
        "decision": state.get("decision"),
    }


async def chat_events(user_text: str, session_id: Optional[str],
                      llm: FakeLLM,
                      emitter: Emitter,
                      store: dict) -> AsyncIterator[dict]:
    """一轮对话，边跑边出事件。yield 的最后一条一定是 done 或 error。

    移植要点（对照现有 orchestrator.chat 的 8 步）：
      第 3 步抽取  → emitter.emit("step", name="extract") + on_token
      第 4/5 步合并/判据 → emit("profile", ...)
      第 6 步回复  → emit("step", name="reply") + on_token 流正文
      第 6.5 步工具 → emit("tool", ...) 结构化，不混进正文
      末步存会话   → emit("done", result=...)
    """
    t_begin = time.monotonic()
    sid = session_id or uuid.uuid4().hex[:12]
    state = {
        "session_id": sid, "profile": {}, "turn": 1,
        "reply": "", "ready": False, "tool_calls": [],
    }

    try:
        # ── 阶段 1：抽取画像 ──
        emitter.emit("step", name="extract", status="start",
                     label="理解你的想法")
        routed = "本地引擎"
        emitter.emit("route", engine="local", reason="未命中地区智能体",
                     label="平台助手")

        async def _extract_token(t):
            emitter.emit("token", target="reasoning", text=t)

        extracted = await llm.json_chat_async([], on_token=_extract_token)
        state["profile"] = {k: v for k, v in extracted.items()}
        emitter.emit("step", name="extract", status="done",
                     detail="命中 3 个字段",
                     fields=list(extracted.keys()))
        emitter.emit("profile", profile=state["profile"], ready=True)
        state["ready"] = True

        # ── 阶段 2：生成回复（正文流） ──
        emitter.emit("step", name="reply", status="start",
                     label="组织回复", engine=routed)

        async def _reply_token(t):
            emitter.emit("token", target="reply", text=t)

        msg = await llm.chat_raw_async([], on_token=_reply_token,
                                       tools=[{"x": 1}])
        reply = (msg.content or "").strip().strip('"').strip("'")

        blocked = None
        tool_calls = []
        for tc in (getattr(msg, "tool_calls", None) or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append({"name": tc.function.name, "args": args})
        state["tool_calls"] = tool_calls

        # ⚠️ 关键：工具轮正文为空 → 前端正文区必须能「空着结束」，
        #    不能一直转圈等 token。这里立刻发 step done 把状态说清楚。
        emitter.emit("step", name="reply", status="done",
                     detail="无正文（模型走了工具）" if not reply
                     else f"{len(reply)} 字")

        # ── 阶段 3：工具执行（结构化事件，带耗时） ──
        if tool_calls:
            emitter.emit("step", name="tools", status="start",
                         label="调用工具")
            for i, tc in enumerate(tool_calls):
                emitter.emit("tool", index=i, name=tc["name"],
                             args=tc["args"], status="running")
                t1 = time.monotonic()
                await asyncio.sleep(0.5)          # 真实里是 flow.generate_itinerary
                emitter.emit("tool", index=i, name=tc["name"],
                             args=tc["args"], status="ok",
                             ms=int((time.monotonic() - t1) * 1000))
            state["action"] = "generate"
            state["itinerary"] = {"stops": [{"name": "后海"}], "hours": 4}
            emitter.emit("step", name="tools", status="done",
                         detail=f"{len(tool_calls)} 个工具")

        if not reply and tool_calls:
            # 老逻辑的第 149 行兜底：模型没写正文 → 再问一次，逼它说话
            msg2 = await llm.chat_raw_async([], tools=None)
            reply = (msg2.content or "").strip()
        if not reply:
            reply = "嗯，我记下了。"

        # ── 治理决策：老接口里这些是隐式的（拦掉工具/改写话术），
        #    流式下必须显式 emit，否则用户看不懂「为什么没按我说的做」。
        state["decision"] = []
        if tool_calls and not msg.content:
            state["decision"].append({
                "kind": "tool_no_text",
                "label": "模型只调工具没写正文，正文由兜底二次调用生成",
            })
        if blocked:
            state["decision"].append({"kind": "boundary",
                                      "label": f"{blocked}不在数据覆盖范围"})
        if state["decision"]:
            for d in state["decision"]:
                emitter.emit("decision", type=d["kind"], label=d["label"])

        state["reply"] = reply
        state["turn"] = 2

        # ── 收尾：done 面与老接口同构 ──
        store[sid] = state            # 真实里是 save_session(conv, user_id)
        emitter.emit("done", result=_public(state),
                     total_ms=int((time.monotonic() - t_begin) * 1000))

    except asyncio.CancelledError:
        # ⚠️ 客户端断开：不要当成错误吞掉，也不要再 emit（管道已断）。
        #    真实系统在这里应做「半成品落盘」或直接丢弃。
        raise
    except Exception as e:  # noqa: BLE001 —— 兜底必须存在，否则前端永远转圈
        emitter.emit("error", message=str(e),
                     code=type(e).__name__,
                     recoverable=True)


async def chat_stream(user_text: str, session_id: Optional[str],
                      llm: FakeLLM, emitter: Emitter, store: dict):
    """包装：把 emitter 里的事件当流吐出去。

    ⚠️ 坑（本 spike 实测）：`async def` + 内部只有 `yield` 才产生异步生成器。
       chat_events() 是纯 async 协程（事件走 sink），要**显式**把它的事件
       转成流 —— 否则调用方 await 到的是 coroutine，`async for` 直接 TypeError。
    """
    task = asyncio.create_task(chat_events(user_text, session_id,
                                           llm, emitter, store))
    seen = 0
    try:
        while True:
            buf = emitter._buf
            while seen < len(buf):
                yield buf[seen]
                seen += 1
            if task.done():
                # 补掉done之后可能还排队的最后一帧
                for ev in emitter._buf[seen:]:
                    yield ev
                    seen += 1
                task.result()          # 让内部异常正常抛出
                return
            await asyncio.sleep(0.01)
    finally:
        if not task.done():
            task.cancel()
