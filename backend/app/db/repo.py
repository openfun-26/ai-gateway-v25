"""数据访问层：settings / channels / models / api_keys / logs / rules。"""
import json
import secrets
from typing import Any, Optional

from ..core.cache import cache
from ..core.config import DEFAULT_SETTINGS, now_local_str, today_local_str, mask_key
from ..core.database import db
from ..core.state import state

# ============ settings ============

async def get_settings() -> dict:
    rows = await db.fetchall("SELECT key, value FROM settings")
    s = {k: v for k, v in DEFAULT_SETTINGS.items()}
    for r in rows:
        s[r["key"]] = r["value"]
    return s

async def get_setting(key: str, default: str = "") -> str:
    row = await db.fetchone("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row else str(DEFAULT_SETTINGS.get(key, default))

async def set_setting(key: str, value: Any):
    await db.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value) if not isinstance(value, str) else value),
    )

async def set_settings_many(d: dict):
    for k, v in d.items():
        await set_setting(k, v)

def s_int(settings: dict, key: str, default: int = 0) -> int:
    try:
        return int(float(settings.get(key, default)))
    except Exception:
        return default

def s_float(settings: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(settings.get(key, default))
    except Exception:
        return default

# ============ channels ============

CHANNEL_FIELDS = ["name", "grp", "vendor", "base_url", "api_key", "protocol", "enabled",
                  "timeout_ms", "weight", "max_concurrency", "max_retries", "cooldown_sec",
                  "http_proxy", "extra_headers", "retry_status_codes", "silent_degrade",
                  "model_whitelist", "model_blacklist", "cb_error_threshold", "cb_window_sec",
                  "cb_freeze_sec", "paid"]

def _norm_channel(d: dict) -> dict:
    out = {}
    for f in CHANNEL_FIELDS:
        v = d.get(f)
        if v is None:
            continue
        if f in ("extra_headers", "retry_status_codes") and not isinstance(v, str):
            out[f] = json.dumps(v, ensure_ascii=False)
        elif f in ("enabled", "silent_degrade", "paid"):
            out[f] = 1 if v else 0
        elif f in ("timeout_ms", "weight", "max_concurrency", "max_retries", "cooldown_sec", "cb_window_sec", "cb_freeze_sec"):
            out[f] = int(v or 0)
        elif f == "cb_error_threshold":
            out[f] = float(v or 0)
        else:
            out[f] = str(v)
    return out

async def list_channels(enabled_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM channels"
    if enabled_only:
        sql += " WHERE enabled=1"
    sql += " ORDER BY id"
    rows = await db.fetchall(sql)
    for r in rows:
        r["api_key_masked"] = mask_key(r.get("api_key", ""))
        rt = state.channels.get(r["id"])
        if rt:
            r.update(rt.to_row())
        else:
            r.update({"current_concurrency": 0, "today_requests": r.get("today_requests", 0),
                      "today_failures": r.get("today_failures", 0), "avg_latency_ms": 0,
                      "circuit_state": "closed", "success_rate": 100.0})
    return rows

async def get_channel(cid: int) -> Optional[dict]:
    r = await db.fetchone("SELECT * FROM channels WHERE id=?", (cid,))
    if r:
        r["api_key_masked"] = mask_key(r.get("api_key", ""))
    return r

async def create_channel(d: dict) -> int:
    data = _norm_channel(d)
    data.setdefault("created_at", now_local_str())
    cols = ",".join(data.keys())
    marks = ",".join("?" for _ in data)
    cid = await db.execute(f"INSERT INTO channels({cols}) VALUES({marks})", tuple(data.values()))
    cache.invalidate("channels")
    return cid

async def update_channel(cid: int, d: dict):
    data = _norm_channel(d)
    if not data:
        return
    sets = ",".join(f"{k}=?" for k in data)
    await db.execute(f"UPDATE channels SET {sets} WHERE id=?", (*data.values(), cid))
    cache.invalidate("channels")

async def delete_channel(cid: int):
    await db.execute("DELETE FROM channels WHERE id=?", (cid,))
    await db.execute("DELETE FROM models WHERE channel_id=?", (cid,))
    state.drop_channel(cid)
    cache.invalidate("channels")
    cache.invalidate("models")

async def restore_channel_daily(today: str):
    """重启后把渠道今日计数与当日对齐（若 DB 记录是旧的一天则清零）。"""
    rows = await db.fetchall("SELECT id, today_requests, today_failures FROM channels")
    # 以最近一次日志日期判断；简单策略：重启即保留 DB 值（写入时机见 forward），
    # 由调用方日切任务负责清零。
    for r in rows:
        rt = state.ch(r["id"])
        rt.today_requests = r["today_requests"] or 0
        rt.today_failures = r["today_failures"] or 0

async def persist_channel_daily():
    for cid, rt in state.channels.items():
        if rt.today_requests or rt.today_failures:
            await db.execute("UPDATE channels SET today_requests=?, today_failures=? WHERE id=?",
                             (rt.today_requests, rt.today_failures, cid))

# ============ models ============

async def list_models(filters: dict | None = None) -> list[dict]:
    sql = """SELECT m.*, c.name AS channel_name, c.grp AS channel_group, c.enabled AS channel_enabled
             FROM models m LEFT JOIN channels c ON c.id = m.channel_id WHERE 1=1"""
    params: list = []
    f = filters or {}
    if f.get("channel_id"):
        sql += " AND m.channel_id=?"
        params.append(f["channel_id"])
    if f.get("search"):
        sql += " AND (m.upstream_model LIKE ? OR m.alias LIKE ?)"
        kw = f"%{f['search']}%"
        params += [kw, kw]
    if f.get("status"):
        sql += " AND m.status=?"
        params.append(f["status"])
    if f.get("vendor"):
        sql += " AND m.vendor_tag=?"
        params.append(f["vendor"])
    if f.get("group"):
        sql += " AND c.grp=?"
        params.append(f["group"])
    sql += " ORDER BY m.id"
    return await db.fetchall(sql, params)

async def get_model(mid: int) -> Optional[dict]:
    return await db.fetchone("SELECT * FROM models WHERE id=?", (mid,))

async def create_model(d: dict) -> int:
    return await db.execute(
        """INSERT INTO models(channel_id, upstream_model, alias, vendor_tag, emoji, grp, enabled,
           remark, skip_health, prefer_group) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (d.get("channel_id"), d.get("upstream_model", ""), d.get("alias", ""), d.get("vendor_tag", ""),
         d.get("emoji", ""), d.get("grp", "default"), 1 if d.get("enabled", 1) else 0,
         d.get("remark", ""), 1 if d.get("skip_health") else 0, d.get("prefer_group", "")))

async def update_model(mid: int, d: dict):
    fields = ["upstream_model", "alias", "vendor_tag", "emoji", "grp", "enabled", "remark",
              "skip_health", "prefer_group", "status", "last_http_status", "latency_ms", "last_check_time", "channel_id"]
    data = {}
    for f in fields:
        if f in d:
            v = d[f]
            if f in ("enabled", "skip_health"):
                v = 1 if v else 0
            data[f] = v
    if not data:
        return
    sets = ",".join(f"{k}=?" for k in data)
    await db.execute(f"UPDATE models SET {sets} WHERE id=?", (*data.values(), mid))
    cache.invalidate("models_list")

async def delete_model(mid: int):
    await db.execute("DELETE FROM models WHERE id=?", (mid,))
    cache.invalidate("models_list")

async def add_model_if_missing(channel_id: int, upstream_model: str, vendor_tag: str = "", emoji: str = ""):
    row = await db.fetchone("SELECT id FROM models WHERE channel_id=? AND upstream_model=?",
                            (channel_id, upstream_model))
    if not row:
        await create_model({"channel_id": channel_id, "upstream_model": upstream_model,
                            "vendor_tag": vendor_tag, "emoji": emoji})

# ============ api_keys ============

async def list_api_keys() -> list[dict]:
    return await db.fetchall("SELECT * FROM api_keys ORDER BY id")

async def get_api_key_by_token(token: str) -> Optional[dict]:
    return await db.fetchone("SELECT * FROM api_keys WHERE key=?", (token,))

async def get_api_key(kid: int) -> Optional[dict]:
    return await db.fetchone("SELECT * FROM api_keys WHERE id=?", (kid,))

KEY_FIELDS = ["name", "tag", "enabled", "expires_at", "quota_requests", "quota_total_tokens",
              "quota_input_tokens", "quota_output_tokens", "period", "rps", "model_whitelist",
              "model_blacklist", "ip_whitelist", "alert_threshold"]

def _norm_key(d: dict) -> dict:
    out = {}
    for f in KEY_FIELDS:
        if f not in d:
            continue
        v = d[f]
        if f == "enabled":
            out[f] = 1 if v else 0
        elif f in ("quota_requests", "quota_total_tokens", "quota_input_tokens", "quota_output_tokens", "rps", "alert_threshold"):
            out[f] = int(v or 0)
        else:
            out[f] = str(v or "")
    return out

async def create_api_key(d: dict) -> dict:
    data = _norm_key(d)
    token = d.get("key") or ("sk-gw-" + secrets.token_hex(16))
    data["key"] = token
    data.setdefault("created_at", now_local_str())
    cols = ",".join(data.keys())
    marks = ",".join("?" for _ in data)
    kid = await db.execute(f"INSERT INTO api_keys({cols}) VALUES({marks})", tuple(data.values()))
    return await get_api_key(kid)

async def update_api_key(kid: int, d: dict):
    data = _norm_key(d)
    if not data:
        return
    sets = ",".join(f"{k}=?" for k in data)
    await db.execute(f"UPDATE api_keys SET {sets} WHERE id=?", (*data.values(), kid))

async def delete_api_key(kid: int):
    await db.execute("DELETE FROM api_keys WHERE id=?", (kid,))

async def reset_key_quota(kid: int):
    await db.execute("""UPDATE api_keys SET used_requests=0, used_input_tokens=0,
                        used_output_tokens=0, period_anchor='' WHERE id=?""", (kid,))

async def bump_key_usage(kid: int, prompt_tokens: int, completion_tokens: int):
    await db.execute("""UPDATE api_keys SET used_requests=used_requests+1,
        used_input_tokens=used_input_tokens+?, used_output_tokens=used_output_tokens+?,
        last_used_at=? WHERE id=?""", (prompt_tokens, completion_tokens, now_local_str(), kid))

# ============ logs ============

async def insert_log(d: dict):
    await db.execute(
        """INSERT INTO logs(ts, request_type, protocol, key_name, model, vendor_tag, source_ip,
           channel, latency_ms, prompt_tokens, completion_tokens, http_status, status, error,
           request_payload, response_payload)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (d.get("ts") or now_local_str(), d.get("request_type", "forward"), d.get("protocol", "openai"),
         d.get("key_name", ""), d.get("model", ""), d.get("vendor_tag", ""), d.get("source_ip", ""),
         d.get("channel", ""), int(d.get("latency_ms") or 0), int(d.get("prompt_tokens") or 0),
         int(d.get("completion_tokens") or 0), int(d.get("http_status") or 0), d.get("status", "success"),
         (d.get("error") or "")[:2000], (d.get("request_payload") or "")[:16000],
         (d.get("response_payload") or "")[:16000]))

def _logs_where(f: dict) -> tuple[str, list]:
    sql, params = " WHERE 1=1", []
    if f.get("start"):
        sql += " AND ts>=?"
        params.append(f["start"])
    if f.get("end"):
        sql += " AND ts<=?"
        params.append(f["end"] + " 23:59:59" if len(str(f["end"])) == 10 else f["end"])
    if f.get("key_name"):
        sql += " AND key_name=?"
        params.append(f["key_name"])
    if f.get("model"):
        sql += " AND model LIKE ?"
        params.append(f"%{f['model']}%")
    if f.get("vendor"):
        sql += " AND vendor_tag=?"
        params.append(f["vendor"])
    if f.get("channel"):
        sql += " AND channel=?"
        params.append(f["channel"])
    if f.get("request_type"):
        sql += " AND request_type=?"
        params.append(f["request_type"])
    if f.get("status"):
        sql += " AND status=?"
        params.append(f["status"])
    elif f.get("errors_only"):
        sql += " AND status NOT IN ('success')"
    if f.get("q"):
        sql += " AND (error LIKE ? OR model LIKE ? OR key_name LIKE ? OR channel LIKE ? OR request_payload LIKE ?)"
        kw = f"%{f['q']}%"
        params += [kw, kw, kw, kw, kw]
    return sql, params

async def list_logs(f: dict, page: int = 1, size: int = 50) -> dict:
    where, params = _logs_where(f)
    total = await db.scalar("SELECT COUNT(*) FROM logs" + where, params)
    rows = await db.fetchall(
        f"SELECT id,ts,request_type,protocol,key_name,model,vendor_tag,source_ip,channel,latency_ms,"
        f"prompt_tokens,completion_tokens,http_status,status,error FROM logs{where} "
        f"ORDER BY id DESC LIMIT ? OFFSET ?", (*params, size, (page - 1) * size))
    return {"total": total, "rows": rows}

async def get_log(log_id: int) -> Optional[dict]:
    return await db.fetchone("SELECT * FROM logs WHERE id=?", (log_id,))

async def delete_log(log_id: int):
    await db.execute("DELETE FROM logs WHERE id=?", (log_id,))

async def delete_logs_batch(ids: list[int]):
    if not ids:
        return
    marks = ",".join("?" for _ in ids)
    await db.execute(f"DELETE FROM logs WHERE id IN ({marks})", ids)

async def clear_logs(errors_only: bool = False):
    if errors_only:
        await db.execute("DELETE FROM logs WHERE status!='success'")
    else:
        await db.execute("DELETE FROM logs")

async def logs_for_export(f: dict, limit: int = 100000) -> list[dict]:
    where, params = _logs_where(f)
    return await db.fetchall("SELECT * FROM logs" + where + " ORDER BY id DESC LIMIT ?", (*params, limit))

async def cleanup_logs(retention_days: int, max_rows: int):
    if retention_days > 0:
        from .config import parse_iso
        import datetime
        cutoff = (datetime.datetime.utcnow() + datetime.timedelta(hours=8) - datetime.timedelta(days=retention_days)).strftime("%Y-%m-%d %H:%M:%S")
        await db.execute("DELETE FROM logs WHERE ts < ?", (cutoff,))
    if max_rows > 0:
        cnt = await db.scalar("SELECT COUNT(*) FROM logs")
        if cnt > max_rows:
            await db.execute("DELETE FROM logs WHERE id IN (SELECT id FROM logs ORDER BY id ASC LIMIT ?)",
                             (cnt - max_rows,))

# ============ routing rules ============

async def list_routing_rules() -> list[dict]:
    return await db.fetchall("SELECT * FROM routing_rules ORDER BY priority, id")

async def create_routing_rule(d: dict) -> int:
    return await db.execute(
        "INSERT INTO routing_rules(priority, match_type, match_value, target_group, enabled) VALUES(?,?,?,?,?)",
        (int(d.get("priority") or 0), d.get("match_type", "model"), d.get("match_value", ""),
         d.get("target_group", ""), 1 if d.get("enabled", 1) else 0))

async def update_routing_rule(rid: int, d: dict):
    data = {}
    for f in ("priority", "match_type", "match_value", "target_group", "enabled"):
        if f in d:
            data[f] = 1 if d[f] else 0 if f == "enabled" else (int(d[f] or 0) if f == "priority" else d[f])
    if not data:
        return
    sets = ",".join(f"{k}=?" for k in data)
    await db.execute(f"UPDATE routing_rules SET {sets} WHERE id=?", (*data.values(), rid))

async def delete_routing_rule(rid: int):
    await db.execute("DELETE FROM routing_rules WHERE id=?", (rid,))

# ============ proxy rules ============

async def list_proxy_rules(enabled_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM proxy_rules"
    if enabled_only:
        sql += " WHERE enabled=1"
    sql += " ORDER BY id"
    rows = await db.fetchall(sql)
    for r in rows:
        r["api_key_masked"] = mask_key(r.get("api_key", ""))
    return rows

async def create_proxy_rule(d: dict) -> int:
    return await db.execute(
        "INSERT INTO proxy_rules(name, path_prefix, target_url, api_key, vendor_tag, enabled) VALUES(?,?,?,?,?,?)",
        (d.get("name", ""), d.get("path_prefix", ""), d.get("target_url", ""), d.get("api_key", ""),
         d.get("vendor_tag", ""), 1 if d.get("enabled", 1) else 0))

async def update_proxy_rule(rid: int, d: dict):
    data = {}
    for f in ("name", "path_prefix", "target_url", "api_key", "vendor_tag", "enabled"):
        if f in d:
            data[f] = 1 if d[f] else 0 if f == "enabled" else d[f]
    if not data:
        return
    sets = ",".join(f"{k}=?" for k in data)
    await db.execute(f"UPDATE proxy_rules SET {sets} WHERE id=?", (*data.values(), rid))

async def delete_proxy_rule(rid: int):
    await db.execute("DELETE FROM proxy_rules WHERE id=?", (rid,))

# ============ model blacklist ============

async def list_blacklist() -> list[dict]:
    return await db.fetchall("SELECT * FROM model_blacklist ORDER BY id")

async def add_blacklist(model: str, reason: str = ""):
    await db.execute("INSERT INTO model_blacklist(model, reason) VALUES(?,?) ON CONFLICT(model) DO NOTHING",
                     (model, reason))

async def remove_blacklist(bid: int):
    await db.execute("DELETE FROM model_blacklist WHERE id=?", (bid,))

async def blacklist_set() -> set[str]:
    rows = await db.fetchall("SELECT model FROM model_blacklist")
    return {r["model"] for r in rows}

# ============ 重置统计 ============

async def reset_all_stats():
    await db.execute("DELETE FROM logs")
    await db.execute("UPDATE channels SET today_requests=0, today_failures=0")
    await db.execute("UPDATE api_keys SET used_requests=0, used_input_tokens=0, used_output_tokens=0")
    for rt in state.channels.values():
        rt.today_requests = 0
        rt.today_failures = 0
    state.quota_alerted.clear()
    cache.invalidate()
