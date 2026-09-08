import time

from conftest import FakeEmbedding, FakeLLM, FakeReranker
from fastapi.testclient import TestClient

from backend.app.main import create_app


def wait_document(client, doc_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        doc = client.get(f"/api/documents/{doc_id}").json()
        if doc["status"] in {"ready", "failed"}:
            return doc
        time.sleep(0.02)
    raise AssertionError("Worker did not finish")


def test_api_upload_chat_delete_restart(settings):
    app = create_app(settings, FakeEmbedding(), FakeReranker(), FakeLLM())
    with TestClient(app) as client:
        upload = client.post(
            "/api/documents/upload", files={"file": ("../政策.md", "# 住宿\n北京住宿600元。".encode())}
        )
        assert upload.status_code == 202
        doc_id = upload.json()["document_id"]
        assert upload.json()["filename"] == "政策.md"
        assert wait_document(client, doc_id)["status"] == "ready"
        assert client.get(f"/api/documents/{doc_id}/chunks").json()[0]["document_id"] == doc_id
        response = client.post("/api/chat", json={"message": "北京住宿标准？", "document_ids": [doc_id]})
        assert response.status_code == 200
        assert "600" in response.json()["answer"]
        assert "debug" not in response.json()
    with TestClient(create_app(settings, FakeEmbedding(), FakeReranker(), FakeLLM())) as client:
        assert client.get(f"/api/documents/{doc_id}").json()["status"] == "ready"
        assert client.delete(f"/api/documents/{doc_id}").status_code == 204
        assert client.get(f"/api/documents/{doc_id}").status_code == 404
        assert client.post("/api/chat", json={"message": "北京住宿标准？"}).json()["citations"] == []


def test_bad_uploads_and_cross_origin(settings):
    with TestClient(create_app(settings, FakeEmbedding(), FakeReranker(), FakeLLM())) as client:
        assert client.post("/api/documents/upload", files={"file": ("test.exe", b"hello")}).status_code == 415
        assert client.post("/api/documents/upload", files={"file": ("test.txt", b"")}).status_code == 400
        assert client.post("/api/chat", json={"message": "   "}).status_code == 422
        assert (
            client.post(
                "/api/chat", json={"message": "hello"}, headers={"Origin": "https://untrusted.example"}
            ).status_code
            == 403
        )
        assert client.get("/api/documents/bad-id").status_code == 404


def test_failed_import_can_retry(settings):
    with TestClient(create_app(settings, FakeEmbedding(), FakeReranker(), FakeLLM())) as client:
        doc_id = client.post("/api/documents/upload", files={"file": ("empty.txt", b"  ")}).json()[
            "document_id"
        ]
        doc = wait_document(client, doc_id)
        assert doc["status"] == "failed" and doc["error"]
        assert client.post(f"/api/documents/{doc_id}/retry").status_code == 202
        assert wait_document(client, doc_id)["status"] == "failed"


def test_restart_recovers_interrupted_import(settings):
    app = create_app(settings, FakeEmbedding(), FakeReranker(), FakeLLM())
    with TestClient(app) as client:
        doc_id = client.post(
            "/api/documents/upload", files={"file": ("policy.txt", "北京住宿600元".encode())}
        ).json()["document_id"]
        assert wait_document(client, doc_id)["status"] == "ready"
        app.state.repository.update(doc_id, status="indexing")
    with TestClient(create_app(settings, FakeEmbedding(), FakeReranker(), FakeLLM())) as client:
        assert wait_document(client, doc_id)["status"] == "ready"
        assert len(client.get(f"/api/documents/{doc_id}/chunks").json()) == 1
