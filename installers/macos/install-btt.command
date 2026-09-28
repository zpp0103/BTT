#!/usr/bin/env bash
#
# BTT macOS 安装器（本机自用版，适配 Intel Mac）
# 双击本文件即可：解析 Python 3.11 → 建虚拟环境 → 装依赖 → 装项目。
# 若从 DMG 卷（/Volumes/*）启动，会先把源码复制到 ~/BTT 再安装。
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

echo "[BTT Installer] 仓库根目录: ${REPO_ROOT}"

# 若从安装卷启动（DMG 挂载路径），复制到本地可写目录再安装
if [[ "${REPO_ROOT}" == /Volumes/* ]]; then
  TARGET="${HOME}/BTT"
  echo "[BTT Installer] 检测到从安装卷启动，复制源码到 ${TARGET} ..."
  rm -rf "${TARGET}"
  mkdir -p "${TARGET}"
  rsync -a --exclude '.git' --exclude '.venv' --exclude 'dist' \
    --exclude '__pycache__' --exclude '*.pyc' --exclude '*.pyo' \
    --exclude 'user_data' --exclude 'node_modules' --exclude '.DS_Store' \
    "${REPO_ROOT}/" "${TARGET}/"
  REPO_ROOT="${TARGET}"
  cd "${REPO_ROOT}"
  echo "[BTT Installer] 已复制到 ${REPO_ROOT}"
fi

# 解析 Python 3.11+（本机优先用 QClaw 自带的 python3.11，也兼容系统/其他 python3.11+）
resolve_python() {
  local candidates=(
    "/Users/a123/Library/Application Support/QClaw/python/bin/python3.11"
    "python3.14" "python3.13" "python3.12" "python3.11" "python3"
  )
  for py in "${candidates[@]}"; do
    if [[ -x "${py}" ]] || [[ -n "$(command -v "${py}" 2>/dev/null)" ]]; then
      local ver
      ver="$("${py}" - <<'PY' 2>/dev/null
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)" || continue
      case "${ver}" in
        3.11|3.12|3.13|3.14)
          echo "${py}"
          return 0
          ;;
      esac
    fi
  done
  return 1
}

PYTHON_BIN="$(resolve_python || true)"
if [[ -z "${PYTHON_BIN}" ]]; then
  echo "未找到 Python 3.11+。本项目需要 Python 3.11 或更新版本。" >&2
  echo "可安装：brew install python@3.11  或从 https://www.python.org 下载 3.11+" >&2
  exit 1
fi
echo "[BTT Installer] 使用 Python: ${PYTHON_BIN}"

# 准备 cryptography 在 Intel Mac 上的源码编译环境（rust + 本地 OpenSSL）
if [[ -f "${HOME}/.cargo/env" ]]; then
  # shellcheck disable=SC1090
  source "${HOME}/.cargo/env"
fi
if [[ -d "${HOME}/.local/openssl" ]]; then
  export OPENSSL_DIR="${HOME}/.local/openssl"
  export OPENSSL_LIB_DIR="${HOME}/.local/openssl/lib"
  export OPENSSL_INCLUDE_DIR="${HOME}/.local/openssl/include"
  echo "[BTT Installer] 使用本地 OpenSSL: ${OPENSSL_DIR}"
fi

if [[ ! -f ".venv/bin/python" ]]; then
  echo "[BTT Installer] 创建虚拟环境..."
  "${PYTHON_BIN}" -m venv .venv
fi

VENV_PYTHON="${REPO_ROOT}/.venv/bin/python"
echo "[BTT Installer] 安装依赖..."
"${VENV_PYTHON}" -m pip install --upgrade pip wheel setuptools
"${VENV_PYTHON}" -m pip install -r requirements-dev.txt
"${VENV_PYTHON}" -m pip install -e .

if [[ "${1:-}" != "--skip-ui" ]]; then
  echo "[BTT Installer] 安装 FreqUI..."
  "${VENV_PYTHON}" -m freqtrade install-ui || echo "[BTT Installer] FreqUI 安装跳过（可稍后手动安装）"
fi

# 启动器：在 venv 中执行任意 freqtrade 命令
cat > "${REPO_ROOT}/run-btt.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "${REPO_ROOT}"
source "${REPO_ROOT}/.venv/bin/activate"
"$@"
EOF
chmod +x "${REPO_ROOT}/run-btt.sh"

# 启动器：打开 crypto_quant_ai 的 FastAPI 网页服务
cat > "${REPO_ROOT}/launch-api.command" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "${REPO_ROOT}"
source "${REPO_ROOT}/.venv/bin/activate"
PYTHONPATH="${REPO_ROOT}" uvicorn crypto_quant_ai.backend.api.app:app --reload --port 8000
EOF
chmod +x "${REPO_ROOT}/launch-api.command"

# 生成可拖入「应用程序」文件夹的 .app（双击启动网页服务）
if [[ -f "${SCRIPT_DIR}/make-app.sh" ]]; then
  echo "[BTT Installer] 生成 BTT.app（可拖入 /Applications，双击开网页）..."
  bash "${SCRIPT_DIR}/make-app.sh" "${REPO_ROOT}"
fi

# 桌面优先本地配置（若仓库提供模板则复制；否则跳过）
DEFAULT_TEMPLATE="${REPO_ROOT}/installers/templates/config.local.desktop.json"
mkdir -p "${REPO_ROOT}/user_data"
DEFAULT_TARGET="${REPO_ROOT}/user_data/config.local.desktop.json"
if [[ ! -f "${DEFAULT_TARGET}" && -f "${DEFAULT_TEMPLATE}" ]]; then
  cp "${DEFAULT_TEMPLATE}" "${DEFAULT_TARGET}"
  echo "[BTT Installer] 已创建桌面本地配置: user_data/config.local.desktop.json"
fi

echo
echo "[BTT Installer] 完成。"
echo "用法："
echo "  source .venv/bin/activate"
echo "  python -m freqtrade backtesting --help"
echo "  ./run-btt.sh python -m freqtrade trade --config user_data/config.local.desktop.json --strategy <策略>"
echo "  ./launch-api.command   # 启动 crypto_quant_ai 网页服务 (http://localhost:8000/docs)"
