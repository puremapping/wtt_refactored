#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同步 chat() → 同步生成器 的重构模板（对应项目里真实的 orchestrator.chat）

规则只有三条，照抄即可：
  ① 原函数体一行不删，只是把「最终 return conv」拆成
     「每完成一步 yield 一个事件」+「最后 yield done(result=...)」
  ② 同步接口 chat() 保留为 **消费器**：`for ev in chat_events(...)` 抽干后取 done
     → 逻辑只有一份，两套接口不可能分叉
  ③ LLM 调用点加 on_token 回调（默认 None），同步调用方不传 = 行为完全不变
     → 现有 FakeLLM 只要多接受一个 on_token kwarg 就能继续用

为什么不用「改成 async def + async for」：
  现有 chat() 是纯同步的（openai.OpenAI 同步客户端 + 同步 SQLite）。
  async 化会连带改 LLM 封装和全部测试的假货；而这个功能的实时性要求
  只到「token 级」几百毫秒，同步线程 + 队列完全够。
"""
from __future__ import annotations

from typing import Iterator, Optional

from spike_sse_stream.stream_core import FakeLLM  # 只借用假 LLM


# ══════════════════════════════════════════════════════════════
# 同步生成器（重构后的 chat）
# ══════════════════════════════════════════════════════════════

def chat_events_sync(user_text: str,
                     session_id: Optional[str] = None,
                     llm: Optional[FakeLLM] = None,
                     current_itinerary: dict = None,
                     user_id: str = None,
                     region_agent=None) -> Iterator[dict]:
    """yield 事件；最后一条一定是 done 或 error。"""
    llm = llm or FakeLLM()

    try:
        # ── 1. 取或建会话（原样）──
        sid = session_id or "sess-new"

        # ── 2. 抽取画像 ──
        yield {"kind": "step", "name": "extract", "status": "start",
               "label": "理解你的想法"}

        def _on_extract_token(t):
            pass                       # 同步生成器里没法「中途 yield」，攒起来

        extracted = llm.json_chat([], on_token=_on_extract_token)
        # ⚠️ 注意这个限制：真·逐字流式只有异步生成器能做。
        #    同步生成器只能在「一次 LLM 调用结束」处 yield 一个事件，
        #    所以抽取这一步是「step start → step done」，不吐中间 token。
        #    够用：抽取本来就不该给用户看原文，短视频式的字面流是花架子。
        yield {"kind": "step", "name": "extract", "status": "done",
               "detail": "字段：" + " · ".join(extracted.keys()),
               "fields": list(extracted.keys())}
        yield {"kind": "profile", "profile": extracted, "ready": True}

        # ── 3. 生成回复（这里要 token 级流式）──
        yield {"kind": "step", "name": "reply", "status": "start",
               "label": "组织回复"}

        buf: list[str] = []

        def _on_token(t):
            buf.append(t)              # 同步回调：只能攒

        msg = llm.chat_raw([], tools=[{"x": 1}], on_token=_on_token)
        reply = (msg.content or "").strip()

        # ⚠️ 关键限制：同步生成器**不能**在 LLM 调用内部 yield。
        #    想让正文逐字到浏览器，必须用 async 生成器 + async LLM（见 stream_core.py）。
        #    折中方案（本项目建议）：同步生成器把攒好的正文**一次性**作为
        #    「正文块」事件发出，前端仍做打字机动画。收益：面板/步骤是真实时，
        #    正文是「整段到达 + 动画播放」。要真 token 流，就必须把 LLM 层
        #    改成 async（只改 llm.py 一个文件，编排逻辑不动）。
        if reply:
            yield {"kind": "token", "target": "reply", "text": reply,
                   "whole": True}      # whole=True 告诉前端「这是整段，不是碎片」

        tool_calls = []
        for tc in (getattr(msg, "tool_calls", None) or []):
            tool_calls.append({"name": tc.function.name, "args": {}})

        yield {"kind": "step", "name": "reply", "status": "done",
               "detail": "无正文（模型走了工具）" if not reply else f"{len(reply)} 字"}

        # ── 4. 工具执行 ──
        for i, tc in enumerate(tool_calls):
            yield {"kind": "tool", "index": i, "name": tc["name"],
                   "args": tc["args"], "status": "running"}
            # 真实现：flow.generate_itinerary(...)  ← 同步阻塞，本来就在线程里
            yield {"kind": "tool", "index": i, "name": tc["name"],
                   "args": tc["args"], "status": "ok", "ms": 500}

        if not reply and tool_calls:
            msg2 = llm.chat_raw([], tools=None)     # 逼它说话
            reply = (msg2.content or "").strip()
        if not reply:
            reply = "嗯，我记下了。"

        # ── 5. 收尾：done 面与老接口**同构** ──
        yield {"kind": "done", "result": {
            "session_id": sid, "reply": reply, "profile": extracted,
            "turn": 2, "ready": True, "tool_calls": tool_calls,
        }}
    except Exception as e:                       # noqa: BLE001
        yield {"kind": "error", "message": str(e), "code": type(e).__name__}


# ══════════════════════════════════════════════════════════════
# 同步接口 = 消费器（这就是 chat() 的新实现，签名对外不变）
# ══════════════════════════════════════════════════════════════

class _Conv:                    # 占位：真实里是 Conversation dataclass
    def __init__(self, result):
        self.session_id = result["session_id"]
        self.tool_calls = result["tool_calls"]
        self.messages = [{"role": "assistant", "content": result["reply"]}]
        self.profile = result["profile"]
        self.turn = result["turn"]
        self.ready = result["ready"]


def chat(session_id, user_text, llm=None, current_itinerary=None,
         user_id=None, region_agent=None):
    """对外签名与行为**完全不变**。内部抽干同一份事件流。"""
    result = None
    for ev in chat_events_sync(user_text, session_id, llm=llm,
                               current_itinerary=current_itinerary,
                               user_id=user_id, region_agent=region_agent):
        if ev["kind"] == "done":
            result = ev["result"]
        elif ev["kind"] == "error":
            # ⚠️ 老接口错误语义是「抛异常」，路由层包成 500。保持这一点，
            #    否则现有 routers/chat.py 的 try/except 再也接不到错误。
            raise RuntimeError(ev["message"])
    return _Conv(result)


if __name__ == "__main__":
    print("sync 接口 →", chat(None, "想去北京").messages[-1]["content"][:20])
    print("事件流：")
    for ev in chat_events_sync("想去北京"):
        print("  ", ev["kind"], ev.get("status") or ev.get("target") or "")
