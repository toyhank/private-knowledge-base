#!/usr/bin/env python3
"""Reproducible end-to-end benchmark for a running KnowIsland instance.

The benchmark deliberately measures what the public API can verify:
- answer correctness for deterministic sample questions;
- citation presence / refusal behavior;
- whether returned citation text contains the expected supporting evidence;
- latency.

It does not claim Recall@K unless retrieval debug traces are explicitly available.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "benchmark" / "company_policy.jsonl"
DEFAULT_DOCUMENT = ROOT / "samples" / "公司测试制度.md"
NO_ANSWER_TEXT = "知识库中没有找到足够信息"


@dataclass
class CaseResult:
    case_id: str
    question: str
    expect_refusal: bool
    answer: str
    answer_ok: bool
    citation_ok: bool
    passed: bool
    citation_count: int
    latency_ms: int
    request_id: str | None
    citations: list[dict[str, Any]]
    debug: dict[str, Any] | None = None


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        for key in ("id", "question", "expect_refusal"):
            if key not in case:
                raise ValueError(f"{path}:{line_no}: missing {key!r}")
        cases.append(case)
    if not cases:
        raise ValueError(f"No benchmark cases found in {path}")
    return cases


def contains_all(text: str, terms: list[str]) -> bool:
    lowered = text.casefold()
    return all(str(term).casefold() in lowered for term in terms)


def evaluate_case(case: dict[str, Any], response: dict[str, Any]) -> CaseResult:
    answer = str(response.get("answer", ""))
    citations = list(response.get("citations") or [])
    expect_refusal = bool(case["expect_refusal"])

    if expect_refusal:
        answer_ok = NO_ANSWER_TEXT in answer
        citation_ok = len(citations) == 0
    else:
        must_contain = [str(x) for x in case.get("must_contain", [])]
        answer_ok = bool(answer.strip()) and contains_all(answer, must_contain)
        support_terms = [str(x) for x in case.get("support_terms", must_contain)]
        citation_ok = bool(citations) and any(
            contains_all(str(citation.get("text", "")), support_terms) for citation in citations
        )

    latency_ms = response.get("latency_ms")
    if not isinstance(latency_ms, int):
        latency_ms = 0

    return CaseResult(
        case_id=str(case["id"]),
        question=str(case["question"]),
        expect_refusal=expect_refusal,
        answer=answer,
        answer_ok=answer_ok,
        citation_ok=citation_ok,
        passed=answer_ok and citation_ok,
        citation_count=len(citations),
        latency_ms=latency_ms,
        request_id=response.get("request_id"),
        citations=citations,
        debug=response.get("debug"),
    )


def wait_until_ready(client: httpx.Client, doc_id: str, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_status = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/documents/{doc_id}")
        response.raise_for_status()
        document = response.json()
        status = document["status"]
        if status != last_status:
            print(f"Document status: {status}", flush=True)
            last_status = status
        if status == "ready":
            return
        if status == "failed":
            raise RuntimeError(document.get("error") or "Document indexing failed")
        time.sleep(1.5)
    raise TimeoutError(f"Document did not become ready within {timeout_seconds}s")


def upload_document(client: httpx.Client, path: Path, timeout_seconds: int) -> str:
    media_type = "text/markdown" if path.suffix.lower() == ".md" else "application/octet-stream"
    with path.open("rb") as source:
        response = client.post(
            "/api/documents/upload",
            files={"file": (path.name, source, media_type)},
        )
    response.raise_for_status()
    doc_id = response.json()["document_id"]
    print(f"Uploaded benchmark document: {doc_id}", flush=True)
    wait_until_ready(client, doc_id, timeout_seconds)
    return doc_id


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def build_summary(results: list[CaseResult]) -> dict[str, Any]:
    positives = [result for result in results if not result.expect_refusal]
    negatives = [result for result in results if result.expect_refusal]
    latencies = [result.latency_ms for result in results if result.latency_ms > 0]

    def ratio(items: list[CaseResult], predicate) -> float:
        return sum(1 for item in items if predicate(item)) / len(items) if items else 0.0

    summary = {
        "cases": len(results),
        "passed": sum(result.passed for result in results),
        "end_to_end_pass_rate": ratio(results, lambda result: result.passed),
        "answer_accuracy": ratio(results, lambda result: result.answer_ok),
        "citation_grounding_rate": ratio(positives, lambda result: result.citation_ok),
        "refusal_accuracy": ratio(negatives, lambda result: result.passed),
        "positive_cases": len(positives),
        "refusal_cases": len(negatives),
        "median_latency_ms": int(statistics.median(latencies)) if latencies else None,
        "mean_latency_ms": int(statistics.mean(latencies)) if latencies else None,
    }
    return summary


def render_markdown(
    *,
    base_url: str,
    dataset: Path,
    document: Path,
    summary: dict[str, Any],
    results: list[CaseResult],
) -> str:
    rows = []
    for result in results:
        rows.append(
            "| {id} | {kind} | {answer} | {citation} | {passed} | {latency} |".format(
                id=result.case_id,
                kind="refusal" if result.expect_refusal else "answer",
                answer="✅" if result.answer_ok else "❌",
                citation="✅" if result.citation_ok else "❌",
                passed="✅" if result.passed else "❌",
                latency=f"{result.latency_ms} ms" if result.latency_ms else "n/a",
            )
        )

    return f"""# KnowIsland benchmark

This file is generated by `python scripts/benchmark.py`.

The benchmark intentionally reports **end-to-end API behavior**, not a synthetic
retrieval score. A positive case passes only when the answer contains its expected
facts **and** at least one returned citation contains the expected supporting text.
A refusal case passes only when the system refuses and returns no citations.

## Summary

| Metric | Result |
|---|---:|
| Cases | {summary["cases"]} |
| Passed | {summary["passed"]}/{summary["cases"]} |
| End-to-end pass rate | {pct(summary["end_to_end_pass_rate"])} |
| Answer accuracy | {pct(summary["answer_accuracy"])} |
| Citation grounding rate (positive cases) | {pct(summary["citation_grounding_rate"])} |
| Refusal accuracy | {pct(summary["refusal_accuracy"])} |
| Median API latency | {summary["median_latency_ms"] if summary["median_latency_ms"] is not None else "n/a"} ms |
| Mean API latency | {summary["mean_latency_ms"] if summary["mean_latency_ms"] is not None else "n/a"} ms |

## Cases

| ID | Type | Answer | Citation/refusal | Pass | API latency |
|---|---|---:|---:|---:|---:|
{chr(10).join(rows)}

## Reproduce

```bash
python scripts/benchmark.py --base-url {base_url}
```

Dataset: `{dataset.relative_to(ROOT)}`

Document: `{document.relative_to(ROOT)}`

The sample document is synthetic test data and does not represent a real company's policy.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the KnowIsland end-to-end benchmark.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--document", type=Path, default=DEFAULT_DOCUMENT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "benchmark" / "results")
    parser.add_argument("--index-timeout", type=int, default=600)
    parser.add_argument("--request-timeout", type=int, default=660)
    parser.add_argument("--keep-document", action="store_true")
    args = parser.parse_args(argv)

    dataset = args.dataset.resolve()
    document = args.document.resolve()
    cases = load_cases(dataset)
    results: list[CaseResult] = []
    doc_id: str | None = None

    with httpx.Client(
        base_url=args.base_url,
        timeout=args.request_timeout,
        trust_env=False,
    ) as client:
        health = client.get("/api/health")
        health.raise_for_status()
        print("Health:", json.dumps(health.json(), ensure_ascii=False), flush=True)

        try:
            doc_id = upload_document(client, document, args.index_timeout)
            for index, case in enumerate(cases, start=1):
                print(f"[{index}/{len(cases)}] {case['question']}", flush=True)
                response = client.post(
                    "/api/chat",
                    json={"message": case["question"], "document_ids": [doc_id]},
                )
                response.raise_for_status()
                result = evaluate_case(case, response.json())
                results.append(result)
                print(
                    f"  {'PASS' if result.passed else 'FAIL'} "
                    f"answer={result.answer_ok} citation={result.citation_ok} "
                    f"latency={result.latency_ms}ms",
                    flush=True,
                )
        finally:
            if doc_id and not args.keep_document:
                try:
                    response = client.delete(f"/api/documents/{doc_id}")
                    if response.status_code not in (204, 404):
                        print(
                            f"WARN: benchmark document cleanup returned {response.status_code}",
                            file=sys.stderr,
                        )
                except httpx.HTTPError as exc:
                    print(f"WARN: could not clean up benchmark document: {exc}", file=sys.stderr)

    summary = build_summary(results)
    payload = {
        "base_url": args.base_url,
        "dataset": str(dataset),
        "document": str(document),
        "summary": summary,
        "results": [result.__dict__ for result in results],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "latest.json"
    md_path = args.output_dir / "latest.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        render_markdown(
            base_url=args.base_url,
            dataset=dataset,
            document=document,
            summary=summary,
            results=results,
        ),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0 if summary["passed"] == summary["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
