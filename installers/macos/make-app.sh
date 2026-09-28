#!/usr/bin/env bash
#
# 生成 BTT 的 macOS .app 套装（本机自用版）
#   BTT.app       —— 双击启动 crypto_quant_ai FastAPI 服务并打开网页
#   BTT Stop.app  —— 双击停止该服务
# 用法：bash make-app.sh <安装根目录>
#   安装根目录下需已存在 .venv（由 install-btt.command 装好）
#
set -euo pipefail

TARGET="${1:-${HOME}/BTT}"
APP="${TARGET}/BTT.app"
STOP="${TARGET}/BTT Stop.app"

echo "[make-app] 生成: ${APP}"

mkdir -p "${APP}/Contents/MacOS" "${APP}/Contents/Resources"
mkdir -p "${STOP}/Contents/MacOS" "${STOP}/Contents/Resources"

# ---- BTT.app Info.plist ----
cat > "${APP}/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>BTT</string>
  <key>CFBundleDisplayName</key><string>BTT</string>
  <key>CFBundleIdentifier</key><string>com.roundtable.btt</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleExecutable</key><string>BTT</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

# ---- BTT.app 启动器（双击即运行此脚本）----
cat > "${APP}/Contents/MacOS/BTT" <<'LAUNCH'
#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# 候选安装根：app 所在目录的父目录、~/BTT、~/projects/BTT
CANDIDATES=(
  "$(cd "${APP_DIR}/.." && pwd)"
  "${HOME}/BTT"
  "${HOME}/projects/BTT"
)
VENV=""
REPO_ROOT=""
for c in "${CANDIDATES[@]}"; do
  if [[ -x "${c}/.venv/bin/python" ]]; then VENV="${c}/.venv"; REPO_ROOT="${c}"; break; fi
done
if [[ -z "${VENV}" ]]; then
  /usr/bin/osascript -e 'display dialog "未找到 BTT 虚拟环境，请先运行 install-btt.command 完成安装。" buttons {"OK"} default button "OK"' 2>/dev/null || true
  exit 1
fi

LOG_DIR="${HOME}/Library/Logs/BTT"
mkdir -p "${LOG_DIR}"
LOG="${LOG_DIR}/server.log"

# 若服务已在运行，直接打开网页
if pgrep -f "uvicorn crypto_quant_ai" >/dev/null 2>&1; then
  open "http://127.0.0.1:8000/docs" 2>/dev/null || true
  exit 0
fi

cd "${REPO_ROOT}"
PYTHONPATH="${REPO_ROOT}" nohup "${VENV}/bin/python" -m uvicorn crypto_quant_ai.backend.api.app:app \
  --host 127.0.0.1 --port 8000 >> "${LOG}" 2>&1 &

sleep 3
open "http://127.0.0.1:8000/docs" 2>/dev/null || true
exit 0
LAUNCH
chmod +x "${APP}/Contents/MacOS/BTT"

# ---- BTT Stop.app Info.plist ----
cat > "${STOP}/Contents/Info.plist" <<'PLIST2'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>BTT Stop</string>
  <key>CFBundleDisplayName</key><string>BTT Stop</string>
  <key>CFBundleIdentifier</key><string>com.roundtable.btt.stop</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleExecutable</key><string>BTT</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
</dict>
</plist>
PLIST2

# ---- BTT Stop.app 启动器 ----
cat > "${STOP}/Contents/MacOS/BTT" <<'STOPL'
#!/usr/bin/env bash
set -uo pipefail
if pkill -f "uvicorn crypto_quant_ai" 2>/dev/null; then
  /usr/bin/osascript -e 'display notification "BTT 服务已停止" with title "BTT"' 2>/dev/null || true
else
  /usr/bin/osascript -e 'display notification "BTT 服务未在运行" with title "BTT"' 2>/dev/null || true
fi
exit 0
STOPL
chmod +x "${STOP}/Contents/MacOS/BTT"

echo "[make-app] 完成:"
echo "  ${APP}"
echo "  ${STOP}"
echo "把这两个 .app 拖到 /Applications 即可双击使用。"
