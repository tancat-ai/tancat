"""Persist run results to disk for historical comparison and flaky-test tracking.

Provides SQLite-backed persistence for ``RunResult`` objects so that consecutive
pytest runs can be compared over time.

No Streamlit imports — fully unit-testable in isolation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.pytest_output_parser import RunResult

if TYPE_CHECKING:
    from src.sqlite_persistence import SQLitePersistence

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PersistedTestResult:
    """Serializable mirror of :class:`TestResult`."""

    name: str
    status: str
    duration: float
    error_message: str
    file_path: str


@dataclass
class PersistedRunResult:
    """Serializable mirror of :class:`RunResult` with persistence metadata."""

    run_id: str = ""  # ISO-8601 timestamp, unique per file
    test_package: str = ""  # path to the test package that was run
    results: list[PersistedTestResult] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration: float = 0.0
    raw_output: str = ""

    # Computed on load (not stored on disk)
    flaky_tests: list[str] = field(default_factory=list)


@dataclass
class RunHistory:
    """Aggregated statistics across multiple persisted runs."""

    total_runs: int = 0
    total_passed: int = 0
    total_failed: int = 0
    total_skipped: int = 0
    total_errors: int = 0
    test_flakiness: dict[str, dict[str, int]] = field(default_factory=dict)
    # test_flakiness maps test_name -> {"passed": N, "failed": N, "skipped": N, "error": N}


# ---------------------------------------------------------------------------
# SQLite singleton (lazy initialization to avoid circular imports)
# ---------------------------------------------------------------------------

_db: SQLitePersistence | None = None


def _get_db() -> SQLitePersistence:
    """Return the global SQLitePersistence singleton (lazy init)."""
    global _db
    if _db is None:
        from src.sqlite_persistence import SQLitePersistence

        _db = SQLitePersistence()
    return _db


def _reset_db() -> None:
    """Reset the global DB singleton. Used in tests for isolation."""
    global _db
    if _db is not None:
        _db.close()
        _db = None


# ---------------------------------------------------------------------------
# Public API — delegates to SQLite backend
# ---------------------------------------------------------------------------


def persist_run_result(
    run_result: RunResult,
    test_package: str = "",
    directory: Path | None = None,
) -> Path:
    """Write a single ``RunResult`` to the SQLite database.

    Args:
        run_result: Parsed pytest result to persist.
        test_package: Path or identifier of the test package that was run.
        directory: Unused (kept for backwards compatibility).

    Returns:
        Path to the SQLite database file.
    """
    _get_db().persist_run_result(run_result, test_package)
    return _get_db().db_path


def load_run_result(filepath: Path) -> PersistedRunResult:
    """Load a single persisted run result from SQLite.

    Extracts the run_id from the filepath stem.

    Args:
        filepath: A Path whose stem is the run_id (ISO-8601 timestamp).

    Returns:
        The persisted run result.

    Raises:
        ValueError: If the run is not found in the database.
    """
    run_id = filepath.stem
    result = _get_db().load_run_result(run_id)
    if result is None:
        raise ValueError(f"Run not found: {run_id}")
    return result


def list_run_results(directory: Path | None = None) -> list[str]:
    """Return sorted list of run IDs (oldest first).

    Args:
        directory: Unused (kept for backwards compatibility).

    Returns:
        List of ISO-8601 run ID strings.
    """
    return _get_db().list_run_results()


def load_all_run_results(directory: Path | None = None) -> list[PersistedRunResult]:
    """Load every persisted run result (oldest first).

    Args:
        directory: Unused (kept for backwards compatibility).

    Returns:
        List of persisted run results.
    """
    return _get_db().load_all_run_results()


# ---------------------------------------------------------------------------
# History & flakiness analysis
# ---------------------------------------------------------------------------


def compute_run_history(
    runs: list[PersistedRunResult] | None = None,
    directory: Path | None = None,
) -> RunHistory:
    """Aggregate statistics across all persisted runs.

    Args:
        runs: Explicit list of runs to analyse. When *None*, loads all
              persisted runs from the SQLite database.
        directory: Unused (kept for backwards compatibility).
    """
    if runs is None:
        return _get_db().compute_run_history()

    # If explicit runs provided, compute in-memory (for backwards compat)
    history = RunHistory()
    history.total_runs = len(runs)

    for run in runs:
        history.total_passed += run.passed
        history.total_failed += run.failed
        history.total_skipped += run.skipped
        history.total_errors += run.errors

        for result in run.results:
            name = result.name
            if name not in history.test_flakiness:
                history.test_flakiness[name] = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
            bucket = history.test_flakiness[name]
            if result.status == "passed":
                bucket["passed"] += 1
            elif result.status == "failed":
                bucket["failed"] += 1
            elif result.status == "skipped":
                bucket["skipped"] += 1
            else:
                bucket["error"] += 1

    return history


def get_flaky_tests(
    runs: list[PersistedRunResult] | None = None,
    directory: Path | None = None,
    min_runs: int = 2,
) -> list[tuple[str, dict[str, int]]]:
    """Return tests that have inconsistent results across runs.

    A test is considered *flaky* when it has both passes and failures
    (or errors) across at least ``min_runs`` observations.

    Args:
        runs: Explicit list of runs. When *None*, uses SQLite database.
        directory: Unused (kept for backwards compatibility).
        min_runs: Minimum number of observations to consider a test flaky.

    Returns:
        List of ``(test_name, counts)`` tuples sorted by flakiness score
        (ratio of minority outcome to total runs, descending).
    """
    if runs is None:
        return _get_db().get_flaky_tests(min_runs)

    # In-memory fallback for explicit runs
    history = compute_run_history(runs, directory)

    flaky: list[tuple[str, dict[str, int]]] = []
    for name, counts in history.test_flakiness.items():
        total = counts["passed"] + counts["failed"] + counts["error"]
        if total < min_runs:
            continue
        has_pass = counts["passed"] > 0
        has_fail = counts["failed"] > 0 or counts["error"] > 0
        if has_pass and has_fail:
            flaky.append((name, counts))

    # Sort by flakiness ratio (minority / total), descending
    def _flakiness_score(item: tuple[str, dict[str, int]]) -> float:
        _name, counts = item
        total = counts["passed"] + counts["failed"] + counts["error"]
        if total == 0:
            return 0.0
        minority = min(counts["passed"], counts["failed"] + counts["error"])
        return minority / total

    flaky.sort(key=_flakiness_score, reverse=True)
    return flaky


# ---------------------------------------------------------------------------
# Convenience: compare two consecutive runs
# ---------------------------------------------------------------------------


@dataclass
class RunComparison:
    """Side-by-side comparison of two runs."""

    older: PersistedRunResult
    newer: PersistedRunResult
    improved: list[str]  # tests that went from fail/error to pass
    regressed: list[str]  # tests that went from pass to fail/error
    new_failures: list[str]  # tests that didn't exist in older run but fail in newer


def compare_runs(
    older: PersistedRunResult,
    newer: PersistedRunResult,
) -> RunComparison:
    """Compare two runs and classify per-test changes."""

    older_status: dict[str, str] = {r.name: r.status for r in older.results}
    newer_status: dict[str, str] = {r.name: r.status for r in newer.results}

    all_names = set(older_status) | set(newer_status)

    improved: list[str] = []
    regressed: list[str] = []
    new_failures: list[str] = []

    for name in all_names:
        old = older_status.get(name, "absent")
        new = newer_status.get(name, "absent")

        if old in ("failed", "error") and new == "passed":
            improved.append(name)
        elif old == "passed" and new in ("failed", "error"):
            regressed.append(name)
        elif old == "absent" and new in ("failed", "error"):
            new_failures.append(name)

    return RunComparison(
        older=older,
        newer=newer,
        improved=sorted(improved),
        regressed=sorted(regressed),
        new_failures=sorted(new_failures),
    )


def compare_latest_runs(
    n: int = 2,
    directory: Path | None = None,
) -> RunComparison | None:
    """Compare the latest ``n`` runs (defaults to last 2).

    Returns *None* when fewer than 2 runs are available.
    """
    all_runs = load_all_run_results(directory)
    if len(all_runs) < 2:
        return None
    recent = all_runs[-n:]
    return compare_runs(recent[0], recent[-1])


# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------


def delete_old_runs(
    keep: int = 50,
    directory: Path | None = None,
) -> int:
    """Delete oldest run results, keeping the most recent ``keep`` runs.

    Returns the number of runs deleted.
    """
    return _get_db().delete_old_runs(keep)


def to_dict(run: PersistedRunResult) -> dict[str, Any]:
    """Convert a ``PersistedRunResult`` to a plain dict (for API/serialization)."""
    return asdict(run)


def from_dict(data: dict[str, Any]) -> PersistedRunResult:
    """Construct a ``PersistedRunResult`` from a plain dict."""
    test_results = [
        PersistedTestResult(
            name=r["name"],
            status=r["status"],
            duration=r["duration"],
            error_message=r["error_message"],
            file_path=r["file_path"],
        )
        for r in data["results"]
    ]
    return PersistedRunResult(
        run_id=data["run_id"],
        test_package=data["test_package"],
        results=test_results,
        total=data["total"],
        passed=data["passed"],
        failed=data["failed"],
        skipped=data["skipped"],
        errors=data["errors"],
        duration=data["duration"],
        raw_output=data.get("raw_output", ""),
    )
