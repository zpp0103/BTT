#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DIST_DIR="${REPO_ROOT}/dist"
STAGE_DIR="${DIST_DIR}/btt-macos-stage"
DMG_PATH="${DIST_DIR}/btt-macos-installer.dmg"

rm -rf "${STAGE_DIR}"
mkdir -p "${STAGE_DIR}/installers/windows" "${STAGE_DIR}/installers/macos" "${STAGE_DIR}/installers/templates"

cp "${REPO_ROOT}/installers/macos/install-btt.command" "${STAGE_DIR}/installers/macos/"
cp "${REPO_ROOT}/installers/windows/install-btt.ps1" "${STAGE_DIR}/installers/windows/"
cp "${REPO_ROOT}/installers/windows/install-btt.bat" "${STAGE_DIR}/installers/windows/"
cp "${REPO_ROOT}/installers/templates/config.local.desktop.json" "${STAGE_DIR}/installers/templates/"
cp "${REPO_ROOT}/README.md" "${STAGE_DIR}/README.md"

chmod +x "${STAGE_DIR}/installers/macos/install-btt.command"

rm -f "${DMG_PATH}"
hdiutil create -volname "BTT Installer" -srcfolder "${STAGE_DIR}" -ov -format UDZO "${DMG_PATH}"
echo "Created: ${DMG_PATH}"
