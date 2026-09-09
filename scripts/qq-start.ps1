# ============================================================
# 启动 NapCat + QQ（QQ 侧续火花的运行载体）
# 原理：launcher.bat 从注册表定位本机 QQ → 注入 NapCat → 插件自动加载
# 首次运行会弹出 QQ 登录窗口，扫码登录一次即可
# 注意：launcher 会请求管理员权限（注入 QQ 需要），UAC 弹窗点「是」
# ============================================================
. (Join-Path $PSScriptRoot "common.ps1")

$bootBat = Join-Path $NapCatDir "launcher.bat"
if (-not (Test-Path $bootBat)) {
    Write-Fail "未找到 NapCat 启动器：$bootBat"
    exit 2
}
$pluginFile = Join-Path $NapCatDir "plugins\auto-tasks\index.mjs"
if (-not (Test-Path $pluginFile)) {
    Write-Warn2 "续火花插件未部署：正在从 napcat-plugin-auto-tasks\dist 复制……"
    New-Item -ItemType Directory -Force -Path (Split-Path $pluginFile) | Out-Null
    Copy-Item (Join-Path $ProjectRoot "napcat-plugin-auto-tasks\dist\*") (Split-Path $pluginFile) -Force
    Write-Ok "插件部署完成"
}

Write-Step "正在启动 NapCat（会弹 UAC 提权与 QQ 窗口）……"
Write-Step "首次启动扫码登录 QQ；登录后保持控制台窗口开着即可持续续火花"
Write-Step "插件配置入口：NapCat WebUI → 插件管理 → Auto Tasks（好友自动续火花）"
Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "`"$bootBat`"" -WorkingDirectory $NapCatDir
Write-Ok "NapCat 已拉起（详情看弹出的控制台窗口）"
