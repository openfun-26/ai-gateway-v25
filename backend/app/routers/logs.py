"""调用日志 / 错误日志 API。"""
import csv
import io

from fastapi import APIRouter, Body, Query
from fastapi.responses import StreamingResponse

from ..db import repo

router = APIRouter(prefix="/admin/api/logs", tags=["logs"])


def _filters(**kw) -> dict:
    return {k: v for k, v in kw.items() if v not in (None, "", "all")}


@router.get("")
async def list_logs(page: int = 1, size: int = 50, start: str = "", end: str = "",
                    key_name: str = "", model: str = "", vendor: str = "", channel: str = "",
                    request_type: str = "", status: str = "", q: str = ""):
    f = _filters(start=start, end=end, key_name=key_name, model=model, vendor=vendor,
                 channel=channel, request_type=request_type, status=status, q=q)
    return await repo.list_logs(f, page, size)


@router.get("/errors")
async def list_errors(page: int = 1, size: int = 50, start: str = "", end: str = "",
                      model: str = "", channel: str = "", request_type: str = "", q: str = ""):
    f = _filters(start=start, end=end, model=model, channel=channel, request_type=request_type, q=q)
    f["errors_only"] = True
    return await repo.list_logs(f, page, size)


@router.get("/export-csv")
async def export_csv(start: str = "", end: str = "", key_name: str = "", model: str = "",
                     vendor: str = "", channel: str = "", request_type: str = "",
                     status: str = "", q: str = "", errors_only: str = ""):
    f = _filters(start=start, end=end, key_name=key_name, model=model, vendor=vendor,
                 channel=channel, request_type=request_type, status=status, q=q)
    if errors_only:
        f["errors_only"] = True
    rows = await repo.logs_for_export(f)
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(["时间", "请求类型", "对外协议", "key备注", "模型", "厂商标签", "源IP", "渠道",
                "耗时ms", "prompt_tokens", "completion_tokens", "HTTP状态码", "状态", "错误消息"])
    for r in rows:
        w.writerow([r["ts"], r["request_type"], r["protocol"], r["key_name"], r["model"],
                    r["vendor_tag"], r["source_ip"], r["channel"], r["latency_ms"],
                    r["prompt_tokens"], r["completion_tokens"], r["http_status"], r["status"], r["error"]])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=logs.csv"})


@router.get("/{log_id}")
async def get_log(log_id: int):
    row = await repo.get_log(log_id)
    if not row:
        return {"ok": False, "error": "不存在"}
    return {"ok": True, "log": row}


@router.delete("/{log_id}")
async def delete_log(log_id: int):
    await repo.delete_log(log_id)
    return {"ok": True}


@router.post("/batch-delete")
async def batch_delete(body: dict = Body(...)):
    ids = body.get("ids") or []
    await repo.delete_logs_batch(ids)
    return {"ok": True, "deleted": len(ids)}


@router.delete("")
async def clear_all(errors_only: bool = False):
    await repo.clear_logs(errors_only)
    return {"ok": True}
