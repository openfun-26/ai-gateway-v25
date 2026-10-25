"""模型监控 API。"""
import asyncio
import csv
import io

from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse

from ..core.cache import cache
from ..core.database import db
from ..db import repo
from ..services import health

router = APIRouter(prefix="/admin/api/models", tags=["models"])


@router.get("")
async def list_models(channel_id: int = None, search: str = "", status: str = "",
                      vendor: str = "", group: str = ""):
    rows = await repo.list_models({"channel_id": channel_id, "search": search, "status": status,
                                   "vendor": vendor, "group": group})
    return {"rows": rows}


@router.post("")
async def create_model(data: dict = Body(...)):
    mid = await repo.create_model(data)
    cache.invalidate()
    return {"ok": True, "id": mid}


@router.put("/{model_id}")
async def update_model(model_id: int, data: dict = Body(...)):
    await repo.update_model(model_id, data)
    cache.invalidate()
    return {"ok": True}


@router.delete("/{model_id}")
async def delete_model(model_id: int):
    await repo.delete_model(model_id)
    cache.invalidate()
    return {"ok": True}


@router.post("/reorder")
async def reorder_model(data: dict = Body(...)):
    """上移/下移模型：交换相邻排序值，决定 auto 规则外的备选降级顺序。"""
    mid = int(data.get("id") or 0)
    direction = data.get("direction")  # "up" | "down"
    if not mid or direction not in ("up", "down"):
        return {"ok": False, "error": "参数错误"}
    rows = await db.fetchall("SELECT id, sort_order FROM models ORDER BY sort_order, id")
    ids = [r["id"] for r in rows]
    if mid not in ids:
        return {"ok": False, "error": "模型不存在"}
    i = ids.index(mid)
    j = i - 1 if direction == "up" else i + 1
    if j < 0 or j >= len(ids):
        return {"ok": True, "moved": False}
    ids[i], ids[j] = ids[j], ids[i]
    for idx, model_id in enumerate(ids):
        await db.execute("UPDATE models SET sort_order=? WHERE id=?", (idx + 1, model_id))
    cache.invalidate()
    return {"ok": True, "moved": True}


@router.get("/auto-rules")
async def list_auto_rules():
    rows = await db.fetchall("SELECT * FROM auto_rules ORDER BY priority, id")
    return {"rows": rows}


@router.post("/auto-rules")
async def create_auto_rule(data: dict = Body(...)):
    keyword = (data.get("keyword") or "").strip()
    model_name = (data.get("model_name") or "").strip()
    if not keyword or not model_name:
        return {"ok": False, "error": "关键词与目标模型不能为空"}
    await db.execute(
        "INSERT INTO auto_rules(keyword, model_name, priority, enabled, created_at) VALUES(?,?,?,?,?)",
        (keyword, model_name, int(data.get("priority") or 0), 1 if data.get("enabled", 1) else 0,
         __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    return {"ok": True}


@router.put("/auto-rules/{rule_id}")
async def update_auto_rule(rule_id: int, data: dict = Body(...)):
    fields, vals = [], []
    for f in ("keyword", "model_name", "priority", "enabled"):
        if f in data:
            fields.append(f"{f}=?")
            vals.append(int(data[f]) if f in ("priority", "enabled") else str(data[f]))
    if fields:
        vals.append(rule_id)
        await db.execute(f"UPDATE auto_rules SET {', '.join(fields)} WHERE id=?", vals)
    return {"ok": True}


@router.delete("/auto-rules/{rule_id}")
async def delete_auto_rule(rule_id: int):
    await db.execute("DELETE FROM auto_rules WHERE id=?", (rule_id,))
    return {"ok": True}


@router.post("/health-check-all")
async def hc_all():
    started = health.start_background_check(repo.s_int(await repo.get_settings(), "health_timeout_sec", 15))
    return {"ok": True, "started": started, "message": "" if started else "检测任务已在进行中"}


@router.post("/health-check-channel/{channel_id}")
async def hc_channel(channel_id: int):
    settings = await repo.get_settings()
    n = await health.check_channel_models(channel_id, repo.s_int(settings, "health_timeout_sec", 15))
    return {"ok": True, "checked": n}


@router.post("/test")
async def test_model(data: dict = Body(...)):
    """单模型测试：自定义 prompt，返回响应内容 + 耗时 + token。"""
    import json
    import time
    channel = await repo.get_channel(int(data.get("channel_id") or 0))
    if not channel:
        return {"ok": False, "error": "渠道不存在"}
    model_name = data.get("model") or ""
    prompt = data.get("prompt") or "Hello, 请回复 'pong'"
    up_proto = channel.get("protocol", "openai")
    payload = ({"model": model_name, "max_tokens": 256,
                "messages": [{"role": "user", "content": prompt}]}
               if up_proto == "anthropic" else
               {"model": model_name, "max_tokens": 256,
                "messages": [{"role": "user", "content": prompt}]})
    path = "/v1/messages" if up_proto == "anthropic" else "/chat/completions"
    t0 = time.monotonic()
    from ..services import upstream
    resp, err = await upstream.call_upstream(channel, path, payload)
    latency = int((time.monotonic() - t0) * 1000)
    if err:
        return {"ok": False, "error": err, "latency_ms": latency}
    if resp.status_code >= 400:
        text = (await resp.aread()).decode("utf-8", "ignore")
        return {"ok": False, "error": f"HTTP {resp.status_code}: {text[:500]}", "latency_ms": latency,
                "http_status": resp.status_code}
    data_out = resp.json()
    pt, ct = upstream.extract_usage(data_out, up_proto)
    if up_proto == "anthropic":
        content = "".join(b.get("text", "") for b in data_out.get("content", []) if isinstance(b, dict))
    else:
        msg = (data_out.get("choices") or [{}])[0].get("message") or {}
        content = msg.get("content") or ""
    return {"ok": True, "content": content, "latency_ms": latency, "prompt_tokens": pt,
            "completion_tokens": ct, "http_status": resp.status_code}


@router.post("/batch")
async def batch_update(data: dict = Body(...)):
    action = data.get("action")
    ids = data.get("ids") or []
    value = data.get("value")
    for mid in ids:
        if action == "enable":
            await repo.update_model(mid, {"enabled": 1})
        elif action == "disable":
            await repo.update_model(mid, {"enabled": 0})
        elif action == "set_remark":
            await repo.update_model(mid, {"remark": str(value or "")})
        elif action == "set_vendor":
            await repo.update_model(mid, {"vendor_tag": str(value or "")})
        elif action == "delete":
            await repo.delete_model(mid)
    cache.invalidate()
    return {"ok": True, "affected": len(ids)}


@router.get("/export-csv")
async def export_csv():
    rows = await repo.list_models({})
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(["渠道分组", "渠道名称", "模型ID", "对外别名", "状态", "厂商标签", "emoji",
                "最近检测HTTP状态码", "平均耗时ms", "上次检测时间", "备注"])
    for r in rows:
        w.writerow([r.get("channel_group", ""), r.get("channel_name", ""), r["upstream_model"],
                    r.get("alias", ""), r.get("status", ""), r.get("vendor_tag", ""), r.get("emoji", ""),
                    r.get("last_http_status", ""), r.get("latency_ms", ""), r.get("last_check_time", ""),
                    r.get("remark", "")])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=models.csv"})


@router.post("/discover")
async def discover_models(data: dict = Body(...)):
    """从指定渠道拉取 /models 列表补录模型表。"""
    from ..services import upstream
    channel = await repo.get_channel(int(data.get("channel_id") or 0))
    if not channel:
        return {"ok": False, "error": "渠道不存在"}
    client = upstream.get_client(channel)
    base = (channel.get("base_url") or "").rstrip("/")
    if channel.get("protocol") == "openai" and not base.endswith("/v1") and "/v1" not in base:
        base += "/v1"
    try:
        resp = await client.get(base + "/models", headers=upstream.build_headers(channel))
        data_out = resp.json()
        ids = [m.get("id") for m in data_out.get("data", []) if m.get("id")]
    except Exception as e:
        return {"ok": False, "error": str(e)}
    added = 0
    for mid in ids:
        row = await db.fetchone("SELECT id FROM models WHERE channel_id=? AND upstream_model=?",
                                (channel["id"], mid))
        if not row:
            await repo.create_model({"channel_id": channel["id"], "upstream_model": mid,
                                     "vendor_tag": channel.get("vendor", "")})
            added += 1
    cache.invalidate()
    return {"ok": True, "added": added, "total": len(ids)}
