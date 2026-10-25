#!/usr/bin/env bash
# ============================================================================
#  AI 聚合网关 v20 · 一键管理脚本（PC / Termux 通用）
#
#  用法:
#    bash start.sh              # 启动（默认，后台运行）
#    bash start.sh start        # 同上
#    bash start.sh foreground   # 前台运行（Ctrl+C 停止，Termux 防杀推荐）
#    bash start.sh stop         # 停止网关
#    bash start.sh restart      # 重启
#    bash start.sh status       # 查看运行状态
#    bash start.sh logs [N]     # 查看最近 N 行日志（默认 50）
#    bash start.sh logs follow  # 实时跟踪日志
#    bash start.sh help         # 帮助
#
#  首次使用:
#    1) bash termux-setup.sh    # 仅 Termux 需要：修复 pydantic-core 预编译依赖
#    2) bash start.sh           # 自动装依赖 → 建库 → 生成默认密钥（打印在日志里）
#    3) 浏览器打开管理台 http://127.0.0.1:9009 配置渠道与密钥
#    4) 需要 FRP 内网穿透？到管理台「FRP 内网穿透」页粘贴你的 frpc 配置
#       （模板参考项目根 frpc.example.ini；本脚本绝不自动写入你的穿透配置）
# ============================================================================
set -u
cd "$(dirname "$0")"
ROOT_DIR="$(pwd)"

VERSION="v20"
PORT_DEFAULT=9010
ADMIN_PORT_DEFAULT=9009
PID_FILE="data/gateway.pid"
LOG_FILE="data/gateway.log"

# ---------- 颜色 ----------
if [ -t 1 ]; then
  C_G="\033[32m"; C_Y="\033[33m"; C_R="\033[31m"; C_B="\033[36m"; C_0="\033[0m"
else
  C_G=""; C_Y=""; C_R=""; C_B=""; C_0=""
fi
ok()   { echo -e "${C_G}[✓]${C_0} $*"; }
warn() { echo -e "${C_Y}[!]${C_0} $*"; }
err()  { echo -e "${C_R}[✗]${C_0} $*"; }
info() { echo -e "${C_B}[·]${C_0} $*"; }

# ---------- 读端口（环境变量 > db > 默认） ----------
read_ports() {
  PORT="${GATEWAY_PORT:-$PORT_DEFAULT}"
  ADMIN_PORT="${GATEWAY_ADMIN_PORT:-$ADMIN_PORT_DEFAULT}"
  if command -v python3 >/dev/null 2>&1 && [ -f data/gateway.db ]; then
    _p=$(python3 -c "
import sqlite3
try:
    db=sqlite3.connect('data/gateway.db')
    d=dict(db.execute('SELECT key,value FROM settings').fetchall())
    print(d.get('port',''), d.get('admin_port',''))
except Exception: pass" 2>/dev/null)
    _p1="${_p%% *}"; _p2="${_p#* }"
    [ -n "$_p1" ] && [ "$PORT" = "$PORT_DEFAULT" ] && PORT="$_p1"
    [ -n "$_p2" ] && [ "$ADMIN_PORT" = "$ADMIN_PORT_DEFAULT" ] && ADMIN_PORT="$_p2"
  fi
}

find_python() {
  PYTHON_BIN="${GATEWAY_PYTHON:-}"
  if [ -z "$PYTHON_BIN" ]; then
    for cand in python3.13 python3.12 python3.11 python3; do
      if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys' 2>/dev/null; then
        PYTHON_BIN="$cand"; break
      fi
    done
  fi
  if [ -z "$PYTHON_BIN" ]; then
    err "未找到 python3，请先安装：Termux 执行 pkg install python；PC 安装 Python ≥3.10"
    exit 1
  fi
}

check_deps() {
  find_python
  NEED_INSTALL=0
  $PYTHON_BIN - <<'EOF' 2>/dev/null || NEED_INSTALL=1
import fastapi, uvicorn, httpx, aiosqlite
EOF
  if [ "$NEED_INSTALL" = "1" ]; then
    if [ -n "${PREFIX:-}" ] && [[ "$PREFIX" == *com.termux* ]] && ! $PYTHON_BIN -c 'import pydantic_core' 2>/dev/null; then
      err "检测到 Termux：pydantic-core 需要预编译 wheel，请先执行：bash termux-setup.sh"
      exit 1
    fi
    info "安装后端依赖（backend/requirements.txt，全部锁定版本）..."
    $PYTHON_BIN -m pip install -r backend/requirements.txt \
      || $PYTHON_BIN -m pip install --break-system-packages -r backend/requirements.txt \
      || { err "依赖安装失败，请检查网络后重试"; exit 1; }
  else
    ok "依赖完整（解释器: $PYTHON_BIN）"
  fi
}

gw_pid() { [ -f "$PID_FILE" ] && head -1 "$PID_FILE" 2>/dev/null; }

is_running() {
  local p; p=$(gw_pid)
  [ -n "$p" ] && kill -0 "$p" 2>/dev/null
}

port_busy_other() {  # 端口被非本网关进程占用时返回 0
  command -v fuser >/dev/null 2>&1 || return 1
  local pids=""
  pids=$(fuser "$1/tcp" 2>/dev/null | tr -s ' ' ' ')
  [ -n "$pids" ] || return 1
  local p; p=$(gw_pid)
  [ "$pids" != "$p" ]
}

cmd_start() {
  local FOREGROUND="${1:-}"
  read_ports
  echo -e "${C_B}=====================================================${C_0}"
  echo -e "${C_B}   AI 聚合网关 ${VERSION}   API:${PORT}  管理台:${ADMIN_PORT}${C_0}"
  echo -e "${C_B}=====================================================${C_0}"

  if is_running; then
    warn "网关已在运行（PID $(gw_pid)）。重启请用: bash start.sh restart"
    exit 0
  fi

  # 1) 依赖
  check_deps

  # 2) dist
  if [ ! -f dist/index.html ]; then
    warn "未找到 dist/index.html：管理台界面缺失（API 仍可用）。"
    info "构建方法：cd frontend && npm install && npm run build（产物自动输出到项目根 dist/）"
  else
    ok "管理台前端 dist/ 就绪"
  fi

  # 3) frpc 执行权限
  if [ -f ./frpc ] && [ ! -x ./frpc ]; then
    chmod +x ./frpc && ok "已为 frpc 添加执行权限"
  fi

  # 4) 端口占用检测（read_ports 已在函数开头执行）
  if port_busy_other "$PORT";        then err "端口 ${PORT} 已被其他程序占用，请释放或修改设置后重试"; exit 1; fi
  if port_busy_other "$ADMIN_PORT";  then err "端口 ${ADMIN_PORT} 已被其他程序占用，请释放或修改设置后重试"; exit 1; fi

  # 5) 首次启动引导
  FIRST_RUN=0
  [ ! -f data/gateway.db ] && FIRST_RUN=1
  if [ "$FIRST_RUN" = "1" ]; then
    echo -e "${C_G}>>> 检测到首次启动，将自动完成：${C_0}"
    echo "    1. 创建数据库 data/gateway.db（全部表结构自动初始化）"
    echo "    2. 生成默认客户端密钥 sk-gw-xxxx（打印在日志开头，稍后用 bash start.sh logs 查看）"
    echo "    3. 管理台配置建议：先到「上游渠道」添加渠道 → 「客户端密钥」管理密钥"
  fi

  # 6) FRP 引导（绝不自动写入用户配置）
  if [ -f ./frpc ]; then
    FRP_EMPTY=$($PYTHON_BIN - <<'EOF' 2>/dev/null || echo "?"
import sqlite3
try:
    db = sqlite3.connect('data/gateway.db')
    row = db.execute("SELECT value FROM settings WHERE key='frp_config'").fetchone()
    print('1' if not (row and row[0] and row[0].strip()) else '0')
except Exception:
    print('?')
EOF
)
    if [ "$FRP_EMPTY" = "1" ]; then
      warn "FRP 尚未配置：需要内网穿透时，到管理台「FRP 内网穿透」页粘贴你的 frpc 配置"
      info "配置模板见项目根 frpc.example.ini（填你自己的服务器地址/端口/token/远程端口）"
      info "保存后在该页一键启动，或开启「网关启动时自动启动 FRP」"
    fi
  fi

  # 7) 启动
  mkdir -p data
  if [ "$FOREGROUND" = "foreground" ]; then
    info "前台启动：API http://0.0.0.0:${PORT} + 管理台 http://0.0.0.0:${ADMIN_PORT}（Ctrl+C 停止）"
    cd backend && GATEWAY_PORT="$PORT" GATEWAY_ADMIN_PORT="$ADMIN_PORT" exec "$PYTHON_BIN" run.py
  else
    info "后台启动：API http://0.0.0.0:${PORT}（可穿透） + 管理台 http://0.0.0.0:${ADMIN_PORT}（仅内网）"
    cd backend
    GATEWAY_PORT="$PORT" GATEWAY_ADMIN_PORT="$ADMIN_PORT" PYTHONUNBUFFERED=1 \
      nohup "$PYTHON_BIN" run.py >> "${ROOT_DIR}/${LOG_FILE}" 2>&1 &
    local pid=$!
    cd "$ROOT_DIR"
    echo "$pid" > "$PID_FILE"
    # 就绪等待
    local ready=0
    for i in $(seq 1 15); do
      if $PYTHON_BIN -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:${ADMIN_PORT}/admin/api/settings',timeout=2)" 2>/dev/null; then
        ready=1; break
      fi
      sleep 1
    done
    if [ "$ready" = "1" ]; then
      ok "网关已启动（PID $pid）"
      echo -e "    ${C_G}管理台${C_0}: http://127.0.0.1:${ADMIN_PORT}   （仅内网，请勿穿透）"
      echo -e "    ${C_G}API${C_0}    : http://127.0.0.1:${PORT}/v1/chat/completions"
      [ "$FIRST_RUN" = "1" ] && echo -e "    ${C_Y}首次启动${C_0}: 默认密钥见日志 → bash start.sh logs 30"
      echo -e "    日志: \`${LOG_FILE}\`（bash start.sh logs follow 实时跟踪）"
    else
      err "网关 15 秒内未就绪，请查看日志定位: bash start.sh logs 50"
      exit 1
    fi
  fi
}

cmd_stop() {
  read_ports  # 兜底 fuser 需要实际端口（用户可能在管理台改过）
  if ! is_running; then
    warn "网关未在运行"
    command -v fuser >/dev/null 2>&1 && fuser -k ${PORT}/tcp ${ADMIN_PORT}/tcp 2>/dev/null
    return 0
  fi
  local p; p=$(gw_pid)
  info "停止网关（PID $p）..."
  kill "$p" 2>/dev/null
  for _ in $(seq 1 10); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
  kill -9 "$p" 2>/dev/null
  rm -f "$PID_FILE"
  # 兜底清理残留端口占用（如 frpc 子进程、半退出状态），确保 restart 立即可用
  command -v fuser >/dev/null 2>&1 && fuser -k ${PORT}/tcp ${ADMIN_PORT}/tcp 2>/dev/null
  sleep 1
  ok "已停止"
}

cmd_status() {
  read_ports
  if is_running; then
    ok "网关运行中（PID $(gw_pid)）"
  else
    warn "网关未运行"
  fi
  command -v curl >/dev/null 2>&1 || return 0
  curl -s -o /dev/null -w "    API    http://127.0.0.1:${PORT}  ->  HTTP %{http_code}\n" "http://127.0.0.1:${PORT}/v1/models" 2>/dev/null
  curl -s -o /dev/null -w "    管理台 http://127.0.0.1:${ADMIN_PORT}  ->  HTTP %{http_code}\n" "http://127.0.0.1:${ADMIN_PORT}/admin/" 2>/dev/null
}

cmd_logs() {
  [ -f "$LOG_FILE" ] || { warn "暂无日志文件 ${LOG_FILE}"; exit 0; }
  if [ "${1:-}" = "follow" ] || [ "${1:-}" = "-f" ]; then
    tail -f "$LOG_FILE"
  else
    tail -n "${1:-50}" "$LOG_FILE"
  fi
}

case "${1:-start}" in
  start)              cmd_start ;;
  foreground|fg)      cmd_start foreground ;;
  stop)               cmd_stop ;;
  restart)            cmd_stop; sleep 2; cmd_start ;;
  status)             cmd_status ;;
  logs)               shift; cmd_logs "$@" ;;
  help|-h|--help)     sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//' ;;
  *)                  err "未知命令: $1"; sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
