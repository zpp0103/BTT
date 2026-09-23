#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

echo "[BTT Installer] Repository root: ${REPO_ROOT}"

resolve_python() {
  local candidates=("python3.14" "python3.13" "python3.12" "python3.11" "python3")
  for py in "${candidates[@]}"; do
    if command -v "${py}" >/dev/null 2>&1; then
      local ver
      ver="$("${py}" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
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
  echo "No supported Python interpreter found (requires Python 3.11-3.14)." >&2
  exit 1
fi
echo "[BTT Installer] Using Python: ${PYTHON_BIN}"

if [[ ! -f ".venv/bin/python" ]]; then
  echo "[BTT Installer] Creating virtual environment..."
  "${PYTHON_BIN}" -m venv .venv
fi

VENV_PYTHON="${REPO_ROOT}/.venv/bin/python"
echo "[BTT Installer] Installing dependencies..."
"${VENV_PYTHON}" -m pip install --upgrade pip wheel setuptools
"${VENV_PYTHON}" -m pip install -r requirements-dev.txt
"${VENV_PYTHON}" -m pip install -e .

if [[ "${1:-}" != "--skip-ui" ]]; then
  echo "[BTT Installer] Installing FreqUI..."
  "${VENV_PYTHON}" -m freqtrade install-ui
fi

cat > "${REPO_ROOT}/run-backtest.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "${REPO_ROOT}"
"${VENV_PYTHON}" -m freqtrade backtesting --help
echo
echo "Example:"
echo "\"${VENV_PYTHON}\" -m freqtrade backtesting --config tests/testdata/config.tests.json --strategy SampleStrategy --strategy-path tests/strategy/strats --datadir tests/testdata --timerange 20180110-20180130 -i 5m --cache none"
EOF
chmod +x "${REPO_ROOT}/run-backtest.sh"

echo "[BTT Installer] Done."
echo "Next:"
echo "1) source .venv/bin/activate"
echo "2) python -m freqtrade backtesting --help"
echo "3) ./run-backtest.sh"

DEFAULT_TEMPLATE="${REPO_ROOT}/installers/templates/config.local.desktop.json"
mkdir -p "${REPO_ROOT}/user_data"
DEFAULT_TARGET="${REPO_ROOT}/user_data/config.local.desktop.json"
if [[ ! -f "${DEFAULT_TARGET}" ]]; then
  cp "${DEFAULT_TEMPLATE}" "${DEFAULT_TARGET}"
  echo "[BTT Installer] Created desktop-first local config: user_data/config.local.desktop.json"
else
  echo "[BTT Installer] Desktop-first local config already exists: user_data/config.local.desktop.json"
fi
