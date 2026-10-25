"""上游渠道调用层：httpx 客户端管理、路由选渠道、重试与状态码判定。"""
import asyncio
import json
import random
import re
import time
from collections import deque
from typing import Any

import httpx

from ..core.cache import cache
from ..core.database import db
from ..core.state import state
from ..db import repo

# ---------------- httpx 客户端池 ----------------

_clients: dict[tuple, httpx.AsyncClient] = {}


def get_client(channel: dict) -> httpx.AsyncClient:
    key = (channel["id"], channel.get("http_proxy", ""))
    c = _clients.get(key)
    if c is None:
        c = httpx.AsyncClient(
            timeout=httpx.Timeout(channel.get("timeout_ms") or 60000, connect=15.0),
            proxy=channel.get("http_proxy") or None,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            trust_env=False,
        )
        _clients[key] = c
    return c


async def close_clients():
    for c in _clients.values():
        await c.aclose()
    _clients.clear()


def build_headers(channel: dict, extra: dict | None = None) -> dict:
    h = {"Content-Type": "application/json"}
    if channel.get("protocol") == "anthropic":
        h["x-api-key"] = channel.get("api_key", "")
        h["anthropic-version"] = "2023-06-01"
    else:
        h["Authorization"] = f"Bearer {channel.get('api_key', '')}"
    try:
        eh = json.loads(channel.get("extra_headers") or "{}")
        if isinstance(eh, dict):
            h.update({str(k): str(v) for k, v in eh.items()})
    except Exception:
        pass
    if extra:
        h.update(extra)
    return h


# ---------------- 路由选渠道 ----------------

async def pick_channels(model_row: dict | None, requested_model: str) -> list[dict]:
    """§8.1 步骤7-8：模型级专属规则 > routing_rules > 全局策略排序。"""
    settings = await repo.get_settings()
    channels = await get_channels_snapshot()

    # 目标渠道组
    target_group = ""
    if model_row and model_row.get("prefer_group"):
        target_group = model_row["prefer_group"]
    if not target_group:
        for rule in await repo.list_routing_rules():
            if not rule.get("enabled"):
                continue
            if rule["match_type"] == "model":
                vals = [v.strip() for v in (rule["match_value"] or "").replace("，", ",").split(",") if v.strip()]
                if requested_model in vals or (model_row and model_row["upstream_model"] in vals):
                    target_group = rule["target_group"]
                    break
            elif rule["match_type"] == "group" and model_row:
                vals = [v.strip() for v in (rule["match_value"] or "").replace("，", ",").split(",") if v.strip()]
                if model_row.get("channel_group") in vals or model_row.get("grp") in vals:
                    target_group = rule["target_group"]
                    break

    pool = [c for c in channels if not target_group or c["grp"] == target_group]

    # 模型级专属路由组可能没有可用渠道 -> 回退全池
    if not pool and target_group:
        pool = channels

    # 过滤：模型白/黑名单、模型级失败冷却、熔断、冷却、并发
    candidates = []
    up_name = (model_row or {}).get("upstream_model") or ""
    for c in pool:
        wl, bl = c.get("model_whitelist", ""), c.get("model_blacklist", "")
        check_name = requested_model or (model_row or {}).get("upstream_model", "")
        if wl and not _in_list(check_name, wl):
            continue
        if bl and _in_list(check_name, bl):
            continue
        if up_name and state.model_in_fail(c["id"], up_name):
            continue   # 该渠道上此模型刚被上游判定不可用，暂跳过（不影响渠道其他模型）
        rt = state.ch(c["id"])
        err_th = c.get("cb_error_threshold") or repo.s_float(settings, "circuit_error_threshold", 50)
        window = c.get("cb_window_sec") or repo.s_int(settings, "circuit_window_sec", 60)
        freeze = c.get("cb_freeze_sec") or repo.s_int(settings, "circuit_freeze_sec", 300)
        if state.circuit_check(c["id"], err_th, freeze):
            continue
        if rt.in_cooldown():
            continue
        if rt.concurrency >= (c.get("max_concurrency") or 5):
            continue
        candidates.append(c)

    if not candidates:
        return []

    strategy = settings.get("routing_strategy", "weighted_round_robin")
    adaptive = repo.s_int(settings, "auto_adaptive_weight") == 1

    if strategy == "least_concurrency":
        candidates.sort(key=lambda c: state.ch(c["id"]).concurrency)
    elif strategy == "least_latency":
        candidates.sort(key=lambda c: state.ch(c["id"]).lat_ema or 1e9)
    elif strategy == "failover":
        candidates.sort(key=lambda c: -_success_rate(c["id"]))
    elif strategy == "round_robin":
        idx = getattr(pick_channels, "_rr", 0) + 1
        pick_channels._rr = idx
        candidates = candidates[idx % len(candidates):] + candidates[:idx % len(candidates)]
    else:  # weighted_round_robin（加权随机；自适应权重按成功率修正）
        weights = []
        for c in candidates:
            w = max(1, c.get("weight") or 1)
            if adaptive:
                w = max(1, int(w * _success_rate(c["id"]) / 100.0)) or 1
            weights.append(w)
        # 按权重随机排序（无放回抽样近似）
        ordered = []
        cand = list(zip(candidates, weights))
        while cand:
            total = sum(w for _, w in cand)
            r = random.uniform(0, total)
            acc = 0
            for i, (c, w) in enumerate(cand):
                acc += w
                if acc >= r:
                    ordered.append(c)
                    cand.pop(i)
                    break
        candidates = ordered

    return candidates


def _in_list(name: str, csv: str) -> bool:
    items = [x.strip() for x in (csv or "").replace("，", ",").split(",") if x.strip()]
    if not items:
        return False
    return any(it == name or (it.endswith("*") and name.startswith(it[:-1])) for it in items)


def _success_rate(cid: int) -> float:
    rt = state.channels.get(cid)
    if not rt or not rt.results:
        return 100.0
    ok = sum(1 for _, o in rt.results if o)
    return ok / len(rt.results) * 100.0


async def get_channels_snapshot() -> list[dict]:
    snap = cache.get("channels_snapshot")
    if snap is not None:
        return snap
    rows = await repo.list_channels(enabled_only=True)
    cache.set("channels_snapshot", rows, 8.0)
    return rows


# ---------------- 单渠道调用 ----------------

_VER_SEG = re.compile(r"/v\d+(?:/|$)")


def upstream_url(channel: dict, path: str) -> str:
    """拼接上游 URL。base 已带版本段（/v1、/v4、/api/paas/v4 等）则尊重用户配置，不再补 /v1。"""
    base = (channel.get("base_url") or "").rstrip("/")
    if channel.get("protocol") == "openai" and not _VER_SEG.search(base + "/"):
        base += "/v1"
    if base.endswith("/v1") and path.startswith("/v1/"):   # 防御双拼
        path = path[3:]
    return base + path


async def call_upstream(channel: dict, path: str, payload: dict, extra_headers: dict | None = None):
    """返回 (httpx.Response, error_str)。流式时调用方负责 aclose。"""
    client = get_client(channel)
    url = upstream_url(channel, path)
    headers = build_headers(channel, extra_headers)
    try:
        resp = await client.post(url, json=payload, headers=headers)
        return resp, None
    except httpx.TimeoutException:
        return None, "上游请求超时"
    except httpx.HTTPError as e:
        return None, f"上游连接失败: {type(e).__name__}"


async def call_upstream_get(channel: dict, url: str, timeout: float | None = None):
    """GET 请求上游（用于拉取模型列表等），返回 (httpx.Response, error_str)。"""
    client = get_client(channel)
    headers = build_headers(channel)
    try:
        resp = await client.get(url, headers=headers, timeout=timeout)
        return resp, None
    except httpx.TimeoutException:
        return None, "上游请求超时"
    except httpx.HTTPError as e:
        return None, f"上游连接失败: {type(e).__name__}"


def should_retry(channel: dict, status_code: int) -> bool:
    try:
        codes = json.loads(channel.get("retry_status_codes") or "[429,500,502,503,504]")
        return status_code in codes
    except Exception:
        return status_code in (429, 500, 502, 503, 504)


def extract_usage(data: dict, protocol: str) -> tuple[int, int]:
    """从上游响应提取 (prompt_tokens, completion_tokens)。"""
    try:
        if protocol == "anthropic":
            u = data.get("usage") or {}
            return u.get("input_tokens", 0) or 0, u.get("output_tokens", 0) or 0
        u = data.get("usage") or {}
        return u.get("prompt_tokens", 0) or 0, u.get("completion_tokens", 0) or 0
    except Exception:
        return 0, 0
