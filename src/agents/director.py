"""QA Director Agent — routes criteria, assigns priority, flags ambiguities.

Takes the ``StoryAnalysis`` from the Ingestion Agent and produces a
confirmed list of ``Criterion`` objects ready for the Script Synthesizer.

Phase 1b: uses deterministic heuristics + existing SpecAnalyzer for
priority assignment and ambiguity detection.  Future phases can add
LLM-based reasoning for complex stories.
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.pipeline_state import Criterion, PipelineState

logger = logging.getLogger(__name__)


class QADirectorAgent:
    """Routes and prioritises test conditions from story analysis.

    Current implementation:
    - Passes through criteria from the Ingestion Agent unchanged.
    - Assigns priority based on condition type (boundary > happy_path > exploratory).
    - Flags ambiguities for human review.

    Future: LLM-based reasoning for complex multi-condition stories
    where criteria have non-obvious ordering or dependency relationships.

    Args:
        client: LLMClient (reserved for future LLM-based prioritisation).
    """

    # Priority ordering: boundary tests catch the most bugs
    _TYPE_PRIORITY: dict[str, str] = {
        "boundary": "high",
        "negative": "high",
        "ambiguity": "high",
        "happy_path": "medium",
        "exploratory": "low",
        "regression": "medium",
    }

    def __init__(self, client: Any | None = None) -> None:
        self._client = client  # reserved for future LLM reasoning

    async def __call__(self, state: PipelineState) -> dict[str, Any]:
        """Assign priority and detect prerequisites for each condition.

        Returns a dict with ``test_conditions`` and optionally
        ``errors`` set.
        """
        analysis = state.story_analysis
        if analysis is None or not analysis.criteria:
            return {
                "test_conditions": [],
                "errors": ["No criteria from ingestion — nothing to plan"],
            }

        conditions: list[Criterion] = []
        errors: list[str] = []

        for i, criterion in enumerate(analysis.criteria):
            # Assign priority from type
            priority = self._TYPE_PRIORITY.get(criterion.condition_type, "medium")

            # Detect prerequisites: if this isn't the first criterion and
            # the previous one isn't a navigation/setup step, assume dependency
            prerequisite_refs: list[str] = []
            if i > 0:
                # Simple heuristic: every test after the first depends on
                # the previous test's setup.  Future: LLM-based dependency
                # analysis for complex multi-page flows.
                prerequisite_refs = [analysis.criteria[i - 1].ref]

            # Flag ambiguities for human review
            needs_clarification = criterion.condition_type in ("ambiguity", "exploratory")
            clarification = ""
            if needs_clarification and not criterion.clarification_question:
                clarification = f"Condition '{criterion.description}' needs refinement before generation"

            conditions.append(
                Criterion(
                    ref=criterion.ref,
                    description=criterion.description,
                    condition_type=criterion.condition_type,
                    priority=priority,
                    source_text=criterion.source_text,
                    needs_clarification=needs_clarification,
                    clarification_question=clarification or criterion.clarification_question,
                    prerequisite_refs=prerequisite_refs,
                    # 16b D12 — carry provenance through the QA Director hop
                    source_refs=list(criterion.source_refs),
                    justification=criterion.justification,
                )
            )

        logger.info(
            "QA Director: %d conditions routed (%d need clarification)",
            len(conditions),
            sum(1 for c in conditions if c.needs_clarification),
        )

        return {"test_conditions": conditions, "errors": errors}
