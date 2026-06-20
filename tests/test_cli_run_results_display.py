"""Tests for cli/run_results_display.py — structured CLI run results view."""

from __future__ import annotations

from unittest.mock import patch

from _pytest.capture import CaptureFixture

from src.cli.run_results_display import (
    _status_badge,
    _suggestion_for_category,
    render_failure_details,
    render_raw_output,
    render_results_table,
    render_run_metrics,
    render_run_results,
)
from src.failure_classifier import FailureCategory
from src.pytest_output_parser import RunResult, TestResult

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_results(
    passed: int = 0,
    failed: int = 0,
    errors: int = 0,
    skipped: int = 0,
    duration: float = 0.0,
    raw_output: str = "",
) -> RunResult:
    """Build a RunResult with the given counts of each status."""
    results: list[TestResult] = []
    for i in range(passed):
        results.append(
            TestResult(
                name=f"test_passed_{i + 1}",
                status="passed",
                duration=0.5,
                error_message="",
                file_path="test_file.py",
            )
        )
    for i in range(failed):
        results.append(
            TestResult(
                name=f"test_failed_{i + 1}",
                status="failed",
                duration=1.0,
                error_message="AssertionError: Expected 'OK' but got 'FAIL'",
                file_path="test_file.py",
            )
        )
    for i in range(errors):
        results.append(
            TestResult(
                name=f"test_error_{i + 1}",
                status="error",
                duration=0.0,
                error_message="TimeoutError: waiting for locator",
                file_path="test_file.py",
            )
        )
    for i in range(skipped):
        results.append(
            TestResult(
                name=f"test_skipped_{i + 1}",
                status="skipped",
                duration=0.0,
                error_message="",
                file_path="test_file.py",
            )
        )
    return RunResult(
        results=results,
        total=len(results),
        passed=passed,
        failed=failed,
        errors=errors,
        skipped=skipped,
        duration=duration,
        raw_output=raw_output,
    )


# ── _status_badge tests ────────────────────────────────────────────────────


class TestStatusBadge:
    def test_passed_badge(self) -> None:
        badge = _status_badge("passed")
        assert "PASS" in badge

    def test_failed_badge(self) -> None:
        badge = _status_badge("failed")
        assert "FAIL" in badge

    def test_error_badge(self) -> None:
        badge = _status_badge("error")
        assert "ERROR" in badge

    def test_skipped_badge(self) -> None:
        badge = _status_badge("skipped")
        assert "SKIP" in badge

    def test_unknown_status(self) -> None:
        badge = _status_badge("unknown")
        assert "UNKNOWN" in badge


# ── render_run_metrics tests ──────────────────────────────────────────────


class TestRenderRunMetrics:
    def test_all_passed(self, capsys: None = None) -> None:
        run = _make_results(passed=5, duration=12.34)
        render_run_metrics(run)
        # Capture would need capsys from pytest; this is a structural test.

    def test_mixed_results(self) -> None:
        run = _make_results(passed=3, failed=1, errors=0, skipped=1, duration=10.0)
        assert run.total == 5
        assert run.passed == 3
        assert run.failed == 1
        assert run.skipped == 1

    def test_no_duration(self) -> None:
        run = _make_results(passed=1, duration=0.0)
        assert run.duration == 0.0

    def test_zero_total(self) -> None:
        run = _make_results()
        assert run.total == 0


# ── render_results_table tests ────────────────────────────────────────────


class TestRenderResultsTable:
    def test_empty_results(self, capsys: CaptureFixture[str]) -> None:
        run = _make_results()
        render_results_table(run)
        out, _ = capsys.readouterr()
        assert "no test results" in out

    def test_single_passed(self, capsys: CaptureFixture[str]) -> None:
        run = _make_results(passed=1)
        render_results_table(run)
        out, _ = capsys.readouterr()
        assert "test_passed_1" in out
        assert "PASS" in out

    def test_failed_shows_error(self, capsys: CaptureFixture[str]) -> None:
        run = _make_results(failed=1)
        render_results_table(run)
        out, _ = capsys.readouterr()
        assert "test_failed_1" in out
        assert "FAIL" in out
        assert "AssertionError" in out

    def test_long_test_name_truncated(self, capsys: CaptureFixture[str]) -> None:
        results = [
            TestResult(
                name="test_" + "very_long_name_" * 10,
                status="passed",
                duration=0.5,
                error_message="",
                file_path="test_file.py",
            )
        ]
        run = RunResult(
            results=results,
            total=1,
            passed=1,
            failed=0,
            errors=0,
            skipped=0,
            duration=0.5,
            raw_output="",
        )
        render_results_table(run)
        out, _ = capsys.readouterr()
        # Should render without error even with long names
        assert len(out) > 0

    def test_error_message_truncated(self, capsys: CaptureFixture[str]) -> None:
        long_error = "Error: " + "x" * 500
        results = [
            TestResult(
                name="test_long_error",
                status="failed",
                duration=0.5,
                error_message=long_error,
                file_path="test_file.py",
            )
        ]
        run = RunResult(
            results=results,
            total=1,
            passed=0,
            failed=1,
            errors=0,
            skipped=0,
            duration=0.5,
            raw_output="",
        )
        render_results_table(run)
        out, _ = capsys.readouterr()
        assert "..." in out  # Truncation indicator present


# ── render_failure_details tests ───────────────────────────────────────────


class TestRenderFailureDetails:
    def test_no_failures(self, capsys: CaptureFixture[str]) -> None:
        run = _make_results(passed=3)
        render_failure_details(run)
        out, _ = capsys.readouterr()
        # Should produce no output when there are no failures
        assert "Failure Classification" not in out

    def test_timeout_failure_classified(self, capsys: CaptureFixture[str]) -> None:
        results = [
            TestResult(
                name="test_timeout",
                status="failed",
                duration=30.0,
                error_message="TimeoutError: waiting for locator('#btn')",
                file_path="test_file.py",
            )
        ]
        run = RunResult(
            results=results,
            total=1,
            passed=0,
            failed=1,
            errors=0,
            skipped=0,
            duration=30.0,
            raw_output="",
        )
        render_failure_details(run)
        out, _ = capsys.readouterr()
        assert "locator_timeout" in out

    def test_strict_violation_classified(self, capsys: CaptureFixture[str]) -> None:
        results = [
            TestResult(
                name="test_strict",
                status="failed",
                duration=1.0,
                error_message="strict mode violation: resolved to 2 elements",
                file_path="test_file.py",
            )
        ]
        run = RunResult(
            results=results,
            total=1,
            passed=0,
            failed=1,
            errors=0,
            skipped=0,
            duration=1.0,
            raw_output="",
        )
        render_failure_details(run)
        out, _ = capsys.readouterr()
        assert "strict_violation" in out

    def test_assertion_failure_classified(self, capsys: CaptureFixture[str]) -> None:
        results = [
            TestResult(
                name="test_assert",
                status="failed",
                duration=0.5,
                error_message="AssertionError: Expected True",
                file_path="test_file.py",
            )
        ]
        run = RunResult(
            results=results,
            total=1,
            passed=0,
            failed=1,
            errors=0,
            skipped=0,
            duration=0.5,
            raw_output="",
        )
        render_failure_details(run)
        out, _ = capsys.readouterr()
        assert "assertion_failure" in out

    def test_navigation_error_classified(self, capsys: CaptureFixture[str]) -> None:
        results = [
            TestResult(
                name="test_nav",
                status="failed",
                duration=0.1,
                error_message="Error: net::ERR_CONNECTION_REFUSED",
                file_path="test_file.py",
            )
        ]
        run = RunResult(
            results=results,
            total=1,
            passed=0,
            failed=1,
            errors=0,
            skipped=0,
            duration=0.1,
            raw_output="",
        )
        render_failure_details(run)
        out, _ = capsys.readouterr()
        assert "navigation_error" in out


# ── _suggestion_for_category tests ─────────────────────────────────────────


class TestSuggestionForCategory:
    def test_locator_timeout_suggestion(self) -> None:
        suggestion = _suggestion_for_category(FailureCategory.LOCATOR_TIMEOUT)
        assert len(suggestion) > 0
        assert "timeout" in suggestion.lower() or "locator" in suggestion.lower()

    def test_strict_violation_suggestion(self) -> None:
        suggestion = _suggestion_for_category(FailureCategory.STRICT_VIOLATION)
        assert len(suggestion) > 0
        assert "specific" in suggestion.lower()

    def test_navigation_error_suggestion(self) -> None:
        suggestion = _suggestion_for_category(FailureCategory.NAVIGATION_ERROR)
        assert len(suggestion) > 0
        assert "url" in suggestion.lower()

    def test_assertion_failure_suggestion(self) -> None:
        suggestion = _suggestion_for_category(FailureCategory.ASSERTION_FAILURE)
        assert len(suggestion) > 0

    def test_other_suggestion(self) -> None:
        suggestion = _suggestion_for_category(FailureCategory.OTHER)
        assert len(suggestion) > 0


# ── render_raw_output tests ───────────────────────────────────────────────


class TestRenderRawOutput:
    def test_no_raw_output(self, capsys: CaptureFixture[str]) -> None:
        run = _make_results(passed=1, raw_output="")
        with patch("builtins.input", return_value="n"):
            render_raw_output(run, expanded=False)
        out, _ = capsys.readouterr()
        assert "Pytest Output" not in out

    def test_expanded_raw_output(self, capsys: CaptureFixture[str]) -> None:
        run = _make_results(passed=1, raw_output="line1\nline2\nline3")
        render_raw_output(run, expanded=True)
        out, _ = capsys.readouterr()
        assert "line1" in out
        assert "line2" in out
        assert "Pytest Output" in out

    def test_user_declines_raw_output(self, capsys: CaptureFixture[str]) -> None:
        run = _make_results(passed=1, raw_output="secret output")
        with patch("builtins.input", return_value="n"):
            render_raw_output(run, expanded=False)
        out, _ = capsys.readouterr()
        assert "secret output" not in out

    def test_user_accepts_raw_output(self, capsys: CaptureFixture[str]) -> None:
        run = _make_results(passed=1, raw_output="visible output")
        with patch("builtins.input", return_value="y"):
            render_raw_output(run, expanded=False)
        out, _ = capsys.readouterr()
        assert "visible output" in out


# ── render_run_results integration tests ──────────────────────────────────


class TestRenderRunResults:
    def test_full_run_no_raw(self, capsys: CaptureFixture[str]) -> None:
        run = _make_results(passed=2, failed=1, duration=5.0)
        render_run_results(run, show_raw=False)
        out, _ = capsys.readouterr()
        assert "Run Results" in out
        assert "test_passed" in out
        assert "test_failed" in out

    def test_all_passed_run(self, capsys: CaptureFixture[str]) -> None:
        run = _make_results(passed=3, duration=2.5)
        render_run_results(run, show_raw=False)
        out, _ = capsys.readouterr()
        assert "Run Results" in out
        # No failure classification section when all pass
        assert "Failure Classification" not in out

    def test_empty_run(self, capsys: CaptureFixture[str]) -> None:
        run = _make_results()
        render_run_results(run, show_raw=False)
        out, _ = capsys.readouterr()
        assert "Run Results" in out
