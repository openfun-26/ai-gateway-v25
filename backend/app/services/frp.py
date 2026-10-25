"""FRP-Client 管理：subprocess 拉起 frpc，日志内存环形缓冲，网关退出自动终止。"""
import asyncio
import atexit
import re
import subprocess
import threading
from collections import deque

from ..core.config import BASE_DIR, DATA_DIR, FRPC_BIN, FRP_TEMP_INI


class FrpManager:
    def __init__(self):
        self.proc = None
        self.logs: deque[str] = deque(maxlen=1000)   # 环形缓冲，重启清空
        self.state = "stopped"                        # stopped / running / error
        self.err_msg = ""
        self._lock = asyncio.Lock()
        self._reader_task = None

    # ---------- 配置 ----------
    async def save_config(self, ini_text: str) -> dict:
        await _repo_set("frp_config", ini_text)
        self.write_temp_ini(ini_text)
        return self.validate_ini(ini_text)

    def write_temp_ini(self, ini_text: str):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        FRP_TEMP_INI.write_text(ini_text or "", encoding="utf-8")

    @staticmethod
    def validate_ini(ini_text: str) -> dict:
        """解析 ini 中 local_port，≠9010 时给出警告（不阻断）。"""
        warnings: list[str] = []
        port = None
        m = re.search(r"local_port\s*=\s*(\d+)", ini_text or "")
        if m:
            port = int(m.group(1))
            if port != 9010:
                warnings.append(f"ini 中 local_port={port}，与网关端口 9010 不一致，穿透后可能无法访问网关（不阻断启动）。")
        else:
            warnings.append("未在配置中找到 local_port，请确认使用本地代理转发配置（不阻断启动）。")
        return {"local_port": port, "warnings": warnings}

    # ---------- 启停 ----------
    async def start(self) -> dict:
        async with self._lock:
            if self.proc and self.proc.poll() is None:
                return {"ok": False, "message": "FRP 已在运行中"}
            if not FRPC_BIN.exists():
                self.state = "error"
                self.err_msg = "未找到 frpc 二进制：请自行下载 aarch64/对应平台版本放入项目根目录并 chmod +x frpc"
                self._log(self.err_msg)
                return {"ok": False, "message": self.err_msg}
            ini = await _repo_get("frp_config")
            self.write_temp_ini(ini)
            if not FRP_TEMP_INI.exists():
                return {"ok": False, "message": "frp_temp.ini 写入失败"}
            if not (ini or "").strip():
                return {"ok": False, "message": "尚未保存 FRP 配置，请先在 FRP 设置里填写并保存后再启动"}
            try:
                self.logs.clear()
                self.proc = subprocess.Popen(
                    ["./frpc", "-c", str(FRP_TEMP_INI)], cwd=str(BASE_DIR),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, errors="ignore")
                self.state = "running"
                self.err_msg = ""
                self._log(f"[frp] 已启动 PID={self.proc.pid}")
                self._start_reader()
                # 短暂观察是否立即退出
                await asyncio.sleep(0.8)
                if self.proc.poll() is not None:
                    self.state = "error"
                    self.err_msg = f"frpc 立即退出，退出码 {self.proc.returncode}（请检查配置/二进制架构）"
                    self._log(f"[frp] {self.err_msg}")
                    return {"ok": False, "message": self.err_msg}
                return {"ok": True, "message": "FRP 已启动"}
            except Exception as e:
                self.state = "error"
                self.err_msg = str(e)
                self._log(f"[frp] 启动失败: {e}")
                return {"ok": False, "message": str(e)}

    def _start_reader(self):
        proc = self.proc
        if not proc or not proc.stdout:
            return

        def pump():
            try:
                for line in proc.stdout:
                    self._log(line.rstrip("\n"))
            except Exception:
                pass

        t = threading.Thread(target=pump, daemon=True)
        t.start()

    def _log(self, line: str):
        self.logs.append(line)

    async def stop(self) -> dict:
        async with self._lock:
            if not self.proc or self.proc.poll() is not None:
                self.state = "stopped"
                return {"ok": True, "message": "FRP 未在运行"}
            try:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except Exception:
                    self.proc.kill()
                    self.proc.wait(timeout=3)
                self._log("[frp] 已停止")
                self.state = "stopped"
                return {"ok": True, "message": "FRP 已停止"}
            except Exception as e:
                self.state = "error"
                return {"ok": False, "message": str(e)}

    def status(self) -> dict:
        running = self.proc is not None and self.proc.poll() is None
        if running:
            self.state = "running"
        elif self.state == "running":
            self.state = "error"
            self.err_msg = f"frpc 进程意外退出（退出码 {self.proc.returncode if self.proc else '?'}）"
        return {"state": self.state, "running": running, "error": self.err_msg,
                "binary_exists": FRPC_BIN.exists(),
                "pid": self.proc.pid if running else None}

    def get_logs(self) -> list[str]:
        return list(self.logs)[-500:]

    def clear_logs(self):
        self.logs.clear()

    def shutdown(self):
        """网关退出时终止子进程。"""
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=3)
                except Exception:
                    self.proc.kill()
        except Exception:
            pass


frp = FrpManager()
atexit.register(frp.shutdown)


async def _repo_get(key: str) -> str:
    from ..db import repo
    return await repo.get_setting(key, "")


async def _repo_set(key: str, value: str):
    from ..db import repo
    await repo.set_setting(key, value)
