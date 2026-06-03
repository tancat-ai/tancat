# `src/run_result_persistence.py` — Run Result Persistence

**Module:** Persist run results to disk for historical comparison and flaky-test tracking  
**Created:** 2026-06-02  
**Status:** Stable

---

## Overview

Provides thin JSON persistence for `RunResult` objects so that consecutive pytest runs can be compared over time. Stored artifacts live under `evidence/run_results/` as one file per run, named by ISO-8601 timestamp.

No Streamlit imports — fully unit-testable in isolation.

---

## Dependencies

| Import | Source | Purpose |
|--------|--------|---------|
| `json` | stdlib | Serialization |
| `dataclasses` | stdlib | Data structure definitions |
| `datetime` | stdlib | Timestamp generation |
| `pathlib.Path` | stdlib | File system operations |
| `src.pytest_output_parser.RunResult` | `src/pytest_output_parser.py` | Source data for persistence |

---

## Data Structures

### `PersistedTestResult`

Serializable mirror of `TestResult` from the parser module.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Test function name (e.g., `test_01_login_page_displayed`) |
| `status` | `str` | `"passed"`, `"failed"`, `"error"`, `"skipped"` |
| `duration` | `float` | Execution time in seconds |
| `error_message` | `str` | Error text (empty string if passed) |
| `file_path` | `str` | Relative path to test file |

### `PersistedRunResult`

Serializable mirror of `RunResult` with persistence metadata.

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | `str` | ISO-8601 timestamp, unique per file |
| `test_package` | `str` | Path to the test package that was run |
| `results` | `list[PersistedTestResult]` | Per-test results |
| `total` | `int` | Total test count |
| `passed` | `int` | Passed count |
| `failed` | `int` | Failed count |
| `skipped` | `int` | Skipped count |
| `errors` | `int` | Error count |
| `duration` | `float` | Total run duration in seconds |
| `raw_output` | `str` | Preserved pytest stdout for reference |
| `flaky_tests` | `list[str]` | Computed on load (not stored on disk) |

### `RunHistory`

Aggregated statistics across multiple persisted runs.

| Field | Type | Description |
|-------|------|-------------|
| `total_runs` | `int` | Number of runs in history |
| `total_passed` | `int` | Cumulative passed count |
| `total_failed` | `int` | Cumulative failed count |
| `total_skipped` | `int` | Cumulative skipped count |
| `total_errors` | `int` | Cumulative error count |
| `test_flakiness` | `dict[str, dict[str, int]]` | Maps test name → `{"passed": N, "failed": N, "skipped": N, "error": N}` |

### `RunComparison`

Side-by-side comparison of two runs.

| Field | Type | Description |
|-------|------|-------------|
| `older` | `PersistedRunResult` | Earlier run |
| `newer` | `PersistedRunResult` | Later run |
| `improved` | `list[str]` | Tests that went from fail/error to pass |
| `regressed` | `list[str]` | Tests that went from pass to fail/error |
| `new_failures` | `list[str]` | Tests not in older run but failing in newer |

---

## Public API

### Persistence Operations

| Function | Signature | Description |
|----------|-----------|-------------|
| `persist_run_result` | `(run_result: RunResult, test_package: str = "", directory: Path \| None = None) -> Path` | Write a single `RunResult` to disk as timestamped JSON. Returns absolute path to written file. |
| `load_run_result` | `(filepath: Path) -> PersistedRunResult` | Load a single persisted run result from disk. |
| `list_run_results` | `(directory: Path \| None = None) -> list[Path]` | Return sorted list of persisted run-result file paths (oldest first). |
| `load_all_run_results` | `(directory: Path \| None = None) -> list[PersistedRunResult]` | Load every persisted run result (oldest first). |

### History & Flakiness Analysis

| Function | Signature | Description |
|----------|-----------|-------------|
| `compute_run_history` | `(runs: list[PersistedRunResult] \| None = None, directory: Path \| None = None) -> RunHistory` | Aggregate statistics across all persisted runs. When `runs` is `None`, loads all persisted runs from `directory`. |
| `get_flaky_tests` | `(runs: list[PersistedRunResult] \| None = None, directory: Path \| None = None, min_runs: int = 2) -> list[tuple[str, dict[str, int]]]` | Return tests with inconsistent results across runs. A test is flaky when it has both passes and failures across at least `min_runs` observations. Sorted by flakiness ratio (descending). |

### Run Comparison

| Function | Signature | Description |
|----------|-----------|-------------|
| `compare_runs` | `(older: PersistedRunResult, newer: PersistedRunResult) -> RunComparison` | Compare two runs and classify per-test changes (improved, regressed, new_failures). |
| `compare_latest_runs` | `(n: int = 2, directory: Path \| None = None) -> RunComparison \| None` | Compare the latest `n` runs. Returns `None` when fewer than 2 runs available. |

### Housekeeping

| Function | Signature | Description |
|----------|-----------|-------------|
| `delete_old_runs` | `(keep: int = 50, directory: Path \| None = None) -> int` | Delete oldest run-result files, keeping the most recent `keep` runs. Returns number of files deleted. |
| `to_dict` | `(run: PersistedRunResult) -> dict[str, Any]` | Convert to plain dict for API/serialization. |
| `from_dict` | `(data: dict[str, Any]) -> PersistedRunResult` | Construct from plain dict. |

---

## File Format

Each persisted run is stored as a JSON file in `evidence/run_results/`:

```
evidence/
  └── run_results/
      ├── run_2026-06-02T18-30-00-000000.json
      ├── run_2026-06-02T19-15-30-000000.json
      └── ...
```

Filename format: `run_{iso_timestamp}.json` where colons are replaced with hyphens for Windows compatibility.

JSON structure:
```json
{
  "run_id": "2026-06-02T18:30:00.000000",
  "test_package": "generated_tests/test_tc_001_login",
  "results": [
    {
      "name": "test_01_login_page_displayed",
      "status": "passed",
      "duration": 1.23,
      "error_message": "",
      "file_path": "generated_tests/test_tc_001_login/test_01_login_page_displayed.py"
    }
  ],
  "total": 5,
  "passed": 4,
  "failed": 1,
  "skipped": 0,
  "errors": 0,
  "duration": 8.45,
  "raw_output": "...",
  "flaky_tests": []
}
```

---

## Integration Points

| Consumer | Integration |
|----------|-------------|
| `src/pipeline_run_service.py` | `PipelineExecutionResult.persist` parameter triggers `persist_run_result()` after test execution |
| Future UI/CLI | `load_all_run_results()` + `compute_run_history()` for trending dashboards |
| Future CI | `compare_latest_runs()` for regression detection in CI pipelines |

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| JSON format over SQLite | Simple, human-readable, git-tracked, no migration needed |
| Timestamp in filename | Natural sort order matches chronological order, no index needed |
| Default retention of 50 runs | Balances history depth with disk usage |
| Flakiness = both pass AND fail across runs | Catches intermittent failures, not consistently broken tests |
| `min_runs=2` threshold | Requires at least 2 observations before flagging flakiness |

---

## Test Coverage

32 unit tests in `tests/test_run_result_persistence.py` covering:
- Persist/load round-trip
- Empty runs
- Sorted listing
- History computation
- Flakiness detection with min_runs threshold
- Run comparison (improve, regress, new failures)
- Latest run comparison edge cases
- Retention deletion
- Serialization round-trip

---

## Notes

- Module is fully synchronous — no async I/O
- Thread-safe for single-writer scenarios (typical for test pipeline)
- No locking for concurrent writers — not designed for parallel persistence
- `flaky_tests` field on `PersistedRunResult` is computed on load, not persisted