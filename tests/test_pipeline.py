from datetime import UTC, datetime
from uuid import uuid4

import pytest
from conftest import FakeEmbedding, FakeLLM, FakeReranker

from backend.app.repository import Repository
from backend.app.schemas import ChatRequest, Chunk, Document
from backend.app.services.rag_service import NO_ANSWER, RagService
from backend.app.services.retrieval_service import RetrievalService
from backend.app.services.vector_store import VectorStore


@pytest.fixture
def pipeline(settings):
    store = VectorStore(settings)
    repository = Repository(settings.data_dir / "test.sqlite3")
    embedding = FakeEmbedding()
    ids = [str(uuid4()), str(uuid4())]
    texts = ["北京出差住宿标准为每人每晚600元。", "国内出差餐饮补贴100元。"]
    chunks = []
    for i in range(2):
        repository.add(
            Document(
                document_id=ids[i],
                filename=f"{i}.md",
                file_type=".md",
                file_size=30,
                created_at=datetime.now(UTC).isoformat(),
                status="ready",
                chunk_count=1,
            )
        )
        chunks.append(
            Chunk(
                chunk_id=str(uuid4()),
                document_id=ids[i],
                filename=f"{i}.md",
                page=i + 1,
                section="政策",
                text=texts[i],
                chunk_index=0,
            )
        )
    store.upsert_chunks(chunks, embedding.embed_documents(texts))
    yield repository, store, RetrievalService(embedding, store, settings), chunks
    store.close()


def test_qdrant_search_filter_delete(pipeline):
    _, store, retrieval, chunks = pipeline
    hits = retrieval.retrieve("北京住宿标准", [c.document_id for c in chunks])
    assert hits[0].chunk == chunks[0]
    assert retrieval.retrieve("北京住宿标准", [chunks[1].document_id])[0].chunk == chunks[1]
    store.delete_document(chunks[0].document_id)
    assert retrieval.retrieve("北京住宿标准", [chunks[0].document_id]) == []
    assert len(store.chunks(chunks[1].document_id)) == 1


def test_retrieval_rerank_citations_and_prompt(settings, pipeline):
    repository, _, retrieval, chunks = pipeline
    llm = FakeLLM()
    rag = RagService(settings, repository, retrieval, FakeReranker(), llm)
    response = rag.answer(ChatRequest(message="北京住宿标准是多少？"))
    assert "600" in response.answer
    assert response.citations[0].chunk_id == chunks[0].chunk_id
    assert response.citations[0].text == chunks[0].text
    assert response.citations[0].page == 1
    assert response.debug is None
    assert "知识库中没有找到足够信息" in llm.messages[0]["content"]
    assert "未经信任的数据" in llm.messages[0]["content"]


@pytest.mark.parametrize("answer", ["标准为9999元。[99]", "标准为600元，没有引用。", NO_ANSWER])
def test_invalid_or_missing_citations_refused(settings, pipeline, answer):
    repository, _, retrieval, _ = pipeline
    response = RagService(settings, repository, retrieval, FakeReranker(), FakeLLM(answer)).answer(
        ChatRequest(message="北京住宿标准？")
    )
    assert response.answer == NO_ANSWER and not response.citations


def test_no_relevant_evidence_skips_llm(settings, pipeline):
    repository, _, retrieval, chunks = pipeline
    llm = FakeLLM()
    rag = RagService(settings, repository, retrieval, FakeReranker(), llm)
    assert rag.answer(ChatRequest(message="火星的温度？")).answer == NO_ANSWER
    assert not llm.messages
    repository.update(chunks[0].document_id, status="indexing")
    assert not rag.answer(ChatRequest(message="北京住宿标准？")).citations


def test_debug_is_explicit_opt_in(settings, pipeline):
    repository, _, retrieval, _ = pipeline
    settings.rag_debug = True
    result = RagService(settings, repository, retrieval, FakeReranker(), FakeLLM()).answer(
        ChatRequest(message="北京住宿标准？")
    )
    assert result.debug["retrieved"] and result.debug["selected"]


def test_multiple_chinese_chunks_fit_token_budget(settings, pipeline):
    repository, _, retrieval, chunks = pipeline
    settings.rag_debug = True

    class HighScoreReranker:
        def rerank(self, query, hits):
            return [h.model_copy(update={"score": 0.95}) for h in hits]

    llm = FakeLLM("根据资料 [1] 和 [2]，标准明确。")
    rag = RagService(settings, repository, retrieval, HighScoreReranker(), llm)
    result = rag.answer(ChatRequest(message="出差住宿和餐饮标准是多少？"))
    assert len(result.debug["selected"]) == 2
