$ErrorActionPreference = "Stop"
$swRoot = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..\software"
$py = Join-Path $swRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "[X] software/.venv missing"; exit 2 }
& $py -c "import sys; sys.path.insert(0, r'$swRoot'); from backend.scheduler import remove; r = remove(); print(r['msg']); exit(0 if r['ok'] else 1)"
exit $LASTEXITCODE