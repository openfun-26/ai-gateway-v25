"""FastAPI 入口：静态托管 dist、生命周期、路由挂载、反代 catch-all、SPA fallback、多格式路径兼容。"""
import asyncio
import contextlib
import os
import re

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .core.cache import cache
from .core.config import DIST_DIR, DB_PATH, GATEWAY_VERSION, now_local_str, today_local_str
from .core.database import db
from .core.limiter import RateLimiter
from .core.state import state
from .db.schema import init_db
from .db import repo
from .gateway import routes as gateway_routes
from .gateway.auth import authenticate
from .routers import dashboard, models, channels, keys, routing, logs, settings
from .services import forward, proxy as proxy_svc, health as health_svc, frp as frp_svc

app = FastAPI(title="AI Aggregation Gateway", docs_url=None, redoc_url=None)

app.state.limiter = RateLimiter()
app.state.auth_fn = authenticate


# ---- 管理台端口（9009）：构建期同步读取 SQLite；修改后重启生效 ----
def _bootstrap_admin_port() -> int:
    try:
        import sqlite3
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute("SELECT value FROM settings WHERE key='admin_port'").fetchone()
        conn.close()
        return int(row[0]) if row and row[0] else 9009
    except Exception:
        return 9009


app.state.admin_port = _bootstrap_admin_port()


# ---- 入站路径多格式兼容：/v4/v1/chat/completions、/api/paas/v4/chat/completions、/chat/completions 等 ----
# 统一重写为标准 /v1/<endpoint> 后进入网关；反代规则命中的路径不重写（反代优先）。
_KNOWN_EPS = {"chat/completions", "completions", "embeddings", "models", "moderations",
              "messages", "responses", "rerank", "audio/transcriptions", "audio/translations",
              "audio/speech", "images/generations", "images/edits", "images/variations"}


def _bootstrap_proxy_prefixes() -> list[str]:
    try:
        import sqlite3
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute("SELECT path_prefix FROM proxy_rules WHERE enabled=1").fetchall()
        conn.close()
        return [(r[0] or "").strip().rstrip("/") for r in rows if r[0] and r[0].strip()]
    except Exception:
        return []


_proxy_prefixes = _bootstrap_proxy_prefixes()


@app.middleware("http")
async def _path_compat(request: Request, call_next):
    # 管理台端口不做 API 路径兼容重写：/models 等路径是管理台 SPA 页面，
    # 若重写为 /v1/models 会劫持页面落入 API 鉴权（v20 修复的致命 bug）。
    srv = request.scope.get("server")
    port = srv[1] if isinstance(srv, tuple) and len(srv) > 1 else 0
    if port and port == app.state.admin_port:
        return await call_next(request)
    path = request.url.path
    if not (path == "/v1" or path.startswith("/v1/")):
        if _proxy_prefixes and any(path == p or path.startswith(p + "/") for p in _proxy_prefixes):
            return await call_next(request)          # 反代规则优先，不做兼容重写
        parts = [s for s in path.split("/") if s]
        for i in range(len(parts)):
            tail = "/".join(parts[i:])
            if tail in _KNOWN_EPS:
                request.scope["path"] = "/v1/" + tail
                break
    return await call_next(request)


@app.middleware("http")
async def _port_guard(request: Request, call_next):
    """端口隔离：API 口(9010)只暴露 /v1/* 与反代；管理台/管理 API 仅内网管理口(9009)。"""
    srv = request.scope.get("server")
    port = srv[1] if isinstance(srv, tuple) and len(srv) > 1 else 0
    if port and port == app.state.admin_port:
        return await call_next(request)          # 管理口：全放行（未穿透，仅内网可达）
    path = request.url.path
    blocked = (path == "/" or path.startswith(
        ("/admin", "/assets", "/fonts", "/favicon", "/docs", "/redoc", "/openapi.json")))
    if blocked:
        if "text/html" in request.headers.get("accept", ""):
            return HTMLResponse(
                "<h1>403</h1><p>管理台不在本端口开放：请通过内网访问管理台端口（默认 9009）。</p>",
                status_code=403)
        return JSONResponse({"error": "admin UI/API is served on internal admin port (default 9009)"},
                            status_code=403)
    return await call_next(request)              # /v1/*、反代规则路径等对外服务照常


@app.on_event("startup")
async def _startup():
    print(f"==> AI 聚合网关 {GATEWAY_VERSION} 启动：API 9010(/v1 多格式兼容) + 管理台 9009（双端口隔离）")
    await db.connect()
    await init_db()
    # 首次启动：无任何客户端密钥时自动生成默认密钥（开源开箱体验）
    try:
        _cnt = await db.fetchall("SELECT COUNT(*) AS n FROM api_keys")
        if not _cnt or not _cnt[0]["n"]:
            import secrets
            _key = "sk-gw-" + secrets.token_hex(16)
            await db.execute("INSERT INTO api_keys(key, name, enabled, created_at) VALUES(?,?,1,?)",
                             (_key, "default", now_local_str()))
            print("=" * 64)
            print(f"==> 首次启动已生成默认客户端密钥: {_key}")
            print("==> 调用示例: curl http://127.0.0.1:9010/v1/chat/completions -H \"Authorization: Bearer <密钥>\" ...")
            print("==> 更多密钥请到管理台「客户端密钥」页生成与管理")
            print("=" * 64)
    except Exception:
        pass
    # 恢复渠道今日计数（若跨日则清零）
    await repo.restore_channel_daily(today_local_str())
    await repo.set_setting("last_start_date", today_local_str())
    # 默认设置落库
    s = await repo.get_settings()
    # FRP 自启
    if repo.s_int(s, "frp_autostart") == 1:
        asyncio.create_task(frp_svc.frp.start())
    # 后台任务：健康检测 / 日志清理 / 日切 / 今日计数落库
    app.state.bg_tasks = [
        asyncio.create_task(_health_loop()),
        asyncio.create_task(_cleanup_loop()),
        asyncio.create_task(_housekeeping_loop()),
    ]


@app.on_event("shutdown")
async def _shutdown():
    for t in getattr(app.state, "bg_tasks", []):
        t.cancel()
    with contextlib.suppress(Exception):
        await repo.persist_channel_daily()
    await frp_svc.frp.shutdown()
    await forward.upstream.close_clients()
    await db.close()


async def _health_loop():
    await health_svc.background_loop(app)


async def _cleanup_loop():
    while True:
        try:
            s = await repo.get_settings()
            await repo.cleanup_logs(repo.s_int(s, "log_retention_days", 30), repo.s_int(s, "log_max_rows", 50000))
        except asyncio.CancelledError:
            return
        except Exception:
            pass
        await asyncio.sleep(3600)


async def _housekeeping_loop():
    """日切（今日统计清零）+ 渠道今日计数周期落库。"""
    last_date = today_local_str()
    counter = 0
    while True:
        try:
            await asyncio.sleep(60)
            today = today_local_str()
            if today != last_date:
                state.daily_rollover(today, last_date)
                last_date = today
                await db.execute("UPDATE channels SET today_requests=0, today_failures=0")
            counter += 1
            if counter % 10 == 0:
                await repo.persist_channel_daily()
        except asyncio.CancelledError:
            return
        except Exception:
            pass


# CORS（构建期同步读取 SQLite 配置；修改后重启生效）
def _bootstrap_cors_origins() -> str:
    try:
        import sqlite3
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute("SELECT value FROM settings WHERE key='cors_origins'").fetchone()
        conn.close()
        return row[0] if row and row[0] else "*"
    except Exception:
        return "*"


_origins = [o.strip() for o in _bootstrap_cors_origins().split(",") if o.strip() and o.strip() != "*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- 管理端 REST ----
app.include_router(dashboard.router)
app.include_router(models.router)
app.include_router(channels.router)
app.include_router(keys.router)
app.include_router(routing.router)
app.include_router(logs.router)
app.include_router(settings.router)

# ---- 对外网关端点 ----
app.include_router(gateway_routes.router)


# ---- 反代 catch-all（网关保留端点之后匹配） ----
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
               include_in_schema=False)
async def catch_all(request: Request, path: str):
    # 1) 反代规则匹配（POST/PUT 等业务方法）
    if request.method in ("POST", "PUT", "PATCH", "DELETE", "GET"):
        resp = await proxy_svc.handle_proxy(request)
        if resp is not None:
            return resp

    # 2) 静态资源托管 dist/
    if request.method in ("GET", "HEAD"):
        # 安全：阻止路径穿越
        rel = os.path.normpath(path).lstrip("/").replace("..", "")
        candidate = DIST_DIR / rel
        if rel and candidate.is_file():
            return FileResponse(candidate)
        # assets/fonts 等已知静态目录
        if rel.startswith(("assets/", "fonts/", "favicon")) and candidate.exists():
            return FileResponse(candidate)
        # SPA history fallback
        index = DIST_DIR / "index.html"
        if index.is_file():
            return FileResponse(index)
        return HTMLResponse("<h1>dist/ 未构建</h1><p>请先在 frontend 目录执行构建，并把产物复制到项目根 dist/。</p>",
                            status_code=404)
    return JSONResponse({"error": "not found"}, status_code=404)
