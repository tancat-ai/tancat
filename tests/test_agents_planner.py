"""Unit tests for PlannerAgent."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.planner import PlannerAgent
from src.agents.state import WorkflowState


@pytest.fixture
def mock_client() -> MagicMock:
    """Return a mock LLMClient with an async generate method."""
    client = MagicMock()
    client.generate = AsyncMock(return_value="## Test Plan\n\n### test_01_login\n...")
    return client


class TestPlannerAgent:
    """Test PlannerAgent with mocked LLMClient."""

    def test_planner_returns_test_plan(self, mock_client: MagicMock) -> None:
        """Planner produces a non-empty test plan."""

        async def _run() -> None:
            planner = PlannerAgent(mock_client)
            state = WorkflowState(
                user_story="As a user I want to log in",
                conditions="1. Enter credentials\n2. Submit form",
                expected_test_count=2,
            )
            result = await planner(state)
            assert "test_plan" in result
            assert result["test_plan"].strip()
            mock_client.generate.assert_called_once()

        asyncio.run(_run())

    def test_planner_uses_prepared_conditions(self, mock_client: MagicMock) -> None:
        """Planner calls generate with conditions in the prompt."""

        async def _run() -> None:
            planner = PlannerAgent(mock_client)
            state = WorkflowState(
                user_story="test",
                conditions="1. first\n2. second",
                expected_test_count=2,
            )
            await planner(state)
            call_args = mock_client.generate.call_args
            prompt_text = call_args[0][0] if call_args[0] else call_args.kwargs.get("prompt", "")
            assert "first" in prompt_text
            assert "second" in prompt_text
            assert "2 test functions" in prompt_text

        asyncio.run(_run())
