"""d-0050: a bare test count can never read as data.

The eval report records which source produced its test counts - ``junit`` (the
XML the runner received), ``log`` (pytest's final summary line only) or
``none``. These tests pin that the source travels with the count: into the CI
markdown summary, into the human report, through a baseline round-trip, and
that an older record without the field reads empty rather than failing.
"""

from __future__ import annotations

import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))

from ci_summary import build_summary  # noqa: E402
from eval_metrics import HarnessReport, StoryResult  # noqa: E402


def _report(tests_executed: int, source: str) -> HarnessReport:
    return HarnessReport(
        stories=[
            StoryResult(
                "eval-001",
                "saucedemo",
                3,
                3,
                tests_executed=tests_executed,
                tests_count_source=source,
            )
        ]
    )


class TestSummaryCarriesSource:
    def test_markdown_summary_names_the_source_beside_a_zero(self) -> None:
        """A zero with source 'none' must not read as a measured zero."""
        lines = build_summary(_report(0, "none"))
        executed = [ln for ln in lines if ln.startswith("| Tests executed |")]
        assert len(executed) == 1
        assert "0 (source: none)" in executed[0]

    def test_markdown_summary_names_junit(self) -> None:
        lines = build_summary(_report(4, "junit"))
        executed = [ln for ln in lines if ln.startswith("| Tests executed |")]
        assert "4 (source: junit)" in executed[0]

    def test_report_summary_names_the_source(self) -> None:
        summary = _report(0, "none").to_summary()
        assert "count source: none" in summary
        assert "count_source=none" in summary

    def test_report_source_is_mixed_when_stories_disagree(self) -> None:
        report = HarnessReport(
            stories=[
                StoryResult("eval-001", "saucedemo", 1, 1, tests_count_source="junit"),
                StoryResult("eval-002", "demoqa", 1, 1, tests_count_source="log"),
            ]
        )
        assert report.tests_count_source == "mixed (junit, log)"


class TestRoundTripKeepsSource:
    def test_roundtrip_keeps_the_source(self) -> None:
        data = _report(5, "junit").to_dict()
        restored = HarnessReport.from_dict(data)
        assert restored.stories[0].tests_count_source == "junit"
        assert restored.tests_count_source == "junit"

    def test_old_record_without_the_field_reads_empty(self) -> None:
        """A baseline written before the field existed loads, and says absent."""
        old = {
            "stories": [
                {
                    "story_id": "eval-001",
                    "site": "saucedemo",
                    "total_criteria": 1,
                    "criteria_with_skeletons": 1,
                    "resolutions": [],
                    "tests_executed": 0,
                    "tests_passed": 0,
                }
            ]
        }
        restored = HarnessReport.from_dict(old)
        assert restored.stories[0].tests_count_source == ""
        # Not an error, and never silently a measured zero: the aggregate names
        # the absence.
        assert restored.tests_count_source == "none"
        assert "0 (source: none)" in "\n".join(build_summary(restored))
