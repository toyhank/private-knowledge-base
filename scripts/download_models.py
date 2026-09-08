"""Download only public model files; no document data is read or sent."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import Settings

settings = Settings()
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
from huggingface_hub import snapshot_download

requested = sys.argv[1:]
for model in requested or (settings.embedding_model, settings.reranker_model):
    print(f"Downloading {model} -> {settings.model_cache}", flush=True)
    snapshot_download(
        model,
        cache_dir=str(settings.model_cache),
        allow_patterns=["*.json", "*.safetensors", "*.bin", "*.model", "*.txt"],
        ignore_patterns=["onnx/*", "openvino/*"],
        max_workers=4,
    )
    print(f"Ready: {model}", flush=True)
