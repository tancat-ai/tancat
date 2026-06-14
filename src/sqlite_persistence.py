"""SQLite-backed persistence for run results.

Provides a single-file database replacement for the JSON-based persistence
layer.  All public API methods mirror the signatures in
``run_result_persistence.py`` so the wrapper layer can delegate transparently.

No server process required — ``sqlite3`` is in the Python standard library.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.pytest_output_parser import RunResult

# ---------------------------------------------------------------------------
# Default database location
# ---------------------------------------------------------------------------

_DEFAULT_DB_DIR = Path("evidence")
_DEFAULT_DB_FILE = _DEFAULT_DB_DIR / "run_results.sqlite"

# ---------------------------------------------------------------------------
# Schema — executed once on first initialisation
# ---------------------------------------------------------------------------

_SCHEMA_SQL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS runs (
        run_id        TEXT PRIMARY KEY,
        test_package  TEXT    NOT NULL DEFAULT '',
        total         INTEGER NOT NULL DEFAULT 0,
        passed        INTEGER NOT NULL DEFAULT 0,
        failed        INTEGER NOT NULL DEFAULT 0,
        skipped       INTEGER NOT NULL DEFAULT 0,
        errors        INTEGER NOT NULL DEFAULT 0,
        duration      REAL    NOT NULL DEFAULT 0.0,
        raw_output    TEXT,
        created_at    TEXT    NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS test_results (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id        TEXT    NOT NULL,
        name          TEXT    NOT NULL,
        status        TEXT    NOT NULL,
        duration      REAL    NOT NULL DEFAULT 0.0,
        error_message TEXT,
        file_path     TEXT,
        FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_test_results_run_id ON test_results(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_test_results_name ON test_results(name)",
    "CREATE INDEX IF NOT EXISTS idx_test_results_status ON test_results(status)",
    "CREATE INDEX IF NOT EXISTS idx_test_results_name_status ON test_results(name, status)",
]


# ---------------------------------------------------------------------------
# Data classes (mirror run_result_persistence dataclasses)
# ---------------------------------------------------------------------------


@dataclass
class PersistedTestResult:
    """Serializable mirror of :class:`TestResult`."""

    name: str = ""
    status: str = ""
    duration: float = 0.0
    error_message: str = ""
    file_path: str = ""


@dataclass
class PersistedRunResult:
    """Serializable mirror of :class:`RunResult` with persistence metadata."""

    run_id: str = ""
    test_package: str = ""
    results: list[PersistedTestResult] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration: float = 0.0
    raw_output: str = ""
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


# ---------------------------------------------------------------------------
# SQLite Persistence Class
# ---------------------------------------------------------------------------


class SQLitePersistence:
    """SQLite-backed persistence for run results.

    Parameters
    ----------
    db_path :
        Absolute or relative path to the ``.sqlite`` database file.
        Defaults to ``evidence/run_results.sqlite``.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB_FILE
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn: sqlite3.Connection = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row

        # PRAGMA configuration — WAL for concurrency, FK enforcement for CASCADE
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")

        self._create_schema()

    # ------------------------------------------------------------------
    # Property: expose db_path for wrappers / export tools
    # ------------------------------------------------------------------

    @property
    def db_path(self) -> Path:
        """Path to the SQLite database file."""
        return self._db_path

    # ------------------------------------------------------------------
    # Schema initialisation
    # ------------------------------------------------------------------

    def _create_schema(self) -> None:
        """Create tables and indexes if they don't exist."""
        for sql in _SCHEMA_SQL:
            self._conn.execute(sql)
        self._conn.commit()

    # ------------------------------------------------------------------
    # CRUD — persist run result
    # ------------------------------------------------------------------

    def persist_run_result(
        self,
        run_result: RunResult,
        test_package: str = "",
    ) -> str:
        """Write a run to the database.

        Returns the generated ``run_id`` (ISO-8601 timestamp).
        """
        timestamp = datetime.now(UTC).isoformat()

        self._conn.execute(
            """
            INSERT INTO runs
                (run_id, test_package, total, passed, failed, skipped, errors,
                 duration, raw_output, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                test_package,
                run_result.total,
                run_result.passed,
                run_result.failed,
                run_result.skipped,
                run_result.errors,
                run_result.duration,
                run_result.raw_output,
                timestamp,
            ),
        )

        # Insert individual test results
        for r in run_result.results:
            self._conn.execute(
                """
                INSERT INTO test_results
                    (run_id, name, status, duration, error_message, file_path)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    r.name,
                    r.status,
                    r.duration,
                    r.error_message,
                    r.file_path,
                ),
            )

        self._conn.commit()
        return timestamp

    # ------------------------------------------------------------------
    # CRUD — load single run
    # ------------------------------------------------------------------

    def load_run_result(self, run_id: str) -> PersistedRunResult | None:
        """Load a single run by ``run_id``.

        Returns ``None`` if the run does not exist.
        """
        row = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()

        if row is None:
            return None

        run = PersistedRunResult(
            run_id=row["run_id"],
            test_package=row["test_package"],
            total=row["total"],
            passed=row["passed"],
            failed=row["failed"],
            skipped=row["skipped"],
            errors=row["errors"],
            duration=row["duration"],
            raw_output=row["raw_output"] or "",
        )

        # Load individual test results for this run
        cursor = self._conn.execute("SELECT * FROM test_results WHERE run_id = ? ORDER BY id", (run_id,))

        for tr_row in cursor.fetchall():
            run.results.append(
                PersistedTestResult(
                    name=tr_row["name"],
                    status=tr_row["status"],
                    duration=tr_row["duration"],
                    error_message=tr_row["error_message"] or "",
                    file_path=tr_row["file_path"] or "",
                )
            )

        return run

    # ------------------------------------------------------------------
    # CRUD — list runs
    # ------------------------------------------------------------------

    def list_run_results(self) -> list[str]:
        """Return sorted list of run_ids (oldest first)."""
        rows = self._conn.execute("SELECT run_id FROM runs ORDER BY created_at").fetchall()
        return [row["run_id"] for row in rows]

    # ------------------------------------------------------------------
    # CRUD — load all runs
    # ------------------------------------------------------------------

    def load_all_run_results(self) -> list[PersistedRunResult]:
        """Load every persisted run (oldest first)."""
        results: list[PersistedRunResult] = []
        for run_id in self.list_run_results():
            run = self.load_run_result(run_id)
            if run is not None:
                results.append(run)
        return results

    # ------------------------------------------------------------------
    # History — compute using SQL aggregation
    # ------------------------------------------------------------------

    def compute_run_history(self) -> RunHistory:
        """Aggregate stats directly from SQL instead of in-memory loops."""
        history = RunHistory()

        # Aggregate run-level stats
        row = self._conn.execute(
            """
            SELECT
                COUNT(*)   as total_runs,
                COALESCE(SUM(passed), 0)  as total_passed,
                COALESCE(SUM(failed), 0)  as total_failed,
                COALESCE(SUM(skipped), 0) as total_skipped,
                COALESCE(SUM(errors), 0)  as total_errors
            FROM runs
            """
        ).fetchone()

        if row is not None:
            history.total_runs = row["total_runs"]
            history.total_passed = row["total_passed"]
            history.total_failed = row["total_failed"]
            history.total_skipped = row["total_skipped"]
            history.total_errors = row["total_errors"]

        # Aggregate per-test flakiness using SQL GROUP BY
        rows = self._conn.execute(
            """
            SELECT
                name,
                SUM(CASE WHEN status = 'passed'  THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN status = 'failed'  THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) as skipped,
                SUM(CASE WHEN status = 'error'   THEN 1 ELSE 0 END) as errors
            FROM test_results
            GROUP BY name
            """
        ).fetchall()

        for tr_row in rows:
            history.test_flakiness[tr_row["name"]] = {
                "passed": tr_row["passed"],
                "failed": tr_row["failed"],
                "skipped": tr_row["skipped"],
                "error": tr_row["errors"],
            }

        return history

    # ------------------------------------------------------------------
    # Flaky test detection — SQL HAVING
    # ------------------------------------------------------------------

    def get_flaky_tests(self, min_runs: int = 2) -> list[tuple[str, dict[str, int]]]:
        """Detect flaky tests using SQL GROUP BY + HAVING.

        A test is *flaky* when it has both passes and failures (or errors)
        across at least ``min_runs`` observations.

        Returns results sorted by flakiness ratio (descending).
        """
        rows = self._conn.execute(
            f"""
            SELECT
                name,
                SUM(CASE WHEN status = 'passed'  THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN status = 'failed'  THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'error'   THEN 1 ELSE 0 END) as errors,
                SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) as skipped
            FROM test_results
            GROUP BY name
            HAVING COUNT(*) >= {min_runs}
               AND SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) > 0
               AND (
                   SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) > 0
                OR SUM(CASE WHEN status = 'error'  THEN 1 ELSE 0 END) > 0
               )
            """
        ).fetchall()

        flaky: list[tuple[str, dict[str, int]]] = []
        for row in rows:
            counts = {
                "passed": row["passed"],
                "failed": row["failed"],
                "skipped": row["skipped"],
                "error": row["errors"],
            }
            flaky.append((row["name"], counts))

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

    # ------------------------------------------------------------------
    # Housekeeping — delete old runs
    # ------------------------------------------------------------------

    def delete_old_runs(self, keep: int = 50) -> int:
        """Delete oldest runs, keeping the most recent ``keep`` runs.

        Returns the number of runs deleted.  Foreign-key CASCADE ensures
        child ``test_results`` rows are removed automatically.
        """
        # Find run_ids to delete (oldest first, everything beyond ``keep``)
        # Secondary sort on run_id ensures deterministic order when timestamps match
        rows = self._conn.execute(
            """
            SELECT run_id FROM runs
            ORDER BY created_at, run_id
            LIMIT -1 OFFSET ?
            """,
            (keep,),
        ).fetchall()

        deleted = len(rows)
        for row in rows:
            self._conn.execute("DELETE FROM runs WHERE run_id = ?", (row["run_id"],))

        self._conn.commit()
        return deleted

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        try:
            self._conn.close()
        except Exception:
            pass

    def __enter__(self) -> SQLitePersistence:
        """Support context-manager protocol."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close connection on context-manager exit."""
        self.close()
