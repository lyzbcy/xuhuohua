# 每日定时任务入口：无窗口静默运行抖音续火花（由软件注册，路径自动跟随项目位置）
# 注意：必须用 Continue —— PS 5.1 下 stderr 2>&1 重定向 + Stop 会让引擎第一条
# WARNING 就中断整个管道，导致本次运行报废且日志残缺。
$ErrorActionPreference = "Continue"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$projRoot = Split-Path -Parent (Split-Path -Parent $here)
$py = Join-Path $projRoot "douyin-auto-fire\.venv\Scripts\python.exe"
$logDir = Join-Path $projRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
# 与软件界面日志同一份文件，用户只需要看一个地方
$log = Join-Path $logDir ("{0}-software.log" -f (Get-Date -Format "yyyy-MM-dd"))

function L($m) { Add-Content -Path $log -Value ("[{0}] [SCHED] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m) -Encoding UTF8 }

Set-Location (Join-Path $projRoot "douyin-auto-fire")
$state = Test-Path "storage-state.json"
$hasCookie = $false
if (Test-Path ".env") { $hasCookie = [bool](Select-String -Path ".env" -Pattern '^\s*DOUYIN_COOKIE=\S' -Quiet) }
if (-not $state -and -not $hasCookie) { L "未登录抖音，跳过本次定时任务"; exit 3 }

L "定时任务触发，开始运行"
& $py run.py 2>&1 | ForEach-Object { L ("[OUT] " + $_) }
L "本次运行结束（退出码 $LASTEXITCODE）"
exit $LASTEXITCODE
