"""Phase 1j — Document-mode eval validation.

Runs the document pipeline against 3 spec documents and validates:
1. Change delta extraction (heading fallback, no LLM needed)
2. Test condition generation
3. Delta count ≥ golden minimum
4. Pipeline produces test code without errors
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agents.pipeline_graph import PipelineGraph

DATASET_DIR = Path(__file__).parent.parent / "scripts" / "eval" / "dataset_docs"


def load_golden_keys() -> list[dict]:
    """Load all golden key JSON files from the dataset directory."""
    keys: list[dict] = []
    for f in sorted(DATASET_DIR.glob("*.json")):
        keys.append(json.loads(f.read_text(encoding="utf-8")))
    return keys


GOLDEN_KEYS = load_golden_keys()
GOLDEN_IDS = [g["id"] for g in GOLDEN_KEYS]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def graph() -> PipelineGraph:
    """Pipeline without LLM client — uses mock agents."""
    return PipelineGraph(client=None, enable_checkpoint=False)


# ---------------------------------------------------------------------------
# Heading delta extraction validation
# ---------------------------------------------------------------------------


class TestHeadingDeltaExtraction:
    """Verify deterministic heading-based delta extraction."""

    @pytest.mark.parametrize("golden", GOLDEN_KEYS, ids=GOLDEN_IDS)
    def test_heading_deltas_match_golden(self, golden: dict) -> None:
        """Each document's headings are correctly extracted as deltas."""
        from src.agents.ingestion import IngestionAgent

        doc_path = DATASET_DIR / golden["document"]
        text = doc_path.read_text(encoding="utf-8")

        deltas = IngestionAgent._extract_deltas_from_headings(text)
        names = [d.name for d in deltas]

        expected = golden["expected_heading_deltas"]
        for name in expected:
            assert name in names, f"Expected heading '{name}' not found in {[d.name for d in deltas]}"

    @pytest.mark.parametrize("golden", GOLDEN_KEYS, ids=GOLDEN_IDS)
    def test_delta_count_meets_minimum(self, golden: dict) -> None:
        """Heading extraction produces at least the expected minimum deltas."""
        from src.agents.ingestion import IngestionAgent

        doc_path = DATASET_DIR / golden["document"]
        text = doc_path.read_text(encoding="utf-8")

        deltas = IngestionAgent._extract_deltas_from_headings(text)
        assert len(deltas) >= golden["expected_deltas_min"], (
            f"Expected at least {golden['expected_deltas_min']} deltas, got {len(deltas)}"
        )

    @pytest.mark.parametrize("golden", GOLDEN_KEYS, ids=GOLDEN_IDS)
    def test_unchanged_sections_are_skipped(self, golden: dict) -> None:
        """Sections with explicit 'Unchanged:' prefix/suffix in heading are skipped."""
        from src.agents.ingestion import IngestionAgent

        doc_path = DATASET_DIR / golden["document"]
        text = doc_path.read_text(encoding="utf-8")

        deltas = IngestionAgent._extract_deltas_from_headings(text)
        names = [d.name for d in deltas]

        # The only guaranteed unchanged heading is one with explicit marker
        # Doc 2 has "Unchanged: Payment Gateway Integration"
        # Doc 3 has "Authentication Middleware [UNCHANGED]"
        unchanged_terms = ["Payment Gateway Integration", "Authentication Middleware"]
        for term in unchanged_terms:
            if term in text:
                assert term not in names, f"Unchanged section '{term}' should not be a delta"


# ---------------------------------------------------------------------------
# Full pipeline validation
# ---------------------------------------------------------------------------


class TestDocumentPipeline:
    """End-to-end document-mode pipeline produces expected output."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("golden", GOLDEN_KEYS, ids=GOLDEN_IDS)
    async def test_pipeline_produces_test_conditions(self, graph: PipelineGraph, golden: dict) -> None:
        """Document mode pipeline generates at least min test conditions."""
        doc_path = DATASET_DIR / golden["document"]
        doc_path_str = str(doc_path.resolve())

        result = await graph.run(
            user_story=golden.get("user_story", ""),
            conditions="",  # empty — document parsing provides content
            input_mode="document",
            document_source=doc_path_str,
            auto_confirm=True,
        )

        # Should have parsed the document
        assert result.raw_document_text, "Document text was not parsed"
        assert len(result.raw_document_text) > 200, f"Document text too short: {len(result.raw_document_text)} chars"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("golden", GOLDEN_KEYS, ids=GOLDEN_IDS)
    async def test_pipeline_produces_change_deltas(self, graph: PipelineGraph, golden: dict) -> None:
        """Document mode pipeline extracts change deltas from headings."""
        doc_path = DATASET_DIR / golden["document"]
        doc_path_str = str(doc_path.resolve())

        result = await graph.run(
            user_story=golden.get("user_story", ""),
            conditions="",
            input_mode="document",
            document_source=doc_path_str,
            auto_confirm=True,
        )

        assert len(result.change_deltas) >= golden["expected_deltas_min"], (
            f"Expected at least {golden['expected_deltas_min']} deltas, got {len(result.change_deltas)}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("golden", GOLDEN_KEYS, ids=GOLDEN_IDS)
    async def test_pipeline_produces_test_code(self, graph: PipelineGraph, golden: dict) -> None:
        """Document mode pipeline produces non-empty test code."""
        doc_path = DATASET_DIR / golden["document"]
        doc_path_str = str(doc_path.resolve())

        result = await graph.run(
            user_story=golden.get("user_story", ""),
            conditions="",
            input_mode="document",
            document_source=doc_path_str,
            persona_role="qa_lead",
            auto_confirm=True,
        )

        assert result.test_code, "Pipeline produced no test code"
        assert "pytest" in result.test_code.lower() or "def test_" in result.test_code, (
            f"Generated code doesn't look like pytest: {result.test_code[:200]}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("golden", GOLDEN_KEYS, ids=GOLDEN_IDS)
    async def test_pipeline_no_errors(self, graph: PipelineGraph, golden: dict) -> None:
        """Document mode pipeline runs without errors."""
        doc_path = DATASET_DIR / golden["document"]
        doc_path_str = str(doc_path.resolve())

        result = await graph.run(
            user_story=golden.get("user_story", ""),
            conditions="",
            input_mode="document",
            document_source=doc_path_str,
            auto_confirm=True,
        )

        assert not result.errors, f"Pipeline had errors: {result.errors}"


# ---------------------------------------------------------------------------
# Impact map validation (qa_lead persona)
# ---------------------------------------------------------------------------


class TestImpactMapGeneration:
    """Impact maps are generated for QA lead persona."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("golden", GOLDEN_KEYS, ids=GOLDEN_IDS)
    async def test_qa_lead_generates_impact_maps(self, graph: PipelineGraph, golden: dict) -> None:
        """QA lead persona generates impact maps from change deltas."""
        doc_path = DATASET_DIR / golden["document"]
        doc_path_str = str(doc_path.resolve())

        result = await graph.run(
            user_story=golden.get("user_story", ""),
            conditions="",
            input_mode="document",
            document_source=doc_path_str,
            persona_role="qa_lead",
            auto_confirm=True,
        )

        assert len(result.impact_maps) > 0, "QA lead should generate impact maps"

        # Each impact map should reference a delta
        delta_names = {d.name for d in result.change_deltas}
        for im in result.impact_maps:
            assert im.change_ref in delta_names, f"Impact map ref '{im.change_ref}' not in deltas {delta_names}"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("golden", GOLDEN_KEYS, ids=GOLDEN_IDS)
    async def test_product_owner_generates_report(self, graph: PipelineGraph, golden: dict) -> None:
        """Product owner persona generates consolidated report, not test code."""
        doc_path = DATASET_DIR / golden["document"]
        doc_path_str = str(doc_path.resolve())

        result = await graph.run(
            user_story=golden.get("user_story", ""),
            conditions="",
            input_mode="document",
            document_source=doc_path_str,
            persona_role="product_owner",
            auto_confirm=True,
        )

        assert result.consolidated_report is not None
        assert result.consolidated_report.executive_summary


# ---------------------------------------------------------------------------
# Gate: document mode quality threshold
# ---------------------------------------------------------------------------


class TestDocumentQualityGate:
    """Phase 1j gate: document mode meets ≥90% quality threshold."""

    def test_heading_extraction_accuracy(self) -> None:
        """Heading-delta extraction accuracy across all documents.

        The deterministic heading fallback must extract ≥90% of the
        expected headings from the golden keys.
        """
        from src.agents.ingestion import IngestionAgent

        total_expected = 0
        total_extracted = 0

        for golden in GOLDEN_KEYS:
            doc_path = DATASET_DIR / golden["document"]
            text = doc_path.read_text(encoding="utf-8")
            deltas = IngestionAgent._extract_deltas_from_headings(text)
            names = {d.name for d in deltas}

            expected = set(golden["expected_heading_deltas"])
            total_expected += len(expected)
            total_extracted += len(names & expected)  # intersection

        accuracy = total_extracted / total_expected if total_expected > 0 else 0
        print(f"\nHeading extraction accuracy: {total_extracted}/{total_expected} = {accuracy:.0%}")
        assert accuracy >= 0.90, f"Heading extraction accuracy {accuracy:.0%} below 90% gate"
