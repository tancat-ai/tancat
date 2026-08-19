"""Tests for constrained semantic candidate ranking."""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
import pytest

from src.semantic_candidate_ranker import (
    DEFAULT_RESOLUTION_TIMEOUT,
    SemanticCandidateRanker,
    _is_timeout_error,
)


class _FakeGenerator:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    async def generate(
        self,
        prompt: str,
        timeout: int = 300,
        system_prompt: str | None = None,
        enable_thinking: bool | None = None,
    ) -> str:
        _ = prompt, timeout, system_prompt, enable_thinking
        return json.dumps(self.payload)


def test_choose_best_candidate_returns_selected_shortlisted_candidate() -> None:
    ranker = SemanticCandidateRanker(_FakeGenerator({"selected_index": 1, "assertion_type": "toBeVisible"}))
    candidates = [
        {"selector": "#cart-link", "text": "Cart", "role": "a"},
        {"selector": ".cart_description", "text": "Blue Top", "role": "div"},
    ]

    import asyncio

    result = asyncio.run(
        ranker.choose_best_candidate(
            action="ASSERT",
            description="items added correctly",
            current_url="https://example.com/view_cart",
            candidates=candidates,
        )
    )

    # B-020: ASSERT results include assertion_type and expected_value
    assert result is not None
    assert result["selector"] == ".cart_description"
    assert result["assertion_type"] == "toBeVisible"
    assert "expected_value" in result


def test_choose_best_candidate_returns_none_for_invalid_json() -> None:
    class _BadGenerator:
        async def generate(
            self,
            prompt: str,
            timeout: int = 300,
            system_prompt: str | None = None,
            enable_thinking: bool | None = None,
        ) -> str:
            _ = prompt, timeout, system_prompt, enable_thinking
            return "not json"

    ranker = SemanticCandidateRanker(_BadGenerator())

    import asyncio

    result = asyncio.run(
        ranker.choose_best_candidate(
            action="CLICK",
            description="go to cart",
            current_url="https://example.com/",
            candidates=[{"selector": "#one"}],
        )
    )

    assert result is None or result == {"selector": "#one"}


# ── Resolution-timeout fix (session 2026-08-18) ─────────────────────────────
# The old hard-coded 45s timeout plus a silent `except Exception: return None`
# produced flat-0% eval scores with no log. These tests pin the new contract:
# configurable default, timeout passed through, and loud (logged) failures.


class _RecordingGenerator:
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self.payload = payload or {}
        self.timeouts_seen: list[int] = []
        self.thinking_seen: list[bool | None] = []

    async def generate(
        self,
        prompt: str,
        timeout: int = 300,
        system_prompt: str | None = None,
        enable_thinking: bool | None = None,
    ) -> str:
        _ = prompt, system_prompt
        self.timeouts_seen.append(timeout)
        self.thinking_seen.append(enable_thinking)
        return json.dumps(self.payload)


class _RaisingGenerator:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    async def generate(
        self,
        prompt: str,
        timeout: int = 300,
        system_prompt: str | None = None,
        enable_thinking: bool | None = None,
    ) -> str:
        _ = prompt, timeout, system_prompt, enable_thinking
        raise self.exc


def test_default_resolution_timeout_is_120() -> None:
    assert DEFAULT_RESOLUTION_TIMEOUT == 120.0
    assert SemanticCandidateRanker().timeout == 120.0


def test_custom_timeout_is_passed_to_generator() -> None:
    generator = _RecordingGenerator({"selected_index": 0})
    ranker = SemanticCandidateRanker(generator, timeout=77.0)

    asyncio.run(
        ranker.choose_best_candidate(
            action="CLICK",
            description="login button",
            current_url="https://example.com/",
            candidates=[{"selector": "#a"}, {"selector": "#b"}],
        )
    )

    assert generator.timeouts_seen == [77]


def test_timeout_returns_none_and_logs_loudly(caplog: pytest.LogCaptureFixture) -> None:
    # Mimic LLMClient.generate: provider timeout wrapped in RuntimeError.
    wrapped = RuntimeError("Failed to generate tests: read timed out")
    wrapped.__cause__ = httpx.ReadTimeout("read timed out")
    ranker = SemanticCandidateRanker(_RaisingGenerator(wrapped))

    with caplog.at_level(logging.WARNING, logger="src.semantic_candidate_ranker"):
        result = asyncio.run(
            ranker.choose_best_candidate(
                action="FILL",
                description="username field",
                current_url="https://example.com/login",
                candidates=[{"selector": "#a"}, {"selector": "#b"}],
            )
        )

    assert result is None
    timeout_logs = [r for r in caplog.records if "TIMED OUT" in r.getMessage()]
    assert len(timeout_logs) == 1
    assert "username field" in timeout_logs[0].getMessage()


def test_non_timeout_failure_also_logged(caplog: pytest.LogCaptureFixture) -> None:
    ranker = SemanticCandidateRanker(_RaisingGenerator(ValueError("boom")))

    with caplog.at_level(logging.WARNING, logger="src.semantic_candidate_ranker"):
        result = asyncio.run(
            ranker.choose_best_candidate(
                action="CLICK",
                description="submit",
                current_url="https://example.com/",
                candidates=[{"selector": "#a"}, {"selector": "#b"}],
            )
        )

    assert result is None
    assert any("failed" in r.getMessage() and "TIMED OUT" not in r.getMessage() for r in caplog.records)


def test_batch_timeout_logs_every_affected_placeholder(caplog: pytest.LogCaptureFixture) -> None:
    wrapped = RuntimeError("Failed to generate tests: read timed out")
    wrapped.__cause__ = httpx.ReadTimeout("read timed out")
    ranker = SemanticCandidateRanker(_RaisingGenerator(wrapped))

    items = [
        {"action": "CLICK", "description": "add to cart", "candidates": [{"selector": "#a"}, {"selector": "#b"}]},
        {
            "action": "ASSERT",
            "description": "cart count shows 1",
            "candidates": [{"selector": "#c"}, {"selector": "#d"}],
        },
    ]

    with caplog.at_level(logging.WARNING, logger="src.semantic_candidate_ranker"):
        results = asyncio.run(ranker.choose_best_candidates_batch(items=items))

    assert results == [None, None]
    timeout_logs = [r for r in caplog.records if "TIMED OUT" in r.getMessage()]
    assert len(timeout_logs) == 1
    message = timeout_logs[0].getMessage()
    assert "add to cart" in message
    assert "cart count shows 1" in message


def test_is_timeout_error_detects_direct_and_wrapped_timeouts() -> None:
    direct = httpx.ConnectTimeout("connect timed out")
    assert _is_timeout_error(direct)
    assert _is_timeout_error(TimeoutError())

    wrapped = RuntimeError("Failed to generate tests: timed out")
    wrapped.__cause__ = httpx.ReadTimeout("read timed out")
    assert _is_timeout_error(wrapped)

    assert not _is_timeout_error(ValueError("boom"))
    chained = RuntimeError("outer")
    chained.__cause__ = ValueError("inner")
    assert not _is_timeout_error(chained)


def test_resolution_timeout_plumbs_through_matcher_and_orchestrator() -> None:
    from src.element_matcher import ElementMatcher
    from src.placeholder_orchestrator import PlaceholderOrchestrator
    from src.placeholder_resolver import PlaceholderResolver

    matcher = ElementMatcher(PlaceholderResolver(), generator=None, resolution_timeout=33.0)
    assert matcher._semantic_ranker.timeout == 33.0

    orchestrator = PlaceholderOrchestrator(resolution_timeout=44.0)
    assert orchestrator.semantic_ranker.timeout == 44.0


def test_default_plumbing_keeps_default_timeout() -> None:
    from src.placeholder_orchestrator import PlaceholderOrchestrator

    orchestrator = PlaceholderOrchestrator()
    assert orchestrator.semantic_ranker.timeout == DEFAULT_RESOLUTION_TIMEOUT


# ── Thinking-mode switch (2026-08-18) ───────────────────────────────────────
# Thinking models (Qwen3.6/3.8) burn the token budget on reasoning and return
# empty content — the got=0 collapse and the resolution timeouts. Resolution
# is a structured pick-from-candidates task: the pipeline sends
# enable_thinking=False explicitly (never a silent override: None = model
# default, and the delivered mode is logged by LLMClient).


def test_ranker_defaults_to_thinking_off() -> None:
    assert SemanticCandidateRanker().enable_thinking is False


def test_ranker_sends_thinking_off_to_generator() -> None:
    generator = _RecordingGenerator({"selected_index": 0})
    ranker = SemanticCandidateRanker(generator)

    asyncio.run(
        ranker.choose_best_candidate(
            action="CLICK",
            description="login button",
            current_url="https://example.com/",
            candidates=[{"selector": "#a"}, {"selector": "#b"}],
        )
    )

    assert generator.thinking_seen == [False]


def test_ranker_thinking_mode_is_overridable() -> None:
    generator = _RecordingGenerator({"selected_index": 0})
    ranker = SemanticCandidateRanker(generator, enable_thinking=None)

    asyncio.run(
        ranker.choose_best_candidate(
            action="CLICK",
            description="login button",
            current_url="https://example.com/",
            candidates=[{"selector": "#a"}, {"selector": "#b"}],
        )
    )

    # None = send nothing, model/server default governs.
    assert generator.thinking_seen == [None]


def test_batch_resolution_sends_thinking_off() -> None:
    generator = _RecordingGenerator({"results": []})
    ranker = SemanticCandidateRanker(generator)

    asyncio.run(
        ranker.choose_best_candidates_batch(
            items=[
                {
                    "action": "CLICK",
                    "description": "add to cart",
                    "candidates": [{"selector": "#a"}, {"selector": "#b"}],
                }
            ]
        )
    )

    assert generator.thinking_seen == [False]
