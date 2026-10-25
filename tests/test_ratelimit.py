"""BUG-7 限流器单测"""
from app.core.ratelimit import SlidingWindowLimiter


def test_allows_within_quota():
    lim = SlidingWindowLimiter(3, 60)
    assert lim.allow("ip1")
    assert lim.allow("ip1")
    assert lim.allow("ip1")


def test_blocks_over_quota():
    lim = SlidingWindowLimiter(3, 60)
    for _ in range(3):
        assert lim.allow("ip1")
    assert not lim.allow("ip1")
    assert not lim.allow("ip1")     # 持续拒绝


def test_keys_independent():
    lim = SlidingWindowLimiter(1, 60)
    assert lim.allow("ip1")
    assert not lim.allow("ip1")
    assert lim.allow("ip2")         # 别的 key 不受影响


def test_window_slides(monkeypatch):
    import time
    lim = SlidingWindowLimiter(1, 60)
    assert lim.allow("ip1")
    assert not lim.allow("ip1")
    # 时间越过窗口 → 重新放行
    real_mono = time.monotonic
    monkeypatch.setattr(time, "monotonic",
                        lambda: real_mono() + 61)
    assert lim.allow("ip1")


def test_prune_keeps_memory_bounded():
    lim = SlidingWindowLimiter(1, 60)
    for i in range(5000):
        lim.allow(f"ip{i}")          # 每个 key 用满后不再来
    # 再触发一轮 prune（窗口过后）
    import time as _t
    real_mono = _t.monotonic
    _t.monotonic = lambda: real_mono() + 61
    try:
        lim.allow("fresh")
    finally:
        _t.monotonic = real_mono
    assert len(lim._hits) < 5000     # 过期 key 已被清
