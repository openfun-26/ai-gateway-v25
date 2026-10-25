"""进程内 TTL 缓存 + 全局缓存命中率统计。"""
import time
from typing import Any, Optional


class TTLCache:
    def __init__(self):
        self._store: dict[str, tuple[float, Any]] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if item and item[0] > time.monotonic():
            self.hits += 1
            return item[1]
        if item:
            self._store.pop(key, None)
        self.misses += 1
        return None

    def set(self, key: str, value: Any, ttl: float = 15.0):
        self._store[key] = (time.monotonic() + ttl, value)

    def invalidate(self, prefix: str | None = None):
        if prefix is None:
            self._store.clear()
            return
        for k in [k for k in self._store if k.startswith(prefix)]:
            self._store.pop(k, None)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


cache = TTLCache()
