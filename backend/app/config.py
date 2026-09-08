import ipaddress
from pathlib import Path
from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


def local_endpoint(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        return False
    if parsed.hostname in {"localhost", "host.docker.internal", "qdrant"}:
        return True
    try:
        addr = ipaddress.ip_address(parsed.hostname)
        return addr.is_loopback or (addr.is_private and not addr.is_unspecified)
    except ValueError:
        return False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    data_dir: Path = ROOT / "data"
    model_cache: Path = ROOT / "models"
    qdrant_url: str = ""
    qdrant_collection: str = "knowledge_bge_m3_v1"
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"
    embedding_batch_size: int = 4
    embedding_dimensions: int = 1024
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_device: str = "cpu"
    reranker_batch_size: int = 2
    reranker_max_length: int = 1200
    models_local_only: bool = True
    llm_base_url: str = "http://127.0.0.1:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "knowledge-qwen3:8b"
    llm_reasoning_effort: str = "none"
    llm_context_tokens: int = 8192
    llm_max_tokens: int = 768
    llm_timeout_seconds: int = 180
    allow_remote_endpoints: bool = False
    chunk_size: int = 800
    chunk_overlap: int = 120
    retrieval_top_k: int = 30
    rerank_top_k: int = 5
    min_rerank_score: float = 0.15
    max_upload_mb: int = 25
    max_parsed_chars: int = 2_000_000
    max_pdf_pages: int = 500
    rag_debug: bool = False
    frontend_dist: Path = ROOT / "frontend" / "dist"

    @model_validator(mode="after")
    def validate_settings(self):
        if not 0 <= self.chunk_overlap < self.chunk_size <= 2000:
            raise ValueError("需要 0 <= CHUNK_OVERLAP < CHUNK_SIZE <= 2000")
        if self.embedding_device not in {"cpu", "cuda"} or self.reranker_device not in {"cpu", "cuda"}:
            raise ValueError("模型设备必须是 cpu 或 cuda")
        for field in (
            "embedding_batch_size",
            "embedding_dimensions",
            "reranker_batch_size",
            "retrieval_top_k",
            "rerank_top_k",
            "max_upload_mb",
            "max_pdf_pages",
            "max_parsed_chars",
            "llm_timeout_seconds",
            "llm_max_tokens",
        ):
            if getattr(self, field) <= 0:
                raise ValueError(f"{field} 必须大于 0")
        if self.rerank_top_k > self.retrieval_top_k or not 0 <= self.min_rerank_score <= 1:
            raise ValueError("检索数量或重排阈值配置无效")
        if self.reranker_max_length < self.chunk_size + 128 or self.reranker_max_length > 8192:
            raise ValueError("RERANKER_MAX_LENGTH 需要容纳 chunk 和问题，且不能超过 8192")
        if self.llm_context_tokens - self.llm_max_tokens < 2048:
            raise ValueError("LLM 上下文预算不足")
        if not self.allow_remote_endpoints:
            for url in (self.llm_base_url, self.qdrant_url):
                if url and not local_endpoint(url):
                    raise ValueError("默认仅允许本地/私网模型和向量服务地址")
        return self
