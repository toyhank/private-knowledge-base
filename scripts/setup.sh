#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SKIP_MODELS=0
SKIP_LLM=0
for arg in "$@"; do
  case "$arg" in
    --skip-models) SKIP_MODELS=1 ;;
    --skip-llm) SKIP_LLM=1 ;;
    *)
      echo "Unknown option: $arg" >&2
      echo "Usage: ./scripts/setup.sh [--skip-models] [--skip-llm]" >&2
      exit 2
      ;;
  esac
done

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing dependency: $1. $2" >&2
    exit 1
  fi
}

echo "== KnowIsland setup =="

need uv "Install uv: https://docs.astral.sh/uv/"
need npm "Install Node.js 22+: https://nodejs.org/"
need ollama "Install Ollama: https://ollama.com/"

echo "[1/6] Creating Python environment..."
uv sync --python 3.12 --cache-dir .cache/uv

if [[ ! -f .env ]]; then
  echo "[2/6] Creating .env from .env.example..."
  cp .env.example .env
else
  echo "[2/6] Keeping existing .env"
fi

if [[ "$SKIP_MODELS" -eq 0 ]]; then
  echo "[3/6] Downloading local embedding/reranker models..."
  .venv/bin/python scripts/download_models.py
else
  echo "[3/6] Skipping BGE model download"
fi

echo "[4/6] Installing frontend dependencies..."
npm ci --prefix frontend

echo "[5/6] Building frontend..."
npm run build --prefix frontend

if [[ "$SKIP_LLM" -eq 0 ]]; then
  echo "[6/6] Preparing local Qwen model..."
  ollama pull qwen3:8b
  ollama create knowledge-qwen3:8b -f scripts/Modelfile
else
  echo "[6/6] Skipping Ollama model setup"
fi

echo
echo "Setup complete."
echo "Start KnowIsland with:"
echo "  ./scripts/start.sh"
echo "Then open http://127.0.0.1:8000"
