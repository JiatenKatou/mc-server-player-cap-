# Minecraft 服务器人数上限计算器 —— 命令行启动器
# 用法：powershell -ExecutionPolicy Bypass -File .\命令行.ps1
#       powershell -ExecutionPolicy Bypass -File .\命令行.ps1 --mods 30 --cpu "i5-12400" --ram 16G --net "良好"

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$bundled = Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$python = if (Test-Path $bundled) { $bundled }
          elseif (Get-Command python -ErrorAction SilentlyContinue) { 'python' }
          else { 'py' }

$env:PYTHONIOENCODING = 'utf-8'
& $python -m mc_player_calc.cli @args
