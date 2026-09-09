# ============================================================
# 检查更新：核对本地版本与上游远端版本，安全更新
# 依据：E:\共享\tools\软件开发\软件组件\自适应更新检测.md
#   - 更新前提醒开代理（国内访问 GitHub 慢）
#   - 失败兜底：提示重试，本地配置（gitignored）不受影响
# ============================================================
. (Join-Path $PSScriptRoot "common.ps1")

Write-Step ("当前项目版本：v" + (Get-ProjectVersion))
Write-Warn2 "国内网络建议先开代理，更新 GitHub 仓库会快很多"
Write-Step "正在检查上游项目更新（douyin-auto-fire / napcat-plugin-auto-tasks / DouYinSparkFlow）……"

$repos = @(
    @{ Name = "douyin-auto-fire（抖音主力）";        Dir = $DouyinDir },
    @{ Name = "napcat-plugin-auto-tasks（QQ插件）";  Dir = Join-Path $ProjectRoot "napcat-plugin-auto-tasks" },
    @{ Name = "DouYinSparkFlow（抖音备选）";         Dir = Join-Path $ProjectRoot "DouYinSparkFlow" }
)

$failed = @()
foreach ($r in $repos) {
    if (-not (Test-Path (Join-Path $r.Dir ".git"))) { continue }
    Push-Location $r.Dir
    git fetch --quiet 2>$null
    $local  = git rev-parse HEAD
    $remote = git rev-parse "@{u}" 2>$null
    if ($LASTEXITCODE -ne 0) { $remote = git rev-parse origin/HEAD 2>$null }
    if ($local -eq $remote) {
        Write-Ok ($r.Name + " 已是最新")
    } else {
        Write-Step ($r.Name + " 有更新，正在拉取……")
        git pull --ff-only --quiet 2>$null
        if ($LASTEXITCODE -eq 0) { Write-Ok ($r.Name + " 更新完成") }
        else { Write-Fail ($r.Name + " 更新失败（本地有改动冲突？），可稍后重试"); $failed += $r.Name }
    }
    Pop-Location
}

# 抖音侧依赖同步（上游 requirements 变化时保持一致）
if ((Test-Path (Join-Path $DouyinDir ".venv\Scripts\python.exe")) -and ($failed.Count -eq 0)) {
    Write-Step "同步抖音侧 Python 依赖……"
    Push-Location $DouyinDir
    & .\.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
    Pop-Location
    Write-Ok "依赖同步完成"
}

if ($failed.Count -gt 0) {
    Write-Warn2 ("以下仓库更新失败：" + ($failed -join "、") + "。不影响现有使用，可下次重试")
} else {
    Write-Ok "全部检查完毕"
}
Write-Step "注意：你的个人配置（config.json / storage-state.json / .env）不会被更新覆盖"
