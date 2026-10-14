# Minecraft 服务器人数上限计算器 —— 桌面窗口版（tkinter，不启动本地服务）
# 用法：右键「使用 PowerShell 运行」

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$bundled = Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$python = if (Test-Path $bundled) { $bundled }
          elseif (Get-Command python -ErrorAction SilentlyContinue) { 'python' }
          else { 'py' }

$env:PYTHONIOENCODING = 'utf-8'
& $python -m mc_player_calc.gui
