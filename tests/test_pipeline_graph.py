"""Tests for src/agents/pipeline_graph.py — Phase 1a graph scaffold."""

from __future__ import annotations

import pytest

pytest.importorskip("langgraph", reason="langgraph extra not installed")

from src.agents.pipeline_graph import PipelineGraph, _after_qa_director, _after_synthesizer
from src.agents.pipeline_state import Criterion, PipelineState, StoryAnalysis

# ---------------------------------------------------------------------------
# PipelineState
# ---------------------------------------------------------------------------


class TestPipelineState:
    def test_default_state(self) -> None:
        state = PipelineState()
        assert state.user_story == ""
        assert state.test_conditions == []
        assert state.plan_confirmed is False
        assert state.auto_confirm is False

    def test_roundtrip_serialization(self) -> None:
        state = PipelineState(
            user_story="As a user I want to login",
            base_url="https://example.com",
            pom_mode=True,
            plan_confirmed=True,
            test_code="def test_login(): pass",
        )
        d = state.to_dict()
        restored = PipelineState.from_dict(d)
        assert restored.user_story == state.user_story
        assert restored.base_url == state.base_url
        assert restored.pom_mode == state.pom_mode

    def test_roundtrip_with_story_analysis(self) -> None:
        state = PipelineState(
            user_story="story",
            story_analysis=StoryAnalysis(
                story_text="story",
                criteria=[Criterion(ref="TC01.01", description="login", condition_type="happy_path", priority="high")],
                source_format="free-form",
            ),
        )
        d = state.to_dict()
        restored = PipelineState.from_dict(d)
        assert restored.story_analysis is not None
        assert restored.story_analysis.criteria[0].ref == "TC01.01"


class TestCriterion:
    def test_defaults(self) -> None:
        c = Criterion(ref="TC01.01", description="test", condition_type="happy_path", priority="medium")
        assert c.needs_clarification is False
        assert c.prerequisite_refs == []


class TestStoryAnalysis:
    def test_defaults(self) -> None:
        sa = StoryAnalysis()
        assert sa.criteria == []
        assert sa.domain_terms == []
        assert sa.source_format == ""


# ---------------------------------------------------------------------------
# Conditional routing
# ---------------------------------------------------------------------------


class TestAfterQADirector:
    def test_auto_confirm_routes_to_synthesize(self) -> None:
        state = PipelineState(auto_confirm=True)
        assert _after_qa_director(state) == "synthesize"

    def test_plan_confirmed_routes_to_synthesize(self) -> None:
        state = PipelineState(plan_confirmed=True)
        assert _after_qa_director(state) == "synthesize"

    def test_neither_pauses_at_checkpoint(self) -> None:
        state = PipelineState(auto_confirm=False, plan_confirmed=False)
        assert _after_qa_director(state) == "__end__"


class TestAfterSynthesizer:
    def test_no_errors_proceeds_to_postprocess(self) -> None:
        state = PipelineState(errors=[], retry_count=0)
        assert _after_synthesizer(state) == "postprocess"

    def test_errors_with_retries_left_retries(self) -> None:
        state = PipelineState(errors=["bad"], retry_count=0, max_retries=2)
        assert _after_synthesizer(state) == "synthesize"

    def test_errors_exhausted_retries_proceeds(self) -> None:
        state = PipelineState(errors=["bad"], retry_count=3, max_retries=2)
        assert _after_synthesizer(state) == "postprocess"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


class TestPipelineGraphBuild:
    def test_graph_compiles(self) -> None:
        graph = PipelineGraph()
        assert graph.compiled_graph is not None

    def test_graph_has_four_nodes(self) -> None:
        graph = PipelineGraph()
        nodes = graph.compiled_graph.get_graph().nodes
        assert "ingest" in nodes
        assert "plan" in nodes
        assert "synthesize" in nodes
        assert "postprocess" in nodes

    def test_entry_point_is_ingest(self) -> None:
        graph = PipelineGraph()
        # The entry point should be "ingest"
        assert graph.compiled_graph is not None


# ---------------------------------------------------------------------------
# Full graph execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_runs_end_to_end() -> None:
    """Verify the graph runs ingest → plan → synthesize → postprocess → END
    without errors, producing a test_code output."""
    graph = PipelineGraph()
    result = await graph.run(
        user_story="Login to the site\nAdd item to cart\nCheckout",
        base_url="https://example.com",
        auto_confirm=True,
    )
    assert result.test_code != ""
    assert "Phase 1b" in result.test_code
    assert result.errors == []
    assert result.story_analysis is not None
    assert len(result.story_analysis.criteria) == 3


@pytest.mark.asyncio
async def test_graph_pauses_at_checkpoint() -> None:
    """Without auto_confirm, the graph should pause after plan node."""
    graph = PipelineGraph(enable_checkpoint=True)
    result = await graph.run(
        user_story="Login",
        base_url="https://example.com",
        auto_confirm=False,
    )
    # Graph paused — plan_confirmed is False, no test_code generated
    assert result.plan_confirmed is False
    assert result.test_code == ""
    assert result.story_analysis is not None


@pytest.mark.asyncio
async def test_graph_resume_after_checkpoint() -> None:
    """Resume a paused graph with confirmed conditions."""
    graph = PipelineGraph(enable_checkpoint=True)

    # First run — pauses after plan
    state = await graph.run(
        user_story="Login to site",
        base_url="https://example.com",
        auto_confirm=False,
    )
    assert state.plan_confirmed is False
    assert state.test_conditions != []

    # Resume with confirmed conditions
    confirmed = state.test_conditions
    result = await graph.resume_after_checkpoint(state, confirmed)

    assert result.plan_confirmed is True
    assert result.test_code != ""
    assert "Phase 1b" in result.test_code


@pytest.mark.asyncio
async def test_graph_empty_story_produces_no_conditions() -> None:
    """Empty user story should produce an empty criteria list, not crash."""
    graph = PipelineGraph()
    result = await graph.run(user_story="", base_url="https://example.com", auto_confirm=True)
    # Should not crash — may produce summary analysis or empty
    assert result is not None


@pytest.mark.asyncio
async def test_graph_postprocessor_catches_syntax_error() -> None:
    """The postprocessor should catch invalid Python syntax."""
    graph = PipelineGraph()

    from src.agents.pipeline_state import Criterion, StoryAnalysis

    state = PipelineState(
        user_story="test",
        auto_confirm=True,
        plan_confirmed=True,
        story_analysis=StoryAnalysis(
            criteria=[Criterion(ref="TC01.01", description="test", condition_type="happy_path", priority="medium")],
        ),
        test_conditions=[Criterion(ref="TC01.01", description="test", condition_type="happy_path", priority="medium")],
        test_code="def broken( pass",  # syntax error, no placeholders
    )

    result = await graph._postprocess(state)
    assert len(result["errors"]) >= 1
    assert any("Syntax" in str(e) for e in result["errors"])
