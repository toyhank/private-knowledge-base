import logging
from queue import Queue
from threading import Event, Thread

from ..chunking import split_chunks
from ..parsers import parse_document

logger = logging.getLogger("knowledge.documents")


class DocumentService:
    """One bounded-model worker. Persisted statuses recover work after process restart."""

    def __init__(self, settings, repository, embedding, vectors, operation_lock):
        self.settings, self.repository, self.embedding, self.vectors = (
            settings,
            repository,
            embedding,
            vectors,
        )
        self.lock = operation_lock
        self.queue = Queue()
        self.stop_event = Event()
        self.thread = Thread(target=self._worker, name="document-indexer", daemon=True)

    def path(self, doc):
        return self.settings.data_dir / "uploads" / f"{doc.document_id}{doc.file_type}"

    def start(self):
        for doc in self.repository.list():
            if doc.status in {"uploaded", "parsing", "indexing", "deleting"}:
                self.queue.put(doc.document_id)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.queue.put(None)
        self.thread.join()  # Do not close Qdrant while the worker still owns it.

    def _worker(self):
        while not self.stop_event.is_set():
            doc_id = self.queue.get()
            try:
                if doc_id is None:
                    break
                doc = self.repository.get(doc_id)
                if not doc:
                    continue
                if doc.status == "deleting":
                    self.delete(doc_id)
                else:
                    self.index(doc_id)
            except Exception:
                logger.exception("Background document operation failed for %s", doc_id)
            finally:
                self.queue.task_done()

    def index(self, doc_id):
        doc = self.repository.get(doc_id)
        try:
            with self.lock:
                self.repository.update(doc_id, status="parsing", chunk_count=0, error=None)
                self.vectors.delete_document(doc_id)
            blocks = parse_document(self.path(doc), self.settings)
            chunks = split_chunks(
                blocks,
                doc_id,
                doc.filename,
                self.embedding.tokenizer,
                self.settings.chunk_size,
                self.settings.chunk_overlap,
            )
            with self.lock:
                self.repository.update(doc_id, status="indexing")
            batch = self.settings.embedding_batch_size
            for offset in range(0, len(chunks), batch):
                if self.stop_event.is_set():
                    return  # Keep indexing status so startup retries from a clean index.
                group = chunks[offset : offset + batch]
                embeddings = self.embedding.embed_documents([c.text for c in group])
                with self.lock:
                    self.vectors.upsert_chunks(group, embeddings)
            with self.lock:
                self.repository.update(doc_id, status="ready", chunk_count=len(chunks))
        except Exception as exc:
            try:
                with self.lock:
                    self.vectors.delete_document(doc_id)
            except Exception:
                logger.exception("Partial index cleanup failed: %s", doc_id)
            self.repository.update(doc_id, status="failed", error=str(exc)[:600], chunk_count=0)
            logger.exception("Index failed: %s", doc_id)

    def delete(self, doc_id):
        with self.lock:
            doc = self.repository.get(doc_id)
            if doc:
                self.repository.update(doc_id, status="deleting", error=None)
                self.vectors.delete_document(doc_id)
                self.path(doc).unlink(missing_ok=True)
                self.repository.delete(doc_id)
