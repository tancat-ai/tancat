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
    assert "Still checking" in result.message("http://127.0.0.1:9/v1")


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


# ---------------------------------------------------------------------------
# t-1514: a slow model is not "no model"
# ---------------------------------------------------------------------------


def test_a_slow_model_is_reported_as_still_checking(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 3s answer after a 1.5s deadline must never say "no model is configured".

    llama.cpp's first /v1/models answer took about 7s for the owner (t-0715); a buyer
    with that server would have been told they had no model (t-1514).
    """
    import src.llm_client as llm_client

    class _SlowButAlive:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def list_models(self, timeout: int = 30) -> list[str]:
            time.sleep(3.0)
            return ["qwen2.5:7b"]

    monkeypatch.setattr(llm_client, "LLMClient", _SlowButAlive)

    result = model_probe.probe_models("openai-local", "http://localhost:8080/v1", budget=0.5)
    message = result.message("http://localhost:8080/v1")

    assert result.finished is False
    assert "Still checking" in message, message
    assert "no model is configured yet" not in message.lower()
    assert "0.5s" in message, "the message must report the budget it was given"


def test_an_unfinished_probe_keeps_the_models_it_already_had() -> None:
    """The cached list is the truth until a probe finishes with a different answer."""
    previous = model_probe.ProbeResult(models=["qwen2.5:7b"], finished=True, budget=1.5)
    unfinished = model_probe.ProbeResult(models=[], finished=False, budget=0.5)

    merged = model_probe.keep_previous_models(unfinished, previous)

    assert merged.models == ["qwen2.5:7b"]
    assert merged.message("http://localhost:8080/v1") == "", "a known model must not be warned over"


def test_a_finished_empty_probe_does_replace_the_old_list() -> None:
    previous = model_probe.ProbeResult(models=["qwen2.5:7b"], finished=True, budget=1.5)
    empty = model_probe.ProbeResult(models=[], finished=True, budget=1.5)

    merged = model_probe.keep_previous_models(empty, previous)

    assert merged.models == []
    assert "No model is configured yet" in merged.message("http://localhost:8080/v1")


def test_the_message_reports_the_budget_it_was_given() -> None:
    result = model_probe.ProbeResult(models=[], finished=False, budget=4.0)

    assert "4.0s" in result.message("http://x")
    assert "1.5s" not in result.message("http://x")


# ---------------------------------------------------------------------------
# t-1514: the probe closes what it opens
# ---------------------------------------------------------------------------


def test_the_probe_closes_the_client_it_built(monkeypatch: pytest.MonkeyPatch) -> None:
    """The client owns an httpx pool; an abandoned thread must not leave it open."""
    import src.llm_client as llm_client

    closed: list[bool] = []

    class _Client:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def list_models(self, timeout: int = 30) -> list[str]:
            return ["qwen2.5:7b"]

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(llm_client, "LLMClient", _Client)

    model_probe.probe_models("ollama", "http://localhost:11434", budget=1.0)

    assert closed == [True], "the probe dropped its client without closing it"


def test_the_probe_closes_the_client_even_when_the_list_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.llm_client as llm_client

    closed: list[bool] = []

    class _Client:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def list_models(self, timeout: int = 30) -> list[str]:
            raise ConnectionError("refused")

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(llm_client, "LLMClient", _Client)

    model_probe.probe_models("ollama", "http://localhost:11434", budget=1.0)

    assert closed == [True]


# ---------------------------------------------------------------------------
# t-1514: auto-detect keeps its two seconds
# ---------------------------------------------------------------------------


def test_auto_detect_allows_two_seconds_per_port() -> None:
    """0.5s stopped finding a server on :8000/:5000 that takes a moment (t-1514)."""
    from src.llm_providers import LOCAL_DETECT_TIMEOUT

    assert LOCAL_DETECT_TIMEOUT == 2.0
