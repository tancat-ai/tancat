"""B-091 — the per-condition fragment path must honour the thinking switch.

Measured 2026-09-24: the landing-page re-run took 42–130s per skeleton fragment
because `TestOrchestrator._generate_single_condition_fragment` called
`client.generate(prompt)` with no `enable_thinking`, so the model default
(thinking ON for Qwen3.8) governed. The documented delivered mode is
thinking-off (`enable_thinking_default()`, 17–25s per fragment). Bypassing
`TestGenerator.generate` (which does pass the switch) sent nothing.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.orchestrator import TestOrchestrator
from src.spec_analyzer import TestCondition
from src.test_generator import TestGenerator

FRAGMENT = """from playwright.sync_api import Page, expect


def test_tc01_01_hero_headline(page: Page):
    {{GOTO:http://localhost:8079/}}
    {{ASSERT:hero headline visible}}
"""


def _orchestrator(*, enable_thinking: bool | None = None) -> tuple[TestOrchestrator, MagicMock]:
    client = MagicMock()
    client.generate = AsyncMock(return_value=FRAGMENT)
    generator = TestGenerator(client=client, output_dir="generated_tests")
    return TestOrchestrator(generator, enable_thinking=enable_thinking), client


def _condition() -> TestCondition:
    return TestCondition(
        id="TC01.01",
        type="happy_path",
        text="The hero headline is visible on load",
        expected="hero headline visible",
        source="ai",
    )


def _generate(orch: TestOrchestrator) -> None:
    asyncio.run(
        orch._generate_single_condition_fragment(
            user_story="review the landing page",
            known_urls_block="- http://localhost:8079/",
            ordered_conditions=[],
            condition=_condition(),
        )
    )


def test_fragment_path_sends_thinking_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AITEST_ENABLE_THINKING", raising=False)
    orch, client = _orchestrator()
    _generate(orch)
    assert client.generate.await_args is not None
    assert client.generate.await_args.kwargs["enable_thinking"] is False


def test_fragment_path_honours_explicit_thinking_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AITEST_ENABLE_THINKING", raising=False)
    orch, client = _orchestrator(enable_thinking=True)
    _generate(orch)
    assert client.generate.await_args.kwargs["enable_thinking"] is True


def test_fragment_path_env_opt_in_turns_thinking_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITEST_ENABLE_THINKING", "1")
    orch, client = _orchestrator()
    _generate(orch)
    assert client.generate.await_args.kwargs["enable_thinking"] is True
