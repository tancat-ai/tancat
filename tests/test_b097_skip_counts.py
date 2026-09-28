"""B-097: surface resolved/unresolved counts per test when a test is skipped.

A test with any unresolved placeholder keeps its single per-test ``pytest.skip()``
(a test that was never fully verified must not report green), but the skip must
not hide the placeholders that DID resolve. These tests pin the counts at the
emit chokepoint, in the pipeline result, in the written artifact, and in the
eval harness's ``StoryResult``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from src.orchestrator import PipelineRunResult
from src.pipeline_models import PlaceholderUse, TestJourney, TestResolutionCounts, TestStep
from src.pipeline_writer import PipelineArtifactWriter
from src.skip_manager import build_test_resolution_counts, insert_consolidated_skips

_EVAL_DIR = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))

from eval_metrics import HarnessReport, StoryResult  # noqa: E402
from golden_validator import extract_test_resolution_counts, validate_story  # noqa: E402


def _placeholder(action: str, description: str, line_number: int) -> PlaceholderUse:
    token = f"{{{{{action}:{description}}}}}"
    return PlaceholderUse(
        action=action,
        description=description,
        token=token,
        line_number=line_number,
        raw_line=token,
    )


def _journey(test_name: str, descriptions: list[tuple[str, str]]) -> TestJourney:
    steps = [
        TestStep(
            line_number=index + 2,
            raw_line="x",
            placeholders=[_placeholder(action, description, index + 2)],
        )
        for index, (action, description) in enumerate(descriptions)
    ]
    return TestJourney(test_name=test_name, start_line=1, end_line=len(steps) + 2, steps=steps)


# ---------------------------------------------------------------------------
# Emit chokepoint
# ---------------------------------------------------------------------------


class TestBuildCounts:
    def test_one_unresolved_and_n_resolved_reports_both(self) -> None:
        """The B-097 case: 1 unresolved + 3 resolved -> both counts, total 4."""
        journey = _journey(
            "test_01_partial",
            [("CLICK", "a"), ("FILL", "b"), ("CLICK", "c"), ("ASSERT", "d")],
        )

        counts = build_test_resolution_counts([journey], {"test_01_partial": ["d"]})

        assert len(counts) == 1
        assert counts[0].test_name == "test_01_partial"
        assert counts[0].resolved == 3
        assert counts[0].unresolved == 1
        assert counts[0].total == 4
        assert counts[0].to_dict() == {
            "test_name": "test_01_partial",
            "resolved": 3,
            "unresolved": 1,
            "total": 4,
        }

    def test_fully_resolved_test_has_zero_unresolved(self) -> None:
        journey = _journey("test_01", [("CLICK", "a"), ("CLICK", "a")])
        counts = build_test_resolution_counts([journey], {})
        assert counts[0].resolved == 2
        assert counts[0].unresolved == 0

    def test_duplicate_unresolved_description_counts_once(self) -> None:
        """The skip reason dedupes descriptions; the count must match it."""
        journey = _journey("test_01", [("CLICK", "a"), ("CLICK", "a"), ("CLICK", "b")])
        counts = build_test_resolution_counts([journey], {"test_01": ["a", "a"]})
        assert counts[0].unresolved == 1
        assert counts[0].resolved == 2
        assert counts[0].total == 3


class TestSkipMessage:
    def test_skip_message_names_both_counts(self) -> None:
        journey = _journey("test_01_partial", [("CLICK", "a"), ("ASSERT", "missing")])
        counts = TestResolutionCounts(test_name="test_01_partial", resolved=1, unresolved=1)
        lines = ["def test_01_partial(page):", "    pass"]

        emitted = insert_consolidated_skips(
            lines,
            [journey],
            {"test_01_partial": ["missing"]},
            lines,
            test_counts={"test_01_partial": counts},
        )

        skip_lines = [line for line in emitted if "pytest.skip(" in line]
        assert len(skip_lines) == 1
        assert "unresolved placeholders for: 'missing'" in skip_lines[0]
        assert ". 1 of 2 placeholders resolved" in skip_lines[0]

    def test_no_counts_keeps_the_old_message(self) -> None:
        """Backward compatible: no counts passed -> no suffix appended."""
        journey = _journey("test_01", [("ASSERT", "missing")])
        lines = ["def test_01(page):", "    pass"]

        emitted = insert_consolidated_skips(
            lines,
            [journey],
            {"test_01": ["missing"]},
            lines,
        )

        skip_line = next(line for line in emitted if "pytest.skip(" in line)
        assert "'missing'" in skip_line
        assert "placeholders resolved" not in skip_line


# ---------------------------------------------------------------------------
# Product surface: PipelineRunResult + written artifact
# ---------------------------------------------------------------------------


class TestPipelineSurface:
    def test_run_result_carries_counts(self) -> None:
        result = PipelineRunResult(test_resolution_counts=[TestResolutionCounts("test_01", resolved=3, unresolved=1)])
        assert result.test_resolution_counts[0].resolved == 3
        assert result.test_resolution_counts[0].unresolved == 1

    def test_coverage_summary_carries_counts(self) -> None:
        result = PipelineRunResult(
            journeys=[_journey("test_01_partial", [("CLICK", "a")])],
            test_resolution_counts=[TestResolutionCounts("test_01_partial", resolved=3, unresolved=1)],
        )
        summary = PipelineArtifactWriter._build_coverage_summary_dict(result)
        assert summary["test_resolution_counts"] == [
            {
                "test_name": "test_01_partial",
                "resolved": 3,
                "unresolved": 1,
                "total": 4,
            }
        ]


# ---------------------------------------------------------------------------
# Report surface: eval-harness StoryResult
# ---------------------------------------------------------------------------

_SKIPPED_CODE = (
    "def test_01_login(page):\n"
    "    pytest.skip(\"Skipping: unresolved placeholders for: 'a'; 'b'. "
    '3 of 5 placeholders resolved")\n'
    "\n"
    "def test_02_clean(page):\n"
    "    pass\n"
)


class TestReportSurface:
    def test_extract_counts_from_emitted_skip(self) -> None:
        counts = extract_test_resolution_counts(_SKIPPED_CODE)
        assert counts == [{"test_name": "test_01_login", "resolved": 3, "unresolved": 2, "total": 5}]

    def test_validate_story_populates_story_result(self) -> None:
        golden: dict[str, Any] = {
            "id": "eval-997",
            "site": "test",
            "base_url": "https://example.com",
            "conditions": ["1. Login"],
            "golden_resolutions": [
                {
                    "criterion_index": 0,
                    "placeholders": [
                        {
                            "action": "CLICK",
                            "description": "login button",
                            "expected_locator": "#login",
                            "tolerance_selectors": [],
                        }
                    ],
                }
            ],
        }
        story = validate_story(_SKIPPED_CODE, golden)
        assert story.test_resolution_counts == [
            {"test_name": "test_01_login", "resolved": 3, "unresolved": 2, "total": 5}
        ]

    def test_summary_renders_the_counts(self) -> None:
        story = StoryResult(
            story_id="eval-997",
            site="test",
            total_criteria=1,
            criteria_with_skeletons=2,
            tests_executed=2,
            tests_passed=1,
            test_resolution_counts=[{"test_name": "test_01_login", "resolved": 3, "unresolved": 2, "total": 5}],
        )
        rendered = HarnessReport(stories=[story]).to_summary()
        assert "test_01_login 3/5 resolved" in rendered


# ---------------------------------------------------------------------------
# End-to-end: the real resolution path emits and records the counts
# ---------------------------------------------------------------------------


class TestEndToEndEmit:
    def test_partial_test_reports_both_counts(self) -> None:
        """One unresolved + one resolved placeholder through the real emitter."""
        import asyncio

        from src.pipeline_models import PageRequirement
        from src.placeholder_orchestrator import PlaceholderOrchestrator

        skeleton = (
            "def test_checkout(page):\n    page.click('{{CLICK:Buy Now}}')\n    page.click('{{CLICK:Missing Thing}}')\n"
        )
        scraped_data = {
            "https://example.com/": [
                {"selector": "#buy-now", "tag": "button", "role": "button", "text": "Buy Now"},
            ]
        }
        journey = TestJourney(
            test_name="test_checkout",
            start_line=1,
            end_line=3,
            steps=[
                TestStep(
                    line_number=2,
                    raw_line="page.click('{{CLICK:Buy Now}}')",
                    placeholders=[_placeholder("CLICK", "Buy Now", 2)],
                ),
                TestStep(
                    line_number=3,
                    raw_line="page.click('{{CLICK:Missing Thing}}')",
                    placeholders=[_placeholder("CLICK", "Missing Thing", 3)],
                ),
            ],
        )
        orch = PlaceholderOrchestrator(starting_url="https://example.com/")

        async def run() -> str:
            return await orch._replace_placeholders_sequentially(
                skeleton_code=skeleton,
                journeys=[journey],
                page_requirements=[PageRequirement(keyword="home")],
                seed_urls=["https://example.com/"],
                scraped_data=scraped_data,
                scraped_errors={},
            )

        emitted = asyncio.run(run())

        counts = orch.test_resolution_counts
        assert len(counts) == 1
        assert (counts[0].resolved, counts[0].unresolved, counts[0].total) == (1, 1, 2)
        skip_line = next(line for line in emitted.splitlines() if "pytest.skip(" in line)
        assert ". 1 of 2 placeholders resolved" in skip_line
