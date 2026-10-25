"""双端口启动器：
  - API 口（默认 9010，可被 FRP 穿透对外）：仅 /v1/* 与反代规则，管理台/管理 API 一律 403
  - 管理口（默认 9009，不穿透、仅内网）：管理台页面 + 管理 API 全量
端口来源：环境变量 GATEWAY_PORT / GATEWAY_ADMIN_PORT > SQLite settings(port/admin_port) > 默认 9010/9009
"""
import asyncio
import os
import signal

import uvicorn

from app.main import app


def _int_env(name: str, default: int = 0) -> int:
    try:
        return int(os.environ.get(name) or 0) or default
    except Exception:
        return default


API_PORT = _int_env("GATEWAY_PORT", 9010)
_env_admin = _int_env("GATEWAY_ADMIN_PORT", 0)
ADMIN_PORT = _env_admin or getattr(app.state, "admin_port", 9009)
app.state.admin_port = ADMIN_PORT   # 中间件按此端口放行管理面


async def main():
    api_cfg = uvicorn.Config(app, host=os.environ.get("GATEWAY_HOST", "0.0.0.0"),
                             port=API_PORT, log_level="info", lifespan="on")
    admin_cfg = uvicorn.Config(app, host=os.environ.get("GATEWAY_ADMIN_HOST", "0.0.0.0"),
                               port=ADMIN_PORT, log_level="warning", lifespan="off")
    s_api, s_admin = uvicorn.Server(api_cfg), uvicorn.Server(admin_cfg)

    async def _watch():
        """任一 server 退出（Ctrl+C / 异常）时带停另一个，避免进程挂死。"""
        while not (s_api.should_exit or s_admin.should_exit):
            await asyncio.sleep(0.2)
        s_api.should_exit = True
        s_admin.should_exit = True

    print(f"==> API   端口: http://0.0.0.0:{API_PORT}  （/v1/* 对外，可穿透）")
    print(f"==> 管理台端口: http://0.0.0.0:{ADMIN_PORT}  （仅内网，浏览器打开管理后台）")
    await asyncio.gather(s_api.serve(), s_admin.serve(), _watch())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
