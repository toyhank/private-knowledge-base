import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime

os.environ["TOKENIZERS_PARALLELISM"] = "false"
from logging.handlers import RotatingFileHandler
from threading import Lock, RLock
from typing import Annotated
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .repository import Repository
from .schemas import ChatRequest, ChatResponse, Document
from .services.document_service import DocumentService
from .services.embedding_service import EmbeddingService
from .services.llm_client import LLMClient
from .services.rag_service import RagService
from .services.reranker_service import RerankerService
from .services.retrieval_service import RetrievalService
from .services.vector_store import VectorStore


def create_app(settings=None, embedding=None, reranker=None, llm=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        (settings.data_dir / "uploads").mkdir(exist_ok=True)
        settings.model_cache.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            settings.data_dir / "rag.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
        )
        logger = logging.getLogger("knowledge")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        repository = Repository(settings.data_dir / "metadata.sqlite3")
        vectors = VectorStore(settings)
        emb = embedding or EmbeddingService(settings)
        lock = RLock()
        docs = DocumentService(settings, repository, emb, vectors, lock)
        app.state.repository, app.state.vectors, app.state.docs = repository, vectors, docs
        app.state.operation_lock = lock
        app.state.chat_lock = Lock()
        app.state.embedding = emb
        app.state.reranker = reranker or RerankerService(settings)
        app.state.rag = RagService(
            settings,
            repository,
            RetrievalService(emb, vectors, settings),
            app.state.reranker,
            llm or LLMClient(settings),
        )
        docs.start()
        try:
            yield
        finally:
            docs.stop()
            vectors.close()
            logger.removeHandler(handler)
            handler.close()

    app = FastAPI(title="私有知识库", lifespan=lifespan)

    @app.middleware("http")
    async def protect_local_app(request: Request, call_next):
        # Same-origin browser writes prevent arbitrary websites from uploading/deleting local data.
        origin = request.headers.get("origin")
        if request.method in {"POST", "DELETE", "PUT", "PATCH"} and origin:
            from urllib.parse import urlparse

            if urlparse(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "不允许跨站操作本地知识库"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'"
        )
        return response

    def get_doc(doc_id):
        try:
            UUID(doc_id)
        except ValueError:
            raise HTTPException(404, "文档不存在")
        doc = app.state.repository.get(doc_id)
        if not doc:
            raise HTTPException(404, "文档不存在")
        return doc

    @app.get("/api/health")
    def health():
        reachable, available, error = False, False, None
        try:
            with httpx.Client(timeout=3, trust_env=False) as client:
                response = client.get(
                    f"{settings.llm_base_url.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                )
                response.raise_for_status()
                reachable = True
                available = settings.llm_model in [model["id"] for model in response.json().get("data", [])]
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            error = "本地模型服务未连接"
        return {
            "status": "ok",
            "storage": "server" if settings.qdrant_url else "local",
            "llm": {
                "reachable": reachable,
                "available": available,
                "model": settings.llm_model,
                "error": error,
            },
            "embedding_loaded": getattr(app.state.embedding, "_model", None) is not None,
            "reranker_loaded": getattr(app.state.reranker, "_model", None) is not None,
            "devices": {"embedding": settings.embedding_device, "reranker": settings.reranker_device},
        }

    @app.get("/api/documents", response_model=list[Document])
    def list_documents():
        return app.state.repository.list()

    @app.post("/api/documents/upload", response_model=Document, status_code=202)
    def upload_document(file: Annotated[UploadFile, File()]):
        from pathlib import Path

        filename = (file.filename or "document").replace("\\", "/").split("/")[-1][:240]
        suffix = Path(filename).suffix.lower()
        if suffix not in {".pdf", ".docx", ".md", ".txt"}:
            raise HTTPException(415, "仅支持 PDF、DOCX、Markdown 和 TXT")
        doc_id = str(uuid4())
        doc = Document(
            document_id=doc_id,
            filename=filename,
            file_type=suffix,
            file_size=0,
            created_at=datetime.now(UTC).isoformat(),
            status="uploaded",
        )
        target = app.state.docs.path(doc)
        temporary = target.with_suffix(suffix + ".part")
        try:
            with temporary.open("wb") as output:
                while data := file.file.read(1024 * 1024):
                    doc.file_size += len(data)
                    if doc.file_size > settings.max_upload_mb * 1024 * 1024:
                        raise HTTPException(413, f"文件不能超过 {settings.max_upload_mb} MB")
                    output.write(data)
            if doc.file_size == 0:
                raise HTTPException(400, "不能上传空文件")
            temporary.replace(target)
            app.state.repository.add(doc)
        except Exception:
            temporary.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            raise
        finally:
            file.file.close()
        app.state.docs.queue.put(doc_id)
        return doc

    @app.get("/api/documents/{doc_id}", response_model=Document)
    def document_detail(doc_id: str):
        return get_doc(doc_id)

    @app.get("/api/documents/{doc_id}/chunks")
    def document_chunks(doc_id: str, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
        doc = get_doc(doc_id)
        if doc.status != "ready":
            raise HTTPException(409, "文档尚未就绪")
        return app.state.vectors.chunks(doc_id, offset, limit)

    @app.post("/api/documents/{doc_id}/retry", response_model=Document, status_code=202)
    def retry_document(doc_id: str):
        with app.state.operation_lock:
            doc = get_doc(doc_id)
            if doc.status != "failed":
                raise HTTPException(409, "只有失败的文档可以重试")
            app.state.repository.update(doc_id, status="uploaded", error=None)
            app.state.docs.queue.put(doc_id)
            return get_doc(doc_id)

    @app.delete("/api/documents/{doc_id}", status_code=204)
    def delete_document(doc_id: str):
        get_doc(doc_id)
        try:
            app.state.docs.delete(doc_id)
        except Exception as exc:
            raise HTTPException(503, "删除未完成，请检查向量服务后重试；重启时也会继续清理") from exc

    @app.post("/api/chat", response_model=ChatResponse, response_model_exclude_none=True)
    def chat(body: ChatRequest):
        if not app.state.chat_lock.acquire(blocking=False):
            raise HTTPException(429, "正在回答上一条问题，请稍后再试")
        try:
            with app.state.operation_lock:
                for doc_id in body.document_ids:
                    if get_doc(doc_id).status != "ready":
                        raise HTTPException(409, "选中的文档尚未就绪")
                return app.state.rag.answer(body)
        except HTTPException:
            raise
        except Exception as exc:
            logging.getLogger("knowledge").exception("Chat failed")
            detail = str(exc) if isinstance(exc, RuntimeError) else "检索或模型服务不可用，请查看本地日志"
            raise HTTPException(503, detail) from exc
        finally:
            app.state.chat_lock.release()

    if settings.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
    return app


app = create_app()
