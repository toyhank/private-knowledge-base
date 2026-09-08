"""End-to-end verification against a running app with real local models."""

import json
import sys
import time
from pathlib import Path

import httpx

root = Path(__file__).resolve().parents[1]
base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
with httpx.Client(base_url=base, timeout=660, trust_env=False) as client:
    with (root / "samples/公司测试制度.md").open("rb") as source:
        response = client.post(
            "/api/documents/upload", files={"file": ("公司测试制度.md", source, "text/markdown")}
        )
    response.raise_for_status()
    doc_id = response.json()["document_id"]
    print(f"Uploaded {doc_id}", flush=True)
    deadline = time.monotonic() + 600
    last = ""
    while time.monotonic() < deadline:
        response = client.get(f"/api/documents/{doc_id}")
        response.raise_for_status()
        doc = response.json()
        if doc["status"] != last:
            print(f"Status: {doc['status']}", flush=True)
            last = doc["status"]
        if doc["status"] == "ready":
            break
        if doc["status"] == "failed":
            raise RuntimeError(doc["error"])
        time.sleep(2)
    else:
        raise TimeoutError("Document indexing timeout")
    results = []
    for question in ["北京出差的住宿标准是多少？", "公司的火星基地地址是什么？"]:
        started = time.monotonic()
        response = client.post("/api/chat", json={"message": question, "document_ids": [doc_id]})
        response.raise_for_status()
        answer = response.json()
        result = {"question": question, "seconds": round(time.monotonic() - started, 2), **answer}
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    assert "600" in results[0]["answer"] and results[0]["citations"], "Failed answer/citation check"
    assert all(c["document_id"] == doc_id and "600" in c["text"] for c in results[0]["citations"])
    assert "没有找到足够信息" in results[1]["answer"] and not results[1]["citations"]
    # Keep the sample document so the user can immediately try the completed UI.
    out = root / "test-results"
    out.mkdir(exist_ok=True)
    (out / "real-model-smoke.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Real-model smoke test passed. Sample document retained.", flush=True)
