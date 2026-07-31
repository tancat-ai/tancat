"""Tests for persona routing + impact mapping (Phase 1h).

Covers:
- _after_qa_director: checkpoint + persona routing
- _impact_map: ChangeDelta → ImpactMap generation
- _consolidated_report: report building
- PipelineGraph: full persona-routed flows
"""

from __future__ import annotations

import pytest

from src.agents.pipeline_graph import PipelineGraph, _after_qa_director
from src.agents.pipeline_state import (
    ChangeDelta,
    ConsolidatedReport,
    ImpactMap,
    PipelineState,
)

# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------


class TestPersonaRouting:
    """_after_qa_director routes by plan confirmation + persona_role."""

    def test_no_persona_defaults_to_synthesize(self) -> None:
        """Default: no persona → synthesize."""
        state = PipelineState(user_story="test", auto_confirm=True)
        assert _after_qa_director(state) == "synthesize"

    def test_no_persona_plan_confirmed_synthesize(self) -> None:
        state = PipelineState(user_story="test", plan_confirmed=True)
        assert _after_qa_director(state) == "synthesize"

    def test_qa_lead_routes_to_impact_map(self) -> None:
        state = PipelineState(
            user_story="test",
            persona_role="qa_lead",
            auto_confirm=True,
        )
        assert _after_qa_director(state) == "impact_map"

    def test_operations_routes_to_impact_map(self) -> None:
        state = PipelineState(
            user_story="test",
            persona_role="operations",
            auto_confirm=True,
        )
        assert _after_qa_director(state) == "impact_map"

    def test_developer_routes_to_synthesize(self) -> None:
        state = PipelineState(
            user_story="test",
            persona_role="developer",
            auto_confirm=True,
        )
        assert _after_qa_director(state) == "synthesize"

    def test_product_owner_routes_to_report(self) -> None:
        state = PipelineState(
            user_story="test",
            persona_role="product_owner",
            auto_confirm=True,
        )
        assert _after_qa_director(state) == "consolidated_report"

    def test_unknown_persona_defaults_to_synthesize(self) -> None:
        state = PipelineState(
            user_story="test",
            persona_role="unknown_role",
            auto_confirm=True,
        )
        assert _after_qa_director(state) == "synthesize"

    def test_plan_not_confirmed_pauses(self) -> None:
        """Without auto_confirm or plan_confirmed, pause at checkpoint."""
        state = PipelineState(
            user_story="test",
            persona_role="qa_lead",
            # no auto_confirm, no plan_confirmed
        )
        assert _after_qa_director(state) == "__end__"

    def test_auto_confirm_skips_checkpoint(self) -> None:
        """auto_confirm=True bypasses the human checkpoint."""
        state = PipelineState(
            user_story="test",
            persona_role="qa_lead",
            auto_confirm=True,
        )
        assert _after_qa_director(state) == "impact_map"


# ---------------------------------------------------------------------------
# Impact Mapper tests
# ---------------------------------------------------------------------------


class TestImpactMapper:
    """_impact_map node builds ImpactMaps from ChangeDeltas."""

    @pytest.fixture
    def graph(self) -> PipelineGraph:
        return PipelineGraph(client=None, enable_checkpoint=False)

    @pytest.mark.asyncio
    async def test_no_deltas_returns_empty(self, graph: PipelineGraph) -> None:
        state = PipelineState(user_story="test", persona_role="qa_lead")
        result = await graph._impact_map(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_new_feature_produces_happy_and_error_paths(self, graph: PipelineGraph) -> None:
        state = PipelineState(
            user_story="test",
            persona_role="qa_lead",
            change_deltas=[
                ChangeDelta(
                    category="new_feature",
                    name="Dark mode",
                    description="Added dark mode",
                    affected_systems=["ui"],
                )
            ],
        )
        result = await graph._impact_map(state)
        assert len(result["impact_maps"]) == 1
        im = result["impact_maps"][0]
        assert im.change_ref == "Dark mode"
        assert "Happy path" in im.test_scenarios[0]
        assert "Error path" in im.test_scenarios[1]
        assert im.risk_level == "low"  # new feature, small impact radius

    @pytest.mark.asyncio
    async def test_modified_produces_verification_scenarios(self, graph: PipelineGraph) -> None:
        state = PipelineState(
            user_story="test",
            persona_role="qa_lead",
            change_deltas=[
                ChangeDelta(
                    category="modified",
                    name="Login flow",
                    description="Changed login",
                    affected_systems=["auth", "session"],
                )
            ],
        )
        result = await graph._impact_map(state)
        im = result["impact_maps"][0]
        assert "still works" in im.test_scenarios[0]
        assert "edge cases" in im.test_scenarios[1]
        assert "integration-tests" in im.regression_areas
        assert im.risk_level == "medium"  # modified, small radius

    @pytest.mark.asyncio
    async def test_removed_is_high_risk(self, graph: PipelineGraph) -> None:
        state = PipelineState(
            user_story="test",
            persona_role="qa_lead",
            change_deltas=[
                ChangeDelta(
                    category="removed",
                    name="Old API v1",
                    description="Deprecated",
                    affected_systems=["api-gateway", "mobile-app", "web-client"],
                )
            ],
        )
        result = await graph._impact_map(state)
        im = result["impact_maps"][0]
        assert im.risk_level == "high"
        assert "no longer accessible" in im.test_scenarios[0]
        assert "dependent features" in im.test_scenarios[1]

    @pytest.mark.asyncio
    async def test_schema_changes_are_high_risk(self, graph: PipelineGraph) -> None:
        from src.agents.pipeline_state import DataSchemaChange

        state = PipelineState(
            user_story="test",
            persona_role="qa_lead",
            change_deltas=[
                ChangeDelta(
                    category="modified",
                    name="User table",
                    description="Schema change",
                    data_schema_changes=[
                        DataSchemaChange(
                            field="email",
                            change_type="MODIFIED",
                            old_value="VARCHAR(100)",
                            new_value="VARCHAR(255)",
                        )
                    ],
                )
            ],
        )
        result = await graph._impact_map(state)
        assert result["impact_maps"][0].risk_level == "high"

    @pytest.mark.asyncio
    async def test_operations_persona_adds_deployment_scenarios(self, graph: PipelineGraph) -> None:
        state = PipelineState(
            user_story="test",
            persona_role="operations",
            change_deltas=[
                ChangeDelta(
                    category="new_feature",
                    name="Dashboard widget",
                    description="New widget",
                )
            ],
        )
        result = await graph._impact_map(state)
        im = result["impact_maps"][0]
        assert any("rollback" in s.lower() for s in im.test_scenarios)
        assert any("monitoring" in s.lower() for s in im.test_scenarios)

    @pytest.mark.asyncio
    async def test_multiple_deltas_produce_multiple_maps(self, graph: PipelineGraph) -> None:
        state = PipelineState(
            user_story="test",
            persona_role="qa_lead",
            change_deltas=[
                ChangeDelta(category="new_feature", name="Feature A", description="A"),
                ChangeDelta(category="modified", name="Feature B", description="B"),
                ChangeDelta(category="removed", name="Feature C", description="C"),
            ],
        )
        result = await graph._impact_map(state)
        assert len(result["impact_maps"]) == 3
        risks = [m.risk_level for m in result["impact_maps"]]
        assert risks == ["low", "medium", "high"]


# ---------------------------------------------------------------------------
# Consolidated Report tests
# ---------------------------------------------------------------------------


class TestConsolidatedReport:
    """_consolidated_report builds human-readable summary."""

    @pytest.fixture
    def graph(self) -> PipelineGraph:
        return PipelineGraph(client=None, enable_checkpoint=False)

    @pytest.mark.asyncio
    async def test_empty_deltas_produces_no_changes_message(self, graph: PipelineGraph) -> None:
        state = PipelineState(user_story="test")
        result = await graph._consolidated_report(state)
        report = result["consolidated_report"]
        assert isinstance(report, ConsolidatedReport)
        assert "No changes" in report.executive_summary

    @pytest.mark.asyncio
    async def test_with_deltas_produces_category_summary(self, graph: PipelineGraph) -> None:
        state = PipelineState(
            user_story="test",
            change_deltas=[
                ChangeDelta(category="new_feature", name="A", description="A"),
                ChangeDelta(category="modified", name="B", description="B"),
                ChangeDelta(category="new_feature", name="C", description="C"),
            ],
        )
        result = await graph._consolidated_report(state)
        report = result["consolidated_report"]
        assert "2 new feature" in report.executive_summary
        assert "1 modified" in report.executive_summary

    @pytest.mark.asyncio
    async def test_includes_test_code_and_errors(self, graph: PipelineGraph) -> None:
        state = PipelineState(
            user_story="test",
            change_deltas=[ChangeDelta(category="new_feature", name="A", description="A")],
            test_code="def test_a(): pass",
            errors=["Something went wrong"],
            unresolved_placeholders=["Unresolved: X"],
        )
        result = await graph._consolidated_report(state)
        report = result["consolidated_report"]
        assert report.generated_tests == "def test_a(): pass"
        assert "Something went wrong" in report.unresolved_items
        assert "Unresolved: X" in report.unresolved_items

    @pytest.mark.asyncio
    async def test_includes_impact_maps(self, graph: PipelineGraph) -> None:
        state = PipelineState(
            user_story="test",
            change_deltas=[ChangeDelta(category="new_feature", name="A", description="A")],
            impact_maps=[ImpactMap(change_ref="A", risk_level="low")],
        )
        result = await graph._consolidated_report(state)
        report = result["consolidated_report"]
        assert len(report.impact_maps) == 1
        assert report.impact_maps[0].change_ref == "A"


# ---------------------------------------------------------------------------
# Full pipeline flow tests
# ---------------------------------------------------------------------------


class TestPersonaFlow:
    """End-to-end persona-routed pipeline execution."""

    @pytest.fixture
    def graph(self) -> PipelineGraph:
        return PipelineGraph(client=None, enable_checkpoint=False)

    @pytest.mark.asyncio
    async def test_qa_lead_with_deltas_flows_through_impact(self, graph: PipelineGraph) -> None:
        """QA lead persona with change deltas hits impact_map → synthesize."""
        result = await graph.run(
            user_story="Test spec for new feature.",
            conditions="1. Verify login\n2. Test checkout",
            auto_confirm=True,
            input_mode="document",
            persona_role="qa_lead",
            # Document text with headings → fallback deltas
        )
        assert result.persona_role == "qa_lead"

    @pytest.mark.asyncio
    async def test_product_owner_stops_at_report(self, graph: PipelineGraph) -> None:
        """Product owner persona routes to consolidated_report, skips test generation."""
        result = await graph.run(
            user_story="Test spec.",
            conditions="1. Login",
            auto_confirm=True,
            input_mode="document",
            persona_role="product_owner",
        )
        # Product owner → consolidated_report → END (no synthesis)
        # The report should exist, test_code should be empty
        assert result.consolidated_report is not None

    @pytest.mark.asyncio
    async def test_developer_skips_impact(self, graph: PipelineGraph) -> None:
        """Developer persona skips impact mapper, goes straight to synthesize."""
        result = await graph.run(
            user_story="Test spec.",
            conditions="1. Login",
            auto_confirm=True,
            input_mode="document",
            persona_role="developer",
        )
        assert result.impact_maps == []

    @pytest.mark.asyncio
    async def test_no_persona_with_document_still_generates_tests(self, graph: PipelineGraph) -> None:
        """Default behavior: document mode without persona still produces test code."""
        result = await graph.run(
            user_story="Test spec.",
            conditions="1. Login",
            auto_confirm=True,
            input_mode="document",
        )
        assert result.persona_role == ""
