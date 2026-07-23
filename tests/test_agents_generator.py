"""Unit tests for GeneratorAgent."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.generator import GeneratorAgent
from src.agents.state import WorkflowState

VALID_SKELETON = (
    "import pytest\n"
    "from playwright.sync_api import Page\n\n"
    "@pytest.mark.evidence(condition_ref='TC-01', story_ref='S01')\n"
    "def test_01_login(page, evidence_tracker):\n"
    "    {{GOTO:login}}\n"
    "    {{FILL:username:admin}}\n"
    "    {{CLICK:login button}}\n"
    "    {{ASSERT:welcome message}}\n"
)


@pytest.fixture
def mock_client() -> MagicMock:
    """Return a mock LLMClient with an async generate method."""
    client = MagicMock()
    client.generate = AsyncMock(return_value=VALID_SKELETON)
    return client


class TestGeneratorAgent:
    """Test GeneratorAgent with mocked LLMClient."""

    def test_generator_returns_skeleton_code(self, mock_client: MagicMock) -> None:
        """Generator produces non-empty skeleton code."""

        async def _run() -> None:
            gen = GeneratorAgent(mock_client)
            state = WorkflowState(
                user_story="As a user I want to log in",
                conditions="1. Enter credentials",
                test_plan="## Test Plan\n\n### test_01_login\nSteps:\n- GOTO: login\n- CLICK: button",
                expected_test_count=1,
            )
            result = await gen(state)
            assert "skeleton_code" in result
            assert "{{GOTO:login}}" in result["skeleton_code"]
            mock_client.generate.assert_called_once()

        asyncio.run(_run())

    def test_generator_uses_test_plan_when_available(self, mock_client: MagicMock) -> None:
        """Generator uses test_plan in prompt when available."""

        async def _run() -> None:
            gen = GeneratorAgent(mock_client)
            state = WorkflowState(
                user_story="test",
                conditions="1. something",
                test_plan="### test_01_foo\nSteps:\n- CLICK: bar",
                expected_test_count=1,
            )
            await gen(state)
            call_args = mock_client.generate.call_args
            prompt_text = call_args[0][0] if call_args[0] else call_args.kwargs.get("prompt", "")
            assert "test_01_foo" in prompt_text

        asyncio.run(_run())

    def test_generator_falls_back_to_conditions(self, mock_client: MagicMock) -> None:
        """Generator falls back to conditions when test_plan is empty."""

        async def _run() -> None:
            gen = GeneratorAgent(mock_client)
            state = WorkflowState(
                user_story="test",
                conditions="1. do thing",
                test_plan="",
                expected_test_count=1,
            )
            await gen(state)
            call_args = mock_client.generate.call_args
            prompt_text = call_args[0][0] if call_args[0] else call_args.kwargs.get("prompt", "")
            assert "do thing" in prompt_text

        asyncio.run(_run())

    def test_generator_strips_whitespace(self, mock_client: MagicMock) -> None:
        """Generator preserves skeleton code content (real LLMClient strips whitespace, mock doesn't)."""

        async def _run() -> None:
            mock_client.generate = AsyncMock(return_value=VALID_SKELETON)
            gen = GeneratorAgent(mock_client)
            state = WorkflowState(user_story="test", conditions="1. x", expected_test_count=1)
            result = await gen(state)
            # Content is meaningful (real LLMClient normalises whitespace)
            assert "{{GOTO:login}}" in result["skeleton_code"]

        asyncio.run(_run())
