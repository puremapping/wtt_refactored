#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同步生成器 → 异步流 的桥：让现有**同步** chat() 不改成 async 也能流式。

为什么需要这个：
  现有 orchestrator.chat() 是同步函数，内部 LLM 客户端也是同步的（openai.OpenAI）。
  如果为了流式把整条链改成 async，就要同步改 LLM 封装 + 所有测试里的 FakeLLM，
  而项目现有测试用 monkeypatch(orch, "LLM", lambda: fake) 注入假客户端 ——
  签名一变，假货全废。

方案：写一个同步生成器 chat_sync_events()，内部同步批量跑、只在关键节点 yield 事件；
  由 asyncio.to_thread 推给异步 SSE，中间用一个线程安全队列交接。
  好处：现有 chat() 可以原样保留（内部调用同一个 chat_sync_events 然后「抽干」它），
        测试一行都不用改。

⚠️ 坑（这是本方案唯一真正的坑）：
  anyio 的线程池任务**默认不可取消**。客户端断了，SSE 协程被取消，但
  线程里的同步生成器会继续跑到下一次 yield，甚至跑完 —— 继续烧 LLM 的钱。
  规避：.close() 显式停止流（见 SyncEventBridge.stop），而不是依赖 cancel。
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Iterator, Optional


class _Stop:
    """哨兵：告诉消费端「同步侧结束了」"""


STOP = _Stop()


class SyncEventBridge:
    """在线程里跑同步生成器，在主协程里按需取事件。

    时序：
       主协程:  await bridge.get()  ──▶  queue.get(timeout=heartbeat)
       工作线程: for ev in gen: queue.put(ev)
                 finally: queue.put(STOP)
    """

    def __init__(self, gen: Iterator[dict], maxsize: int = 256):
        self._gen = gen
        self._q: queue.Queue = queue.Queue(maxsize=maxsize)
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="chat-sync-gen")
        self._thread.start()

    def _run(self):
        try:
            for ev in self._gen:
                if self._stopped.is_set():
                    break                    # 客户端已走，尽快放手
                # ⚠️ put 用超时轮询，否则队列满 + 没人消费 = 永久阻塞
                while not self._stopped.is_set():
                    try:
                        self._q.put(ev, timeout=0.2)
                        break
                    except queue.Full:
                        continue
        except Exception as e:               # noqa: BLE001 —— 必须转成事件
            self._q.put({"kind": "error", "message": str(e),
                         "code": type(e).__name__})
        finally:
            self._q.put(STOP)
            try:
                self._gen.close()
            except Exception:
                pass

    def stop(self):
        """客户端断开时调用。**唯一可靠的止损开关**。"""
        self._stopped.set()

    def get(self, timeout: float) -> Optional[dict]:
        """拿一条事件；超时返回 None（调用方发心跳）；流结束返回 None 并置空"""
        try:
            item = self._q.get(timeout=timeout)
        except queue.Empty:
            return None
        if item is STOP:
            return None
        return item

    @property
    def finished(self) -> bool:
        return not self._thread.is_alive() and self._q.empty()


# ══════════════════════════════════════════════════════════════
# 用法示例（FastAPI 端）
# ══════════════════════════════════════════════════════════════
#
# @app.post("/api/chat/stream")
# async def api_chat_stream(payload: ChatIn, user=Depends(current_user_optional)):
#     def gen():
#         yield from chat_sync_events(payload.text, payload.session_id, user_id=...)
#
#     bridge = SyncEventBridge(gen())
#     async def body():
#         try:
#             while True:
#                 ev = await asyncio.to_thread(bridge.get, 15)   # ← 15s 心跳
#                 if ev is None:
#                     if bridge.finished:
#                         yield sse_error("no terminal event")
#                         return
#                     yield b": ping\n\n"
#                     continue
#                 yield sse(ev)
#                 if ev["kind"] in ("done", "error"):
#                     return
#         finally:
#             bridge.stop()      # ⚠️ 取消线程池任务不会停同步生成器，必须显式停
#
#     return StreamingResponse(body(), media_type="text/event-stream", headers=SSE_HEADERS)
