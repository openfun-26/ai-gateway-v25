"""客户端密钥管理 API。"""
import csv
import io

from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse

from ..core.cache import cache
from ..core.config import parse_iso, now_local_str
from ..db import repo
from ..core.state import state

router = APIRouter(prefix="/admin/api/keys", tags=["keys"])


def _decorate(k: dict) -> dict:
    """计算剩余额度与状态。"""
    from datetime import datetime
    q_req = k.get("quota_requests") or 0
    q_tt = k.get("quota_total_tokens") or 0
    used_toks = (k.get("used_input_tokens") or 0) + (k.get("used_output_tokens") or 0)
    k["remaining_requests"] = (q_req - (k.get("used_requests") or 0)) if q_req else None
    k["remaining_total_tokens"] = (q_tt - used_toks) if q_tt else None
    k["used_total_tokens"] = used_toks
    k["expired"] = bool(k.get("expires_at") and (parse_iso(k["expires_at"]) or datetime.max)
                        and parse_iso(k["expires_at"]) and parse_iso(now_local_str()) > parse_iso(k["expires_at"]))
    return k


@router.get("")
async def list_keys():
    rows = [_decorate(k) for k in await repo.list_api_keys()]
    return {"rows": rows}


@router.post("")
async def create_key(data: dict = Body(...)):
    k = await repo.create_api_key(data)
    return {"ok": True, "key": k}


@router.put("/{kid}")
async def update_key(kid: int, data: dict = Body(...)):
    await repo.update_api_key(kid, data)
    return {"ok": True}


@router.delete("/{kid}")
async def delete_key(kid: int):
    await repo.delete_api_key(kid)
    state.quota_alerted.discard(kid)
    return {"ok": True}


@router.post("/{kid}/reset-quota")
async def reset_quota(kid: int):
    await repo.reset_key_quota(kid)
    state.quota_alerted.discard(kid)
    return {"ok": True}


@router.post("/{kid}/toggle")
async def toggle_key(kid: int):
    k = await repo.get_api_key(kid)
    if not k:
        return {"ok": False, "error": "不存在"}
    await repo.update_api_key(kid, {"enabled": 0 if k["enabled"] else 1})
    return {"ok": True, "enabled": not k["enabled"]}


@router.get("/export-csv")
async def export_csv():
    rows = [_decorate(k) for k in await repo.list_api_keys()]
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(["备注", "标签", "Key", "启用", "过期时间", "已用请求数", "已用输入token", "已用输出token",
                "总额度次数", "总token额度", "周期", "RPS", "最后调用时间"])
    for k in rows:
        w.writerow([k.get("name", ""), k.get("tag", ""), k["key"], "是" if k["enabled"] else "否",
                    k.get("expires_at", ""), k.get("used_requests", 0), k.get("used_input_tokens", 0),
                    k.get("used_output_tokens", 0), k.get("quota_requests", 0), k.get("quota_total_tokens", 0),
                    k.get("period", "none"), k.get("rps", 0), k.get("last_used_at", "")])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=api_keys.csv"})
