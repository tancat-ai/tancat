"""Script Synthesizer Agent — test conditions → pytest skeleton code.

Wraps the existing ``SkeletonGraph`` (Planner → Generator → Validator)
for the skeleton-generation sub-phase.  For full pipeline generation
(scrape → resolve → code), this agent delegates to the existing
``TestOrchestrator`` as a tool.

Phase 1b: skeleton-only generation via SkeletonGraph.
Phase 1c: full pipeline integration (scrape + resolve + postprocess).
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.graph import SkeletonGraph
from src.agents.pipeline_state import Criterion, PipelineState

logger = logging.getLogger(__name__)


class ScriptSynthesizerAgent:
    """Generates pytest skeleton code from test conditions.

    Uses the existing ``SkeletonGraph`` for the Planner → Generator →
    Validator retry loop.  Accepts an optional ``LLMClient`` for the
    underlying agents; if omitted, the agent produces a placeholder
    skeleton.

    Args:
        client: LLMClient for LLM calls.  If None, produces placeholder output.
    """

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self._skeleton_graph: SkeletonGraph | None = None
        if client is not None:
            self._skeleton_graph = SkeletonGraph(client)

    async def __call__(self, state: PipelineState) -> dict[str, Any]:
        """Generate skeleton code from confirmed test conditions.

        Returns a dict with ``test_code`` and ``errors`` for the graph state.
        """
        conditions = state.test_conditions
        if not conditions:
            return {
                "test_code": "",
                "errors": ["No test conditions to synthesise"],
                "retry_count": state.retry_count + 1,
            }

        # Build conditions text and count for the skeleton graph
        conditions_text = "\n".join(f"{i + 1}. {c.description}" for i, c in enumerate(conditions))
        expected_count = len(conditions)

        if self._skeleton_graph is not None:
            try:
                result = await self._skeleton_graph.run(
                    user_story=state.user_story,
                    conditions=conditions_text,
                    target_urls=[state.base_url] + state.additional_urls,
                    expected_test_count=expected_count,
                )
                code = result.get("skeleton_code", "")
                errors_list: list[str] = result.get("validation_errors", [])
            except Exception as e:
                logger.warning("SkeletonGraph failed: %s — falling back to placeholder", e)
                code = self._placeholder_skeleton(conditions)
                errors_list = [f"Skeleton generation failed: {e}"]
        else:
            code = self._placeholder_skeleton(conditions)
            errors_list = []

        return {
            "test_code": code,
            "errors": errors_list,
            "retry_count": 0,
        }

    @staticmethod
    def _placeholder_skeleton(conditions: list[Criterion]) -> str:
        """Produce a minimal skeleton when no LLM client is available."""
        lines = [
            "# Generated test skeleton — Phase 1b (no LLM client)",
            "import pytest",
            "from playwright.sync_api import Page",
            "",
        ]
        for c in conditions:
            safe_name = c.ref.lower().replace(".", "_").replace("-", "_")
            lines.append(f"@pytest.mark.evidence(condition_ref='{c.ref}', story_ref='S01')")
            lines.append(f"def test_{safe_name}(page: Page, evidence_tracker):")
            lines.append(f"    # {c.description}")
            if c.condition_type == "happy_path":
                lines.append("    {{GOTO:home}}")
                lines.append(f"    {{{{ASSERT:{c.description}}}}}")
            else:
                lines.append(f"    pytest.skip('{c.condition_type}: {c.description} — TODO')")
            lines.append("")
        return "\n".join(lines)
