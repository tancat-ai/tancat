"""Tests for change delta extraction (Phase 1g).

Covers:
- _extract_deltas_from_headings: markdown heading fallback
- _parse_change_deltas_json: JSON parsing with various LLM output quirks
- _extract_change_deltas: LLM-based extraction via mock client
- Integration: deltas flow through __call__ in document mode
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.agents.ingestion import IngestionAgent
from src.agents.pipeline_state import PipelineState

# ---------------------------------------------------------------------------
# Heading-based fallback
# ---------------------------------------------------------------------------


class TestExtractDeltasFromHeadings:
    """_extract_deltas_from_headings deterministic fallback."""

    def test_extracts_markdown_headings(self) -> None:
        text = "# PRD: Login Overhaul (h1 - skipped)\n\n## Add two-factor auth\n\n## Modify password reset\n\n## Keep session timeout unchanged"
        deltas = IngestionAgent._extract_deltas_from_headings(text)
        names = [d.name for d in deltas]
        assert "Add two-factor auth" in names
        assert "Modify password reset" in names
        assert "Keep session timeout unchanged" in names
        # "PRD: Login Overhaul" is h1 — skipped
        assert "PRD: Login Overhaul" not in names

    def test_skips_section_headers(self) -> None:
        text = "# Overview\n\n## Introduction\n\n## Background\n\n## Table of Contents"
        deltas = IngestionAgent._extract_deltas_from_headings(text)
        assert len(deltas) == 0

    def test_skips_short_headings(self) -> None:
        text = "## AB\n\n## Login feature"
        deltas = IngestionAgent._extract_deltas_from_headings(text)
        assert len(deltas) == 1
        assert deltas[0].name == "Login feature"

    def test_default_category_is_modified(self) -> None:
        text = "## New dashboard"
        deltas = IngestionAgent._extract_deltas_from_headings(text)
        assert deltas[0].category == "modified"
        assert deltas[0].affected_systems == []

    def test_h2_and_h3_extracted(self) -> None:
        text = "## Feature A\n\n### Sub-feature A1\n\n# Top level (h1 - skipped)\n\n### Sub-feature A2"
        deltas = IngestionAgent._extract_deltas_from_headings(text)
        names = [d.name for d in deltas]
        assert names == ["Feature A", "Sub-feature A1", "Sub-feature A2"]

    def test_empty_text_returns_empty(self) -> None:
        assert IngestionAgent._extract_deltas_from_headings("") == []
        assert IngestionAgent._extract_deltas_from_headings("Just plain text, no headings.") == []


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------


class TestParseChangeDeltasJson:
    """_parse_change_deltas_json handles various LLM output formats."""

    def test_parses_clean_json(self) -> None:
        response = json.dumps(
            {
                "change_deltas": [
                    {
                        "category": "new_feature",
                        "name": "2FA",
                        "description": "Added SMS auth",
                        "affected_systems": ["auth"],
                        "data_schema_changes": [
                            {
                                "field": "phone",
                                "change_type": "NEW",
                                "old_value": "",
                                "new_value": "VARCHAR(15)",
                                "migration_notes": "",
                            }
                        ],
                    }
                ]
            }
        )
        deltas = IngestionAgent._parse_change_deltas_json(response)
        assert len(deltas) == 1
        assert deltas[0].name == "2FA"
        assert deltas[0].category == "new_feature"
        assert deltas[0].data_schema_changes[0].field == "phone"

    def test_strips_markdown_fences(self) -> None:
        response = '```json\n{"change_deltas": [{"category": "removed", "name": "Old endpoint", "description": "Deprecated", "affected_systems": [], "data_schema_changes": []}]}\n```'
        deltas = IngestionAgent._parse_change_deltas_json(response)
        assert len(deltas) == 1
        assert deltas[0].name == "Old endpoint"
        assert deltas[0].category == "removed"

    def test_returns_empty_on_unparseable(self) -> None:
        assert IngestionAgent._parse_change_deltas_json("Just some prose, no JSON here.") == []
        assert IngestionAgent._parse_change_deltas_json("") == []

    def test_handles_missing_optional_fields(self) -> None:
        response = json.dumps(
            {
                "change_deltas": [
                    {
                        "category": "modified",
                        "name": "Minimal change",
                        "description": "Minimal",
                    }
                ]
            }
        )
        deltas = IngestionAgent._parse_change_deltas_json(response)
        assert len(deltas) == 1
        assert deltas[0].affected_systems == []
        assert deltas[0].data_schema_changes == []

    def test_multiple_deltas(self) -> None:
        response = json.dumps(
            {
                "change_deltas": [
                    {
                        "category": "new_feature",
                        "name": "Feature A",
                        "description": "Added A",
                        "affected_systems": [],
                        "data_schema_changes": [],
                    },
                    {
                        "category": "modified",
                        "name": "Feature B",
                        "description": "Changed B",
                        "affected_systems": ["api"],
                        "data_schema_changes": [],
                    },
                ]
            }
        )
        deltas = IngestionAgent._parse_change_deltas_json(response)
        assert len(deltas) == 2
        assert deltas[0].name == "Feature A"
        assert deltas[1].name == "Feature B"

    def test_missing_change_deltas_key(self) -> None:
        response = json.dumps({"other_field": "value"})
        assert IngestionAgent._parse_change_deltas_json(response) == []

    def test_non_dict_entries_skipped(self) -> None:
        response = json.dumps({"change_deltas": [{"name": "Valid"}, "not a dict", 123, {"name": "Also valid"}]})
        deltas = IngestionAgent._parse_change_deltas_json(response)
        assert len(deltas) == 2
        names = [d.name for d in deltas]
        assert "Valid" in names
        assert "Also valid" in names


# ---------------------------------------------------------------------------
# LLM-based extraction
# ---------------------------------------------------------------------------


class TestExtractChangeDeltasLLM:
    """_extract_change_deltas with mock LLM client."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        client = AsyncMock()
        client.generate = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_parses_valid_llm_response(self, mock_client: AsyncMock) -> None:
        response = json.dumps(
            {
                "change_deltas": [
                    {
                        "category": "new_feature",
                        "name": "Dark mode",
                        "description": "Added dark mode support",
                        "affected_systems": ["ui", "theme-engine"],
                        "data_schema_changes": [],
                    }
                ]
            }
        )
        mock_client.generate.return_value = response

        agent = IngestionAgent(mock_client)
        deltas = await agent._extract_change_deltas("## New dark mode feature\n\nWe added dark mode support.")
        assert len(deltas) == 1
        assert deltas[0].name == "Dark mode"
        mock_client.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_headings_on_llm_error(self, mock_client: AsyncMock) -> None:
        mock_client.generate.side_effect = RuntimeError("LLM timeout")

        agent = IngestionAgent(mock_client)
        text = "## Login flow update\n\n## Payment processor change"
        deltas = await agent._extract_change_deltas(text)

        # Should have fallen back to heading extraction
        names = [d.name for d in deltas]
        assert "Login flow update" in names
        assert "Payment processor change" in names

    @pytest.mark.asyncio
    async def test_falls_back_on_unparseable_response(self, mock_client: AsyncMock) -> None:
        mock_client.generate.return_value = "Here are the changes: 1. Login 2. Payment"

        agent = IngestionAgent(mock_client)
        text = "## Login flow update\n\n## Payment processor change"
        deltas = await agent._extract_change_deltas(text)

        names = [d.name for d in deltas]
        assert "Login flow update" in names  # fallback
        assert "Payment processor change" in names

    @pytest.mark.asyncio
    async def test_no_client_falls_back_immediately(self) -> None:
        agent = IngestionAgent(None)  # type: ignore[arg-type]
        text = "## Feature A\n\n## Feature B"
        deltas = await agent._extract_change_deltas(text)

        names = [d.name for d in deltas]
        assert names == ["Feature A", "Feature B"]


# ---------------------------------------------------------------------------
# Integration: deltas flow through __call__
# ---------------------------------------------------------------------------


class TestChangeDeltaIntegration:
    """Change deltas propagate through the IngestionAgent __call__."""

    @pytest.mark.asyncio
    async def test_document_mode_extracts_deltas(self) -> None:
        """In document mode with a mock LLM, change deltas appear in output."""
        client = AsyncMock()
        client.generate = AsyncMock()
        client.generate.return_value = json.dumps(
            {
                "change_deltas": [
                    {
                        "category": "new_feature",
                        "name": "Search bar",
                        "description": "Added search",
                        "affected_systems": [],
                        "data_schema_changes": [],
                    }
                ]
            }
        )

        agent = IngestionAgent(client)
        state = PipelineState(
            user_story="Spec for search feature.",
            conditions="1. Search\n2. Filter results",
            input_mode="document",
            raw_document_text="## Search bar\n\nWe added a new search bar.",
        )
        result = await agent(state)

        assert "change_deltas" in result
        assert len(result["change_deltas"]) == 1
        assert result["change_deltas"][0].name == "Search bar"

    @pytest.mark.asyncio
    async def test_text_mode_skips_delta_extraction(self) -> None:
        """In text mode, no change delta extraction occurs."""
        client = AsyncMock()
        client.generate = AsyncMock()

        agent = IngestionAgent(client)
        state = PipelineState(
            user_story="As a user I want to log in.",
            conditions="1. Login\n2. Dashboard",
            input_mode="text",
        )
        result = await agent(state)

        assert "change_deltas" in result
        assert result["change_deltas"] == []
        # LLM should NOT have been called for delta extraction
        client.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_document_text_skips_extraction(self) -> None:
        client = AsyncMock()
        client.generate = AsyncMock()

        agent = IngestionAgent(client)
        state = PipelineState(
            user_story="As a user I want to log in.",
            conditions="1. Login",
            input_mode="document",
            raw_document_text="",  # no document text
        )
        result = await agent(state)

        assert result["change_deltas"] == []
        client.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_document_fallback_without_llm_client(self) -> None:
        """No LLM client → heading fallback for delta extraction."""
        agent = IngestionAgent(None)  # type: ignore[arg-type]
        state = PipelineState(
            user_story="Spec document.",
            conditions="1. Feature A",
            input_mode="document",
            raw_document_text="## New widget\n\n### Widget config",
        )
        result = await agent(state)

        names = [d.name for d in result["change_deltas"]]
        assert "New widget" in names
        assert "Widget config" in names
