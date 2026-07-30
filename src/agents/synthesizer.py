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

        Generates one skeleton fragment per condition (to prevent cumulative
        prerequisite chaining) and combines them into a single module.

        Returns a dict with ``test_code`` and ``errors`` for the graph state.
        """
        conditions = state.test_conditions
        if not conditions:
            return {
                "test_code": "",
                "errors": ["No test conditions to synthesise"],
                "retry_count": state.retry_count + 1,
            }

        if self._skeleton_graph is not None:
            try:
                code, errors_list = await self._generate_per_condition(
                    conditions=conditions,
                    user_story=state.user_story,
                    base_url=state.base_url,
                    additional_urls=state.additional_urls,
                )
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

    async def _generate_per_condition(
        self,
        *,
        conditions: list[Criterion],
        user_story: str,
        base_url: str,
        additional_urls: list[str],
    ) -> tuple[str, list[str]]:
        """Generate one skeleton fragment per condition and combine them.

        This prevents cumulative prerequisite chaining — each test function
        starts from scratch, matching the linear pipeline's behaviour.
        """
        import re

        from src.skeleton_parser import SkeletonParser

        assert self._skeleton_graph is not None
        parser = SkeletonParser()
        errors: list[str] = []
        fragments: list[str] = []

        for i, condition in enumerate(conditions):
            try:
                result = await self._skeleton_graph.run(
                    user_story=user_story,
                    conditions=condition.description,
                    target_urls=[base_url] + additional_urls,
                    expected_test_count=1,
                )
                fragment = result.get("skeleton_code", "")
                if result.get("validation_errors"):
                    errors.extend(result["validation_errors"])
            except Exception as e:
                logger.warning("Per-condition generation failed for %s: %s", condition.ref, e)
                fragment = f"# Failed: {condition.description}\n"
                errors.append(f"{condition.ref}: {e}")

            # Renumber test functions: replace test_01 / test_1 with test_{i+1:02d}
            fragment = re.sub(
                r"def test_\d+(_\w*)?",
                f"def test_{i + 1:02d}\\1",
                fragment,
            )
            # Update condition ref in pytest marks
            fragment = re.sub(
                r"condition_ref=['\"][^'\"]+['\"]",
                f'condition_ref="{condition.ref}"',
                fragment,
            )
            fragments.append(fragment)

        # Combine: strip imports from each fragment, collect test functions
        body_blocks: list[str] = []
        for fragment in fragments:
            body = self._strip_imports(fragment).strip()
            if body:
                body_blocks.append(body)

        combined_parts = [
            "from playwright.sync_api import Page, expect",
            "import pytest",
            "",
            "\n\n".join(body_blocks),
        ]
        combined = "\n".join(part for part in combined_parts if part != "")
        combined = parser.normalise_placeholder_actions(combined)

        return combined, errors

    @staticmethod
    def _strip_imports(code: str) -> str:
        """Return fragment body without import lines."""
        lines = code.splitlines()
        result: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                continue
            result.append(line)
        return "\n".join(result)

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
