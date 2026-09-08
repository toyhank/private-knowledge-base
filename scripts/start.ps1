$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (!(Test-Path '.venv\Scripts\python.exe')) { throw '请先运行 uv sync --python 3.12' }
if (!(Test-Path 'frontend\dist\index.html')) { throw '请先在 frontend 中运行 npm ci 和 npm run build' }
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$env:TOKENIZERS_PARALLELISM = 'false'
Write-Host '知屿正在启动：http://127.0.0.1:8000'
& .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

