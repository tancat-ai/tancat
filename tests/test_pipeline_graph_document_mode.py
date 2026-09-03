"""Tests for document-mode pipeline graph (Phase 1f).

Covers:
- State schema: ChangeDelta, DataSchemaChange, ImpactMap, ConsolidatedReport
- PipelineState document-mode fields (input_mode, document_source, etc.)
- _parse_document node: PDF and Markdown input paths
- _route_entry: conditional routing (text vs document mode)
- PipelineGraph.run() with document_mode params
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agents.pipeline_graph import PipelineGraph, _route_entry
from src.agents.pipeline_state import (
    ChangeDelta,
    ConsolidatedReport,
    DataSchemaChange,
    ImpactMap,
    PipelineState,
)

# ---------------------------------------------------------------------------
# State schema tests
# ---------------------------------------------------------------------------


class TestDocumentModeStateSchema:
    """Document-mode dataclasses and PipelineState fields."""

    def test_data_schema_change_defaults(self) -> None:
        dsc = DataSchemaChange(
            field="customer_id",
            change_type="MODIFIED",
            old_value="VARCHAR(8)",
            new_value="VARCHAR(10)",
        )
        assert dsc.field == "customer_id"
        assert dsc.change_type == "MODIFIED"
        assert dsc.migration_notes == ""

    def test_change_delta_defaults(self) -> None:
        cd = ChangeDelta(
            category="new_feature",
            name="Two-factor auth",
            description="Added SMS-based 2FA to login flow",
        )
        assert cd.affected_systems == []
        assert cd.data_schema_changes == []

    def test_change_delta_with_schema_changes(self) -> None:
        dsc = DataSchemaChange(
            field="phone_number",
            change_type="NEW",
            old_value="",
            new_value="VARCHAR(15)",
        )
        cd = ChangeDelta(
            category="new_feature",
            name="2FA",
            description="Added 2FA",
            affected_systems=["auth", "user-service"],
            data_schema_changes=[dsc],
        )
        assert len(cd.data_schema_changes) == 1
        assert cd.affected_systems == ["auth", "user-service"]

    def test_impact_map_defaults(self) -> None:
        im = ImpactMap(change_ref="2FA")
        assert im.impact_radius == []
        assert im.regression_areas == []
        assert im.test_scenarios == []
        assert im.risk_level == "medium"

    def test_consolidated_report_defaults(self) -> None:
        cr = ConsolidatedReport()
        assert cr.executive_summary == ""
        assert cr.change_summary == []
        assert cr.generated_tests == ""

    def test_pipeline_state_document_defaults(self) -> None:
        """Document-mode fields default to text mode."""
        ps = PipelineState(user_story="test")
        assert ps.input_mode == "text"
        assert ps.raw_document_text == ""
        assert ps.document_source == ""
        assert ps.change_deltas == []
        assert ps.persona_role == ""
        assert ps.impact_maps == []
        assert ps.consolidated_report is None

    def test_pipeline_state_document_mode_init(self) -> None:
        """Document-mode fields can be set at init."""
        ps = PipelineState(
            user_story="test",
            input_mode="document",
            document_source="/path/to/spec.pdf",
            persona_role="qa_lead",
        )
        assert ps.input_mode == "document"
        assert ps.document_source == "/path/to/spec.pdf"
        assert ps.persona_role == "qa_lead"


# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------


class TestRouteEntry:
    """_route_entry conditional routing."""

    def test_text_mode_routes_to_ingest(self) -> None:
        state = PipelineState(user_story="test", input_mode="text")
        assert _route_entry(state) == "ingest"

    def test_text_mode_default_routes_to_ingest(self) -> None:
        """Default input_mode is 'text' → routes to ingest."""
        state = PipelineState(user_story="test")
        assert _route_entry(state) == "ingest"

    def test_document_mode_with_source_routes_to_parse(self) -> None:
        state = PipelineState(
            user_story="",
            input_mode="document",
            document_source="/tmp/spec.pdf",
        )
        assert _route_entry(state) == "parse_document"

    def test_document_mode_without_source_routes_to_ingest(self) -> None:
        """No document_source → fall through to ingest."""
        state = PipelineState(
            user_story="test",
            input_mode="document",
            document_source="",
        )
        assert _route_entry(state) == "ingest"


# ---------------------------------------------------------------------------
# _parse_document node tests
# ---------------------------------------------------------------------------


class TestParseDocumentNode:
    """PipelineGraph._parse_document() node."""

    @pytest.fixture
    def graph(self) -> PipelineGraph:
        """PipelineGraph with no LLM client (mock agents)."""
        return PipelineGraph(client=None, enable_checkpoint=False)

    @pytest.mark.asyncio
    async def test_empty_document_source_returns_error(self, graph: PipelineGraph) -> None:
        state = PipelineState(input_mode="document", document_source="")
        result = await graph._parse_document(state)
        assert "empty" in result.get("errors", [""])[0]

    @pytest.mark.asyncio
    async def test_missing_file_returns_error(self, graph: PipelineGraph) -> None:
        state = PipelineState(
            input_mode="document",
            document_source="/nonexistent/path/spec.pdf",
        )
        result = await graph._parse_document(state)
        assert "not found" in result.get("errors", [""])[0].lower()

    @pytest.mark.asyncio
    async def test_markdown_file_read_directly(self, graph: PipelineGraph) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# Test Spec\n\n## Feature: Login\n\nAs a user I want to log in.")
            f.flush()
            path = f.name

        try:
            state = PipelineState(
                input_mode="document",
                document_source=path,
            )
            result = await graph._parse_document(state)
            assert "raw_document_text" in result
            assert "# Test Spec" in result["raw_document_text"]
            assert "As a user" in result["raw_document_text"]
            # user_story seeded with first 500 chars
            assert result.get("user_story", "").startswith("# Test Spec")
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_pdf_file_calls_ingest_pdf(self, graph: PipelineGraph) -> None:
        """Verify PDF path goes through page-aware ingestion (16b Phase 2)."""
        from src.rag_store import DocChunk

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "src.pdf_ingest.ingest_pdf_page_aware",
                return_value=[
                    DocChunk(text="Extracted PDF content.", source="spec.pdf", page=1, route="text"),
                ],
            ) as mock_ingest,
            patch("src.ocr_backends.get_ocr_backend") as mock_backend,
        ):
            mock_ocr = MagicMock()
            mock_ocr.available.return_value = False
            mock_backend.return_value = mock_ocr

            state = PipelineState(
                input_mode="document",
                document_source="/fake/spec.pdf",
            )
            with patch.object(Path, "suffix", new=".pdf"):
                result = await graph._parse_document(state)

            mock_ingest.assert_called_once()
            assert "raw_document_text" in result
            assert "Extracted PDF" in result["raw_document_text"]

    @pytest.mark.asyncio
    async def test_pdf_ingestion_error_returns_error(self, graph: PipelineGraph) -> None:
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "src.pdf_ingest.ingest_pdf_page_aware",
                side_effect=RuntimeError("Corrupt PDF"),
            ),
            patch("src.ocr_backends.get_ocr_backend") as mock_backend,
        ):
            mock_ocr = MagicMock()
            mock_ocr.available.return_value = False
            mock_backend.return_value = mock_ocr

            state = PipelineState(
                input_mode="document",
                document_source="/fake/broken.pdf",
            )
            with patch.object(Path, "suffix", new=".pdf"):
                result = await graph._parse_document(state)
            assert "errors" in result
            assert "Corrupt PDF" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_empty_document_returns_error(self, graph: PipelineGraph) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("   \n\n")
            f.flush()
            path = f.name

        try:
            state = PipelineState(input_mode="document", document_source=path)
            result = await graph._parse_document(state)
            assert "empty" in result.get("errors", [""])[0].lower()
        finally:
            Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# PipelineGraph.run() integration tests
# ---------------------------------------------------------------------------


class TestPipelineGraphDocumentRun:
    """Document-mode params flow through run() into PipelineState."""

    @pytest.fixture
    def graph(self) -> PipelineGraph:
        return PipelineGraph(client=None, enable_checkpoint=False)

    @pytest.mark.asyncio
    async def test_text_mode_is_default(self, graph: PipelineGraph) -> None:
        result = await graph.run(
            user_story="As a user I want to log in.",
            auto_confirm=True,
        )
        assert result.input_mode == "text"
        assert result.document_source == ""

    @pytest.mark.asyncio
    async def test_document_mode_params_propagate(self, graph: PipelineGraph) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# Test\n\nLogin feature spec.")
            f.flush()
            path = f.name

        try:
            result = await graph.run(
                user_story="",
                input_mode="document",
                document_source=path,
                persona_role="qa_lead",
                auto_confirm=True,
            )
            assert result.input_mode == "document"
            assert result.document_source == path
            assert result.persona_role == "qa_lead"
            assert "# Test" in result.raw_document_text
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_document_mode_with_conditions_skip_llm(self, graph: PipelineGraph) -> None:
        """When conditions are provided in document mode, mock Ingestion Agent
        splits user_story by newlines (no LLM client → _ingest_mock path).
        Real agent would use deterministic criteria_from_text."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# Spec\n\n## 1. Login feature\n## 2. Add to cart")
            f.flush()
            path = f.name

        try:
            result = await graph.run(
                user_story="",
                conditions="1. Login\n2. Add to cart",
                input_mode="document",
                document_source=path,
                auto_confirm=True,
            )
            # Mock agent splits user_story (document text) by newlines:
            # "# Spec", "## 1. Login feature", "## 2. Add to cart" → 3 criteria
            assert result.raw_document_text
            assert "Login" in result.raw_document_text
            assert len(result.test_conditions) >= 2
        finally:
            Path(path).unlink(missing_ok=True)
