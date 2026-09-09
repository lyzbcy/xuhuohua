# ============================================================
# 一次性环境安装（新机器/重置后运行）
# 抖音侧：venv + 依赖 + Playwright Chromium
# QQ 侧：构建 napcat 插件并部署到 NapCat plugins 目录
# ============================================================
. (Join-Path $PSScriptRoot "common.ps1")

# ---- 抖音侧 ----
Write-Step "【抖音侧】创建 Python 虚拟环境……"
Push-Location $DouyinDir
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
Write-Step "【抖音侧】安装依赖（可能需要几分钟）……"
& .\.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
Write-Step "【抖音侧】下载 Playwright Chromium 浏览器（约 130MB，耐心等待）……"
& .\.venv\Scripts\python.exe -m playwright install chromium
Pop-Location
Write-Ok "【抖音侧】安装完成"

# ---- QQ 侧 ----
$pluginDir = Join-Path $ProjectRoot "napcat-plugin-auto-tasks"
Write-Step "【QQ侧】构建 NapCat 续火花插件……"
Push-Location $pluginDir
npm install --no-fund --no-audit
npm run build
Pop-Location

# 部署插件到 NapCat（若 NapCat 目录结构已就位）
$napcatPlugins = Join-Path $ProjectRoot "tools\napcat\shell\plugins"
if (Test-Path (Split-Path $napcatPlugins -Parent)) {
    New-Item -ItemType Directory -Force -Path $napcatPlugins | Out-Null
    Copy-Item (Join-Path $pluginDir "dist\*") $napcatPlugins -Recurse -Force
    Write-Ok "【QQ侧】插件已部署到 $napcatPlugins"
} else {
    Write-Warn2 "【QQ侧】NapCat Shell 目录不存在，插件产物在 napcat-plugin-auto-tasks\dist，请参考 docs\部署指南.md 手动部署"
}
Write-Ok "全部安装完成"
