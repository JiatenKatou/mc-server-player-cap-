@echo off
rem ============================================================
rem  Minecraft player-capacity calculator - CLI launcher (ASCII)
rem  Interactive: just run it.  One-shot: add parameters, e.g.
rem    this.cmd --mods 30 --cpu "i5-12400" --ram 16G --net "good"
rem ============================================================
chcp 65001 >nul
setlocal

set "HERE=%~dp0"
set "BUNDLED=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

if exist "%BUNDLED%" (set "PY=%BUNDLED%") else (set "PY=python")

set "PYTHONIOENCODING=utf-8"
cd /d "%HERE%"
"%PY%" -m mc_player_calc.cli %*
echo.
pause
endlocal
