"""Persist run results to disk for historical comparison and flaky-test tracking.

Provides thin JSON persistence for ``RunResult`` objects so that consecutive
pytest runs can be compared over time.  Stored artefacts live under
``evidence/run_results/`` as one file per run, named by ISO-8601 timestamp.

No Streamlit imports — fully unit-testable in isolation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.pytest_output_parser import RunResult

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
# Persistence operations
# ---------------------------------------------------------------------------

_DEFAULT_DIR = Path("evidence/run_results")


def _default_dir() -> Path:
    """Return the default persistence directory (creates if needed)."""
    _DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
    return _DEFAULT_DIR


def persist_run_result(
    run_result: RunResult,
    test_package: str = "",
    directory: Path | None = None,
) -> Path:
    """Write a single ``RunResult`` to disk and return the file path.

    The filename encodes an ISO-8601 UTC timestamp so that runs are
    naturally sortable.

    Args:
        run_result: Parsed pytest result to persist.
        test_package: Path or identifier of the test package that was run.
        directory: Override directory; defaults to ``evidence/run_results``.

    Returns:
        Absolute path to the written JSON file.
    """
    target_dir = directory or _default_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).isoformat()
    safe_id = timestamp.replace(":", "-").replace("+", "-")
    filename = f"run_{safe_id}.json"
    filepath = (target_dir / filename).resolve()

    persisted = PersistedRunResult(
        run_id=timestamp,
        test_package=test_package,
        results=[
            PersistedTestResult(
                name=r.name,
                status=r.status,
                duration=r.duration,
                error_message=r.error_message,
                file_path=r.file_path,
            )
            for r in run_result.results
        ],
        total=run_result.total,
        passed=run_result.passed,
        failed=run_result.failed,
        skipped=run_result.skipped,
        errors=run_result.errors,
        duration=run_result.duration,
        raw_output=run_result.raw_output,
    )

    filepath.write_text(
        json.dumps(asdict(persisted), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return filepath


def load_run_result(filepath: Path) -> PersistedRunResult:
    """Load a single persisted run result from disk."""
    data = json.loads(filepath.read_text(encoding="utf-8"))
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


def list_run_results(directory: Path | None = None) -> list[Path]:
    """Return sorted list of persisted run-result file paths (oldest first)."""
    target_dir = directory or _default_dir()
    if not target_dir.exists():
        return []
    return sorted(target_dir.glob("run_*.json"))


def load_all_run_results(directory: Path | None = None) -> list[PersistedRunResult]:
    """Load every persisted run result (oldest first)."""
    return [load_run_result(p) for p in list_run_results(directory)]


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
              persisted runs from ``directory``.
        directory: Directory to scan when ``runs`` is *None*.
    """
    if runs is None:
        runs = load_all_run_results(directory)

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

    Returns:
        List of ``(test_name, counts)`` tuples sorted by flakiness score
        (ratio of minority outcome to total runs, descending).
    """
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
    """Delete oldest run-result files, keeping the most recent ``keep`` runs.

    Returns the number of files deleted.
    """
    all_files = list_run_results(directory)
    to_delete = all_files[:-keep] if len(all_files) > keep else []
    for filepath in to_delete:
        filepath.unlink(missing_ok=True)
    return len(to_delete)


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
