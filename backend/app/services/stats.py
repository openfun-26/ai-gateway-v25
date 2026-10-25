"""统计服务：从 logs 聚合 + 内存快照（TTL 缓存加速）。"""
import time
from collections import defaultdict

from ..core.cache import cache
from ..core.database import db
from ..core.config import now_local_str, today_local_str
from ..core.limiter import _qps_60
from ..core.state import state
from ..db import repo


def _bucket_size(range_key: str) -> int:
    return {"30m": 60, "1h": 120, "6h": 900, "24h": 1800, "3d": 7200, "7d": 21600}.get(range_key, 1800)


def _range_seconds(range_key: str) -> int:
    return {"30m": 1800, "1h": 3600, "6h": 21600, "24h": 86400, "3d": 259200, "7d": 604800}.get(range_key, 3600)


def _parse_ts(s: str):
    from ..core.config import parse_iso
    return parse_iso(s)


async def summary() -> dict:
    """仪表盘顶部统计卡。"""
    hit = cache.get("stats_summary")
    if hit is not None:
        return hit
    today = today_local_str()
    row = await db.fetchone(
        """SELECT COUNT(*) AS total,
                  SUM(CASE WHEN ts>=? THEN 1 ELSE 0 END) AS today_total,
                  SUM(CASE WHEN status!='success' THEN 1 ELSE 0 END) AS failures,
                  SUM(CASE WHEN ts>=? AND status!='success' THEN 1 ELSE 0 END) AS today_failures,
                  COALESCE(SUM(prompt_tokens),0) AS in_tokens,
                  COALESCE(SUM(completion_tokens),0) AS out_tokens,
                  SUM(CASE WHEN ts>=? THEN COALESCE(prompt_tokens,0)+COALESCE(completion_tokens,0) ELSE 0 END) AS today_tokens
           FROM logs""", (today, today, today))
    total_tokens = (row["in_tokens"] or 0) + (row["out_tokens"] or 0)
    channels = await repo.list_channels()
    online = sum(1 for c in channels if c.get("enabled"))
    keys = await db.fetchone(
        """SELECT COUNT(*) AS valid FROM api_keys WHERE enabled=1
           AND (expires_at='' OR expires_at IS NULL OR expires_at>=?)""", (now_local_str()[:10],))
    out = {
        "total_requests": row["total"] or 0,
        "today_requests": row["today_total"] or 0,
        "failure_requests": row["failures"] or 0,
        "today_failures": row["today_failures"] or 0,
        "total_tokens": total_tokens,
        "today_tokens": row["today_tokens"] or 0,
        "input_tokens": row["in_tokens"] or 0,
        "output_tokens": row["out_tokens"] or 0,
        "online_channels": online,
        "offline_channels": len(channels) - online,
        "valid_keys": keys["valid"] or 0,
        "qps_60s": _qps_60(),
        "cache_hit_rate": round(cache.hit_rate * 100, 2),
        "cache_hits": cache.hits,
        "cache_misses": cache.misses,
    }
    cache.set("stats_summary", out, 8.0)
    return out


async def charts(range_key: str = "1h") -> dict:
    """五张图数据：请求时序 / token 时序 / 每小时分布 / 渠道占比 / 模型占比。"""
    ck = f"stats_charts:{range_key}"
    hit = cache.get(ck)
    if hit is not None:
        return hit
    from datetime import datetime, timedelta
    now = datetime.utcnow() + timedelta(hours=8)
    start = (now - timedelta(seconds=_range_seconds(range_key))).strftime("%Y-%m-%d %H:%M:%S")
    bucket = _bucket_size(range_key)

    rows = await db.fetchall(
        """SELECT ts, status, prompt_tokens, completion_tokens, channel, model FROM logs
           WHERE ts>=?""", (start,))
    t0 = now - timedelta(seconds=_range_seconds(range_key))
    base = int(datetime(t0.year, t0.month, t0.day, t0.hour).timestamp())

    def ts_slot(ts: str) -> int:
        dt = _parse_ts(ts)
        if not dt:
            return base
        return base + ((int(dt.timestamp()) - base) // bucket) * bucket

    req_series = defaultdict(lambda: {"success": 0, "failure": 0})
    tok_series = defaultdict(lambda: {"input": 0, "output": 0})
    hour_dist = defaultdict(int)
    channel_dist = defaultdict(int)
    model_dist = defaultdict(int)

    for r in rows:
        ok = r["status"] == "success"
        slot = ts_slot(r["ts"])
        if ok:
            req_series[slot]["success"] += 1
        else:
            req_series[slot]["failure"] += 1
        tok_series[slot]["input"] += r["prompt_tokens"] or 0
        tok_series[slot]["output"] += r["completion_tokens"] or 0
        hour_dist[(_parse_ts(r["ts"]).hour if _parse_ts(r["ts"]) else 0)] += 1
        channel_dist[r["channel"] or "未记录"] += 1
        model_dist[r["model"] or "未知"] += 1

    def series(d, keys):
        out = []
        t = base
        while t <= int(now.timestamp()):
            v = d.get(t)
            out.append({"t": t, **{k: (v or {}).get(k, 0) if isinstance(v, dict) else (v or 0) for k in keys}})
            t += bucket
        return out

    out = {
        "request_series": series(req_series, ["success", "failure"]),
        "token_series": series(tok_series, ["input", "output"]),
        "hour_dist": [{"hour": h, "count": hour_dist.get(h, 0)} for h in range(24)],
        "channel_dist": [{"name": k, "value": v} for k, v in
                         sorted(channel_dist.items(), key=lambda x: -x[1])[:10]],
        "model_dist": [{"name": k, "value": v} for k, v in
                       sorted(model_dist.items(), key=lambda x: -x[1])[:10]],
    }
    cache.set(ck, out, 15.0)
    return out


async def model_cards() -> list[dict]:
    """模型状态概览卡片（含今日聚合与 QPS）。"""
    hit = cache.get("stats_model_cards")
    if hit is not None:
        return hit
    today = today_local_str()
    rows = await db.fetchall(
        """SELECT m.id, m.upstream_model, m.alias, m.vendor_tag, m.emoji, m.grp, m.status,
                  m.last_http_status, m.latency_ms, m.last_check_time, m.remark,
                  c.name AS channel_name, c.grp AS channel_group
           FROM models m JOIN channels c ON c.id=m.channel_id WHERE m.enabled=1 AND c.enabled=1""")
    agg = {r["model"]: r for r in await db.fetchall(
        """SELECT model, COUNT(*) AS uses,
                  SUM(CASE WHEN ts>=? THEN 1 ELSE 0 END) AS today,
                  SUM(prompt_tokens) AS in_toks, SUM(completion_tokens) AS out_toks
           FROM logs GROUP BY model""", (today,))}
    out = []
    for m in rows:
        display = m.get("alias") or m["upstream_model"]
        a = agg.get(display) or agg.get(m["upstream_model"]) or {}
        out.append({
            **m, "display": display,
            "qps": state.model_qps_value(display),
            "total_uses": a.get("uses", 0) or 0,
            "today_uses": a.get("today", 0) or 0,
            "total_tokens": (a.get("in_toks", 0) or 0) + (a.get("out_toks", 0) or 0),
            "cache_hit_rate": round(cache.hit_rate * 100, 2),
        })
    cache.set("stats_model_cards", out, 8.0)
    return out


async def monitor_recent(limit: int = 50) -> list[dict]:
    rows = await db.fetchall(
        """SELECT id,ts,request_type,protocol,key_name,model,vendor_tag,source_ip,channel,
                  latency_ms,prompt_tokens,completion_tokens,http_status,status,error
           FROM logs ORDER BY id DESC LIMIT ?""", (limit,))
    return rows


async def alerts() -> list[dict]:
    return list(state.alerts)
