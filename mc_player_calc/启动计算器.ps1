# Minecraft 服务器人数上限计算器 —— 本地网页版启动器（推荐）
# 用法：右键「使用 PowerShell 运行」
#      或在终端： powershell -ExecutionPolicy Bypass -File .\启动计算器.ps1
#      指定端口： powershell -ExecutionPolicy Bypass -File .\启动计算器.ps1 --port 9000

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$bundled = Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$python = if (Test-Path $bundled) { $bundled }
          elseif (Get-Command python -ErrorAction SilentlyContinue) { 'python' }
          else { 'py' }

$env:PYTHONIOENCODING = 'utf-8'

Write-Host '正在启动本地网页版……' -ForegroundColor Green
Write-Host '浏览器会自动打开；关闭本窗口（或按 Ctrl+C）即停止服务。' -ForegroundColor DarkGray
Write-Host ''

# 默认：本地网页 + 自动开浏览器
& $python -m mc_player_calc.web @args

# 其它入口（按需把上面一行换成下面任意一条）：
#   & $python -m mc_player_calc.gui              # 桌面窗口版
#   & $python -m mc_player_calc.cli              # 命令行交互版
#   & $python -m mc_player_calc.cli --mods 30 --cpu "i5-12400" --ram 16G --net "良好"
