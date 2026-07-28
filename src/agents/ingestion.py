"""Ingestion Agent — analyses user story text into structured StoryAnalysis.

Wraps the existing ``SpecAnalyzer`` for deterministic criteria extraction
and layers RAG retrieval for domain-specific context enrichment.

Phase 1b: real LLM analysis via SpecAnalyzer + optional RAG.
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.pipeline_state import Criterion, PipelineState, StoryAnalysis
from src.spec_analyzer import SpecAnalyzer

logger = logging.getLogger(__name__)


class IngestionAgent:
    """Analyses user story text and produces structured ``StoryAnalysis``.

    Uses ``SpecAnalyzer`` for criteria extraction (handles numbered lists,
    comma-separated concerns, and LLM fallback for unstructured text).
    Optionally queries the RAG vector store for domain-specific patterns.

    Args:
        client: LLMClient for LLM fallback in SpecAnalyzer.
        rag_retriever: Optional RAGRetriever for domain pattern enrichment.
    """

    def __init__(self, client: Any, rag_retriever: Any | None = None) -> None:
        self._analyzer = SpecAnalyzer(client)
        self._rag = rag_retriever

    async def __call__(self, state: PipelineState) -> dict[str, Any]:
        """Analyse the user story and return ``story_analysis`` for the graph state.

        When ``state.conditions`` is provided (numbered acceptance criteria),
        each line becomes its own criterion — no LLM needed for extraction.
        Falls back to SpecAnalyzer for unstructured story-only input.
        """
        story_text = state.user_story
        if not story_text or not story_text.strip():
            return {
                "story_analysis": StoryAnalysis(story_text=""),
                "errors": ["Empty user story — nothing to analyse"],
            }

        # 1. Deterministic: use acceptance criteria if provided
        if state.conditions and state.conditions.strip():
            conditions = self._criteria_from_text(state.conditions)
            logger.info("Ingestion: extracted %d criteria from acceptance criteria text", len(conditions))
        else:
            # Fall back to SpecAnalyzer for unstructured story text
            try:
                conditions = self._analyzer.analyze(story_text)
            except Exception as e:
                logger.warning("SpecAnalyzer failed: %s — using raw text", e)
                conditions = self._criteria_from_text(story_text)

        # 2. Query RAG for domain context (non-blocking, best-effort)
        domain_terms: list[str] = []
        if self._rag:
            try:
                patterns = self._rag.retrieve(story_text, action_type="ASSERT")
                seen: set[str] = set()
                for p in patterns[:10]:
                    desc = getattr(p, "description", "")
                    if desc and desc not in seen:
                        domain_terms.append(desc)
                        seen.add(desc)
            except Exception as e:
                logger.debug("RAG retrieval skipped: %s", e)

        # 3. Extract assumptions from flagged conditions
        assumptions = [
            c.expected for c in conditions if c.flagged and c.expected and "Needs refinement" not in c.expected
        ]

        # 4. Map SpecAnalyzer.TestCondition → pipeline Criterion
        criteria = [
            Criterion(
                ref=c.id,
                description=c.text,
                condition_type=c.type,
                priority="medium",
                source_text=c.source,
                needs_clarification=c.flagged,
                clarification_question=c.expected if c.flagged else "",
            )
            for c in conditions
        ]

        # 5. Detect source format
        source_format = "free-form"
        if conditions:
            # Heuristic: numbered criteria → "numbered", Gherkin keywords → "gherkin"
            first_text = conditions[0].source.lower() if conditions else ""
            if "acceptance criteria" in first_text or len(conditions) > 1:
                source_format = "numbered"
            if any(kw in story_text.lower() for kw in ("given ", "when ", "then ", "feature:")):
                source_format = "gherkin"

        return {
            "story_analysis": StoryAnalysis(
                story_text=story_text,
                criteria=criteria,
                domain_terms=domain_terms,
                assumptions=assumptions,
                source_format=source_format,
            ),
        }

    @staticmethod
    def _criteria_from_text(conditions_text: str) -> list:
        """Extract criteria deterministically from numbered acceptance criteria.

        Each non-empty line becomes one ``TestCondition``.  Strips leading
        numbering (e.g. '1.', '1)', '[TC-01]').  Returns objects
        compatible with ``SpecAnalyzer.TestCondition``.
        """
        import re

        from src.spec_analyzer import TestCondition

        lines = [line.strip() for line in conditions_text.splitlines() if line.strip()]
        if not lines:
            return []

        conditions: list[TestCondition] = []
        for i, line in enumerate(lines, start=1):
            # Strip leading numbers and markers
            cleaned = re.sub(r"^\d+[.)\]\s]+", "", line).strip()
            cleaned = re.sub(r"^\[([^\]]+)\]\s*", "", cleaned).strip()
            if not cleaned:
                continue

            ref = f"TC01.{i:02d}"
            conditions.append(
                TestCondition(
                    id=ref,
                    type="happy_path",
                    text=cleaned,
                    expected="Meets acceptance criteria.",
                    source=line,
                    flagged=False,
                    src="ai",
                    intent="journey_step",
                )
            )

        return conditions
