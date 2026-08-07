# `src/sqlite_persistence.py` — SQLite Persistence Layer

## Purpose

SQLite-backed persistence for run results, replacing the JSON-based persistence layer. Designed as a drop-in replacement — all public API methods mirror signatures in `run_result_persistence.py` so the wrapper layer can delegate transparently.

Uses `sqlite3` from the Python standard library — no external server or dependencies required.

## Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `_DEFAULT_DB_DIR` | `Path("evidence")` | Default database directory |
| `_DEFAULT_DB_FILE` | `evidence/run_results.sqlite` | Default database file path |

## Schema

### `runs` table
- `run_id` (TEXT, PRIMARY KEY) — ISO-8601 timestamp
- `test_package` (TEXT) — test package name
- `total`, `passed`, `failed`, `skipped`, `errors` (INTEGER)
- `duration` (REAL) — total run duration in seconds
- `raw_output` (TEXT) — full pytest output
- `created_at` (TEXT) — ISO-8601 creation timestamp

### `test_results` table
- `id` (INTEGER, AUTOINCREMENT PRIMARY KEY)
- `run_id` (TEXT, FK → runs.run_id, CASCADE DELETE)
- `name` (TEXT) — test function name
- `status` (TEXT) — "passed", "failed", "skipped", "error"
- `duration` (REAL) — individual test duration
- `error_message` (TEXT)
- `file_path` (TEXT)

### Indexes
- `idx_test_results_run_id` on `test_results(run_id)`
- `idx_test_results_name` on `test_results(name)`
- `idx_test_results_status` on `test_results(status)`
- `idx_test_results_name_status` on `test_results(name, status)`

## Class: `SQLitePersistence`

### Constructor

```python
SQLitePersistence(db_path: Path | None = None, busy_timeout_ms: int = 30000) -> None
```

Initialises the database connection with WAL journal mode, foreign key enforcement, and a 30s `busy_timeout` so concurrent opens (parallel pytest workers, Streamlit + CLI, export + run) serialize instead of failing with "database is locked". Creates the schema automatically.

**Corruption vs. lock handling:** a genuinely corrupt file ("file is not a database"/malformed) is deleted and rebuilt (B-034 — the evidence index rebuilds from sidecars); a transient lock (`OperationalError`) is re-raised and **never** deletes the file.

### Property

- `db_path: Path` — Path to the SQLite database file.

### Methods

#### `persist_run_result(run_result: RunResult, test_package: str = "") -> str`

Writes a run and its individual test results to the database. Returns the generated `run_id` (ISO-8601 timestamp).

#### `load_run_result(run_id: str) -> PersistedRunResult | None`

Loads a single run by ID, including all child test results. Returns `None` if not found.

#### `list_run_results() -> list[str]`

Returns sorted list of run_ids (oldest first).

#### `load_all_run_results() -> list[PersistedRunResult]`

Loads every persisted run (oldest first).

#### `run_stats_by_package() -> dict[str, tuple[int, str]]`

Returns `{test_package: (run_count, last_run_at)}` aggregated in a single `GROUP BY test_package` pass. Lets package-level UI (sidebar dropdown run counts/labels) reconcile against real run history cheaply (B-043).

#### `compute_run_history() -> RunHistory`

Aggregates stats directly from SQL — total runs, pass/fail/skip/error counts, and per-test flakiness using `GROUP BY`.

#### `get_flaky_tests(min_runs: int = 2) -> list[tuple[str, dict[str, int]]]`

Detects flaky tests using SQL `GROUP BY` + `HAVING`. A test is flaky when it has both passes and failures/errors across ≥ `min_runs` observations. Results sorted by flakiness ratio (descending).

#### `query_test_history(test_name_pattern: str = "%", status: str | None = None, date_from: str | None = None, date_to: str | None = None, include_flaky: bool = False) -> list[dict[str, Any]]`

Rich query interface for ad-hoc queries. Supports LIKE patterns, status filtering, date ranges, and flaky-only mode. Returns structured dicts for Jira/heatmap/Gantt exporters.

#### `get_run_stats_for_chart(date_from: str | None = None, date_to: str | None = None) -> list[dict[str, Any]]`

Chart-optimized aggregation query. Returns one row per run with aggregated stats and computed `pass_rate`.

#### `delete_old_runs(keep: int = 50) -> int`

Deletes oldest runs, keeping the most recent `keep` runs. Uses FK CASCADE to clean up child `test_results`.

#### `close() -> None` / `__enter__()` / `__exit__()`

Connection management and context-manager protocol support.

## Design Patterns

- **WAL journal mode**: Enables concurrent reads while writes happen — no table locks during chart rendering.
- **`busy_timeout` (30s)**: Concurrent writers/opener wait for each other instead of raising "database is locked" — parallel xdist workers and Streamlit+CLI overlap are safe.
- **Non-destructive lock handling**: transient `OperationalError` (locked) re-raises; only genuine `DatabaseError` (corruption) triggers the delete-and-rebuild recovery — a healthy database is never deleted on contention.
- **FK CASCADE**: Deleting a `run` automatically removes all child `test_results` rows.
- **Drop-in replacement**: Mirrors `run_result_persistence.py` signatures for transparent delegation.
