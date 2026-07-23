"""Integration tests for SkeletonGraph — graph topology and routing logic."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.agents.graph import SkeletonGraph, _should_retry
from src.agents.state import WorkflowState


class TestShouldRetry:
    """Test the conditional routing function."""

    def test_retry_on_errors_within_limit(self) -> None:
        """Route to 'generate' when errors exist and retries remain."""
        state = WorkflowState(
            validation_errors=["error 1"],
            retry_count=2,
            max_retries=2,
        )
        assert _should_retry(state) == "generate"

    def test_no_retry_when_no_errors(self) -> None:
        """Route to END when there are no validation errors."""
        state = WorkflowState(
            validation_errors=[],
            retry_count=0,
            max_retries=2,
        )
        assert _should_retry(state) == "__end__"

    def test_no_retry_when_exceeded_max(self) -> None:
        """Route to END when retry count exceeds max."""
        state = WorkflowState(
            validation_errors=["error"],
            retry_count=3,
            max_retries=2,
        )
        assert _should_retry(state) == "__end__"


class TestSkeletonGraph:
    """Test SkeletonGraph compilation and basic execution."""

    def test_graph_compiles(self) -> None:
        """SkeletonGraph can be instantiated without errors."""
        client = MagicMock()
        graph = SkeletonGraph(client)
        assert graph._graph is not None

    def test_graph_runs_and_returns_skeleton(self) -> None:
        """Full graph run returns skeleton_code (mocked LLM)."""

        async def _run() -> None:
            client = MagicMock()
            client.generate = AsyncMock(
                side_effect=[
                    "## Test Plan\n\n### test_01_login\nSteps:\n- GOTO: login\n- CLICK: button",
                    "import pytest\nfrom playwright.sync_api import Page\n\ndef test_01_login(page, evidence_tracker):\n    {{GOTO:login}}\n    {{CLICK:button}}\n    {{ASSERT:done}}\n",
                ]
            )
            graph = SkeletonGraph(client)
            result = await graph.run(
                user_story="As a user I want to log in",
                conditions="1. Enter credentials and log in",
                expected_test_count=1,
            )
            assert result["skeleton_code"]
            assert "{{GOTO:login}}" in result["skeleton_code"]
            assert result["test_plan"]
            assert result["validation_errors"] == []

        asyncio.run(_run())

    def test_graph_retries_on_invalid_skeleton(self) -> None:
        """Graph retries when generator produces invalid skeleton."""

        async def _run() -> None:
            client = MagicMock()
            client.generate = AsyncMock(
                side_effect=[
                    # Planner
                    "## Test Plan\n\n### test_01_login\nSteps:\n- GOTO: login",
                    # Generator #1 — invalid (real selectors)
                    'import pytest\nfrom playwright.sync_api import Page\n\ndef test_01_login(page, evidence_tracker):\n    page.locator("#btn").click()\n',
                    # Generator #2 — valid (placeholders)
                    "import pytest\nfrom playwright.sync_api import Page\n\ndef test_01_login(page, evidence_tracker):\n    {{GOTO:login}}\n    {{CLICK:test}}\n",
                ]
            )
            graph = SkeletonGraph(client)
            result = await graph.run(
                user_story="test",
                conditions="1. something",
                expected_test_count=1,
                max_retries=2,
            )
            assert result["skeleton_code"]
            assert "{{GOTO:login}}" in result["skeleton_code"]
            assert result["retry_count"] == 1

        asyncio.run(_run())

    def test_graph_exhausts_retries_gracefully(self) -> None:
        """Graph returns best-effort code even when retries exhausted."""

        async def _run() -> None:
            client = MagicMock()
            client.generate = AsyncMock(
                side_effect=[
                    "## Test Plan\n\n### test_01\nSteps:\n- CLICK: button",
                    # All generator calls: invalid (real selectors)
                    'import pytest\ndef test_01(page, evidence_tracker):\n    page.locator(".btn").click()\n',
                    'import pytest\ndef test_01(page, evidence_tracker):\n    page.locator(".btn").click()\n',
                    'import pytest\ndef test_01(page, evidence_tracker):\n    page.locator(".btn").click()\n',
                ]
            )
            graph = SkeletonGraph(client)
            result = await graph.run(
                user_story="test",
                conditions="1. something",
                expected_test_count=1,
                max_retries=2,
            )
            assert result["skeleton_code"]
            assert len(result["validation_errors"]) > 0
            assert result["retry_count"] >= 2

        asyncio.run(_run())
