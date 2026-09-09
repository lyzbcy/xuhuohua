# ============================================================
# 抖音续火花 - 运行入口
# 用法：douyin-run.ps1           正式发送
#       douyin-run.ps1 -DryRun   演练（只找好友不发消息）
# ============================================================
param([switch]$DryRun)

. (Join-Path $PSScriptRoot "common.ps1")

$py = Join-Path $DouyinDir ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Fail "未找到 Python 虚拟环境，请先运行 scripts/install.ps1 完成安装"
    exit 2
}

# 登录凭证检查（storage-state.json 或 .env 里的 DOUYIN_COOKIE 至少要有一个）
$stateFile = Join-Path $DouyinDir "storage-state.json"
$envFile   = Join-Path $DouyinDir ".env"
$hasCookie = $false
if (Test-Path $envFile) {
    $hasCookie = (Select-String -Path $envFile -Pattern '^\s*DOUYIN_COOKIE=\S' -Quiet)
}
if (-not (Test-Path $stateFile) -and -not $hasCookie) {
    Write-Fail "还没有登录抖音：请先双击 scripts\douyin-login.bat 扫码登录"
    exit 3
}

Set-Location $DouyinDir
if ($DryRun) {
    Write-Step "演练模式启动：只验证登录和好友定位，不会真的发消息……"
    & $py run.py --dry-run
} else {
    Write-Step "正式模式启动：即将给话术库配置的好友发送消息……"
    & $py run.py
}
$code = $LASTEXITCODE
if ($code -eq 0) { Write-Ok "本次抖音续火花任务完成" }
else { Write-Fail "任务异常退出（退出码 $code），详见日志和 douyin-auto-fire\artifacts\run.log" }
exit $code
