"""RPS 滑动窗口限流器（进程内）。"""
import time
from collections import deque


class SlidingWindow:
    """1 秒滑动窗口。limit<=0 表示不限。"""

    def __init__(self, window_sec: float = 1.0):
        self.window = window_sec
        self.ts: deque[float] = deque()

    def allow(self, limit: int) -> bool:
        now = time.monotonic()
        while self.ts and self.ts[0] <= now - self.window:
            self.ts.popleft()
        if limit > 0 and len(self.ts) >= limit:
            return False
        self.ts.append(now)
        return True

    def count(self) -> int:
        now = time.monotonic()
        while self.ts and self.ts[0] <= now - self.window:
            self.ts.popleft()
        return len(self.ts)


class RateLimiter:
    """key 级 + 全局 RPS。"""

    def __init__(self):
        self.global_window = SlidingWindow(1.0)
        self.key_windows: dict[int, SlidingWindow] = {}

    def allow_global(self, limit: int) -> bool:
        return self.global_window.allow(limit)

    def allow_key(self, key_id: int, limit: int) -> bool:
        w = self.key_windows.get(key_id)
        if w is None:
            w = SlidingWindow(1.0)
            self.key_windows[key_id] = w
        return w.allow(limit)

    def recent_qps_60s(self) -> int:
        """实时 QPS：最近 60 秒滑动窗口请求数（供仪表盘）。"""
        return self.global_window.count() if False else _qps_60()


_qps_window: deque[float] = deque()


def record_request_hit():
    _qps_window.append(time.monotonic())


def _qps_60() -> int:
    now = time.monotonic()
    while _qps_window and _qps_window[0] <= now - 60:
        _qps_window.popleft()
    return len(_qps_window)
