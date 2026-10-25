"""上游渠道管理 API。"""
import csv
import io
import json

from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse

from ..core.cache import cache
from ..core.database import db
from ..db import repo
from ..core.state import state

router = APIRouter(prefix="/admin/api/channels", tags=["channels"])


@router.get("")
async def list_channels():
    rows = await repo.list_channels()
    # 附加模型数
    counts = {r["channel_id"]: r["n"] for r in await db.fetchall(
        "SELECT channel_id, COUNT(*) AS n FROM models GROUP BY channel_id")}
    for r in rows:
        r["model_count"] = counts.get(r["id"], 0)
    return {"rows": rows}


@router.post("")
async def create_channel(data: dict = Body(...)):
    cid = await repo.create_channel(data)
    cache.invalidate()
    # 自动拉取模型列表（可选）
    return {"ok": True, "id": cid}


@router.put("/{cid}")
async def update_channel(cid: int, data: dict = Body(...)):
    await repo.update_channel(cid, data)
    cache.invalidate()
    return {"ok": True}


@router.delete("/{cid}")
async def delete_channel(cid: int):
    await repo.delete_channel(cid)
    cache.invalidate()
    return {"ok": True}


@router.post("/{cid}/duplicate")
async def duplicate_channel(cid: int):
    ch = await repo.get_channel(cid)
    if not ch:
        return {"ok": False, "error": "渠道不存在"}
    ch.pop("id", None)
    ch.pop("created_at", None)
    ch["name"] = ch["name"] + "-副本"
    ch["api_key_masked"] = None
    new_id = await repo.create_channel(ch)
    # 复制模型
    models = await db.fetchall("SELECT * FROM models WHERE channel_id=?", (cid,))
    for m in models:
        await repo.create_model({"channel_id": new_id, "upstream_model": m["upstream_model"],
                                 "alias": m.get("alias", ""), "vendor_tag": m.get("vendor_tag", ""),
                                 "emoji": m.get("emoji", ""), "grp": m.get("grp", "default"),
                                 "remark": m.get("remark", ""), "enabled": m.get("enabled", 1),
                                 "skip_health": m.get("skip_health", 0),
                                 "prefer_group": m.get("prefer_group", "")})
    cache.invalidate()
    return {"ok": True, "id": new_id}


@router.post("/{cid}/test")
async def test_channel(cid: int, data: dict = Body(...)):
    import time
    from ..services import upstream
    channel = await repo.get_channel(cid)
    if not channel:
        return {"ok": False, "error": "渠道不存在"}
    model_name = data.get("model") or "gpt-4o-mini"
    prompt = data.get("prompt") or "Hello, 请回复 'pong'"
    up_proto = channel.get("protocol", "openai")
    payload = {"model": model_name, "max_tokens": 256,
               "messages": [{"role": "user", "content": prompt}]}
    path = "/v1/messages" if up_proto == "anthropic" else "/chat/completions"
    t0 = time.monotonic()
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


@router.post("/{cid}/fetch-models")
async def fetch_models(cid: int):
    """从上游拉取可用模型列表（OpenAI: GET /models；Anthropic: GET /v1/models）。"""
    from ..services import upstream
    channel = await repo.get_channel(cid)
    if not channel:
        return {"ok": False, "error": "渠道不存在"}
    proto = channel.get("protocol", "openai")
    base = (channel.get("base_url") or "").rstrip("/")
    if proto == "anthropic":
        url = (base if base.endswith("/v1") else base + "/v1") + "/models?limit=1000"
    else:
        url = upstream.upstream_url(channel, "/models")
    resp, err = await upstream.call_upstream_get(channel, url, timeout=15.0)
    if err:
        return {"ok": False, "error": err}
    if resp.status_code >= 400:
        text = (await resp.aread()).decode("utf-8", "ignore")
        return {"ok": False, "error": f"HTTP {resp.status_code}: {text[:300]}", "http_status": resp.status_code}
    try:
        data = resp.json()
    except Exception:
        return {"ok": False, "error": "上游返回非 JSON 内容"}
    ids = []
    for m in (data.get("data") or []):
        if isinstance(m, dict) and m.get("id"):
            ids.append(str(m["id"]))
        elif isinstance(m, str):
            ids.append(m)
    return {"ok": True, "models": sorted(set(ids))}


@router.post("/{cid}/import-models")
async def import_models(cid: int, data: dict = Body(...)):
    """把模型批量挂到渠道下（自动跳过已存在的）。"""
    names = [str(m).strip() for m in (data.get("models") or []) if str(m).strip()]
    if not names:
        return {"ok": False, "error": "未选择任何模型"}
    if not await repo.get_channel(cid):
        return {"ok": False, "error": "渠道不存在"}
    existing = {r["upstream_model"] for r in await db.fetchall(
        "SELECT upstream_model FROM models WHERE channel_id=?", (cid,))}
    added = skipped = 0
    for n in dict.fromkeys(names):
        if n in existing:
            skipped += 1
            continue
        await repo.create_model({"channel_id": cid, "upstream_model": n, "alias": n})
        existing.add(n)
        added += 1
    cache.invalidate()
    return {"ok": True, "added": added, "skipped": skipped}


@router.post("/batch")
async def batch(data: dict = Body(...)):
    action, ids = data.get("action"), data.get("ids") or []
    for cid in ids:
        if action == "enable":
            await repo.update_channel(cid, {"enabled": 1})
        elif action == "disable":
            await repo.update_channel(cid, {"enabled": 0})
        elif action == "delete":
            await repo.delete_channel(cid)
    cache.invalidate()
    return {"ok": True, "affected": len(ids)}


@router.post("/import")
async def import_channels(data: dict = Body(...)):
    """批量导入：每行 JSON 或 名称|分组|base_url|key|协议 管道分隔。"""
    text = data.get("text") or ""
    added, errors = 0, []
    for i, line in enumerate(text.strip().splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            if line.startswith("{"):
                obj = json.loads(line)
                await repo.create_channel(obj)
                added += 1
            else:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 4:
                    errors.append(f"第{i+1}行: 字段不足（需要 名称|分组|base_url|key|协议）")
                    continue
                await repo.create_channel({
                    "name": parts[0], "grp": parts[1], "base_url": parts[2],
                    "api_key": parts[3], "protocol": (parts[4] if len(parts) > 4 else "openai")})
                added += 1
        except Exception as e:
            errors.append(f"第{i+1}行: {e}")
    cache.invalidate()
    return {"ok": True, "added": added, "errors": errors}


@router.get("/groups")
async def groups():
    rows = await db.fetchall("SELECT DISTINCT grp FROM channels ORDER BY grp")
    return {"groups": [r["grp"] for r in rows]}
