#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
export HF_HUB_DISABLE_TELEMETRY=1
export TOKENIZERS_PARALLELISM=false
exec .venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

