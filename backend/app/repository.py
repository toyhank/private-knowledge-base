import sqlite3
from contextlib import contextmanager

from .schemas import Document


class Repository:
    """SQLite owns document lifecycle; Qdrant owns chunk payloads and vectors."""

    def __init__(self, path):
        self.path = path
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS documents (
                document_id TEXT PRIMARY KEY, filename TEXT NOT NULL, file_type TEXT NOT NULL,
                file_size INTEGER NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL,
                chunk_count INTEGER NOT NULL DEFAULT 0, error TEXT)""")

    @contextmanager
    def connect(self):
        with sqlite3.connect(self.path, timeout=30) as db:
            db.row_factory = sqlite3.Row
            yield db

    def add(self, document: Document):
        values = document.model_dump()
        with self.connect() as db:
            db.execute(
                f"INSERT INTO documents ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",
                list(values.values()),
            )

    def list(self):
        with self.connect() as db:
            return [
                Document(**dict(row))
                for row in db.execute("SELECT * FROM documents ORDER BY created_at DESC")
            ]

    def get(self, document_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM documents WHERE document_id=?", (document_id,)).fetchone()
            return Document(**dict(row)) if row else None

    def update(self, document_id, **fields):
        if not fields or not set(fields) <= {"status", "chunk_count", "error"}:
            raise ValueError("Invalid document update")
        with self.connect() as db:
            db.execute(
                f"UPDATE documents SET {','.join(f'{key}=?' for key in fields)} WHERE document_id=?",
                [*fields.values(), document_id],
            )

    def delete(self, document_id):
        with self.connect() as db:
            db.execute("DELETE FROM documents WHERE document_id=?", (document_id,))
