from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Document(BaseModel):
    document_id: str
    filename: str
    file_type: str
    file_size: int
    created_at: str
    status: Literal["uploaded", "parsing", "indexing", "ready", "failed", "deleting"]
    chunk_count: int = 0
    error: str | None = None


class Chunk(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    page: int | None = None
    section: str = ""
    text: str
    chunk_index: int


class Hit(BaseModel):
    chunk: Chunk
    retrieval_score: float
    score: float = 0


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    document_ids: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("message")
    @classmethod
    def nonblank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("请输入问题")
        return value


class Citation(Chunk):
    id: int
    score: float


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    request_id: str
    debug: dict | None = None
    created_at: str | None = None
    latency_ms: int | None = None
