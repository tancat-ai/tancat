"""Tests for src.run_history_cli — CLI ASCII table formatters."""

from __future__ import annotations

from pathlib import Path

from src.run_history_cli import (
    _format_run_date,
    _truncate,
    format_flaky_tests_table,
    format_full_history_summary,
    format_run_comparison,
    format_run_history_table,
)
from src.run_result_persistence import PersistedRunResult, PersistedTestResult, RunComparison

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_run(
    run_id: str = "2026-06-11T20:30:00",
    test_package: str = "test_demo",
    passed: int = 8,
    failed: int = 2,
    skipped: int = 1,
    errors: int = 0,
    duration: float = 12.5,
) -> PersistedRunResult:
    return PersistedRunResult(
        run_id=run_id,
        test_package=test_package,
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors,
        duration=duration,
        results=[],
    )


def _make_test_result(name: str, status: str) -> PersistedTestResult:
    return PersistedTestResult(name=name, status=status, duration=0.0, error_message="", file_path="")


# ── format_run_date ──────────────────────────────────────────────────────────


def test_format_run_date_full_iso() -> None:
    result = _format_run_date("2026-06-11T20:30:45")
    assert result == "2026-06-11 20:30"


def test_format_run_date_short_time() -> None:
    result = _format_run_date("2026-06-11T9")
    assert result == "2026-06-11 9"


def test_format_run_date_no_t() -> None:
    result = _format_run_date("20260611")
    assert result == "20260611"


# ── _truncate ────────────────────────────────────────────────────────────────


def test_truncate_noop() -> None:
    assert _truncate("short", 10) == "short"


def test_truncate_exact() -> None:
    assert _truncate("exact5", 6) == "exact5"


def test_truncate_long() -> None:
    result = _truncate("a very long test name here", 15)
    assert "…" in result
    assert len(result) <= 15


def test_truncate_min_width() -> None:
    result = _truncate("abc", 2)
    assert result == "ab"


# ── format_run_history_table ─────────────────────────────────────────────────


def test_format_run_history_table_empty() -> None:
    result = format_run_history_table([])
    assert "No run history available" in result


def test_format_run_history_table_single_run() -> None:
    runs = [_make_run()]
    result = format_run_history_table(runs)
    assert "=== Run History ===" in result
    assert "test_demo" in result
    assert "8" in result
    assert "72.7%" in result  # 8/11 = 72.7% (8 passed + 2 failed + 1 skipped)


def test_format_run_history_table_max_rows() -> None:
    runs = [_make_run(run_id=f"2026-06-{i:02d}T12:00:00") for i in range(1, 16)]
    result = format_run_history_table(runs, max_rows=5)
    # Count data lines (non-header, non-separator, non-empty)
    lines = [
        line
        for line in result.splitlines()
        if line.strip()
        and not line.startswith("===")
        and not line.startswith("─")
        and not line.startswith("---")
        and "Date" not in line
        and "last" not in line
    ]
    assert len(lines) == 5


def test_format_run_history_table_sorts_descending() -> None:
    runs = [
        _make_run(run_id="2026-06-01T12:00:00"),
        _make_run(run_id="2026-06-03T12:00:00"),
        _make_run(run_id="2026-06-02T12:00:00"),
    ]
    result = format_run_history_table(runs)
    lines = result.splitlines()
    # First data line should be 2026-06-03
    data_lines = [line for line in lines if line.strip() and "2026" in line]
    assert "2026-06-03" in data_lines[0]


# ── format_flaky_tests_table ─────────────────────────────────────────────────


def test_format_flaky_tests_table_empty() -> None:
    result = format_flaky_tests_table([])
    assert "(none)" in result


def test_format_flaky_tests_table_with_data() -> None:
    flaky = [
        ("test_login", {"passed": 8, "failed": 2}),
        ("test_checkout", {"passed": 5, "failed": 5}),
    ]
    result = format_flaky_tests_table(flaky)
    assert "test_login" in result
    assert "test_checkout" in result
    assert "20.0%" in result  # 2/10 = 20%
    assert "50.0%" in result  # 5/10 = 50%


# ── format_run_comparison ────────────────────────────────────────────────────


def test_format_run_comparison_none() -> None:
    result = format_run_comparison(None)
    assert "insufficient data" in result


def test_format_run_comparison_improved() -> None:
    older = _make_run(run_id="2026-06-10T12:00:00", passed=5, failed=5)
    newer = _make_run(run_id="2026-06-11T12:00:00", passed=8, failed=2)
    comparison = RunComparison(
        older=older,
        newer=newer,
        improved=["test_a"],
        regressed=[],
        new_failures=[],
    )
    result = format_run_comparison(comparison)
    assert "Improved" in result
    assert "test_a" in result
    assert "+" in result  # rate change is positive


def test_format_run_comparison_regressed() -> None:
    older = _make_run(run_id="2026-06-10T12:00:00", passed=8, failed=2)
    newer = _make_run(run_id="2026-06-11T12:00:00", passed=5, failed=5)
    comparison = RunComparison(
        older=older,
        newer=newer,
        improved=[],
        regressed=["test_b"],
        new_failures=["test_c"],
    )
    result = format_run_comparison(comparison)
    assert "Regressed" in result
    assert "test_b" in result
    assert "New Failures" in result
    assert "test_c" in result


# ── format_full_history_summary ──────────────────────────────────────────────


def test_format_full_history_summary_no_directory() -> None:
    """Should not crash when no directory is provided."""
    result = format_full_history_summary()
    assert "=== Run History ===" in result


def test_format_full_history_summary_with_directory(tmp_path: Path) -> None:
    """Should render even with an empty directory."""
    result = format_full_history_summary(directory=str(tmp_path))
    assert "=== Run History ===" in result
