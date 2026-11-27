"""t-1509: the model probe never holds the page.

The browser test proves the page draws inside five seconds; this file proves the
mechanism that makes it so, quickly enough to run everywhere.
"""

from __future__ import annotations

import time

import pytest

from src import model_probe


def test_the_probe_gives_up_inside_its_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """A client that never answers must not become a page that never draws."""
    import src.llm_client as llm_client

    class _Slow:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def list_models(self, timeout: int = 30) -> list[str]:
            time.sleep(timeout)  # the endpoint hangs
            return []

    monkeypatch.setattr(llm_client, "LLMClient", _Slow)

    started = time.perf_counter()
    result = model_probe.probe_models("openai-local", "http://127.0.0.1:9/v1", budget=0.5)
    elapsed = time.perf_counter() - started

    assert elapsed < 1.5, f"the probe took {elapsed:.1f}s"
    assert result.finished is False
    assert result.models == []
    assert "No answer from" in result.message("http://127.0.0.1:9/v1")


def test_a_reachable_endpoint_reports_its_models(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.llm_client as llm_client

    class _Fast:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def list_models(self, timeout: int = 30) -> list[str]:
            return ["qwen2.5:7b"]

    monkeypatch.setattr(llm_client, "LLMClient", _Fast)

    result = model_probe.probe_models("ollama", "http://localhost:11434", budget=1.0)

    assert result.finished
    assert result.models == ["qwen2.5:7b"]
    assert result.message("x") == ""


def test_a_failed_probe_says_what_to_do(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.llm_client as llm_client

    class _Broken:
        def __init__(self, *_a: object, **_k: object) -> None:
            raise ConnectionError("refused")

    monkeypatch.setattr(llm_client, "LLMClient", _Broken)

    result = model_probe.probe_models("openai-local", "", budget=1.0)

    assert not result.finished or result.models == []
    message = result.message("the default endpoint")
    assert "No model is configured yet" in message
    assert "Provider Base URL" in message
