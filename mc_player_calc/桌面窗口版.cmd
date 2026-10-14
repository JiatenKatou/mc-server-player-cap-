@echo off
rem ============================================================
rem  Minecraft player-capacity calculator - desktop window (Tk)
rem  No local server is started by this launcher.
rem  (Chinese .ps1 launcher is preferred if available.)
rem ============================================================
chcp 65001 >nul
setlocal

set "HERE=%~dp0"
set "BUNDLED=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

if exist "%BUNDLED%" (set "PY=%BUNDLED%") else (set "PY=python")

set "PYTHONIOENCODING=utf-8"
cd /d "%HERE%"
"%PY%" -m mc_player_calc.gui
if errorlevel 1 pause
endlocal
