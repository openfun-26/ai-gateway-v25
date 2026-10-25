"""聚合转发服务：网关管线步骤 7-10（选渠道、协议转换、重试/降级/熔断、SSE、计费、日志）。"""
import asyncio
import contextlib
import json
import re
import time
from urllib.parse import quote

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse, Response as FResponse

from ..core.database import db
from ..core.config import now_local_str
from ..core.state import state
from ..db import repo
from . import upstream
from ..gateway import converters
from ..gateway.auth import _err, _client_ip, quota_check_post

_semaphores: dict[tuple, asyncio.Semaphore] = {}


def _get_sem(cid: int, limit: int) -> asyncio.Semaphore:
    key = (cid, limit)
    if key not in _semaphores:
        _semaphores[key] = asyncio.Semaphore(max(1, limit))
    return _semaphores[key]


def _base_log(k: dict | None, body: dict, anthropic: bool, request: Request) -> dict:
    return {
        "request_type": "forward",
        "protocol": "anthropic" if anthropic else "openai",
        "key_name": (k or {}).get("name", ""),
        "model": body.get("model", ""),
        "source_ip": _client_ip(request),
        "request_payload": json.dumps(body, ensure_ascii=False)[:8000],
    }


async def _fail_over_error(settings: dict, log: dict, message: str, anthropic: bool) -> JSONResponse:
    await repo.insert_log({**log, "status": "failure", "error": message[:500], "http_status": 502,
                           "response_payload": message[:2000]})
    return _err(502, "api_error", message, anthropic)


# ======================================================================
# chat/completions 与 /anthropic/v1/messages 统一入口
# ======================================================================

async def handle_chat(request: Request, body: dict, anthropic: bool) -> FResponse:
    k, err_resp = await getattr(request.app.state, "auth_fn")(
        request, requested_model=body.get("model", ""), anthropic=anthropic)
    if err_resp:
        return err_resp

    settings = await repo.get_settings()
    log = _base_log(k, body, anthropic, request)
    requested_model = body.get("model", "")

    model_row = await _resolve(requested_model)
    if not model_row:
        return await _fail_over_error(settings, log, f"模型 '{requested_model}' 不存在或未启用", anthropic)

    stream = bool(body.get("stream"))
    start = time.monotonic()
    log["vendor_tag"] = model_row.get("vendor_tag") or model_row.get("vendor") or ""
    err_box = {"msg": "", "status": 0, "tried": 0}

    # ---- auto 单独选择：先按问题内容匹配规则，再按健康度动态挑选（失败自动换，最多 3 次）----
    if (model_row.get("upstream_model") or "").strip() == "__auto__":
        exclude_up: set[str] = set()
        # v20：auto 规则路由——按最后一条用户消息命中「关键词 -> 模型」规则
        rule_hit = await _match_auto_rule(body.get("messages") or [])
        if rule_hit:
            rule_model, kw = rule_hit
            rule_row = await _resolve(rule_model)
            if rule_row:
                resp = await _run_channels(request, body, k, log, settings, anthropic, stream, start,
                                           "auto", rule_row, err_box)
                if resp is not None:
                    # header 值仅允许 latin-1：中文关键词必须 percent-encode，否则赋值抛 UnicodeEncodeError
                    with contextlib.suppress(Exception):
                        resp.headers["X-Gateway-Auto-Rule"] = f"{quote(str(kw), safe='')} -> {rule_model}"
                    return resp
                exclude_up.add(rule_row.get("upstream_model") or "")
        for _ in range(3):
            target = await _pick_auto(exclude_up)
            if not target:
                break
            ch, up = target
            exclude_up.add(up)
            resp = await _run_channels(request, body, k, log, settings, anthropic, stream, start,
                                       "auto", {**model_row, "upstream_model": up, "channel_id": ch["id"]},
                                       err_box, fixed_channel=ch)
            if resp is not None:
                return resp
        rem = state.cooldown_remaining()
        msg = "auto：当前无可用模型（渠道全部熔断/冷却中" + (f"，约 {rem}s 后自动恢复" if rem else "") + "）"
        return await _fail_over_error(settings, log, msg, anthropic)

    # ---- 原始模型 ----
    resp = await _run_channels(request, body, k, log, settings, anthropic, stream, start,
                               requested_model, model_row, err_box)
    if resp is not None:
        return resp

    # ---- 备选模型降级链：按模型监控列表顺序逐个尝试，auto 兜底 ----
    if repo.s_int(settings, "model_fallback", 1) == 1:
        exclude = {requested_model, model_row.get("upstream_model") or ""}
        for alt_name, alt_row in await _fallback_models(exclude, limit=3):
            log_alt = dict(log)
            resp = await _run_channels(request, body, k, log_alt, settings, anthropic, stream, start,
                                       alt_name, alt_row, err_box)
            if resp is not None:
                with contextlib.suppress(Exception):
                    resp.headers["X-Gateway-Fallback"] = f"{quote(str(requested_model), safe='')} -> {alt_name}"
                return resp
        # auto 兜底（本请求中已失败的模型已被模型级/渠道级冷却自动排除）
        if await _auto_enabled(settings):
            target = await _pick_auto(exclude=set())
            if target:
                ch, up = target
                log_auto = dict(log)
                resp = await _run_channels(request, body, k, log_auto, settings, anthropic, stream, start,
                                           "auto", {**model_row, "upstream_model": up, "channel_id": ch["id"]},
                                           err_box, fixed_channel=ch)
                if resp is not None:
                    with contextlib.suppress(Exception):
                        resp.headers["X-Gateway-Fallback"] = f"{quote(str(requested_model), safe='')} -> auto({up})"
                    return resp

    return await _fail_over_error(settings, log,
                                  f"全部 {max(1, err_box['tried'])} 次调用失败（含备选降级）。最后错误[{err_box['status']}]: {err_box['msg'][:300]}",
                                  anthropic)


async def _auto_enabled(settings: dict) -> bool:
    return repo.s_int(settings, "auto_enabled", 1) == 1


async def _match_auto_rule(messages: list) -> tuple[str, str] | None:
    """auto 规则路由：按最后一条用户消息匹配「关键词 -> 模型」规则（按优先级）。
    返回 (model_name, keyword) 或 None。大小写不敏感。"""
    text = ""
    for m in reversed(messages or []):
        if isinstance(m, dict) and m.get("role") == "user":
            text = str(m.get("content") or "")
            break
    if not text.strip():
        return None
    text_low = text.lower()
    try:
        rules = await db.fetchall("SELECT * FROM auto_rules WHERE enabled=1 ORDER BY priority, id")
    except Exception:
        return None
    for r in rules:
        kw = (r["keyword"] or "").strip()
        if kw and kw.lower() in text_low:
            return (r["model_name"] or "").strip(), kw
    return None


async def _all_enabled_models() -> list[dict]:
    """按模型监控列表顺序（id 升序）返回启用模型。"""
    from ..gateway.auth import get_models_snapshot
    return await get_models_snapshot()


async def _fallback_models(exclude: set[str], limit: int = 3) -> list[tuple[str, dict]]:
    """备选模型：按用户在模型监控页看到的顺序（id 升序），排除请求模型本身。"""
    out: list[tuple[str, dict]] = []
    for m in await _all_enabled_models():
        name = m.get("alias") or m["upstream_model"]
        if name in exclude or m["upstream_model"] in exclude:
            continue
        out.append((name, m))
        if len(out) >= limit:
            break
    return out


async def _pick_auto(exclude: set[str]):
    """auto 智能路由：按渠道成功率从高到低，取该渠道上第一个健康模型。付费渠道可被排除。"""
    settings = await repo.get_settings()
    exclude_paid = repo.s_int(settings, "auto_exclude_paid", 1) == 1
    channels = sorted(await upstream.get_channels_snapshot(),
                      key=lambda c: -upstream._success_rate(c["id"]))
    models = await _all_enabled_models()
    for c in channels:
        if exclude_paid and c.get("paid"):
            continue
        rt = state.ch(c["id"])
        err_th = c.get("cb_error_threshold") or repo.s_float(settings, "circuit_error_threshold", 50)
        freeze = c.get("cb_freeze_sec") or repo.s_int(settings, "circuit_freeze_sec", 300)
        if (state.circuit_check(c["id"], err_th, freeze) or rt.in_cooldown()
                or rt.concurrency >= (c.get("max_concurrency") or 5)):
            continue
        for m in models:
            if m["channel_id"] != c["id"]:
                continue
            up = m["upstream_model"]
            if up in exclude or state.model_in_fail(c["id"], up):
                continue
            if upstream._in_list(up, c.get("model_blacklist", "")):
                continue
            return c, up
    return None


async def _run_channels(request: Request, body: dict, k, log, settings, anthropic, stream, start,
                        model_name: str, model_row: dict, err_box: dict,
                        fixed_channel: dict | None = None) -> FResponse | None:
    """对单个模型执行完整渠道尝试（重试/降级/熔断）。成功返回响应，全部失败返回 None。"""
    if fixed_channel is not None:
        candidates = [fixed_channel]
    else:
        candidates = await upstream.pick_channels(model_row, model_name)
        if not candidates:
            rem = state.cooldown_remaining()
            err_box["msg"] = ("无可用渠道（全部熔断/冷却/并发占满或被过滤"
                              + (f"，约 {rem}s 后自动恢复" if rem else "") + "）")
            err_box["status"] = 502
            return None

    for channel in candidates:
        err_box["tried"] += 1
        rt = state.ch(channel["id"])
        sem = _get_sem(channel["id"], channel.get("max_concurrency") or 5)
        in_proto = "anthropic" if anthropic else "openai"
        up_proto = channel.get("protocol", "openai")

        # 请求体协议转换（入协议 -> 渠道协议）
        if in_proto == up_proto:
            up_body = dict(body)
        elif in_proto == "openai" and up_proto == "anthropic":
            up_body = converters.openai_to_anthropic(body)
        else:
            up_body = converters.anthropic_to_openai(body)
        up_body["stream"] = stream
        # 关键：发上游的是真实模型名，而不是用户请求的别名
        up_body["model"] = model_row.get("upstream_model") or model_name

        path = "/v1/messages" if up_proto == "anthropic" else "/chat/completions"
        retries = max(int(channel.get("max_retries") or 0), repo.s_int(settings, "global_max_retries", 2))
        attempt = 0
        while attempt <= retries:
            attempt += 1
            rt.concurrency += 1
            t0 = time.monotonic()
            try:
                resp, net_err = await upstream.call_upstream(channel, path, up_body)
            finally:
                pass

            latency_ms = int((time.monotonic() - t0) * 1000)

            if net_err:
                rt.concurrency -= 1
                err_box["msg"], err_box["status"] = net_err, 0
                _mark_failure(channel, latency_ms)
                break  # 网络错误渠道内重试无意义 -> 下一渠道

            if resp.status_code >= 400:
                err_text = (await resp.aread()).decode("utf-8", "ignore")[:2000]
                await resp.aclose()
                err_box["msg"], err_box["status"] = err_text, resp.status_code
                # 模型级错误（上游明确说该模型不可用）：只冷却 (渠道,模型) 组合，不拖累渠道
                if _is_model_level_error(resp.status_code, err_text):
                    _mark_failure(channel, latency_ms, model_level=True)
                    state.mark_model_fail(channel["id"], model_row.get("upstream_model") or model_name, 60)
                else:
                    _mark_failure(channel, latency_ms)
                if upstream.should_retry(channel, resp.status_code) and attempt <= retries:
                    await asyncio.sleep(min(1.0 * attempt, 2))
                    continue
                break  # 下一渠道

            # ---- 成功 ----
            rt.concurrency -= 1
            rt.record(True, latency_ms, int(channel.get("cb_window_sec") or 60))
            rt.today_requests += 1

            if stream:
                return await _stream_response(request, resp, channel, model_row, model_name,
                                              k, log, anthropic, in_proto, up_proto, start)
            return await _json_response(resp, channel, model_row, model_name,
                                        k, log, anthropic, in_proto, up_proto, start, latency_ms)

    return None


_MODEL_ERR_PAT = re.compile(
    r"service info not found|model_not_found|model not found|当前模型不可用|模型不可用|"
    r"does not exist|no available channel for model|invalid model|unknown model|not a valid model", re.I)


def _is_model_level_error(status: int, text: str) -> bool:
    """上游明确表示『该模型不存在/不可用』-> 属于模型级错误，而非渠道故障。"""
    return status in (400, 404, 422) and bool(_MODEL_ERR_PAT.search(text or ""))


def _mark_failure(channel: dict, latency_ms: int, model_level: bool = False):
    rt = state.ch(channel["id"])
    rt.today_failures += 1
    rt.today_requests += 1
    if not model_level:
        rt.record(False, latency_ms, int(channel.get("cb_window_sec") or 60))
        rt.cooldown_until = time.monotonic() + max(1, channel.get("cooldown_sec") or 60)


async def _resolve(requested_model: str):
    from ..gateway.auth import resolve_model
    return await resolve_model(requested_model)


# ---------------- 非流式响应 ----------------

async def _json_response(resp, channel, model_row, requested_model, k, log, anthropic,
                         in_proto, up_proto, start, latency_ms) -> FResponse:
    rt = state.ch(channel["id"])
    try:
        data = resp.json()
    except Exception:
        data = {"raw": (await resp.aread()).decode("utf-8", "ignore")[:1000]}

    pt, ct = upstream.extract_usage(data, up_proto)

    # 出协议转换
    if in_proto == "openai":
        if up_proto == "anthropic":
            out = converters.anthropic_resp_to_openai(data, requested_model)
        else:
            out = data
    else:
        if up_proto == "openai":
            out = converters.openai_resp_to_anthropic(data, requested_model)
        else:
            out = data

    # 模型快照发现：把上游返回的真实模型名入库
    _discover_model(channel, out if in_proto == "openai" else {"model": data.get("model", "")}, model_row)

    # 计费 + 日志
    total_ms = int((time.monotonic() - start) * 1000)
    await repo.bump_key_usage(k["id"], pt, ct)
    quota_check_post(k, pt, ct)
    await repo.insert_log({**log, "model": requested_model, "vendor_tag": log.get("vendor_tag", ""),
                           "channel": channel["name"], "latency_ms": total_ms, "prompt_tokens": pt,
                           "completion_tokens": ct, "http_status": resp.status_code, "status": "success",
                           "response_payload": json.dumps(out, ensure_ascii=False)[:8000]})
    state.model_hit(requested_model)
    return JSONResponse(out, status_code=200)


def _discover_model(channel: dict, out: dict, model_row):
    """首次调用成功时补录上游真实模型名到模型表（幂等）。"""
    try:
        name = out.get("model") or model_row["upstream_model"]
        if name and channel.get("protocol") == "openai":
            import asyncio
            asyncio.get_event_loop().create_task(
                repo.add_model_if_missing(channel["id"], name,
                                          model_row.get("vendor_tag") or "", model_row.get("emoji") or ""))
    except Exception:
        pass


# ---------------- 流式响应 ----------------

async def _iter_sse(resp: httpx.Response, up_proto: str):
    """把上游响应解析为 (event_name, data_dict) 序列。"""
    event_name = ""
    buf: list[str] = []
    async for raw in resp.aiter_lines():
        line = raw.rstrip("\r\n")
        if line == "":
            if buf:
                data_str = "\n".join(buf)
                buf = []
                if data_str == "[DONE]":
                    yield ("__done__", None)
                    return
                try:
                    data = json.loads(data_str)
                except Exception:
                    continue
                yield (event_name or ("message" if up_proto == "anthropic" else "chunk"), data)
            event_name = ""
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            buf.append(line[5:].strip())
    if buf:
        try:
            yield (event_name or "chunk", json.loads("\n".join(buf)))
        except Exception:
            pass


async def _stream_response(request, resp, channel, model_row, requested_model, k, log,
                           anthropic, in_proto, up_proto, start) -> StreamingResponse:
    rt = state.ch(channel["id"])
    usage = {"pt": 0, "ct": 0}
    text_acc = {"len": 0}
    status_holder = {"logged": False}

    async def gen():
        status_holder["logged"] = True
        try:
            if in_proto == "openai":
                # 出协议 OpenAI
                if up_proto == "anthropic":
                    conv = converters.AnthropicToOpenAIStream(requested_model)
                    async for ev, data in _iter_sse(resp, up_proto):
                        if ev == "__done__":
                            break
                        for piece in conv.feed(ev, data):
                            yield piece
                    pt, ct = conv.usage_tuple
                else:
                    sent_any = False
                    async for ev, data in _iter_sse(resp, up_proto):
                        if ev == "__done__":
                            break
                        if ev == "chunk":
                            if not sent_any:
                                sent_any = True
                            u = data.get("usage")
                            if u:
                                usage["pt"] = u.get("prompt_tokens", usage["pt"])
                                usage["ct"] = u.get("completion_tokens", usage["ct"])
                            ch0 = (data.get("choices") or [{}])[0]
                            delta = ch0.get("delta") or {}
                            text_acc["len"] += len(delta.get("content") or "")
                            yield "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"
                    if not usage["pt"] and text_acc["len"]:
                        usage["pt"] = max(1, text_acc["len"] // 4)
                    if not usage["ct"] and text_acc["len"]:
                        usage["ct"] = max(1, text_acc["len"] // 4)
                    pt, ct = usage["pt"], usage["ct"]
                    yield "data: [DONE]\n\n"
            else:
                # 出协议 Anthropic
                if up_proto == "openai":
                    conv = converters.OpenAIToAnthropicStream(requested_model)
                    async for ev, data in _iter_sse(resp, up_proto):
                        if ev == "__done__":
                            break
                        for piece in conv.feed(data):
                            yield piece
                    for piece in conv.close():
                        yield piece
                    pt, ct = conv.usage_tuple
                else:
                    pt, ct = 0, 0
                    sent_start = False
                    async for ev, data in _iter_sse(resp, up_proto):
                        if ev == "__done__":
                            break
                        if ev == "message_start":
                            sent_start = True
                            u = (data.get("message") or {}).get("usage") or {}
                            pt = u.get("input_tokens", 0)
                        if ev == "content_block_delta" and (data.get("delta") or {}).get("type") == "text_delta":
                            text_acc["len"] += len(data["delta"].get("text", ""))
                        if ev == "message_delta":
                            u = data.get("usage") or {}
                            ct = u.get("output_tokens", ct)
                        out = f"event: {ev}\ndata: " + json.dumps(data, ensure_ascii=False) + "\n\n"
                        yield out
                    if not sent_start:
                        yield "event: error\ndata: " + json.dumps({"type": "error", "error": {
                            "type": "api_error", "message": "上游流异常结束"}}) + "\n\n"
                    if not ct and text_acc["len"]:
                        ct = max(1, text_acc["len"] // 4)
        except (asyncio.CancelledError, GeneratorExit):
            # 客户端断开：取消上游并记录
            raise
        finally:
            await resp.aclose()
            total_ms = int((time.monotonic() - start) * 1000)
            try:
                await repo.bump_key_usage(k["id"], pt if isinstance(pt, int) else 0,
                                          ct if isinstance(ct, int) else 0)
                quota_check_post(k, pt or 0, ct or 0)
                await repo.insert_log({**log, "model": requested_model, "channel": channel["name"],
                                       "latency_ms": total_ms, "prompt_tokens": pt or 0,
                                       "completion_tokens": ct or 0, "http_status": 200, "status": "success",
                                       "response_payload": f"[stream] ~{text_acc['len']} chars"})
            except Exception:
                pass

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                      "Connection": "keep-alive"})


# ======================================================================
# /v1/models 聚合
# ======================================================================

async def handle_models(request: Request) -> FResponse:
    k, err_resp = await getattr(request.app.state, "auth_fn")(request, requested_model=None, anthropic=False)
    if err_resp:
        return err_resp
    snap_key = f"models_list:{k['id']}"
    out = _cache_get(snap_key)
    if out is None:
        models = await _aggregate_models()
        # key 级模型白/黑名单过滤
        wl, bl = k.get("model_whitelist", ""), k.get("model_blacklist", "")
        from ..gateway.auth import _in_csv_list
        visible = []
        for m in models:
            name = m["id"]
            if wl and not _in_csv_list(name, wl):
                continue
            if bl and _in_csv_list(name, bl):
                continue
            visible.append(m)
        out = {"object": "list", "data": visible}
        _cache_set(snap_key, out, 10.0)
    return JSONResponse(out)


async def _aggregate_models() -> list[dict]:
    models = await _resolve_all_alias()
    seen, data = set(), []
    for m in models:
        display = m.get("alias") or m["upstream_model"]
        if display in seen:
            continue
        seen.add(display)
        data.append({
            "id": display,
            "object": "model",
            "created": 0,
            "owned_by": m.get("vendor_tag") or m.get("vendor") or "gateway",
            "emoji": m.get("emoji") or "🤖",
            "vendor_tag": m.get("vendor_tag") or m.get("vendor") or "",
            "group": m.get("grp") or "default",
            "status": m.get("status", "unknown"),
        })
    return data


async def _resolve_all_alias() -> list[dict]:
    rows = await db.fetchall(
        """SELECT m.alias, m.upstream_model, m.vendor_tag, m.emoji, m.grp, m.status FROM models m
           JOIN channels c ON c.id=m.channel_id WHERE m.enabled=1 AND c.enabled=1 ORDER BY m.id""")
    return rows


_simple_cache: dict = {}


def _cache_get(key):
    from ..core.cache import cache
    return cache.get(key)


def _cache_set(key, val, ttl):
    from ..core.cache import cache
    cache.set(key, val, ttl)


# ======================================================================
# /v1/embeddings：路由至支持 embeddings 的渠道（OpenAI 协议）
# ======================================================================

async def handle_embeddings(request: Request, body: dict) -> FResponse:
    k, err_resp = await getattr(request.app.state, "auth_fn")(request, requested_model=body.get("model", ""),
                                                              anthropic=False)
    if err_resp:
        return err_resp
    log = _base_log(k, body, False, request)
    requested_model = body.get("model", "")
    channels = await upstream.get_channels_snapshot()
    candidates = [c for c in channels if c.get("protocol") == "openai"]
    if requested_model:
        candidates = [c for c in candidates if not c.get("model_blacklist") or not upstream._in_list(requested_model, c["model_blacklist"])]
    last_err = "无支持 embeddings 的可用渠道"
    for channel in candidates[:5]:
        rt = state.ch(channel["id"])
        if rt.in_cooldown() or state.circuit_check(channel["id"], 50, 300):
            continue
        if rt.concurrency >= (channel.get("max_concurrency") or 5):
            continue
        rt.concurrency += 1
        t0 = time.monotonic()
        try:
            resp, net_err = await upstream.call_upstream(channel, "/embeddings", body)
        finally:
            rt.concurrency -= 1
        latency = int((time.monotonic() - t0) * 1000)
        if net_err:
            last_err = net_err
            _mark_failure(channel, latency)
            continue
        if resp.status_code >= 400:
            last_err = (await resp.aread()).decode("utf-8", "ignore")[:500]
            await resp.aclose()
            _mark_failure(channel, latency)
            continue
        data = resp.json()
        pt, ct = upstream.extract_usage(data, "openai")
        rt.record(True, latency, 60)
        rt.today_requests += 1
        await repo.bump_key_usage(k["id"], pt, ct)
        await repo.insert_log({**log, "model": requested_model, "channel": channel["name"],
                               "latency_ms": latency, "prompt_tokens": pt, "completion_tokens": 0,
                               "http_status": resp.status_code, "status": "success"})
        state.model_hit(requested_model)
        return JSONResponse(data)
    await repo.insert_log({**log, "model": requested_model, "status": "failure",
                           "error": last_err[:500], "http_status": 502})
    return _err(502, "api_error", f"embeddings 调用失败: {last_err}", False)
