@echo off
rem ============================================================
rem  Minecraft player-capacity calculator - local WEB launcher
rem  Opens http://127.0.0.1:8765/ in your browser automatically.
rem  Keep this window open while using the page; close it to stop.
rem  (Chinese .ps1 launcher is preferred if available.)
rem ============================================================
chcp 65001 >nul
setlocal

set "HERE=%~dp0"
set "BUNDLED=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

if exist "%BUNDLED%" (set "PY=%BUNDLED%") else (set "PY=python")

set "PYTHONIOENCODING=utf-8"
cd /d "%HERE%"

echo Starting local web UI ... your browser will open shortly.
echo Close this window (or press Ctrl+C) to stop the server.
echo.
"%PY%" -m mc_player_calc.web %*
if errorlevel 1 pause
endlocal
