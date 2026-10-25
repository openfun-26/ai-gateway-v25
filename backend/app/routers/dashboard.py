"""仪表盘：统计、图表、监视器、告警、快捷操作。"""
import asyncio
import csv
import io

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ..core.database import db
from ..core.state import state
from ..db import repo
from ..services import stats, health, forward

router = APIRouter(prefix="/admin/api/dashboard", tags=["dashboard"])


@router.get("/summary")
async def summary():
    return await stats.summary()


@router.get("/charts")
async def charts(range: str = Query("1h")):
    return await stats.charts(range)


@router.get("/model-cards")
async def model_cards():
    return await stats.model_cards()


@router.get("/monitor")
async def monitor(limit: int = 50):
    return {"rows": await stats.monitor_recent(limit)}


@router.get("/alerts")
async def alerts():
    return {"alerts": await stats.alerts()}


@router.post("/alerts/clear")
async def clear_alerts():
    state.clear_alerts()
    return {"ok": True}


@router.post("/health-check-all")
async def health_check_all():
    from ..services import health
    started = health.start_background_check(repo.s_int(await repo.get_settings(), "health_timeout_sec", 15))
    return {"ok": True, "started": started, "message": "" if started else "检测任务已在进行中"}


@router.post("/reset-stats")
async def reset_stats():
    await repo.reset_all_stats()
    return {"ok": True}


@router.post("/clear-logs")
async def clear_logs():
    await repo.clear_logs()
    return {"ok": True}


@router.post("/reset-circuits")
async def reset_circuits():
    state.reset_circuits()
    return {"ok": True}


@router.get("/export-today-csv")
async def export_today_csv():
    from ..core.config import today_local_str
    rows = await repo.logs_for_export({"start": today_local_str()})
    buf = io.StringIO()
    buf.write("\ufeff")  # UTF-8 BOM
    w = csv.writer(buf)
    w.writerow(["时间", "请求类型", "对外协议", "key备注", "模型", "厂商标签", "源IP", "渠道",
                "耗时ms", "prompt_tokens", "completion_tokens", "HTTP状态码", "状态", "错误消息"])
    for r in rows:
        w.writerow([r["ts"], r["request_type"], r["protocol"], r["key_name"], r["model"],
                    r["vendor_tag"], r["source_ip"], r["channel"], r["latency_ms"],
                    r["prompt_tokens"], r["completion_tokens"], r["http_status"], r["status"], r["error"]])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=today_logs.csv"})


@router.post("/refresh-channels-daily")
async def refresh_daily():
    """渠道今日计数落库。"""
    await repo.persist_channel_daily()
    return {"ok": True}
