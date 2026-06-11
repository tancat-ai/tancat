"""CLI renderer for run history — ASCII tables for terminals.

Provides formatters that convert run history data into readable ASCII tables
suitable for CLI display. Complements the Plotly-based chart builder in
run_history_chart.py for environments without GUI capabilities.
"""

from __future__ import annotations

from pathlib import Path

from src.run_result_persistence import PersistedRunResult, RunComparison

# ── Constants ────────────────────────────────────────────────────────────────

_HEADER = "=== Run History ==="
_FLAKY_HEADER_PREFIX = "=== Flaky Tests"
_COMPARISON_HEADER = "=== Last Run Comparison ==="

# ── Run history table ───────────────────────────────────────────────────────


def format_run_history_table(
    runs: list[PersistedRunResult],
    max_rows: int = 10,
) -> str:
    """Return an ASCII table summarising recent test runs.

    Args:
        runs: List of run results (most recent first preferred).
        max_rows: Maximum number of runs to display.

    Returns:
        Multi-line string containing the ASCII table.
    """
    if not runs:
        return f"{_HEADER}\nNo run history available\n"

    # Sort by run_id descending (most recent first)
    sorted_runs = sorted(runs, key=lambda r: r.run_id, reverse=True)
    displayed = sorted_runs[:max_rows]
    total_runs = len(sorted_runs)

    lines: list[str] = []
    lines.append(_HEADER)
    lines.append(f"last {len(displayed)} of {total_runs} runs")
    lines.append("")

    # Header row
    header = f"{'Date':<16} {'Package':<20} {'Pass':>5} {'Fail':>5} {'Skip':>5} {'Err':>5} {'Rate':>7}"
    lines.append(header)
    lines.append("-" * len(header))

    for run in displayed:
        date_str = _format_run_date(run.run_id)
        pkg = _truncate(run.test_package, 19)
        total = run.passed + run.failed + run.skipped + run.errors
        rate = (run.passed / total * 100) if total > 0 else 0.0
        line = (
            f"{date_str:<16} {pkg:<20} {run.passed:>5} {run.failed:>5} {run.skipped:>5} {run.errors:>5} {rate:>6.1f}%"
        )
        lines.append(line)

    lines.append("")
    return "\n".join(lines)


# ── Flaky tests table ───────────────────────────────────────────────────────


def format_flaky_tests_table(
    flaky_tests: list[tuple[str, dict[str, int]]],
) -> str:
    """Return an ASCII table of flaky tests with flakiness scores.

    Args:
        flaky_tests: List of (test_name, counts_dict) where counts_dict has
            keys: passed, failed, skipped, error.

    Returns:
        Multi-line string containing the flaky test table.
    """
    header = f"{_FLAKY_HEADER_PREFIX} ({len(flaky_tests)}) ===" if flaky_tests else "=== Flaky Tests ==="
    lines: list[str] = [header]

    if not flaky_tests:
        lines.append("(none)")
        lines.append("")
        return "\n".join(lines)

    lines.append("")
    table_header = f"{'Test Name':<35} {'Pass':>5} {'Fail':>5} {'Flaky%':>7}"
    lines.append(table_header)
    lines.append("-" * len(table_header))

    for test_name, counts in flaky_tests:
        name = _truncate(test_name, 34)
        passed = counts.get("passed", 0)
        failed = counts.get("failed", 0)
        total = passed + failed
        flaky_pct = (failed / total * 100) if total > 0 else 0.0
        line = f"{name:<35} {passed:>5} {failed:>5} {flaky_pct:>6.1f}%"
        lines.append(line)

    lines.append("")
    return "\n".join(lines)


# ── Run comparison ──────────────────────────────────────────────────────────


def format_run_comparison(
    comparison: RunComparison | None,
) -> str:
    """Return an ASCII summary comparing two consecutive runs.

    Args:
        comparison: RunComparison object with improved/regressed/new_failures lists.

    Returns:
        Multi-line string containing the comparison summary.
    """
    lines: list[str] = [_COMPARISON_HEADER]

    if comparison is None:
        lines.append("insufficient data (need 2+ runs)")
        lines.append("")
        return "\n".join(lines)

    older = comparison.older
    newer = comparison.newer

    older_total = older.passed + older.failed + older.skipped + older.errors
    newer_total = newer.passed + newer.failed + newer.skipped + newer.errors
    older_rate = (older.passed / older_total * 100) if older_total > 0 else 0.0
    newer_rate = (newer.passed / newer_total * 100) if newer_total > 0 else 0.0
    rate_change = newer_rate - older_rate

    sign = "+" if rate_change >= 0 else ""
    lines.append(f"Pass Rate: {older_rate:.1f}% → {newer_rate:.1f}% ({sign}{rate_change:.1f}%)")
    lines.append("")

    # Improved
    improved = comparison.improved
    if improved:
        lines.append(f"Improved ({len(improved)}):")
        for test in improved:
            lines.append(f"  ✓ {_truncate(test, 50)}")
    else:
        lines.append("Improved: (none)")
    lines.append("")

    # Regressed
    regressed = comparison.regressed
    if regressed:
        lines.append(f"Regressed ({len(regressed)}):")
        for test in regressed:
            lines.append(f"  ✗ {_truncate(test, 50)}")
    else:
        lines.append("Regressed: (none)")
    lines.append("")

    # New failures
    new_failures = comparison.new_failures
    if new_failures:
        lines.append(f"New Failures ({len(new_failures)}):")
        for test in new_failures:
            lines.append(f"  ⚠ {_truncate(test, 50)}")
    else:
        lines.append("New Failures: (none)")

    lines.append("")
    return "\n".join(lines)


# ── Full history summary ────────────────────────────────────────────────────


def format_full_history_summary(
    directory: str | None = None,
    max_rows: int = 10,
) -> str:
    """Return a complete history summary including run table, flaky tests, and comparison.

    Args:
        directory: Path to run results directory. If None, uses default.
        max_rows: Maximum number of runs to display in the table.

    Returns:
        Multi-line string combining all history sections.
    """
    from src.run_result_persistence import (
        compute_run_history,
        get_flaky_tests,
        load_all_run_results,
    )

    runs = load_all_run_results(directory=Path(directory) if directory else None)

    parts: list[str] = []
    parts.append(format_run_history_table(runs, max_rows=max_rows))

    if len(runs) >= 2:
        history = compute_run_history(runs)
        flaky = get_flaky_tests(runs)
        parts.append(format_flaky_tests_table(flaky))

        # Compare last two runs
        sorted_runs = sorted(runs, key=lambda r: r.run_id, reverse=True)
        comparison = history.get("last_comparison") if isinstance(history, dict) else None
        if comparison is None and len(sorted_runs) >= 2:
            from src.run_result_persistence import compare_runs

            comparison = compare_runs(sorted_runs[1], sorted_runs[0])
        parts.append(format_run_comparison(comparison))
    else:
        parts.append(format_flaky_tests_table([]))
        parts.append(format_run_comparison(None))

    return "\n".join(parts)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _format_run_date(run_id: str) -> str:
    """Format a run_id (ISO timestamp) as a readable date string.

    Args:
        run_id: ISO format timestamp (e.g., "2026-06-11T20:30:00").

    Returns:
        Formatted date string (e.g., "2026-06-11 20:30").
    """
    if "T" in run_id:
        date_part, time_part = run_id.split("T")
        # Truncate time to HH:MM
        time_short = time_part[:5] if len(time_part) >= 5 else time_part
        return f"{date_part} {time_short}"
    return run_id


def _truncate(text: str, max_width: int) -> str:
    """Truncate text to max_width, adding ellipsis if needed.

    Args:
        text: The text to truncate.
        max_width: Maximum width of the result.

    Returns:
        Truncated text with ellipsis if original was longer than max_width.
    """
    if len(text) <= max_width:
        return text
    if max_width <= 3:
        return text[:max_width]
    return text[: max_width - 3] + "…"
