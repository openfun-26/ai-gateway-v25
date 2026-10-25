"""模型健康检测：真实 chat 测试请求 + 后台定时任务。"""
import asyncio
import contextlib
import json
import re
import time

import httpx

from ..core.config import now_local_str
from ..core.database import db
from ..db import repo
from . import upstream

STATUS_OK, STATUS_OFFLINE, STATUS_LIMITED, STATUS_MISSING = "online", "offline", "limited", "missing"

# 模型级不可用错误特征（与转发层 forward._MODEL_ERR_PAT 保持一致）
_MODEL_FAIL_PAT = re.compile(
    r"service info not found|model_not_found|model not found|当前模型不可用|模型不可用|"
    r"does not exist|no available channel for model|invalid model|unknown model|not a valid model", re.I)


def _mark_model_cool(channel: dict, model: dict, http_code: int, text: str):
    """检测→路由联动：检测确认模型级不可用时，让路由层冷却该 (渠道,模型) 组合。"""
    if http_code == 404:
        secs = 600  # 模型明确缺失，冷却久一些
    elif http_code in (400, 422) or 200 <= http_code < 300:
        secs = 300 if text and _MODEL_FAIL_PAT.search(text) else 0
    else:
        secs = 0
    if secs:
        try:
            from ..core.state import state as st
            st.mark_model_fail(channel["id"], model["upstream_model"], secs)
        except Exception:
            pass


async def check_single_model(model: dict, channel: dict, timeout_sec: int = 15) -> dict:
    """发送简短 chat 测试请求，返回状态更新。"""
    up_proto = channel.get("protocol", "openai")
    path = "/v1/messages" if up_proto == "anthropic" else "/chat/completions"
    if up_proto == "anthropic":
        payload = {"model": model["upstream_model"], "max_tokens": 8,
                   "messages": [{"role": "user", "content": "hi"}]}
    else:
        payload = {"model": model["upstream_model"], "max_tokens": 8,
                   "messages": [{"role": "user", "content": "hi"}]}
    client = upstream.get_client(channel)
    t0 = time.monotonic()
    status, http_code, latency = STATUS_OFFLINE, 0, 0
    body_text = ""
    try:
        resp = await client.post(upstream.upstream_url(channel, path),
                                 json=payload, headers=upstream.build_headers(channel))
        latency = int((time.monotonic() - t0) * 1000)
        http_code = resp.status_code
        if 200 <= resp.status_code < 300:
            # 2xx 不代表健康：许多兼容层对不存在的模型也返回 200+error JSON
            body_ok = True
            try:
                data = resp.json()
                if isinstance(data, dict):
                    body_text = json.dumps(data, ensure_ascii=False)[:2000]
                    if data.get("error") or data.get("type") == "error":
                        body_ok = False
                    elif up_proto == "openai" and not (data.get("choices") or data.get("id")):
                        body_ok = False
                    elif up_proto == "anthropic" and not (data.get("content") or data.get("id")):
                        body_ok = False
            except Exception:
                pass
            status = STATUS_OK if body_ok else STATUS_OFFLINE
        elif resp.status_code == 429:
            status = STATUS_LIMITED
        elif resp.status_code == 404:
            status = STATUS_MISSING
            with contextlib.suppress(Exception):
                body_text = (await resp.aread()).decode("utf-8", "ignore")[:2000]
        elif resp.status_code in (400, 422):
            with contextlib.suppress(Exception):
                body_text = (await resp.aread()).decode("utf-8", "ignore")[:2000]
        await resp.aclose()
    except httpx.TimeoutException:
        status, latency = STATUS_OFFLINE, int((time.monotonic() - t0) * 1000)
    except httpx.HTTPError:
        status = STATUS_OFFLINE
    # 检测→路由联动：确认模型级不可用时冷却该 (渠道,模型)，auto/降级路由立即跳过
    if status in (STATUS_OFFLINE, STATUS_MISSING):
        _mark_model_cool(channel, model, http_code, body_text)
    await repo.update_model(model["id"], {"status": status, "last_http_status": http_code,
                                          "latency_ms": latency, "last_check_time": now_local_str()})
    return {"model_id": model["id"], "status": status, "http_status": http_code, "latency_ms": latency}


async def check_channel_models(channel_id: int, timeout_sec: int = 15) -> int:
    """检测指定渠道下所有启用且未 skip_health 的模型，返回检测数量。"""
    channel = await repo.get_channel(channel_id)
    if not channel:
        return 0
    models = await db.fetchall("SELECT * FROM models WHERE channel_id=? AND enabled=1 AND skip_health=0",
                               (channel_id,))
    sem = asyncio.Semaphore(5)

    async def run(m):
        async with sem:
            await check_single_model(m, channel, timeout_sec)

    await asyncio.gather(*[run(m) for m in models])
    return len(models)


async def check_all_models(timeout_sec: int = 15) -> int:
    """一键全部健康检测。"""
    rows = await db.fetchall(
        """SELECT m.* FROM models m JOIN channels c ON c.id=m.channel_id
           WHERE m.enabled=1 AND c.enabled=1 AND m.skip_health=0""")
    channels = {c["id"]: c for c in await repo.list_channels()}
    sem = asyncio.Semaphore(6)

    async def run(m):
        ch = channels.get(m["channel_id"])
        if ch:
            async with sem:
                await check_single_model(m, ch, timeout_sec)

    await asyncio.gather(*[run(m) for m in rows])
    return len(rows)


_bg_task: asyncio.Task | None = None


def start_background_check(timeout_sec: int = 15) -> bool:
    """以后台任务启动全部模型检测；已有任务在跑则返回 False（防重入）。"""
    global _bg_task
    if _bg_task is not None and not _bg_task.done():
        return False

    async def _run():
        try:
            await check_all_models(timeout_sec)
        except Exception:
            pass

    _bg_task = asyncio.get_running_loop().create_task(_run())
    return True


async def background_loop(app):
    """后台定时检测任务（asyncio.create_task 拉起）。"""
    from ..core.state import state as st
    while True:
        try:
            settings = await repo.get_settings()
            interval = repo.s_int(settings, "health_interval_sec", 300)
            if interval <= 0:
                await asyncio.sleep(30)
                continue
            timeout = repo.s_int(settings, "health_timeout_sec", 15)
            await check_all_models(timeout)
            await asyncio.sleep(max(30, interval))
        except asyncio.CancelledError:
            return
        except Exception:
            await asyncio.sleep(60)
