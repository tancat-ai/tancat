"""Unit tests for src.run_history_chart — Plotly Figure factory.

Verifies chart builder handles empty state, single run, multiple runs,
pass-rate line overlay, flaky markers, and chronological ordering.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.pytest_output_parser import RunResult, TestResult
from src.run_history_chart import build_chart_from_db, build_run_history_chart
from src.run_result_persistence import (
    PersistedRunResult,
    PersistedTestResult,
    _get_db,
    _reset_db,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(
    run_id: str,
    passed: int = 0,
    failed: int = 0,
    skipped: int = 0,
    errors: int = 0,
    test_names: list[str] | None = None,
    test_statuses: list[str] | None = None,
) -> PersistedRunResult:
    """Build a minimal PersistedRunResult for testing."""
    results: list[PersistedTestResult] = []
    if test_names and test_statuses:
        for name, status in zip(test_names, test_statuses, strict=True):
            results.append(PersistedTestResult(name=name, status=status, duration=0.1, error_message="", file_path=""))
    return PersistedRunResult(
        run_id=run_id,
        test_package="test_pkg",
        results=results,
        total=passed + failed + skipped + errors,
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors,
        duration=1.0,
        raw_output="",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_chart_empty_runs() -> None:
    """Graceful empty state when no runs exist."""
    fig = build_run_history_chart([])
    # Should have the "No run history available" annotation
    assert len(list(fig.data)) == 0
    annotations_text = [getattr(a, "text", "") for a in fig.layout.annotations]
    assert "No run history available" in annotations_text


def test_chart_single_run() -> None:
    """Single bar renders correctly with pass rate."""
    run = _make_run("2026-06-11T21:00:00", passed=10, failed=2, skipped=1, errors=0)
    fig = build_run_history_chart([run])

    # 5 traces: 4 bars + 1 line
    assert len(list(fig.data)) == 5

    # Bar traces have correct counts
    pass_y = fig.data[0].y  # type: ignore[attr-defined]
    fail_y = fig.data[1].y  # type: ignore[attr-defined]
    skip_y = fig.data[2].y  # type: ignore[attr-defined]
    error_y = fig.data[3].y  # type: ignore[attr-defined]

    assert pass_y[0] == 10
    assert fail_y[0] == 2
    assert skip_y[0] == 1
    assert error_y[0] == 0

    # Pass rate line
    line_y = fig.data[4].y  # type: ignore[attr-defined]
    assert line_y[0] == round(10 / 12 * 100, 1)  # 83.3


def test_chart_multiple_runs() -> None:
    """Stacked bars with correct counts across multiple runs."""
    runs = [
        _make_run("2026-06-11T20:00:00", passed=14, failed=3, skipped=1, errors=0),
        _make_run("2026-06-11T21:00:00", passed=15, failed=2, skipped=1, errors=0),
    ]
    fig = build_run_history_chart(runs)

    assert len(list(fig.data)) == 5

    pass_y = fig.data[0].y  # type: ignore[attr-defined]
    fail_y = fig.data[1].y  # type: ignore[attr-defined]

    assert list(pass_y) == [14, 15]
    assert list(fail_y) == [3, 2]


def test_chart_pass_rate_line() -> None:
    """Line overlay matches computed pass rates."""
    runs = [
        _make_run("2026-06-11T20:00:00", passed=10, failed=0, skipped=0, errors=0),
        _make_run("2026-06-11T21:00:00", passed=5, failed=5, skipped=0, errors=0),
    ]
    fig = build_run_history_chart(runs)

    line_y = fig.data[4].y  # type: ignore[attr-defined]
    assert list(line_y) == [100.0, 50.0]


def test_chart_flaky_markers() -> None:
    """❗ markers appear on bars where flaky tests occurred."""
    # Test "test_a" passes in run 1, fails in run 2 → flaky
    runs = [
        _make_run(
            "2026-06-11T20:00:00",
            passed=1,
            failed=0,
            skipped=0,
            errors=0,
            test_names=["test_a"],
            test_statuses=["passed"],
        ),
        _make_run(
            "2026-06-11T21:00:00",
            passed=0,
            failed=1,
            skipped=0,
            errors=0,
            test_names=["test_a"],
            test_statuses=["failed"],
        ),
    ]
    fig = build_run_history_chart(runs, include_flaky_markers=True)

    # Both runs contain the flaky test, so both should have annotations
    annotations_text = [getattr(a, "text", "") for a in fig.layout.annotations]
    # Both runs have the flaky test
    assert annotations_text.count("❗") == 2


def test_chart_no_flaky_markers_when_disabled() -> None:
    """No ❗ markers when include_flaky_markers=False."""
    runs = [
        _make_run(
            "2026-06-11T20:00:00",
            passed=1,
            failed=0,
            skipped=0,
            errors=0,
            test_names=["test_a"],
            test_statuses=["passed"],
        ),
        _make_run(
            "2026-06-11T21:00:00",
            passed=0,
            failed=1,
            skipped=0,
            errors=0,
            test_names=["test_a"],
            test_statuses=["failed"],
        ),
    ]
    fig = build_run_history_chart(runs, include_flaky_markers=False)

    annotations_text = [getattr(a, "text", "") for a in fig.layout.annotations]
    assert "❗" not in annotations_text


def test_chart_chronological_order() -> None:
    """Runs are sorted oldest-first regardless of input order."""
    runs = [
        _make_run("2026-06-11T21:00:00", passed=15, failed=2, skipped=0, errors=0),
        _make_run("2026-06-11T20:00:00", passed=14, failed=3, skipped=0, errors=0),
    ]
    fig = build_run_history_chart(runs)

    pass_y = fig.data[0].y  # type: ignore[attr-defined]
    # After sorting: run at 20:00 (14 passed) comes first
    assert list(pass_y) == [14, 15]


def test_chart_single_run_no_flaky_markers() -> None:
    """Single run cannot have flaky tests (needs >= 2 runs)."""
    run = _make_run(
        "2026-06-11T21:00:00",
        passed=5,
        failed=0,
        skipped=0,
        errors=0,
        test_names=["test_a"],
        test_statuses=["passed"],
    )
    fig = build_run_history_chart([run], include_flaky_markers=True)

    annotations_text = [getattr(a, "text", "") for a in fig.layout.annotations]
    assert "❗" not in annotations_text


def test_chart_zero_total_pass_rate() -> None:
    """Pass rate is 0% when all tests are skipped (no pass/fail/error)."""
    run = _make_run("2026-06-11T21:00:00", passed=0, failed=0, skipped=5, errors=0)
    fig = build_run_history_chart([run])

    line_y = fig.data[4].y  # type: ignore[attr-defined]
    assert line_y[0] == 0.0


def test_chart_layout_has_secondary_y_axis() -> None:
    """Secondary y-axis is configured for pass rate percentage."""
    run = _make_run("2026-06-11T21:00:00", passed=10, failed=0, skipped=0, errors=0)
    fig = build_run_history_chart([run])

    # yaxis2 should overlay y and be on the right side
    assert fig.layout.yaxis2.overlaying == "y"  # type: ignore[attr-defined]
    assert fig.layout.yaxis2.side == "right"  # type: ignore[attr-defined]
    assert fig.layout.yaxis2.range == (0, 100)  # type: ignore[attr-defined]


def test_chart_barmode_is_stack() -> None:
    """Bars are stacked, not grouped."""
    run = _make_run("2026-06-11T21:00:00", passed=5, failed=1, skipped=0, errors=0)
    fig = build_run_history_chart([run])

    assert fig.layout.barmode == "stack"


# ---------------------------------------------------------------------------
# Tests for build_chart_from_db (Phase 4)
# ---------------------------------------------------------------------------


@pytest.fixture()
def _setup_db(tmp_path: Path) -> None:
    """Reset the singleton DB to a fresh temp database for isolation."""
    import src.run_result_persistence as mod
    from src.sqlite_persistence import SQLitePersistence

    _reset_db()
    mod._db = SQLitePersistence(db_path=tmp_path / "test_chart.sqlite")


def _persist_run_to_db(
    passed: int = 5,
    failed: int = 2,
    skipped: int = 1,
    errors: int = 0,
) -> str:
    """Persist a RunResult via the SQLite layer and return run_id."""
    results: list[TestResult] = []
    for i in range(passed):
        results.append(TestResult(f"test_pass_{i}", "passed", 0.1, "", "f.py"))
    for i in range(failed):
        results.append(TestResult(f"test_fail_{i}", "failed", 0.1, "err", "f.py"))
    for i in range(skipped):
        results.append(TestResult(f"test_skip_{i}", "skipped", 0.0, "", "f.py"))
    for i in range(errors):
        results.append(TestResult(f"test_error_{i}", "error", 0.1, "boom", "f.py"))

    run = RunResult(
        results=results,
        total=passed + failed + skipped + errors,
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors,
        duration=1.0,
        raw_output="",
    )
    db = _get_db()
    return db.persist_run_result(run)


def test_build_chart_from_db_empty(_setup_db: None) -> None:
    """Returns empty-state chart when DB has no runs."""
    fig = build_chart_from_db()
    assert len(list(fig.data)) == 0
    annotations_text = [getattr(a, "text", "") for a in fig.layout.annotations]
    assert "No run history available" in annotations_text


def test_build_chart_from_db_single_run(_setup_db: None) -> None:
    """Chart from DB with one run matches expected structure."""
    _persist_run_to_db(passed=10, failed=2, skipped=1, errors=0)
    fig = build_chart_from_db()

    # 5 traces: 4 bars + 1 line
    assert len(list(fig.data)) == 5

    pass_y = fig.data[0].y  # type: ignore[attr-defined]
    fail_y = fig.data[1].y  # type: ignore[attr-defined]
    assert pass_y[0] == 10
    assert fail_y[0] == 2


def test_build_chart_from_db_multiple_runs(_setup_db: None) -> None:
    """Chart from DB with multiple runs shows all data."""
    _persist_run_to_db(passed=14, failed=3, skipped=1, errors=0)
    _persist_run_to_db(passed=15, failed=2, skipped=1, errors=0)
    fig = build_chart_from_db()

    pass_y = fig.data[0].y  # type: ignore[attr-defined]
    fail_y = fig.data[1].y  # type: ignore[attr-defined]
    assert list(pass_y) == [14, 15]
    assert list(fail_y) == [3, 2]


def test_build_chart_from_db_pass_rate(_setup_db: None) -> None:
    """Pass rate line computed correctly from DB."""
    _persist_run_to_db(passed=10, failed=0, skipped=0, errors=0)
    _persist_run_to_db(passed=5, failed=5, skipped=0, errors=0)
    fig = build_chart_from_db()

    line_y = fig.data[4].y  # type: ignore[attr-defined]
    assert list(line_y) == [100.0, 50.0]


def test_build_chart_from_db_date_filter(_setup_db: None) -> None:
    """Date range filter limits chart data."""
    _persist_run_to_db(passed=10, failed=0, skipped=0, errors=0)
    id2 = _persist_run_to_db(passed=20, failed=0, skipped=0, errors=0)

    # Only include second run
    fig = build_chart_from_db(date_from=id2, date_to=id2)
    pass_y = fig.data[0].y  # type: ignore[attr-defined]
    assert list(pass_y) == [20]


def test_build_chart_from_db_layout(_setup_db: None) -> None:
    """Chart layout configured correctly (stacked bars, secondary axis)."""
    _persist_run_to_db(passed=5, failed=1, skipped=0, errors=0)
    fig = build_chart_from_db()

    assert fig.layout.barmode == "stack"
    assert fig.layout.yaxis2.overlaying == "y"  # type: ignore[attr-defined]
    assert fig.layout.yaxis2.side == "right"  # type: ignore[attr-defined]
