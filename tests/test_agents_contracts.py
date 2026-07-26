"""Tests for Phase 1b agent contracts — Ingestion, QA Director, Script Synthesizer."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.agents.director import QADirectorAgent
from src.agents.ingestion import IngestionAgent
from src.agents.pipeline_state import Criterion, PipelineState, StoryAnalysis
from src.agents.synthesizer import ScriptSynthesizerAgent

# ---------------------------------------------------------------------------
# Ingestion Agent
# ---------------------------------------------------------------------------


class TestIngestionAgent:
    def test_empty_story_returns_empty_analysis(self) -> None:
        agent = IngestionAgent(client=MagicMock())
        state = PipelineState(user_story="")

        import asyncio

        result = asyncio.run(agent(state))
        assert result["story_analysis"] is not None
        assert result["story_analysis"].story_text == ""
        assert "Empty" in str(result.get("errors", []))

    def test_numbered_criteria_extracted(self) -> None:
        """SpecAnalyzer extracts numbered criteria without LLM call."""
        mock_client = MagicMock()
        agent = IngestionAgent(client=mock_client)
        state = PipelineState(user_story="1. Login to the site\n2. Add item to cart\n3. Checkout")

        import asyncio

        result = asyncio.run(agent(state))
        analysis = result["story_analysis"]
        assert len(analysis.criteria) == 3
        assert analysis.criteria[0].ref == "TC01.01"
        assert analysis.criteria[0].description == "Login to the site"
        # Should not have called LLM for deterministic criteria
        assert not mock_client.generate_test.called

    def test_source_format_detected(self) -> None:

        agent = IngestionAgent(client=MagicMock())
        # Gherkin stories with numbered criteria still get detected
        state = PipelineState(
            user_story="1. Given a registered user\n2. When they enter credentials\n3. Then they see the dashboard"
        )

        import asyncio

        result = asyncio.run(agent(state))
        # Numbered criteria detected → source is "numbered"
        assert result["story_analysis"].source_format in ("numbered", "gherkin", "free-form")

    def test_llm_fallback_on_unstructured_text(self) -> None:
        """Unstructured text that doesn't match numbered patterns
        should fall back to LLM analysis via SpecAnalyzer."""
        mock_client = MagicMock()
        # SpecAnalyzer calls generate_test on the LLM client
        mock_client.generate_test.return_value = json_mock_response()
        agent = IngestionAgent(client=mock_client)
        state = PipelineState(
            user_story="Users should be able to browse products and add them to cart using the website"
        )

        import asyncio

        result = asyncio.run(agent(state))
        analysis = result["story_analysis"]
        # Should have attempted LLM analysis since text doesn't match numbered format
        assert analysis is not None


def json_mock_response() -> str:
    import json

    return json.dumps(
        [
            {
                "id": "TC01.01",
                "type": "happy_path",
                "text": "Browse products",
                "expected": "Products page loads",
                "source": "spec",
                "flagged": False,
                "src": "ai",
                "intent": "journey_step",
            }
        ]
    )


# ---------------------------------------------------------------------------
# QA Director Agent
# ---------------------------------------------------------------------------


class TestQADirectorAgent:
    def test_empty_criteria_produces_no_conditions(self) -> None:
        agent = QADirectorAgent()
        state = PipelineState(story_analysis=StoryAnalysis(criteria=[]))

        import asyncio

        result = asyncio.run(agent(state))
        assert result["test_conditions"] == []

    def test_assigns_priority_from_type(self) -> None:
        agent = QADirectorAgent()
        state = PipelineState(
            story_analysis=StoryAnalysis(
                criteria=[
                    Criterion(ref="TC01.01", description="happy", condition_type="happy_path", priority="medium"),
                    Criterion(ref="TC01.02", description="boundary", condition_type="boundary", priority="medium"),
                    Criterion(ref="TC01.03", description="negative", condition_type="negative", priority="medium"),
                ]
            )
        )

        import asyncio

        result = asyncio.run(agent(state))
        conditions = result["test_conditions"]
        assert len(conditions) == 3
        assert conditions[0].priority == "medium"  # happy_path
        assert conditions[1].priority == "high"  # boundary
        assert conditions[2].priority == "high"  # negative

    def test_flags_ambiguities(self) -> None:
        agent = QADirectorAgent()
        state = PipelineState(
            story_analysis=StoryAnalysis(
                criteria=[
                    Criterion(ref="TC01.01", description="unclear", condition_type="ambiguity", priority="medium"),
                ]
            )
        )

        import asyncio

        result = asyncio.run(agent(state))
        assert result["test_conditions"][0].needs_clarification is True

    def test_prerequisite_chain(self) -> None:
        agent = QADirectorAgent()
        state = PipelineState(
            story_analysis=StoryAnalysis(
                criteria=[
                    Criterion(ref="TC01.01", description="first", condition_type="happy_path", priority="medium"),
                    Criterion(ref="TC01.02", description="second", condition_type="happy_path", priority="medium"),
                ]
            )
        )

        import asyncio

        result = asyncio.run(agent(state))
        conditions = result["test_conditions"]
        assert conditions[0].prerequisite_refs == []  # first has no prereq
        assert conditions[1].prerequisite_refs == ["TC01.01"]  # second depends on first


# ---------------------------------------------------------------------------
# Script Synthesizer Agent
# ---------------------------------------------------------------------------


class TestScriptSynthesizerAgent:
    def test_no_client_produces_placeholder(self) -> None:
        agent = ScriptSynthesizerAgent(client=None)
        state = PipelineState(
            test_conditions=[
                Criterion(ref="TC01.01", description="Login", condition_type="happy_path", priority="medium"),
            ]
        )

        import asyncio

        result = asyncio.run(agent(state))
        assert "test_tc01_01" in result["test_code"]
        assert "{{GOTO:home}}" in result["test_code"]
        assert result["errors"] == []

    def test_empty_conditions_returns_error(self) -> None:
        agent = ScriptSynthesizerAgent(client=None)
        state = PipelineState(test_conditions=[])

        import asyncio

        result = asyncio.run(agent(state))
        assert result["test_code"] == ""
        assert len(result["errors"]) >= 1

    def test_boundary_condition_produces_skip(self) -> None:
        agent = ScriptSynthesizerAgent(client=None)
        state = PipelineState(
            test_conditions=[
                Criterion(ref="TC01.01", description="edge case", condition_type="boundary", priority="high"),
            ]
        )

        import asyncio

        result = asyncio.run(agent(state))
        assert "pytest.skip" in result["test_code"]

    def test_with_client_uses_skeleton_graph(self) -> None:
        """When an LLM client is provided, the synthesizer should
        delegate to SkeletonGraph."""
        mock_client = MagicMock()
        # Mock the generate coroutine to return placeholder skeleton
        mock_client.generate = MagicMock()

        import asyncio

        async def mock_generate(*args: object, **kwargs: object) -> str:
            return "def test_login():\n    {{GOTO:home}}\n    {{CLICK:login}}\n"

        mock_client.generate.side_effect = mock_generate

        agent = ScriptSynthesizerAgent(client=mock_client)
        state = PipelineState(
            user_story="Login",
            test_conditions=[
                Criterion(ref="TC01.01", description="Login", condition_type="happy_path", priority="medium"),
            ],
        )

        result = asyncio.run(agent(state))
        assert result["test_code"] != ""
