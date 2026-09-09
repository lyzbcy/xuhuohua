$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
& "$ProjectRoot\.venv\Scripts\python.exe" "$ProjectRoot\run.py"
exit $LASTEXITCODE
