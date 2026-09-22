import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("knowisland_benchmark", ROOT / "scripts" / "benchmark.py")
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)


def test_positive_case_requires_answer_and_supporting_citation():
    case = {
        "id": "hotel",
        "question": "北京住宿标准？",
        "expect_refusal": False,
        "must_contain": ["600"],
        "support_terms": ["北京", "600"],
    }
    response = {
        "answer": "北京住宿标准是 600 元。[1]",
        "citations": [{"text": "北京出差住宿标准为每人每晚 600 元。"}],
        "latency_ms": 123,
        "request_id": "r1",
    }
    result = benchmark.evaluate_case(case, response)
    assert result.passed
    assert result.answer_ok
    assert result.citation_ok


def test_positive_case_fails_when_citation_does_not_support_answer():
    case = {
        "id": "hotel",
        "question": "北京住宿标准？",
        "expect_refusal": False,
        "must_contain": ["600"],
        "support_terms": ["北京", "600"],
    }
    response = {
        "answer": "北京住宿标准是 600 元。[1]",
        "citations": [{"text": "上海出差住宿标准为每人每晚 550 元。"}],
    }
    result = benchmark.evaluate_case(case, response)
    assert result.answer_ok
    assert not result.citation_ok
    assert not result.passed


def test_refusal_requires_no_citations():
    case = {
        "id": "mars",
        "question": "火星基地地址？",
        "expect_refusal": True,
    }
    response = {
        "answer": "知识库中没有找到足够信息。",
        "citations": [],
    }
    assert benchmark.evaluate_case(case, response).passed

    response["citations"] = [{"text": "unrelated"}]
    assert not benchmark.evaluate_case(case, response).passed


def test_versioned_dataset_has_positive_and_refusal_cases():
    cases = benchmark.load_cases(ROOT / "benchmark" / "company_policy.jsonl")
    assert len(cases) == 10
    assert any(not case["expect_refusal"] for case in cases)
    assert any(case["expect_refusal"] for case in cases)
