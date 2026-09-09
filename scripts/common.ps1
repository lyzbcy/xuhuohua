# ============================================================
# 续火花项目 - 公共库：日志系统 + 路径常量
# 设计依据：E:\共享\tools\软件开发\软件组件\日志系统.md
#   1) 开发者视角：结构化落盘日志，便于定位问题
#   2) 用户视角：控制台输出当前正在做什么，长操作不焦虑
# ============================================================

$script:ProjectRoot = Split-Path -Parent $PSScriptRoot
$script:DouyinDir   = Join-Path $ProjectRoot "douyin-auto-fire"
$script:LogDir      = Join-Path $ProjectRoot "logs"
$script:NapCatDir   = Join-Path $ProjectRoot "tools\napcat\shell"

if (-not (Test-Path $script:LogDir)) { New-Item -ItemType Directory -Path $script:LogDir | Out-Null }

# 当天日志文件：logs/2026-09-09.log
$script:LogFile = Join-Path $script:LogDir ("{0}.log" -f (Get-Date -Format "yyyy-MM-dd"))

function Write-Log {
    param([string]$Level, [string]$Message)
    $line = "[{0}] [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Add-Content -Path $script:LogFile -Value $line -Encoding UTF8
}

# 用户友好的进度提示：同时上屏 + 落盘
function Write-Step {
    param([string]$Message)
    Write-Host ("▶ " + $Message) -ForegroundColor Cyan
    Write-Log -Level "INFO" -Message $Message
}

function Write-Ok {
    param([string]$Message)
    Write-Host ("✔ " + $Message) -ForegroundColor Green
    Write-Log -Level "OK  " -Message $Message
}

function Write-Warn2 {
    param([string]$Message)
    Write-Host ("⚠ " + $Message) -ForegroundColor Yellow
    Write-Log -Level "WARN" -Message $Message
}

function Write-Fail {
    param([string]$Message)
    Write-Host ("✘ " + $Message) -ForegroundColor Red
    Write-Log -Level "FAIL" -Message $Message
}

# 读取项目版本号（版本管理：开发完成必须更新 VERSION）
function Get-ProjectVersion {
    return (Get-Content (Join-Path $script:ProjectRoot "VERSION") -Raw).Trim()
}
