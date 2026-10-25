"""全局常量与路径配置。"""
import os
from pathlib import Path

GATEWAY_VERSION = "v20"

# 项目根目录（backend/app/core/config.py -> 项目根 = 上三级）
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DIST_DIR = BASE_DIR / "dist"
FRPC_BIN = BASE_DIR / "frpc"
FRP_TEMP_INI = DATA_DIR / "frp_temp.ini"

DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "gateway.db"

# 时区口径：本地时区固定 Asia/Shanghai（+8），全部以本地自然日为「今日」
TZ_OFFSET_HOURS = 8

# 对外网关保留端点（反代 catch-all 不得匹配这些路径）
GATEWAY_RESERVED = {
    "/v1/chat/completions",
    "/v1/models",
    "/v1/embeddings",
    "/v1/moderations",
}

DEFAULT_SETTINGS = {
    "port": "9010",
    "admin_port": "9009",              # 管理台独立端口（内网访问，不穿透外网）
    "theme_default": "light",          # light / dark
    "accent_default": "teal",
    "cors_origins": "*",
    "global_rps": "0",                 # 0 = 不限
    "health_timeout_sec": "15",
    "health_interval_sec": "300",      # 0 = 关闭定时检测
    "log_retention_days": "30",
    "log_max_rows": "50000",
    "routing_strategy": "weighted_round_robin",
    "global_max_retries": "2",
    "upstream_freeze_sec": "60",       # 上游报错自动冻结时长
    "circuit_error_threshold": "50",   # %
    "circuit_window_sec": "60",
    "circuit_freeze_sec": "300",
    "auto_adaptive_weight": "0",
    "model_fallback": "1",             # 请求模型失败时按模型监控列表顺序自动降级到备选模型
    "auto_enabled": "1",               # auto 智能路由：可单独选择，也可作为备选链兜底
    "auto_exclude_paid": "1",          # auto 挑选时跳过标记为「付费」的渠道，防止误触付费模型产生费用
    "frp_config": "",
    "frp_autostart": "0",
    "admin_local_only": "0",           # 管理端仅本机可用（默认关闭，允许内网）
}


def now_local_str() -> str:
    """本地时区（Asia/Shanghai 口径）时间字符串，可直接字典序比较。"""
    import datetime
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=TZ_OFFSET_HOURS)).strftime("%Y-%m-%d %H:%M:%S")


def today_local_str() -> str:
    import datetime
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=TZ_OFFSET_HOURS)).strftime("%Y-%m-%d")


def parse_iso(s: str):
    """把存库的时间字符串解析回 datetime（本地口径）。"""
    import datetime
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s[:len(fmt) + 2].strip(), fmt)
        except Exception:
            continue
    return None


def mask_key(key: str) -> str:
    """上游 API-Key 脱敏展示。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return key[:5] + "***" + key[-4:]
