"""对外请求鉴权管线（§8.1 步骤 1-6）。"""
import ipaddress
import time

from fastapi import Request
from fastapi.responses import JSONResponse

from ..core.cache import cache
from ..core.config import parse_iso
from ..core.database import db
from ..core.limiter import record_request_hit, RateLimiter
from ..core.state import state
from ..db import repo


def _err(status: int, etype: str, message: str, anthropic: bool = False) -> JSONResponse:
    if anthropic:
        body = {"type": "error", "error": {"type": etype, "message": message}}
    else:
        body = {"error": {"message": message, "type": etype, "code": etype}}
    return JSONResponse(body, status_code=status)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


def _ip_in_list(ip: str, whitelist: str) -> bool:
    if not whitelist.strip():
        return True
    for item in whitelist.replace("，", ",").split(","):
        item = item.strip()
        if not item:
            continue
        if item == ip:
            return True
        try:
            if ipaddress.ip_address(ip) in ipaddress.ip_network(item, strict=False):
                return True
        except ValueError:
            continue
    return False


def _in_csv_list(name: str, csv: str) -> bool:
    items = [x.strip() for x in csv.replace("，", ",").split(",") if x.strip()]
    if not items:
        return True
    for it in items:
        if it == name or it.endswith("*") and name.startswith(it[:-1]):
            return True
    return False


def _model_display(m: dict) -> str:
    """对外可见名：有别名用别名，否则上游模型名。"""
    return m.get("alias") or m.get("upstream_model", "")


def _period_reset(k: dict):
    """周期额度重置（每日/每月），按本地自然日口径。"""
    period = k.get("period") or "none"
    if period == "none":
        return
    today_marker = repo.today_local_str() if period == "daily" else repo.today_local_str()[:7]
    if (k.get("period_anchor") or "") != today_marker:
        import asyncio
        k["period_anchor"] = today_marker
        k["used_requests"] = 0
        k["used_input_tokens"] = 0
        k["used_output_tokens"] = 0
        k["_needs_reset"] = True


async def authenticate(request: Request, requested_model: str | None = None,
                       anthropic: bool = False) -> tuple[dict | None, JSONResponse | None]:
    """按 §8.1 顺序执行 1-6 步。返回 (api_key_row, error_response)。"""
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not token:
        token = request.headers.get("x-api-key", "").strip()
    if not token:
        return None, _err(401, "invalid_request_error", "Missing API key (Authorization: Bearer ...)", anthropic)

    k = await repo.get_api_key_by_token(token)
    if not k:
        await repo.insert_log({"request_type": "forward", "protocol": "anthropic" if anthropic else "openai",
                               "key_name": token[:12] + "...", "model": requested_model or "",
                               "source_ip": _client_ip(request), "status": "auth_failed",
                               "error": "无效密钥", "http_status": 401})
        return None, _err(401, "invalid_api_key", "Invalid API key", anthropic)

    # 1) 存在性与启用
    if not k.get("enabled"):
        return None, _err(401, "invalid_api_key", "API key disabled", anthropic)

    # 过期检查
    exp = k.get("expires_at")
    if exp:
        exp_dt = parse_iso(exp)
        if exp_dt and parse_iso(repo.now_local_str()) and parse_iso(repo.now_local_str()) > exp_dt:
            return None, _err(401, "invalid_api_key", f"API key expired at {exp}", anthropic)

    # 2) IP 白名单
    ip = _client_ip(request)
    if not _ip_in_list(ip, k.get("ip_whitelist", "")):
        await repo.insert_log({"request_type": "forward", "protocol": "anthropic" if anthropic else "openai",
                               "key_name": k.get("name", ""), "model": requested_model or "",
                               "source_ip": ip, "status": "ip_blocked", "error": f"IP {ip} 不在白名单",
                               "http_status": 403})
        return None, _err(403, "permission_error", f"IP {ip} not allowed", anthropic)

    # 3) 额度检查（含周期重置）
    _period_reset(k)
    if k.pop("_needs_reset", False):
        await repo.db.execute(
            "UPDATE api_keys SET used_requests=0, used_input_tokens=0, used_output_tokens=0, period_anchor=? WHERE id=?",
            (k.get("period_anchor", ""), k["id"]))
    q_req, q_tt = k.get("quota_requests") or 0, k.get("quota_total_tokens") or 0
    q_in, q_out = k.get("quota_input_tokens") or 0, k.get("quota_output_tokens") or 0
    u_req = k.get("used_requests") or 0
    if q_req and u_req >= q_req:
        return None, _err(429, "rate_limit_error", "额度耗尽：总请求数已达上限", anthropic)
    if q_tt and (k.get("used_input_tokens", 0) + k.get("used_output_tokens", 0)) >= q_tt:
        return None, _err(429, "rate_limit_error", "额度耗尽：总 token 已达上限", anthropic)
    if q_in and k.get("used_input_tokens", 0) >= q_in:
        return None, _err(429, "rate_limit_error", "额度耗尽：输入 token 已达上限", anthropic)
    if q_out and k.get("used_output_tokens", 0) >= q_out:
        return None, _err(429, "rate_limit_error", "额度耗尽：输出 token 已达上限", anthropic)

    # 4) key 级 RPS
    limiter: RateLimiter = request.app.state.limiter
    if not limiter.allow_key(k["id"], k.get("rps") or 0):
        await repo.insert_log({"request_type": "forward", "protocol": "anthropic" if anthropic else "openai",
                               "key_name": k.get("name", ""), "model": requested_model or "",
                               "source_ip": ip, "status": "rate_limited", "error": "key 级 RPS 超限",
                               "http_status": 429})
        return None, _err(429, "rate_limit_error", "Rate limit exceeded (key RPS)", anthropic)

    # 5) 全局 RPS
    settings = await repo.get_settings()
    if not limiter.allow_global(repo.s_int(settings, "global_rps")):
        await repo.insert_log({"request_type": "forward", "protocol": "anthropic" if anthropic else "openai",
                               "key_name": k.get("name", ""), "model": requested_model or "",
                               "source_ip": ip, "status": "rate_limited", "error": "全局 RPS 超限",
                               "http_status": 429})
        return None, _err(429, "rate_limit_error", "Rate limit exceeded (global)", anthropic)

    # 6) 模型解析 + 全局黑名单
    model_row = None
    if requested_model:
        model_row = await resolve_model(requested_model)
        bl = await repo.blacklist_set()
        if requested_model in bl or (model_row and _model_display(model_row) in bl) or (
                model_row and model_row["upstream_model"] in bl):
            await repo.insert_log({"request_type": "forward", "protocol": "anthropic" if anthropic else "openai",
                                   "key_name": k.get("name", ""), "model": requested_model,
                                   "source_ip": ip, "status": "blacklisted", "error": "模型在全局黑名单",
                                   "http_status": 403})
            return None, _err(403, "permission_error", f"Model '{requested_model}' is blacklisted", anthropic)
        # key 级模型黑白名单
        if not _in_csv_list(requested_model, k.get("model_whitelist", "")):
            return None, _err(403, "permission_error", f"Model '{requested_model}' not in key whitelist", anthropic)
        if k.get("model_blacklist") and _in_csv_list(requested_model, k.get("model_blacklist", "")):
            return None, _err(403, "permission_error", f"Model '{requested_model}' is blacklisted for this key", anthropic)

    record_request_hit()
    state.model_hit(requested_model or "-")
    return k, None


async def resolve_model(requested: str) -> dict | None:
    """别名映射 -> 真实模型行。优先精确 alias，其次 upstream_model（取第一个启用渠道的）。
    auto 为特殊虚拟模型：由网关动态挑选最优 (渠道,模型)，受设置 auto_enabled 开关控制。"""
    if (requested or "").strip().lower() == "auto":
        settings = await repo.get_settings()
        if repo.s_int(settings, "auto_enabled", 1) == 1:
            return {"alias": "auto", "upstream_model": "__auto__", "enabled": 1, "channel_id": 0,
                    "vendor_tag": "auto", "emoji": "🎯"}
        return None
    models = await get_models_snapshot()
    for m in models:
        if m.get("alias") and m["alias"] == requested and m.get("enabled"):
            return m
    for m in models:
        if m["upstream_model"] == requested and m.get("enabled"):
            return m
    return None


async def get_models_snapshot() -> list[dict]:
    """启用渠道的启用模型快照（缓存 10s）。"""
    snap = cache.get("models_snapshot")
    if snap is not None:
        return snap
    rows = await db.fetchall(
        """SELECT m.*, c.name AS channel_name, c.grp AS channel_group, c.protocol, c.vendor
           FROM models m JOIN channels c ON c.id=m.channel_id
           WHERE m.enabled=1 AND c.enabled=1 ORDER BY m.sort_order, m.id""")
    cache.set("models_snapshot", rows, 10.0)
    return rows


def quota_check_post(k: dict, prompt_tokens: int, completion_tokens: int):
    """计费后检查额度告警阈值。"""
    try:
        total_used = (k.get("used_input_tokens", 0) + k.get("used_output_tokens", 0))
        q_tt = k.get("quota_total_tokens") or 0
        q_req = k.get("quota_requests") or 0
        threshold = k.get("alert_threshold") or 80
        if q_tt and total_used >= q_tt * threshold / 100 and k["id"] not in state.quota_alerted:
            state.quota_alerted.add(k["id"])
            state.push_alert("quota", f"密钥「{k.get('name')}」token 用量已达 {threshold}%")
        if q_req and (k.get("used_requests", 0) + 1) >= q_req * threshold / 100 and k["id"] not in state.quota_alerted:
            state.quota_alerted.add(k["id"])
            state.push_alert("quota", f"密钥「{k.get('name')}」请求次数已达 {threshold}%")
    except Exception:
        pass
