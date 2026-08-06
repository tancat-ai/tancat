"""Unit tests for the run-comparison helpers."""

from __future__ import annotations

from src.run_result_persistence import PersistedRunResult
from src.ui.ui_run_comparison import _delta_icon, _run_label


def _run(**kwargs: object) -> PersistedRunResult:
    base: dict[str, object] = {
        "run_id": "2026-08-05T21:34:12.123",
        "results": [],
        "total": 14,
        "passed": 14,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
        "duration": 142.0,
    }
    base.update(kwargs)
    return PersistedRunResult(**base)  # type: ignore[arg-type]


def test_delta_icon_states() -> None:
    assert _delta_icon("passed", "passed") == "="
    assert _delta_icon("failed", "passed") == "⬆ fixed"
    assert _delta_icon("passed", "failed") == "⬇ regressed"
    assert _delta_icon("skipped", "passed") == "⬆ fixed"
    assert _delta_icon("failed", "skipped") == "↔ changed"
    assert _delta_icon("missing", "passed") == "⬆ fixed"


def test_run_label_formats_counts() -> None:
    label = _run_label(_run())
    assert "14✓" in label and "0✗" in label
    assert "08-05" in label


def test_run_label_handles_short_run_id() -> None:
    label = _run_label(_run(run_id="abc123", total=3, passed=2, failed=1))
    assert "2✓" in label and "1✗" in label


def test_merge_rerun_results_keeps_passing_tests() -> None:
    """A failed-only rerun must merge back into the previous full result."""
    from src.pipeline_run_service import merge_rerun_results
    from src.pytest_output_parser import RunResult, TestResult

    def tr(name: str, status: str) -> TestResult:
        return TestResult(name=name, status=status, duration=1.0, error_message="", file_path="")

    previous = RunResult(
        results=[tr("test_a", "passed"), tr("test_b", "failed"), tr("test_c", "passed")],
        total=3,
        passed=2,
        failed=1,
    )
    rerun = RunResult(
        results=[tr("test_b", "failed")],  # still fails on rerun
        total=1,
        passed=0,
        failed=1,
    )
    merged = merge_rerun_results(previous, rerun)
    assert len(merged.results) == 3, "passing tests must not be dropped"
    assert merged.results[0].name == "test_a" and merged.results[0].status == "passed"
    assert merged.results[1].name == "test_b" and merged.results[1].status == "failed"
    assert merged.results[2].name == "test_c" and merged.results[2].status == "passed"
    assert merged.total == 3 and merged.passed == 2 and merged.failed == 1


def test_merge_rerun_updates_fixed_test() -> None:
    from src.pipeline_run_service import merge_rerun_results
    from src.pytest_output_parser import RunResult, TestResult

    def tr(name: str, status: str) -> TestResult:
        return TestResult(name=name, status=status, duration=1.0, error_message="", file_path="")

    previous = RunResult(results=[tr("test_a", "failed")], total=1, failed=1)
    rerun = RunResult(results=[tr("test_a", "passed")], total=1, passed=1)
    merged = merge_rerun_results(previous, rerun)
    assert merged.results[0].status == "passed"
    assert merged.passed == 1 and merged.failed == 0
