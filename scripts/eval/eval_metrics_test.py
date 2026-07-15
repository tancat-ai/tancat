"""Tests for eval_metrics.py — pure metric computation."""

import pytest
from eval_metrics import (
    BaselineDelta,
    HarnessReport,
    ResolutionResult,
    StoryResult,
    compute_deltas,
    deltas_to_report,
)

# ---------------------------------------------------------------------------
# ResolutionResult
# ---------------------------------------------------------------------------


class TestResolutionResult:
    def test_matched_true(self) -> None:
        r = ResolutionResult(
            action="FILL",
            description="username",
            expected_locator="#user-name",
            tolerance_selectors=[],
            generated_locator="#user-name",
            matched=True,
        )
        assert r.matched is True

    def test_matched_false_unresolved(self) -> None:
        r = ResolutionResult(
            action="FILL",
            description="username",
            expected_locator="#user-name",
            tolerance_selectors=[],
            generated_locator=None,
            matched=False,
        )
        assert r.matched is False


# ---------------------------------------------------------------------------
# HarnessReport properties
# ---------------------------------------------------------------------------


class TestHarnessReportProperties:
    def _report(self, stories: list[StoryResult]) -> HarnessReport:
        return HarnessReport(stories=stories)

    def test_empty_report(self) -> None:
        r = HarnessReport()
        assert r.total_placeholders == 0
        assert r.resolution_accuracy() == 0.0
        assert r.test_pass_rate() == 0.0
        assert r.false_positive_rate() == 0.0
        assert r.skeleton_completeness() == 0.0
        assert r.mean_generation_duration() == 0.0

    def test_total_placeholders(self) -> None:
        story = StoryResult(
            story_id="s1",
            site="test",
            total_criteria=3,
            criteria_with_skeletons=3,
            resolutions=[
                ResolutionResult("FILL", "x", "#a", [], "#a", True),
                ResolutionResult("CLICK", "y", "#b", [], "#b", True),
            ],
        )
        r = self._report([story])
        assert r.total_placeholders == 2
        assert r.correct_resolutions == 2
        assert r.resolution_accuracy() == 100.0

    def test_resolution_accuracy_partial(self) -> None:
        story = StoryResult(
            story_id="s1",
            site="test",
            total_criteria=3,
            criteria_with_skeletons=3,
            resolutions=[
                ResolutionResult("FILL", "x", "#a", [], "#a", True),
                ResolutionResult("FILL", "y", "#b", [], "#wrong", False),
                ResolutionResult("CLICK", "z", "#c", [], "#c", True),
            ],
        )
        r = self._report([story])
        assert r.total_placeholders == 3
        assert r.correct_resolutions == 2
        assert r.resolution_accuracy() == pytest.approx(66.6667)

    def test_test_pass_rate(self) -> None:
        story = StoryResult(
            story_id="s1",
            site="test",
            total_criteria=4,
            criteria_with_skeletons=4,
            tests_executed=4,
            tests_passed=3,
        )
        r = self._report([story])
        assert r.test_pass_rate() == pytest.approx(75.0)

    def test_false_positive_rate(self) -> None:
        story = StoryResult(
            story_id="s1",
            site="test",
            total_criteria=4,
            criteria_with_skeletons=4,
            tests_executed=4,
            tests_passed=3,
            tests_false_positive=1,
        )
        r = self._report([story])
        assert r.false_positive_rate() == pytest.approx(25.0)

    def test_skeleton_completeness(self) -> None:
        story = StoryResult(
            story_id="s1",
            site="test",
            total_criteria=6,
            criteria_with_skeletons=5,
        )
        r = self._report([story])
        assert r.skeleton_completeness() == pytest.approx(83.3333)

    def test_mean_generation_duration(self) -> None:
        stories = [
            StoryResult("s1", "x", 3, 3, generation_duration_s=100.0),
            StoryResult("s2", "x", 3, 3, generation_duration_s=200.0),
        ]
        r = self._report(stories)
        assert r.mean_generation_duration() == 150.0

    def test_aggregates_multiple_stories(self) -> None:
        stories = [
            StoryResult(
                "s1",
                "x",
                3,
                3,
                resolutions=[ResolutionResult("FILL", "a", "#x", [], "#x", True)],
                tests_executed=3,
                tests_passed=2,
                tests_false_positive=0,
            ),
            StoryResult(
                "s2",
                "y",
                5,
                4,
                resolutions=[ResolutionResult("CLICK", "b", "#y", [], "#wrong", False)],
                tests_executed=5,
                tests_passed=4,
                tests_false_positive=1,
            ),
        ]
        r = self._report(stories)
        assert r.total_placeholders == 2
        assert r.correct_resolutions == 1
        assert r.resolution_accuracy() == pytest.approx(50.0)
        assert r.total_tests_executed == 8
        assert r.total_tests_passed == 6
        assert r.total_false_positives == 1
        assert r.test_pass_rate() == pytest.approx(75.0)
        assert r.false_positive_rate() == pytest.approx(12.5)


# ---------------------------------------------------------------------------
# Baseline comparison
# ---------------------------------------------------------------------------


class TestBaselineComparison:
    def test_deltas_computed(self) -> None:
        baseline = HarnessReport(
            stories=[
                StoryResult(
                    "s1",
                    "x",
                    4,
                    4,
                    resolutions=[
                        ResolutionResult("FILL", "a", "#x", [], "#x", True),
                        ResolutionResult("FILL", "b", "#y", [], "#wrong", False),
                    ],
                    tests_executed=4,
                    tests_passed=3,
                    tests_false_positive=0,
                ),
            ]
        )
        current = HarnessReport(
            stories=[
                StoryResult(
                    "s1",
                    "x",
                    4,
                    4,
                    resolutions=[
                        ResolutionResult("FILL", "a", "#x", [], "#x", True),
                        ResolutionResult("FILL", "b", "#y", [], "#y", True),
                    ],
                    tests_executed=4,
                    tests_passed=4,
                    tests_false_positive=0,
                ),
            ]
        )
        deltas = compute_deltas(baseline, current)
        assert len(deltas) == 4
        # Resolution accuracy improved 50 -> 100
        assert deltas[0].metric == "Resolution accuracy"
        assert deltas[0].delta == 50.0
        # Test pass rate improved 75 -> 100
        assert deltas[1].delta == 25.0

    def test_false_positive_delta_inverted(self) -> None:
        """Lower FP rate is better, so delta sign is inverted."""
        baseline = HarnessReport(
            stories=[
                StoryResult(
                    "s1",
                    "x",
                    2,
                    2,
                    tests_executed=4,
                    tests_passed=3,
                    tests_false_positive=2,
                ),
            ]
        )
        current = HarnessReport(
            stories=[
                StoryResult(
                    "s1",
                    "x",
                    2,
                    2,
                    tests_executed=4,
                    tests_passed=3,
                    tests_false_positive=0,
                ),
            ]
        )
        deltas = compute_deltas(baseline, current)
        fp_delta = deltas[2]
        assert fp_delta.metric == "False positive rate"
        assert fp_delta.delta == 50.0  # positive = improvement

    def test_formatted_output(self) -> None:
        d = BaselineDelta("Test", 70.0, 80.0, 10.0)
        assert "+10.0pp" in d.formatted()
        assert "[+]" in d.formatted()

    def test_formatted_negative(self) -> None:
        d = BaselineDelta("Test", 80.0, 70.0, -10.0)
        assert "-10.0pp" in d.formatted()
        assert "[-]" in d.formatted()

    def test_formatted_neutral(self) -> None:
        d = BaselineDelta("Test", 80.0, 80.0, 0.0)
        assert "[=]" in d.formatted()

    def test_deltas_to_report(self) -> None:
        deltas = [
            BaselineDelta("Resolution accuracy", 70.0, 80.0, 10.0),
        ]
        report = deltas_to_report(deltas)
        assert "BASELINE COMPARISON" in report
        assert "Resolution accuracy" in report


# ---------------------------------------------------------------------------
# HarnessReport.to_summary
# ---------------------------------------------------------------------------


class TestSummaryOutput:
    def test_summary_contains_metrics(self) -> None:
        story = StoryResult(
            "eval-001",
            "saucedemo",
            6,
            6,
            resolutions=[ResolutionResult("FILL", "x", "#a", [], "#a", True)],
            tests_executed=6,
            tests_passed=5,
            tests_false_positive=0,
            generation_duration_s=200.0,
        )
        r = HarnessReport(stories=[story])
        summary = r.to_summary()
        assert "EVALUATION HARNESS REPORT" in summary
        assert "eval-001" in summary
        assert "saucedemo" in summary
        assert "Resolution accuracy:" in summary
        assert "PER-STORY BREAKDOWN" in summary


class TestSerialization:
    def test_roundtrip(self) -> None:
        story = StoryResult(
            "eval-001",
            "saucedemo",
            6,
            6,
            resolutions=[
                ResolutionResult("FILL", "x", "#a", ["#b"], "#a", True),
                ResolutionResult("CLICK", "y", "#c", [], "#wrong", False),
            ],
            tests_executed=6,
            tests_passed=5,
            tests_false_positive=1,
            generation_duration_s=200.0,
        )
        r = HarnessReport(stories=[story])
        data = r.to_dict()
        assert "stories" in data
        assert len(data["stories"]) == 1

        r2 = HarnessReport.from_dict(data)
        assert len(r2.stories) == 1
        assert r2.stories[0].story_id == "eval-001"
        assert r2.resolution_accuracy() == pytest.approx(50.0)
        assert r2.test_pass_rate() == pytest.approx(83.3333)
        assert r2.false_positive_rate() == pytest.approx(16.6667, abs=0.1)

    def test_from_dict_empty(self) -> None:
        r = HarnessReport.from_dict({"stories": []})
        assert len(r.stories) == 0
        assert r.resolution_accuracy() == 0.0
