"""系统设置 / 反代规则 / FRP / 模型黑名单 / 配置导入导出 API。"""
import asyncio
import json

from fastapi import APIRouter, Body

from ..core.cache import cache
from ..core.config import DEFAULT_SETTINGS
from ..db import repo
from ..services import frp as frp_svc
from ..services import health

router = APIRouter(prefix="/admin/api", tags=["settings"])

SETTABLE = list(DEFAULT_SETTINGS.keys())


@router.get("/settings")
async def get_settings():
    s = await repo.get_settings()
    # 脱敏 FRP 配置无需脱敏（ini 由用户提供）
    return {"settings": s, "defaults": DEFAULT_SETTINGS}


@router.put("/settings")
async def put_settings(data: dict = Body(...)):
    changed_port = False
    changed_admin_port = False
    for k, v in data.items():
        if k in SETTABLE:
            await repo.set_setting(k, v)
            if k == "port":
                changed_port = True
            if k == "admin_port":
                changed_admin_port = True
    cache.invalidate()
    msg = ""
    if changed_port:
        msg = "监听端口已保存，重启进程后生效"
    if changed_admin_port:
        msg = (msg + "；" if msg else "") + "管理台端口已保存，重启进程后生效"
    return {"ok": True, "port_changed": changed_port, "admin_port_changed": changed_admin_port,
            "message": msg}


@router.post("/settings/vacuum")
async def vacuum():
    async def _do():
        from ..core.database import db
        async with db._wlock:
            await db._w.execute("VACUUM")
            await db._w.commit()
    await _do()
    return {"ok": True}


@router.get("/settings/export")
async def export_config():
    s = await repo.get_settings()
    payload = {
        "settings": s,
        "channels": await repo.list_channels(),
        "models": await repo.list_models({}),
        "api_keys": await repo.list_api_keys(),
        "routing_rules": await repo.list_routing_rules(),
        "proxy_rules": await repo.list_proxy_rules(),
        "model_blacklist": await repo.list_blacklist(),
    }
    for ch in payload["channels"]:
        ch.pop("id", None)
    for m in payload["models"]:
        m.pop("id", None)
    return payload


@router.post("/settings/import")
async def import_config(data: dict = Body(...)):
    """覆盖式导入。"""
    from ..core.database import db
    mode = data.get("mode", "overwrite")
    settings = data.get("settings") or {}
    for k, v in settings.items():
        if k in SETTABLE:
            await repo.set_setting(k, v)
    if mode == "overwrite":
        await db.execute("DELETE FROM channels")
        await db.execute("DELETE FROM models")
        await db.execute("DELETE FROM api_keys")
        await db.execute("DELETE FROM routing_rules")
        await db.execute("DELETE FROM proxy_rules")
        await db.execute("DELETE FROM model_blacklist")
    old_cid_map = {}
    for ch in data.get("channels") or []:
        new_id = await repo.create_channel(ch)
        old_cid_map[ch.get("_id")] = new_id
    for m in data.get("models") or []:
        m["channel_id"] = old_cid_map.get(m.get("channel_id"), m.get("channel_id"))
        await repo.create_model(m)
    for k in data.get("api_keys") or []:
        await repo.create_api_key(k)
    for r in data.get("routing_rules") or []:
        await repo.create_routing_rule(r)
    for r in data.get("proxy_rules") or []:
        await repo.create_proxy_rule(r)
    for b in data.get("model_blacklist") or []:
        await repo.add_blacklist(b.get("model", ""), b.get("reason", ""))
    cache.invalidate()
    return {"ok": True}


# ============ 反代规则 ============

@router.get("/proxy-rules")
async def list_proxy_rules():
    return {"rows": await repo.list_proxy_rules()}


@router.post("/proxy-rules")
async def create_proxy_rule(data: dict = Body(...)):
    rid = await repo.create_proxy_rule(data)
    return {"ok": True, "id": rid}


@router.put("/proxy-rules/{rid}")
async def update_proxy_rule(rid: int, data: dict = Body(...)):
    await repo.update_proxy_rule(rid, data)
    return {"ok": True}


@router.delete("/proxy-rules/{rid}")
async def delete_proxy_rule(rid: int):
    await repo.delete_proxy_rule(rid)
    return {"ok": True}


# ============ 模型黑名单 ============

@router.get("/blacklist")
async def list_blacklist():
    return {"rows": await repo.list_blacklist()}


@router.post("/blacklist")
async def add_blacklist(data: dict = Body(...)):
    await repo.add_blacklist(data.get("model", ""), data.get("reason", ""))
    cache.invalidate()
    return {"ok": True}


@router.delete("/blacklist/{bid}")
async def del_blacklist(bid: int):
    await repo.remove_blacklist(bid)
    cache.invalidate()
    return {"ok": True}


# ============ FRP ============

@router.get("/frp/config")
async def frp_get_config():
    ini = await repo.get_setting("frp_config", "")
    autostart = repo.s_int(await repo.get_settings(), "frp_autostart") == 1
    return {"config": ini, "autostart": autostart, "validation": frp_svc.frp.validate_ini(ini)}


@router.put("/frp/config")
async def frp_save_config(data: dict = Body(...)):
    result = await frp_svc.frp.save_config(data.get("config", ""))
    if "autostart" in data:
        await repo.set_setting("frp_autostart", 1 if data["autostart"] else 0)
    return {"ok": True, "validation": result}


@router.get("/frp/status")
async def frp_status():
    return frp_svc.frp.status()


@router.post("/frp/start")
async def frp_start():
    return await frp_svc.frp.start()


@router.post("/frp/stop")
async def frp_stop():
    return await frp_svc.frp.stop()


@router.get("/frp/logs")
async def frp_logs():
    return {"logs": frp_svc.frp.get_logs()}


@router.post("/frp/logs/clear")
async def frp_clear_logs():
    frp_svc.frp.clear_logs()
    return {"ok": True}


# ============ 引导信息（主题默认等） ============

@router.get("/bootstrap")
async def bootstrap():
    s = await repo.get_settings()
    return {"theme_default": s.get("theme_default", "light"),
            "accent_default": s.get("accent_default", "teal"),
            "port": s.get("port", "9010")}
