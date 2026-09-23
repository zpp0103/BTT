@echo off
setlocal
set SCRIPT_DIR=%~dp0
powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install-btt.ps1" %*
if errorlevel 1 (
  echo.
  echo Installation failed.
  exit /b 1
)
echo.
echo Installation completed successfully.
exit /b 0
