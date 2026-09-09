# 查看今天的运行日志
. (Join-Path $PSScriptRoot "common.ps1")

if (Test-Path $LogFile) {
    Write-Step ("正在打开今日日志：" + $LogFile)
    Start-Process notepad.exe -ArgumentList "`"$LogFile`""
} else {
    Write-Warn2 "今天还没有日志记录（运行过一次脚本后才会生成）"
}
