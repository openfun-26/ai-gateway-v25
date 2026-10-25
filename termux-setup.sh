#!/data/data/com.termux/files/usr/bin/bash
###############################################################################
# AI 聚合网关 · Termux 依赖一键修复脚本 v1.0
#
# 解决的问题：
#   在 Termux (Android aarch64) 上执行 `pip install -r backend/requirements.txt`
#   时，pydantic-core（Rust 扩展）在 PyPI 没有 android 平台的预编译 wheel，
#   pip 回退源码编译 → 需要 Rust → rustup 不支持 aarch64-unknown-linux-android
#   target → 安装失败。
#
# 解决原理：
#   从 Termux User Repository (TUR) 维护的 PyPI 索引拉取官方交叉编译好的
#   Android (aarch64) 预编译 wheel，并全程使用 --only-binary=:all: 禁止
#   任何源码编译，几秒内装完，无需 Rust / clang / binutils。
#
# 用法：把本文件放在项目根目录（与 start.sh 同级），执行：
#   bash termux-setup.sh
#
# 可选环境变量：
#   GATEWAY_PYTHON=python3.13 bash termux-setup.sh   # 指定解释器
###############################################################################
set -uo pipefail

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; N='\033[0m'
ok()   { echo -e "${G}==> ✔${N} $1"; }
info() { echo -e "${G}==>${N} $1"; }
warn() { echo -e "${Y}==> !${N} $1"; }
die()  { echo -e "${R}==> ✗ ${N}$1"; exit 1; }

# ---------- 1. 环境检测 ----------
[[ "${PREFIX:-}" == *com.termux* ]] || die "请在 Termux 中运行本脚本（未检测到 Termux 环境）"
cd "$(dirname "$0")" || die "进入脚本所在目录失败"
[[ -f backend/requirements.txt ]] || die "请把本脚本放在项目根目录（与 start.sh 同级）后再运行"

# 内置 FRP 客户端赋权（穿透已在 start.sh 中自动启动，无需手动操作）
if [[ -f frpc ]]; then
  chmod +x frpc 2>/dev/null && info "frpc 穿透客户端已就绪（start.sh 启动网关时会自动拉起）"
fi

TUR="https://termux-user-repository.github.io/pypi/"

# 选择解释器：GATEWAY_PYTHON > python3.13（TUR wheel 覆盖最全）> python
PY=""
for cand in "${GATEWAY_PYTHON:-}" python3.13 python; do
  [[ -z "$cand" ]] && continue
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys' 2>/dev/null; then
    PY="$cand"; break
  fi
done
[[ -n "$PY" ]] || die "未找到可用的 Python，请先执行: pkg install python"
info "使用解释器: ${PY} ($(${PY} -V 2>&1))"

# ---------- 2. 已装齐则直接通过 ----------
if $PY -c 'import fastapi, uvicorn, httpx, aiosqlite' 2>/dev/null; then
  ok "依赖已全部就绪，无需修复。启动: bash start.sh"
  exit 0
fi

info "[1/3] 升级 pip"
$PY -m pip install -q --upgrade pip 2>/dev/null || warn "pip 升级跳过（不影响安装）"

# ---------- 3. pydantic-core：TUR 预编译 wheel（核心修复点） ----------
if $PY -c 'import pydantic_core' 2>/dev/null; then
  ok "pydantic_core 已可用，跳过"
else
  info "[2/3] 从 TUR 安装预编译 pydantic + pydantic-core（免 Rust 编译）"
  if ! $PY -m pip install --extra-index-url "$TUR" --only-binary=:all: pydantic pydantic-core; then
    warn "TUR 索引不可达，或当前 Python 版本无对应预编译 wheel"
    if $PY -m pip install --only-binary=:all: pydantic pydantic-core 2>/dev/null; then
      ok "已从 PyPI 安装（当前平台存在预编译 wheel）"
    else
      info "切换 python3.13（TUR 对 3.13 的 Android wheel 覆盖最全）..."
      pkg install -y python3.13 || die "pkg install python3.13 失败，请手动安装后重跑本脚本"
      PY=python3.13
      $PY -m pip install --extra-index-url "$TUR" --only-binary=:all: pydantic pydantic-core \
        || die "pydantic 安装失败：请检查网络后重试（必要时切换网络环境）"
    fi
  fi
  $PY -c 'import pydantic_core' 2>/dev/null || die "pydantic_core 安装后不可导入，请截图反馈"
  ok "pydantic-core 预编译 wheel 安装成功（零编译）"
fi

# ---------- 4. 其余依赖：全部为纯 Python wheel ----------
info "[3/3] 安装其余依赖（--only-binary 禁止任何源码编译）"
$PY -m pip install --extra-index-url "$TUR" --only-binary=:all: -r backend/requirements.txt \
  || $PY -m pip install --only-binary=:all: -r backend/requirements.txt \
  || die "依赖安装失败：请检查网络后重试"

# ---------- 5. 验证 ----------
info "验证依赖导入..."
$PY - <<PYEOF || die "依赖验证失败"
import fastapi, uvicorn, httpx, aiosqlite, pydantic, pydantic_core
print(f"    fastapi {fastapi.__version__} | pydantic {pydantic.__version__} | httpx {httpx.__version__} | aiosqlite {aiosqlite.__version__}")
PYEOF

ok "全部依赖就绪！"
echo ""
echo -e "  启动网关：  ${G}GATEWAY_PYTHON=${PY} bash start.sh${N}"
echo -e "  （直接 ${G}bash start.sh${N} 也可以，会自动选用本脚本装好的解释器）"
echo -e "  启动后浏览器打开  ${G}http://127.0.0.1:9010${N}"
