$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot\backend\venv\Scripts\python.exe" -m uvicorn backend.platform.api:app --host 127.0.0.1 --port 8000
