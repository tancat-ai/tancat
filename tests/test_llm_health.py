"""Phase 6d — BYO-LLM health check.

Hermetic tests for :mod:`src.llm_health`. Every check is a pure function of the
``LLMClient`` it is handed, so tests inject a fake client and assert the report
— no network, no LLM, CI-able.

Covers the onboarding branches:
- happy path (reachable + key ok + model listed + capability ok) → ``ok``
- unreachable endpoint (list + probe both fail to connect)
- model-not-in-list
- empty capability response (thinking-model false-positive class)
- soft context-floor warning never blocks ``ok``
- report rendering
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FakeChatCompletion:
    content: str = "pong"


class FakeLLMClient:
    """Minimal LLMClient stand-in with configurable list/probe behaviour."""

    def __init__(
        self,
        *,
        provider: str = "lm-studio",
        base_url: str = "http://localhost:1234",
        model: str = "Qwen/Qwen2.5-14B-Instruct",
        models: list[str] | None = None,
        list_error: Exception | None = None,
        probe_result: str | None = "pong",
        probe_error: Exception | None = None,
    ) -> None:
        self._provider = provider
        self._base_url = base_url
        self._model = model
        self._models = models
        self._list_error = list_error
        self._probe_result = probe_result
        self._probe_error = probe_error
        self.probe_calls = 0

    @property
    def provider_name(self) -> str:
        return self._provider

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def model(self) -> str:
        return self._model

    def list_models(self, timeout: int = 30) -> list[str]:
        if self._list_error is not None:
            raise self._list_error
        return list(self._models if self._models is not None else [self._model])

    def _complete_sync(self, prompt: str, **kwargs: Any) -> FakeChatCompletion:
        self.probe_calls += 1
        if self._probe_error is not None:
            raise self._probe_error
        return FakeChatCompletion(content=self._probe_result if self._probe_result is not None else "")


def test_happy_path_ok() -> None:
    """A reachable endpoint with the model listed and a non-empty probe is OK."""
    from src.llm_health import check_llm

    client = FakeLLMClient(
        model="Qwen/Qwen2.5-14B-Instruct",
        models=["Qwen/Qwen2.5-14B-Instruct", "llama3:8b"],
        probe_result="pong",
    )
    result = check_llm(client, context_floor=0)

    assert result.ok is True
    assert result.reachable is True
    assert result.key_ok is True
    assert result.model_available is True
    assert result.capability_ok is True
    assert result.sample_output == "pong"
    assert "OK" in result.headline
    assert client.probe_calls == 1


def test_unreachable_endpoint() -> None:
    """Both list and probe failing to connect → unreachable, not OK."""
    from src.llm_health import check_llm

    client = FakeLLMClient(
        list_error=ConnectionError("refused"),
        probe_error=ConnectionError("refused"),
    )
    result = check_llm(client, context_floor=0)

    assert result.ok is False
    assert result.reachable is False
    assert result.capability_ok is False
    assert "UNREACHABLE" in result.headline
    assert any("connect" in e.lower() for e in result.errors)


def test_model_not_in_list() -> None:
    """A requested model that is not in the provider's list is flagged."""
    from src.llm_health import check_llm

    client = FakeLLMClient(
        model="gpt-9-not-here",
        models=["gpt-4o", "gpt-4o-mini"],
        probe_result="pong",
    )
    result = check_llm(client, context_floor=0)

    assert result.model_available is False
    assert result.ok is False  # model missing is a hard gate
    assert "not in the" in " ".join(result.errors)


def test_empty_probe_response_is_not_ok() -> None:
    """A reachable endpoint that returns empty content is flagged (thinking-class)."""
    from src.llm_health import check_llm

    client = FakeLLMClient(models=["m"], probe_result="")
    result = check_llm(client, context_floor=0)

    assert result.reachable is True
    assert result.capability_ok is False
    assert result.ok is False
    assert any("empty content" in e for e in result.errors)


def test_reachable_when_list_fails_but_probe_succeeds() -> None:
    """A transient list failure that the probe overwrites → reachable + OK."""
    from src.llm_health import check_llm

    client = FakeLLMClient(
        models=None,
        list_error=RuntimeError("list endpoint glitch"),
        probe_result="pong",
    )
    result = check_llm(client, context_floor=0)

    assert result.reachable is True
    assert result.capability_ok is True
    # The "List models failed" error is cleared once the probe proves the
    # endpoint is usable (model_available stays True — no list to contradict it).
    assert result.ok is True
    assert not any("List models failed" in e for e in result.errors)


def test_context_floor_warning_does_not_block() -> None:
    """The soft size warning surfaces but never sets ok to False."""
    from src.llm_health import check_llm

    client = FakeLLMClient(model="Qwen/Qwen2.5-14B-Instruct", models=["Qwen/Qwen2.5-14B-Instruct"], probe_result="pong")
    result = check_llm(client, context_floor=32768)

    assert result.ok is True
    assert any("context tokens" in w for w in result.warnings)


def test_probe_sends_thinking_off_and_zero_temp() -> None:
    """The capability probe must opt out of thinking mode (AI-050) and pin temp.

    A thinking model left on would burn its budget on reasoning and return
    empty content — a false 'broken response'. The probe must never do that.
    """
    from src.llm_health import _probe_capability

    captured: dict[str, Any] = {}

    class CaptureClient(FakeLLMClient):
        def _complete_sync(self, prompt: str, **kwargs: Any) -> FakeChatCompletion:
            captured.update(kwargs)
            return super()._complete_sync(prompt, **kwargs)

    client = CaptureClient(probe_result="pong")
    _probe_capability(client, timeout=20)
    assert captured.get("enable_thinking") is False
    assert captured.get("temperature") == 0.0


def test_render_report_happy() -> None:
    from src.llm_health import check_llm, render_report

    client = FakeLLMClient(model="Qwen/Qwen2.5-14B-Instruct", models=["Qwen/Qwen2.5-14B-Instruct"], probe_result="pong")
    result = check_llm(client, context_floor=0)
    report = render_report(result)
    assert "✓" in report
    assert "LLM OK" in report
    assert "reachable: yes" in report
    assert "responds : yes" in report


def test_render_report_unreachable() -> None:
    from src.llm_health import check_llm, render_report

    client = FakeLLMClient(list_error=ConnectionError("x"), probe_error=ConnectionError("x"))
    result = check_llm(client, context_floor=0)
    report = render_report(result)
    assert "✗" in report
    assert "UNREACHABLE" in report
    assert "reachable: no" in report


def test_min_context_chars_known_and_unknown() -> None:
    from src.llm_health import min_context_chars

    assert min_context_chars("lm-studio") > 0
    assert min_context_chars("openai") > 0
    # Unknown provider → no floor (skip the size check).
    assert min_context_chars("definitely-not-a-provider") == 0


def test_build_client_returns_real_llmclient_type() -> None:
    """build_client must construct the real LLMClient (the honest seam)."""
    from src.llm_client import LLMClient
    from src.llm_health import build_client

    client = build_client("lm-studio", base_url="http://localhost:1234", model="m")
    assert isinstance(client, LLMClient)
    assert client.provider_name == "lm-studio"
