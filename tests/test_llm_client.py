import json

import httpx
import pytest

from backend.app.config import Settings
from backend.app.services.llm_client import LLMClient


def mock_server(monkeypatch, payload, inspect_request=None, status_code=200):
    original = httpx.Client

    def handler(request):
        if inspect_request:
            inspect_request(request)
        return httpx.Response(status_code, json=payload)

    def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", client)


@pytest.mark.parametrize("effort", ["none", ""])
def test_thinking_control_can_be_disabled_or_omitted(settings, monkeypatch, effort):
    settings.llm_reasoning_effort = effort

    def inspect(request):
        body = json.loads(request.content)
        if effort:
            assert body["reasoning_effort"] == "none"
        else:
            assert "reasoning_effort" not in body

    mock_server(
        monkeypatch, {"choices": [{"finish_reason": "stop", "message": {"content": "600元 [1]"}}]}, inspect
    )
    assert LLMClient(settings).complete([]) == "600元 [1]"


@pytest.mark.parametrize(
    "choice",
    [
        {"finish_reason": "length", "message": {"content": "未完成", "reasoning": "private reasoning"}},
        {"finish_reason": "stop", "message": {"content": "", "reasoning": "private reasoning"}},
    ],
)
def test_partial_answers_and_reasoning_only_are_not_returned(settings, monkeypatch, choice):
    mock_server(monkeypatch, {"choices": [choice]})
    with pytest.raises(RuntimeError) as error:
        LLMClient(settings).complete([])
    assert "private reasoning" not in str(error.value)


def test_remote_service_requires_explicit_configuration():
    with pytest.raises(ValueError, match="本地/私网"):
        Settings(_env_file=None, llm_base_url="https://outside.example/v1")
