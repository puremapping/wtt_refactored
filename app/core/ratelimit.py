#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""进程内滑动窗口限流（BUG-7）

背景：/api/chat 匿名可调且每次真实消耗 GLM 费用，挂到局域网/公网
（演示场景）时可被无限狂刷。纯标准库实现，不引 redis 等新依赖。

单进程内存限流的边界：多 worker 部署时各进程独立计数（当前单进程
uvicorn，够用）；重启即清零（对刷量防护无影响）。
"""
import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """滑动窗口限流器：window_seconds 内最多 max_events 次"""

    def __init__(self, max_events: int, window_seconds: float):
        self.max_events = max_events
        self.window = window_seconds
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_prune = time.monotonic()

    def allow(self, key: str) -> bool:
        """放行一次请求。超过配额返回 False。"""
        now = time.monotonic()
        with self._lock:
            if now - self._last_prune > self.window:
                self._prune(now)
                self._last_prune = now
            q = self._hits[key]
            cutoff = now - self.window
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self.max_events:
                return False
            q.append(now)
            return True

    def _prune(self, now):
        """内存保洁：清掉窗口内无记录的 key（防 IP 维度无限膨胀）"""
        cutoff = now - self.window
        dead = [k for k, q in self._hits.items()
                if not q or q[-1] <= cutoff]
        for k in dead:
            del self._hits[k]
