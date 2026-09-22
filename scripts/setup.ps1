param(
    [switch]$SkipModels,
    [switch]$SkipLlm
)

$ErrorActionPreference = "Stop"

function Require-Command {
    param([string]$Name, [string]$Hint)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name was not found. $Hint"
    }
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

Write-Host "== KnowIsland setup ==" -ForegroundColor Cyan

Require-Command "uv" "Install uv from https://docs.astral.sh/uv/"
Require-Command "npm" "Install Node.js 22+ from https://nodejs.org/"
Require-Command "ollama" "Install Ollama from https://ollama.com/"

Write-Host "[1/6] Creating Python environment..."
uv sync --python 3.12 --cache-dir .cache/uv

if (-not (Test-Path ".env")) {
    Write-Host "[2/6] Creating .env from .env.example..."
    Copy-Item ".env.example" ".env"
} else {
    Write-Host "[2/6] Keeping existing .env"
}

if (-not $SkipModels) {
    Write-Host "[3/6] Downloading local embedding/reranker models..."
    .\.venv\Scripts\python.exe scripts\download_models.py
} else {
    Write-Host "[3/6] Skipping BGE model download"
}

Write-Host "[4/6] Installing frontend dependencies..."
npm.cmd ci --prefix frontend

Write-Host "[5/6] Building frontend..."
npm.cmd run build --prefix frontend

if (-not $SkipLlm) {
    Write-Host "[6/6] Preparing local Qwen model..."
    ollama pull qwen3:8b
    ollama create knowledge-qwen3:8b -f scripts\Modelfile
} else {
    Write-Host "[6/6] Skipping Ollama model setup"
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Start KnowIsland with:"
Write-Host "  .\scripts\start.ps1"
Write-Host "Then open http://127.0.0.1:8000"
