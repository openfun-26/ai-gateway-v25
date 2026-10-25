"""路由&分流策略 API。"""
from fastapi import APIRouter, Body

from ..core.cache import cache
from ..db import repo

router = APIRouter(prefix="/admin/api/routing", tags=["routing"])


@router.get("")
async def get_routing():
    settings = await repo.get_settings()
    rules = await repo.list_routing_rules()
    return {
        "strategy": settings.get("routing_strategy", "weighted_round_robin"),
        "global_max_retries": repo.s_int(settings, "global_max_retries", 2),
        "upstream_freeze_sec": repo.s_int(settings, "upstream_freeze_sec", 60),
        "circuit_error_threshold": repo.s_float(settings, "circuit_error_threshold", 50),
        "circuit_window_sec": repo.s_int(settings, "circuit_window_sec", 60),
        "circuit_freeze_sec": repo.s_int(settings, "circuit_freeze_sec", 300),
        "auto_adaptive_weight": repo.s_int(settings, "auto_adaptive_weight") == 1,
        "rules": rules,
    }


@router.put("/global")
async def put_global(data: dict = Body(...)):
    mapping = {"strategy": "routing_strategy", "global_max_retries": "global_max_retries",
               "upstream_freeze_sec": "upstream_freeze_sec",
               "circuit_error_threshold": "circuit_error_threshold",
               "circuit_window_sec": "circuit_window_sec",
               "circuit_freeze_sec": "circuit_freeze_sec",
               "auto_adaptive_weight": "auto_adaptive_weight"}
    for src, dst in mapping.items():
        if src in data:
            v = data[src]
            if isinstance(v, bool):
                v = "1" if v else "0"
            await repo.set_setting(dst, v)
    cache.invalidate()
    return {"ok": True}


@router.post("/rules")
async def create_rule(data: dict = Body(...)):
    rid = await repo.create_routing_rule(data)
    return {"ok": True, "id": rid}


@router.put("/rules/{rid}")
async def update_rule(rid: int, data: dict = Body(...)):
    await repo.update_routing_rule(rid, data)
    return {"ok": True}


@router.delete("/rules/{rid}")
async def delete_rule(rid: int):
    await repo.delete_routing_rule(rid)
    return {"ok": True}


@router.post("/rules/{rid}/move")
async def move_rule(rid: int, data: dict = Body(...)):
    direction = data.get("direction", "up")
    rules = await repo.list_routing_rules()
    idx = next((i for i, r in enumerate(rules) if r["id"] == rid), None)
    if idx is None:
        return {"ok": False}
    swap = idx - 1 if direction == "up" else idx + 1
    if 0 <= swap < len(rules):
        a, b = rules[idx], rules[swap]
        await repo.update_routing_rule(a["id"], {"priority": b["priority"]})
        await repo.update_routing_rule(b["id"], {"priority": a["priority"]})
    return {"ok": True}
