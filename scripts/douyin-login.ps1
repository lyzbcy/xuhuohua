# ============================================================
# 抖音续火花 - 扫码登录（生成 storage-state.json 登录凭证）
# ============================================================
. (Join-Path $PSScriptRoot "common.ps1")

$py = Join-Path $DouyinDir ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Fail "未找到 Python 虚拟环境，请先运行 scripts/install.ps1 完成安装"
    exit 2
}

Write-Step "正在打开浏览器，请用抖音 App 扫码登录……"
Write-Step "登录成功进入抖音首页后，回到本窗口按 Enter 确认"
Set-Location $DouyinDir
& $py scripts\login.py
$code = $LASTEXITCODE

if ((Test-Path (Join-Path $DouyinDir "storage-state.json")) -and $code -eq 0) {
    Write-Ok "登录成功，凭证已保存到 storage-state.json（不要外传！）"
    Write-Step "建议接着双击 scripts\douyin-run-dryrun.bat 验证一遍"
} else {
    Write-Fail "登录未完成，凭证文件未生成"
}
exit $code
