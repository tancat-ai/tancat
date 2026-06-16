# Feature Spec — SQLite Persistence Layer

**Feature ID:** AI-012
**Created:** 2026-06-14
**Status:** Complete
**Priority:** Medium (Tier 3 — Infrastructure)
**Depends on:** AI-026 (CLI Persist, shipped), AI-011 (Run History Chart, shipped)

---

## 1. Problem Statement

The current persistence layer (`src/run_result_persistence.py`) stores run results as individual JSON files under `evidence/run_results/`. This approach has several limitations:

1. **No queryability** — Cannot run ad-hoc queries like "show all tests that failed on page X" or "what's the flake rate trend for assertion placeholders?"
2. **Linear scans** — `load_all_run_results()` must read and parse every JSON file to compute history
3. **No atomicity** — Concurrent writes (e.g., parallel test runs) risk partial file corruption
4. **No indexing** — Flaky test detection requires loading all runs into memory
5. **Export complexity** — Packaging evidence requires copying many small files instead of one database file

SQLite addresses all these issues with zero infrastructure cost: single file, no server process, ACID compliance, and full SQL query support.

---

## 2. Goals

| Goal | Criteria |
|------|----------|
| Drop-in replacement | Existing public API (`persist_run_result`, `load_run_result`, etc.) unchanged signatures |
| Queryable history | Support SQL queries for flaky test analysis, trend reporting |
| Atomic writes | ACID transactions prevent corruption |
| Single file artifact | One `.sqlite` file replaces 50+ JSON files in exports |
| Backwards compatible | Can still load legacy JSON files via `pipeline_artifact_manager.py` |
| Docker friendly | Single file ships with container, no external DB service |

---

## 3. Non-Goals

- Real-time streaming dashboards (out of scope for this feature)
- Multi-user concurrent access (single developer tool)
- Migration of existing JSON files to SQLite (legacy files remain readable)
- Networked database access (local-only)

---

## 4. Architecture

### 4.1 Database Schema

```sql
-- Run-level metadata
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,           -- ISO-8601 timestamp
    test_package TEXT NOT NULL,         -- path to the test package
    total INTEGER NOT NULL DEFAULT 0,
    passed INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    duration REAL NOT NULL DEFAULT 0.0,
    raw_output TEXT,                    -- pytest raw output (may be large)
    created_at TEXT NOT NULL            -- UTC timestamp
);

-- Individual test results
CREATE TABLE test_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    name TEXT NOT NULL,                 -- test function name
    status TEXT NOT NULL,               -- passed/failed/skipped/error
    duration REAL NOT NULL DEFAULT 0.0,
    error_message TEXT,
    file_path TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

-- Indexes for common queries
CREATE INDEX idx_test_results_run_id ON test_results(run_id);
CREATE INDEX idx_test_results_name ON test_results(name);
CREATE INDEX idx_test_results_status ON test_results(status);
CREATE INDEX idx_test_results_name_status ON test_results(name, status);
```

### 4.1.1 PRAGMA Configuration

The following PRAGMAs must be executed on every new connection to ensure consistent behavior:

```sql
-- Enable Write-Ahead Logging for better concurrency (readers and writers simultaneous)
PRAGMA journal_mode = WAL;

-- Enable foreign key constraints (OFF by default in SQLite)
PRAGMA foreign_keys = ON;
```

**Rationale:**
- **WAL mode**: Allows concurrent reads during writes, critical for scenarios where history is queried while new runs are persisted. Recommended by SQLite docs for multi-access workloads.
- **FK enforcement**: Required for `ON DELETE CASCADE` to work when deleting old runs (cleanups cascade from `runs` → `test_results`).

### 4.2 Module Design

New module: `src/sqlite_persistence.py`

```python
class SQLitePersistence:
    """SQLite-backed persistence for run results."""

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize connection, create schema if needed."""

    def persist_run_result(
        self,
        run_result: RunResult,
        test_package: str = "",
    ) -> str:
        """Write run to DB. Returns run_id."""

    def load_run_result(self, run_id: str) -> PersistedRunResult | None:
        """Load single run by ID."""

    def list_run_results(self) -> list[str]:
        """Return sorted list of run_ids (oldest first)."""

    def load_all_run_results(self) -> list[PersistedRunResult]:
        """Load all runs."""

    def compute_run_history(self) -> RunHistory:
        """Aggregate stats using SQL instead of in-memory loops."""

    def get_flaky_tests(self, min_runs: int = 2) -> list[tuple[str, dict[str, int]]]:
        """Flaky test detection via SQL GROUP BY + HAVING."""

    def delete_old_runs(self, keep: int = 50) -> int:
        """Delete oldest runs. Returns count deleted."""

    def close(self) -> None:
        """Close connection."""
```

### 4.3 API Compatibility

**DECISION: Clean break approach.** Since this is a development tool with no valuable historical data, we use a clean break rather than synthetic Path references.

#### Dataclass Consolidation

**DECISION:** Dataclasses (`PersistedRunResult`, `PersistedTestResult`, `RunHistory`) are defined ONCE in `run_result_persistence.py`. The `sqlite_persistence.py` module imports them from there to avoid duplication and drift.

#### Function Signatures

| Function | Signature | Implementation |
|----------|-----------|---------------|
| `persist_run_result` | `(run_result: RunResult, test_package: str = "", directory: Path \| None = None) -> Path` | Delegates to SQLite, returns DB path |
| `load_run_result` | `(filepath: Path) -> PersistedRunResult` | JSON: legacy loader, SQLite: extracts run_id from stem |
| `list_run_results` | `(directory: Path \| None = None) -> list[str]` | **CHANGED:** Returns `list[str]` run_ids (clean break from `list[Path]`) |
| `load_all_run_results` | `(directory: Path \| None = None) -> list[PersistedRunResult]` | Delegates to SQLite |
| `compute_run_history` | `(runs: list[PersistedRunResult] \| None = None, directory: Path \| None = None) -> RunHistory` | Delegates to SQLite |
| `get_flaky_tests` | `(runs: list[PersistedRunResult] \| None = None, directory: Path \| None = None, min_runs: int = 2) -> list[tuple[str, dict[str, int]]]` | Delegates to SQLite |
| `compare_runs` | `(older: PersistedRunResult, newer: PersistedRunResult) -> RunComparison` | **No change** — pure in-memory logic |
| `compare_latest_runs` | `(n: int = 2, directory: Path \| None = None) -> RunComparison \| None` | Uses `load_all_run_results()` |
| `delete_old_runs` | `(keep: int = 50, directory: Path \| None = None) -> int` | Delegates to SQLite |
| `to_dict` | `(run: PersistedRunResult) -> dict[str, Any]` | **No change** — uses `dataclasses.asdict()` |
| `from_dict` | `(data: dict[str, Any]) -> PersistedRunResult` | **No change** — pure deserialization |

#### Key Design Decisions

- `compare_runs()` is pure in-memory logic — no DB changes needed
- `to_dict()` / `from_dict()` use `dataclasses.asdict()` — no DB changes needed
- `list_run_results()` returns `list[str]` run_ids for cleanliness (clean break — no valuable historical data to preserve)
- JSON files continue to load via `_legacy_load_json()` — zero breaking changes for callers (`run_history_chart.py`, `run_history_cli.py`, UI renderers)
- No migration script needed — the tool generates test data for its own validation, no historical data to preserve

---

## 5. SQL Query Examples

### Flaky test detection (replaces in-memory loop)
```sql
SELECT tr.name,
       SUM(CASE WHEN tr.status = 'passed' THEN 1 ELSE 0 END) as passed,
       SUM(CASE WHEN tr.status = 'failed' THEN 1 ELSE 0 END) as failed,
       SUM(CASE WHEN tr.status = 'error' THEN 1 ELSE 0 END) as errors,
       SUM(CASE WHEN tr.status = 'skipped' THEN 1 ELSE 0 END) as skipped
FROM test_results tr
GROUP BY tr.name
HAVING COUNT(*) >= 2
   AND SUM(CASE WHEN tr.status = 'passed' THEN 1 ELSE 0 END) > 0
   AND (SUM(CASE WHEN tr.status = 'failed' THEN 1 ELSE 0 END) > 0
        OR SUM(CASE WHEN tr.status = 'error' THEN 1 ELSE 0 END) > 0);
```

### Pass rate trend (feeds AI-011 chart)
```sql
SELECT r.run_id, r.passed, r.failed, r.skipped, r.errors,
       CAST(r.passed AS REAL) / r.total as pass_rate
FROM runs r
ORDER BY r.created_at;
```

### Tests failing on specific page
```sql
SELECT DISTINCT tr.name, tr.error_message
FROM test_results tr
WHERE tr.status IN ('failed', 'error')
  AND tr.error_message LIKE '%cart_page%';
```

---

## 6. Integration Points

| Module | Change |
|--------|--------|
| `src/run_result_persistence.py` | Delegate to SQLite, keep JSON fallback |
| `src/sqlite_persistence.py` | Import dataclasses from run_result_persistence (no duplication) |
| `src/run_history_chart.py` | Uses `load_all_run_results()` — same signature, no changes needed |
| `src/run_history_cli.py` | Uses `load_all_run_results()` — same signature, no changes needed |
| `src/ui_renderers.py` | Uses `load_all_run_results()` — same signature, no changes needed |
| `src/pipeline_run_service.py` | Uses `persist_run_result()` — same signature, no changes needed |
| `src/export_service.py` | Phase 3 — copy `.sqlite` file alongside JSON during transition |
| `Dockerfile` | No changes (sqlite3 is in Python stdlib) |
| `pyproject.toml` | No new deps (sqlite3 is stdlib) |

---

## 7. Implementation Phases

### Phase 1 — Core SQLite Module ✅ COMPLETE
- [x] Created `src/sqlite_persistence.py` with schema + CRUD
- [x] Created `tests/test_sqlite_persistence.py` (30+ tests)
- [x] `ruff` → `mypy` → `pytest` green

### Phase 2 — API Compatibility Layer ✅ COMPLETE
- [x] Fixed dataclass duplication — sqlite imports from run_result_persistence
- [x] Added wrapper functions in `run_result_persistence.py` delegating to SQLite
- [x] JSON legacy loader preserved as `_legacy_load_json()` / `_legacy_persist_run_result()`
- [x] `list_run_results()` returns `list[str]` (clean break — run_ids instead of Paths)
- [x] All existing tests pass (adapted for SQLite backend via `_isolated_db` fixture)
- [x] 99 tests pass: 37 persistence tests + 30 sqlite tests + 32 consumer tests
- [x] `ruff` → `mypy` → `pytest` green

### Phase 3 — Export Integration (Session 2)
- **Decision (2026-06-15):** Option B — SQLite ONLY in exports. No transition period needed since SQLite is the source of truth. JSON legacy loader removed immediately.
- [x] `export_service.py` copies `.sqlite` file (replaces JSON directory copy)
- [x] `pipeline_artifact_manager.py` references new format (`_count_run_results` SQLite-aware)
- [x] Remove JSON legacy loader (`_legacy_load_json`, `_legacy_persist_run_result`) from `run_result_persistence.py`
- [x] Simplify `load_run_result()` to SQLite-only
- [x] Update export README template to mention `.sqlite` file
- [x] Tests for export SQLite inclusion

### Phase 4 — Query Interface for Charts ✅ COMPLETE
- [x] `query_test_history()` method — rich filtering (name, status, date range, flaky), returns dicts
- [x] `get_run_stats_for_chart()` method — chart-optimized SQL aggregation
- [x] `build_chart_from_db()` convenience function in run_history_chart.py
- [x] Flaky detection uses SQL-backed `get_flaky_tests()`
- [x] 20 new tests: 8 query_test_history + 6 get_run_stats_for_chart + 6 build_chart_from_db
- [x] All 1215 tests pass, ruff + mypy green

---

## 8. Testing Strategy

| Test Category | Count | Description |
|---------------|-------|-------------|
| Schema creation | 3 | Tables, indexes, idempotent init |
| CRUD operations | 8 | persist, load, list, delete |
| Flaky detection | 5 | SQL matches current algorithm |
| Backwards compat | 4 | JSON files still load |
| API wrappers | 5 | Public functions delegate correctly |
| Edge cases | 3 | Empty DB, concurrent writes, large raw_output |
| **Total** | **28** | |

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Existing JSON files orphaned | Low | Legacy loader preserved indefinitely |
| SQLite file corruption | Low | ACID transactions, WAL mode |
| Performance regression for small datasets | Low | Benchmark: <100 runs, SQLite vs JSON load times |
| Path incompatibility on Windows | Medium | Use `sqlite3` with absolute paths |

---

## 10. Dependencies

- **Runtime:** `sqlite3` (Python stdlib — no new deps)
- **Build:** None
- **Blockers:** None (AI-026 and AI-011 already shipped)

---

## 11. Migration Plan

No data migration required. New runs go to SQLite. Old JSON files remain readable via legacy loader. No migration script needed — the tool generates test data for its own validation purposes, no historical data has lasting value.

---

## 12. Session Notes

### Session 1 (2026-06-14) — Phase 1 Complete
- Created `src/sqlite_persistence.py` (428 lines)
- Created `tests/test_sqlite_persistence.py` (30+ tests)
- Schema with WAL mode + FK enforcement
- Full CRUD, flaky detection, history aggregation via SQL

### Session 2 (2026-06-15) — Phase 2 ✅ COMPLETE
- **Decision:** Clean break for `list_run_results()` — returns `list[str]` run_ids
- **Decision:** No migration script needed — no valuable historical data
- **Decision:** Dataclasses consolidated in `run_result_persistence.py`, imported by `sqlite_persistence.py`
- **Decision:** Export features (test export, report generation) not impacted in Phase 2 — deferred to Phase 3
- Added `_reset_db()` function for test isolation
- Added `_isolated_db` autouse fixture in tests to patch `src.sqlite_persistence._DEFAULT_DB_FILE`
- 99 tests pass: 37 persistence + 30 sqlite + 32 consumer tests
- `ruff` → `mypy` → `pytest` all green

### Session 3 (2026-06-15) — Phase 3 ✅ COMPLETE
- **Decision:** Option B — SQLite ONLY in exports. No transition period.
- **Decision:** JSON legacy loader removed immediately.
- export_service.py copies `.sqlite` file instead of JSON directory
- Export README updated for SQLite-only format
- pipeline_artifact_manager.py counts SQLite DB alongside JSON test files
- 1195 tests pass, ruff/mypy/pytest green

### Session 4 (2026-06-15) — Phase 4 ✅ COMPLETE
- **Decision:** No backwards compatibility needed — dev tool, no historical data
- Implemented `query_test_history()` with name pattern, status, date range, and flaky filters
- Implemented `get_run_stats_for_chart()` with SQL aggregation (pass_rate computed in SQL)
- Added `build_chart_from_db()` convenience function using Plotly
- 20 new tests added (92 total persistence/chart tests)
- All 1215 tests pass, ruff + mypy green

---

*Last updated: 2026-06-15*
