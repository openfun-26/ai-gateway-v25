"""进程内运行时状态：渠道并发/今日统计/熔断器、模型 QPS、告警缓冲。"""
import time
from collections import deque


class ChannelRuntime:
    __slots__ = ("concurrency", "today_requests", "today_failures", "lat_ema",
                 "results", "cooldown_until", "circuit_state", "circuit_opened_at")

    def __init__(self):
        self.concurrency = 0
        self.today_requests = 0
        self.today_failures = 0
        self.lat_ema = 0.0          # 平均耗时指数移动平均
        self.results: deque[tuple[float, bool]] = deque()  # (ts, ok) 熔断窗口
        self.cooldown_until = 0.0
        self.circuit_state = "closed"   # closed / open
        self.circuit_opened_at = 0.0

    def record(self, ok: bool, latency_ms: float, window_sec: int):
        now = time.monotonic()
        self.results.append((now, ok))
        while self.results and self.results[0][0] <= now - window_sec:
            self.results.popleft()
        self.lat_ema = round(self.lat_ema * 0.7 + latency_ms * 0.3, 1) if self.lat_ema else latency_ms

    def error_rate(self) -> float:
        if not self.results:
            return 0.0
        fails = sum(1 for _, ok in self.results if not ok)
        return fails / len(self.results) * 100.0

    def in_cooldown(self) -> bool:
        return time.monotonic() < self.cooldown_until

    def to_row(self) -> dict:
        return {
            "current_concurrency": self.concurrency,
            "today_requests": self.today_requests,
            "today_failures": self.today_failures,
            "avg_latency_ms": self.lat_ema,
            "circuit_state": self.circuit_state,
            "success_rate": round(100 - self.error_rate(), 2) if self.results else 100.0,
        }


class AppState:
    def __init__(self):
        self.channels: dict[int, ChannelRuntime] = {}
        self.model_qps: dict[str, deque] = {}   # "alias或model" -> 60s 窗口时间戳
        self.alerts: deque[dict] = deque(maxlen=20)
        self.quota_alerted: set[int] = set()     # 已发过额度告警的 key id
        self.model_fail_until: dict[tuple[int, str], float] = {}  # (渠道,模型)级失败冷却
        self.started_at = time.time()

    # ---- 渠道运行时 ----
    def ch(self, channel_id: int) -> ChannelRuntime:
        rt = self.channels.get(channel_id)
        if rt is None:
            rt = ChannelRuntime()
            self.channels[channel_id] = rt
        return rt

    def drop_channel(self, channel_id: int):
        self.channels.pop(channel_id, None)

    # ---- 模型 QPS ----
    def model_hit(self, model: str):
        q = self.model_qps.get(model)
        if q is None:
            q = deque()
            self.model_qps[model] = q
        now = time.monotonic()
        q.append(now)
        while q and q[0] <= now - 60:
            q.popleft()

    def cooldown_remaining(self) -> int:
        """所有渠道冷却的最大剩余秒数（无可用渠道时给用户恢复预期）。"""
        now = time.monotonic()
        rem = [rt.cooldown_until - now for rt in self.channels.values() if rt.cooldown_until > now]
        return int(max(rem)) + 1 if rem else 0

    # ---- 模型级失败冷却：{(channel_id, upstream_model): 恢复时间戳} ----
    # 上游明确报「模型不可用」时只冷却该 (渠道,模型) 组合，不影响渠道上其他模型
    def mark_model_fail(self, channel_id: int, upstream_model: str, sec: int = 60):
        if upstream_model:
            self.model_fail_until[(channel_id, upstream_model)] = time.monotonic() + sec

    def model_in_fail(self, channel_id: int, upstream_model: str) -> bool:
        t = self.model_fail_until.get((channel_id, upstream_model))
        if t is None:
            return False
        if t <= time.monotonic():
            self.model_fail_until.pop((channel_id, upstream_model), None)
            return False
        return True

    def model_qps_value(self, model: str) -> int:
        q = self.model_qps.get(model)
        if not q:
            return 0
        now = time.monotonic()
        while q and q[0] <= now - 60:
            q.popleft()
        return len(q)

    # ---- 告警 ----
    def push_alert(self, atype: str, message: str):
        from .config import now_local_str
        self.alerts.appendleft({"ts": now_local_str(), "type": atype, "message": message})

    def clear_alerts(self):
        self.alerts.clear()

    # ---- 熔断检查（返回 True 表示已熔断应拒绝）----
    def circuit_check(self, channel_id: int, err_threshold: float, freeze_sec: int) -> bool:
        rt = self.ch(channel_id)
        if rt.circuit_state == "open":
            if time.monotonic() - rt.circuit_opened_at >= freeze_sec:
                # 半开：放行，窗口重置
                rt.circuit_state = "closed"
                rt.results.clear()
                return False
            return True
        if len(rt.results) >= 5 and rt.error_rate() >= err_threshold:
            rt.circuit_state = "open"
            rt.circuit_opened_at = time.monotonic()
            self.push_alert("circuit", f"渠道 #{channel_id} 错误率 {rt.error_rate():.0f}% 超阈值，熔断 {freeze_sec}s")
            return True
        return False

    def reset_circuits(self):
        for rt in self.channels.values():
            rt.circuit_state = "closed"
            rt.results.clear()
            rt.cooldown_until = 0.0

    # ---- 今日统计日切 ----
    def daily_rollover(self, today: str, last_date: str) -> bool:
        if last_date != today:
            for rt in self.channels.values():
                rt.today_requests = 0
                rt.today_failures = 0
            return True
        return False


state = AppState()
