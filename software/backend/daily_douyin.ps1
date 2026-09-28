# 每日定时任务入口：无窗口静默运行抖音续火花（由软件注册，路径自动跟随项目位置）
# 注意：必须用 Continue —— PS 5.1 下 stderr 2>&1 重定向 + Stop 会让引擎第一条
# WARNING 就中断整个管道，导致本次运行报废且日志残缺。
$ErrorActionPreference = "Continue"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$projRoot = Split-Path -Parent (Split-Path -Parent $here)
$py = Join-Path $projRoot "douyin-auto-fire\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = Join-Path $projRoot "runtime\python.exe" }
$logDir = Join-Path $projRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
# 与软件界面日志同一份文件，用户只需要看一个地方
$log = Join-Path $logDir ("{0}-software.log" -f (Get-Date -Format "yyyy-MM-dd"))

function L($m) { Add-Content -Path $log -Value ("[{0}] [SCHED] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m) -Encoding UTF8 }

if (-not (Test-Path $py)) { L "抖音引擎尚未初始化，跳过本次定时任务"; exit 2 }

Set-Location (Join-Path $projRoot "douyin-auto-fire")
$state = Test-Path "storage-state.json"
$hasCookie = $false
if (Test-Path ".env") { $hasCookie = [bool](Select-String -Path ".env" -Pattern '^\s*DOUYIN_COOKIE=\S' -Quiet) }
if (-not $state -and -not $hasCookie) { L "未登录抖音，跳过本次定时任务"; exit 3 }

# 上次进程异常退出会留下 run.lock；仅在锁里的 PID 已消失时清理。
$lockFile = Join-Path $projRoot "douyin-auto-fire\artifacts\run.lock"
if (Test-Path $lockFile) {
  $lockText = (Get-Content -Path $lockFile -Raw).Trim()
  $lockPid = 0
  $validPid = [int]::TryParse($lockText, [ref]$lockPid)
  if (-not $validPid -or -not (Get-Process -Id $lockPid -ErrorAction SilentlyContinue)) {
    Remove-Item -LiteralPath $lockFile -Force
    L "已清理上次异常退出留下的任务锁"
  }
}

L "定时任务触发，开始运行"
$cfgFile = Join-Path $projRoot "config\settings.json"
$env:HEADLESS = "true"
if (Test-Path $cfgFile) {
  try {
    $browserSettings = Get-Content $cfgFile -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($browserSettings.browser_headless -eq $false) { $env:HEADLESS = "false" }
  } catch { L "浏览器模式设置读取失败，使用默认无头模式" }
}
L ("浏览器模式：" + $(if ($env:HEADLESS -eq "true") { "无头" } else { "有头" }))
$lastSummary = ""
& $py run.py 2>&1 | ForEach-Object {
  $line = [string]$_
  L ("[OUT] " + $line)
  if ($line -match "执行结束: (.+)$") { $script:lastSummary = $Matches[1] }
}
$runExit = $LASTEXITCODE
L "本次运行结束（退出码 $runExit）"

# 企业微信通知（设置页配置后启用）
if (Test-Path $cfgFile) {
  try {
    $cfg = Get-Content $cfgFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $hook = $cfg.wecom_webhook
    if ($hook -and ($runExit -eq 0 -and $cfg.notify_on_success -or $runExit -ne 0 -and $cfg.notify_on_failure)) {
      $last = if ($lastSummary) { $lastSummary } else { "本次未生成结果摘要" }
      $body = @{ msgtype = "text"; text = @{ content = "【续火花】每日抖音任务结束：$last（退出码 $runExit）" } } | ConvertTo-Json -Compress
      try { Invoke-RestMethod -Uri $hook -Method Post -ContentType "application/json; charset=utf-8" -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) | Out-Null } catch { L "企微通知发送失败: $_" }
    }
  } catch { L "读取通知设置失败: $_" }
}
exit $runExit
