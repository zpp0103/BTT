#!/usr/bin/env bash
#
# BTT macOS DMG 打包脚本
# 把仓库源码（排除 .git/.venv/dist 等）rsync 进临时目录，
# 再用 hdiutil 压成 btt-macos-installer.dmg（内含 install-btt.command）。
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DIST_DIR="${REPO_ROOT}/dist"
STAGE_DIR="${DIST_DIR}/btt-macos-stage"
DMG_PATH="${DIST_DIR}/btt-macos-installer.dmg"

rm -rf "${STAGE_DIR}"
mkdir -p "${STAGE_DIR}"

rsync -a --exclude '.git' \
  --exclude '.venv' \
  --exclude 'dist' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '*.pyo' \
  --exclude '*.sqlite*' \
  --exclude 'logfile.txt' \
  --exclude 'user_data' \
  --exclude 'node_modules' \
  --exclude '.DS_Store' \
  --exclude 'freqtrade.egg-info' \
  "${REPO_ROOT}/" "${STAGE_DIR}/"

chmod +x "${STAGE_DIR}/installers/macos/install-btt.command"

rm -f "${DMG_PATH}"
hdiutil create -volname "BTT Installer" -srcfolder "${STAGE_DIR}" -ov -format UDZO "${DMG_PATH}"
echo "Created: ${DMG_PATH}"
