#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DIST_DIR="${REPO_ROOT}/dist"
STAGE_DIR="${DIST_DIR}/btt-macos-stage"
DMG_PATH="${DIST_DIR}/btt-macos-installer.dmg"
INSTALLER_SCRIPT="${REPO_ROOT}/installers/macos/install-btt.command"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script must be run on macOS (Darwin)."
  exit 1
fi

if ! command -v rsync >/dev/null 2>&1; then
  echo "Missing required command: rsync"
  exit 1
fi

if ! command -v hdiutil >/dev/null 2>&1; then
  echo "Missing required command: hdiutil"
  exit 1
fi

if [[ ! -f "${INSTALLER_SCRIPT}" ]]; then
  echo "Missing installer script: ${INSTALLER_SCRIPT}"
  exit 1
fi

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
  "${REPO_ROOT}/" "${STAGE_DIR}/"

chmod +x "${STAGE_DIR}/installers/macos/install-btt.command"

rm -f "${DMG_PATH}"
hdiutil create -volname "BTT Installer" -srcfolder "${STAGE_DIR}" -ov -format UDZO "${DMG_PATH}"
echo "Created: ${DMG_PATH}"
