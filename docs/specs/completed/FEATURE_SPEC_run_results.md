# FEATURE SPEC — Run Results & Report Improvements
## AI-008

**Status:** Implemented — Gap 1 (CLI Run Results) + Gap 2 (Run Result Persistence) completed 2026-06-02  
**Priority:** High — demo quality depends on this  
**Created:** 2026-03-09  
**Last Updated:** 2026-06-02  
**Protected files:** `src/llm_client.py`, `src/test_generator.py`, `main.py`

---

## Implementation Status

### ✅ Implemented (verified 2026-06-02)

| Requirement | Status | File(s) | Notes |
|---|---|---|---|
| Session state bug fix | ✅ Done | `streamlit_app.py` → `ui_pipeline.py` | Migration to pipeline modules eliminated the original wiping bug |
| `src/pytest_output_parser.py` module | ✅ Done | `src/pytest_output_parser.py` | Dataclasses (`TestResult`, `RunResult`) + `parse_pytest_output()` + `format_pytest_output_for_display()`. More advanced than spec: handles SKIPPED, ERRORS, collection errors, per-test duration extraction |
| Unit tests for parser | ✅ Done | `tests/test_pytest_output_parser.py` | 490 lines, ~25+ test functions (spec asked for 10). Covers: all-passed, mixed pass/fail, errors, empty output, collection errors, duration extraction, skip handling, parameterized tests, error message extraction |
| Structured results table in UI | ✅ Done | `src/ui_renderers.py` | `RunResultsDisplay.render()` — metrics grid (Total/Passed/Failed/Skipped/Errors), coverage table with Result column, per-test results table with repair buttons, pytest output expander |
| Coverage + Results integration | ✅ Done | `src/coverage_utils.py` | `build_coverage_display_rows()` accepts `run_results: Sequence[CoverageRunResult]` and maps pass/fail status per criterion via `run_map` |
| RunResult in pipeline service | ✅ Done | `src/pipeline_run_service.py` | `PipelineRunService.run_saved_test()` returns `PipelineExecutionResult` with `run_result: RunResult` |
| Report builder integration | ✅ Done | `src/report_builder.py` | `build_report_dicts()` merges `RunResult` into coverage rows with `run_status`, `run_result`, `failure_note`, `suggested_locators` |
| HTML report with run results | ✅ Done | `src/report_formatters.py` | `_format_html_report()` includes per-test details: status badge, duration, error messages, failure diagnostics (page URL, failure note, suggested alternatives, available elements, screenshots) |
| Jira report with run results | ✅ Done | `src/report_formatters.py` | `_format_jira_report()` includes failure diagnostics section |
| Re-run Failed Only | ✅ Done | `src/ui_renderers.py` | Button wired to `PipelineRunService.run_saved_test(rerun_failed_only=True, previous_run=...)` |
| Re-run All | ✅ Done | `src/ui_renderers.py` | Button wired to full re-run |
| Artifact writer with RunResult | ✅ Done | `src/pipeline_writer.py` | `write_run_artifacts()` writes coverage summary, manifest with page records, journeys, page objects |

### ⚠️ Partially Implemented / Needs Attention

| Requirement | Status | Details |
|---|---|---|
| **Evidence Loader integration with RunResult** | ⚠️ Partial | `src/evidence_loader.py` loads evidence JSON from test packages, but the connection between evidence data and `RunResult` is implicit via `report_builder.py`. Verify evidence data flows correctly into HTML reports when combined with run results. |

### ⚠️ Partially Implemented (additional)

| Requirement | Status | Details |
|---|---|---|
| **CLI Run Results Display** | ✅ Done (2026-06-02) | `cli/run_results_display.py` implemented with `render_run_results()`, `render_run_metrics()`, `render_results_table()`, `render_failure_details()`, `render_raw_output()`. Integrated into `cli/pipeline_runner.py`. 31 unit tests in `tests/test_cli_run_results_display.py`. |

### ✅ Implemented (Gap 2 — 2026-06-02)

| Requirement | Status | Details |
|---|---|---|
| **Run result persistence across sessions** | ✅ Done (2026-06-02) | `src/run_result_persistence.py` persists RunResult as JSON to `evidence/run_results/` with timestamped filenames. Supports history computation, flakiness detection, run comparison, and retention management. 32 unit tests in `tests/test_run_result_persistence.py`. Integrated into `src/pipeline_run_service.py` via `persist` parameter. |

### ❌ Not Implemented (gaps to close)

| Requirement | Status | Details |
|---|---|---|
| (None — all gaps closed) | — | — |

---

## Original Problem Statement

The original problem the feature addressed was:

1. **Broken** — session state bug wiped results immediately after setting ✅ FIXED
2. **Unreadable** — raw pytest stdout dumped into a `st.code()` block ✅ FIXED (structured display)
3. **Disconnected** — pass/fail results had no link back to coverage criteria ✅ FIXED (coverage+results integration)
4. **Incomplete** — HTML report contained only static coverage, not actual run results ✅ FIXED (run results in all report formats)

---

## Current Architecture

### Data Flow

```
User clicks "Run" → PipelineRunService.run_saved_test()
  → subprocess.run(pytest -v ...)
  → parse_pytest_output(raw_stdout) → RunResult
  → stored in st.session_state.pipeline_run_result
  → RunResultsDisplay.render(run_result) [UI]
  → build_report_dicts(coverage, run_result) [Reports]
  → _format_html_report() / _format_jira_report() / generate_local_report()
```

### Key Types

```python
# pytest_output_parser.py
@dataclass
class TestResult:
    name: str              # "test_01_login_page_displayed"
    status: str            # "passed" | "failed" | "error" | "skipped"
    duration: float        # seconds, 0.0 if not available
    error_message: str     # "" if passed, short error if failed
    file_path: str         # relative path to test file

@dataclass
class RunResult:
    results: list[TestResult]
    total: int
    passed: int
    failed: int
    errors: int
    skipped: int
    duration: float        # total run duration in seconds
    raw_output: str        # preserve original for expander

# pipeline_run_service.py
@dataclass(frozen=True)
class PipelineExecutionResult:
    command: list[str]
    run_result: RunResult
    display_output: str
    return_code: int

# coverage_utils.py
@dataclass
class CoverageDisplayRow:
    id_cell: str           # "✅ TC-001"
    requirement: str
    status: str            # "COVERED" | "NOT_COVERED"
    tests: str             # "test_01_login_page_..."
    result: str            # "✅" | "❌" | "⏭️" | "⏳" | "N/A"
```

### Session State Keys

```python
"pipeline_run_result": RunResult | None     # Parsed run result
"pipeline_run_output": str | None           # Formatted display output
"pipeline_saved_path": str | None           # Path to saved test package
```

---

## Original Spec vs. Actual Implementation

### What Changed

| Original Spec | Actual Implementation | Difference |
|---|---|---|
| `src/pytest_output_parser.py` with basic regex parsing | Same module, but with **advanced** parsing: handles SKIPPED, ERRORS, collection errors, per-test duration, parameterized test names | More robust than spec anticipated |
| `display_run_button()` in `streamlit_app.py` | Extracted to `src/ui_pipeline.py` + `src/ui_renderers.py` with `RunResultsDisplay` class | Follows extraction pattern, not in streamlit_app directly |
| Raw `st.code()` replacement with `st.dataframe()` | `st.metric()` grid + `st.table()` with expandable rows + repair buttons | More sophisticated UI than spec |
| Coverage table with Result column | `build_coverage_display_rows()` in `coverage_utils.py` with `CoverageRunResult` Protocol | Cleaner separation, reusable across UI/CLI |
| HTML report with run results | `_format_html_report()` with full failure diagnostics per test (page URL, failure note, suggested alternatives, available elements, screenshot embeds) | Far more detailed than spec |
| 10 unit tests minimum | ~25+ tests in `tests/test_pytest_output_parser.py` | Well-covered |
| Session state bug (2 lines to wipe) | Eliminated by pipeline refactor — results stored in `pipeline_run_result` key | Bug no longer exists in current architecture |
| `last_run_result` in session state | `pipeline_run_result` in session state | Renamed during pipeline refactor |

### What Was Not in Original Spec but Was Added

1. **Re-run Failed Only** — Button to re-run only failed tests using pytest `--lf` equivalent (via `get_failed_nodeids()`)
2. **Re-run All** — Button to re-run all tests in saved package
3. **Failure Classification** — `src/failure_classifier.py` categorizes failures (locator_mismatch, timeout, wrong_page, etc.)
4. **Repair Buttons** — Per-test repair suggestions in results table
5. **Evidence Integration** — `src/evidence_loader.py` + `src/evidence_serializer.py` merge runtime evidence into reports
6. **Artifact Writer** — `src/pipeline_writer.py` writes structured run artifacts (coverage summary, scrape manifest) to disk
7. **CLI Pipeline Runner** — `cli/pipeline_runner.py` uses same `PipelineRunService` for CLI test execution
8. **Pipeline Report Service** — `src/pipeline_report_service.py` orchestrates report generation from run results
9. **Timeout Enforcement** — `PIPELINE_TEST_TIMEOUT` env var (default 300s) prevents hung test runs

---

## Remaining Work

### Gap 1: CLI Structured Run Results — ✅ COMPLETED (2026-06-02)

**Implementation:**
1. Created `cli/run_results_display.py` with ANSI-formatted results display
2. Functions:
   - `render_run_results(run: RunResult, include_raw: bool = True)` — orchestrates all rendering
   - `render_run_metrics(run: RunResult)` — colored summary line (e.g., `✅ 5 passed, 1 failed, 0 errors in 12.3s`)
   - `render_results_table(run: RunResult)` — ASCII table with test name, status badge, duration
   - `render_failure_details(run: RunResult)` — classified failure type with repair suggestions
   - `render_raw_output(raw: str)` — optionally expands raw pytest output
3. Integrated into `cli/pipeline_runner.py` after `run_saved_test()` returns
4. Uses `cli/color.py` for ANSI color codes
5. 31 unit tests in `tests/test_cli_run_results_display.py`

### Gap 2: Run Result Persistence — ✅ COMPLETED (2026-06-02)

**Problem:** Run results exist only in session state. No way to compare runs over time or track flaky tests.

**Implementation:**
1. Created `src/run_result_persistence.py` with persistence data model and API
2. Data types:
   - `PersistedTestResult` — serializable test result (name, status, duration, error_message, file_path)
   - `PersistedRunResult` — serializable run result (test_results, total, passed, failed, errors, skipped, duration, timestamp, test_package)
3. Core functions:
   - `persist_run_result(run: RunResult, *, test_package: str | None = None, directory: Path | None = None) -> Path` — writes timestamped JSON to `evidence/run_results/`
   - `list_run_results(directory: Path | None = None) -> list[Path]` — lists persisted run files sorted by name (oldest first)
   - `load_run_result(path: Path) -> PersistedRunResult` — loads a single run from disk
   - `load_all_run_results(directory: Path | None = None) -> list[PersistedRunResult]` — loads all runs
   - `to_dict(run: PersistedRunResult) -> dict` / `from_dict(data: dict) -> PersistedRunResult` — serialization helpers
4. Analysis functions:
   - `compute_run_history(runs: list[PersistedRunResult]) -> RunHistory` — aggregates total_runs, avg_pass_rate, avg_duration, test_flakiness
   - `get_flaky_tests(history: RunHistory, *, min_runs: int = 3, min_score: float = 0.1) -> list[FlakyTestInfo]` — detects tests with mixed pass/fail across runs (flakiness_score = fails / total, filtered by min_runs and min_score)
   - `compare_runs(older: PersistedRunResult, newer: PersistedRunResult) -> RunComparison` — compares two runs by test name (improved, regressed, new_failures, no_change)
   - `compare_latest_runs(directory: Path | None = None) -> RunComparison | None` — convenience for comparing last 2 runs
   - `delete_old_runs(directory: Path | None = None, keep: int = 50) -> int` — retention management (oldest deleted first)
5. Integration:
   - `src/pipeline_run_service.py` — `PipelineExecutionResult.persist` parameter triggers `persist_run_result()` after run
6. 32 unit tests in `tests/test_run_result_persistence.py` covering:
   - Persist/load round-trip, empty runs, sorted listing
   - History computation, flakiness detection with min_runs/min_score thresholds
   - Run comparison (improve, regress, new failures, no change)
   - Latest run comparison edge cases
   - Retention deletion
   - Serialization round-trip

---

## Original Implementation Order (for reference)

The original spec defined this order:

1. ✅ Fix session state bug (2 lines) → done via pipeline refactor
2. ✅ Create `src/pytest_output_parser.py` with dataclasses and `parse_pytest_output()`
3. ✅ Write `tests/test_pytest_output_parser.py` — all tests passing
4. ✅ Update `display_run_button()` — replaced with `RunResultsDisplay.render()`
5. ✅ Add `run_result` to session state, pass to `display_coverage()`
6. ✅ Update `_generate_html_report()` to include run results
7. ✅ Run full `ruff check . && mypy streamlit_app.py src/ && pytest tests/ -v`

---

## Acceptance Criteria

| Criterion | Status |
|---|---|
| Bug fix: run results persist after download button clicks | ✅ Done |
| Results table shows each test name, pass/fail, duration | ✅ Done |
| Failed tests show error message inline below table | ✅ Done |
| Coverage table shows run result per criterion when available | ✅ Done |
| HTML report includes run results section | ✅ Done |
| CLI structured run results display | ✅ Done (2026-06-02) |
| `pytest tests/ -v` passes with no new failures | ✅ Done (verify before shipping any changes) |
| `mypy streamlit_app.py src/` passes clean | ✅ Done (verify before shipping any changes) |
| `pytest_output_parser.py` has ≥10 unit tests all passing | ✅ Done (~25+ tests) |
| CLI run results display has unit tests | ✅ Done (31 tests in `test_cli_run_results_display.py`) |
| Run result persistence has unit tests | ✅ Done (32 tests in `test_run_result_persistence.py`) |

---

## Dependencies

### Files involved in run results pipeline

```
src/pytest_output_parser.py        # Parse raw pytest output → RunResult
src/pipeline_run_service.py        # Execute tests, return PipelineExecutionResult
src/run_result_persistence.py      # Persist RunResult to JSON, history, flakiness (NEW 2026-06-02)
src/run_utils.py                   # Build pytest command, extract failed nodeids
src/ui_renderers.py                # RunResultsDisplay.render() [Streamlit UI]
src/ui_pipeline.py                 # Pipeline orchestration for UI
src/coverage_utils.py              # Merge run results into coverage display
src/report_builder.py              # Merge run results into report dicts
src/report_formatters.py           # Format reports (HTML, Jira, Local MD)
src/pipeline_report_service.py     # Orchestrate report generation
src/pipeline_writer.py             # Write run artifacts to disk
src/evidence_loader.py             # Load evidence JSON from test packages
src/failure_classifier.py          # Classify failure types
```

### CLI files involved

```
cli/main.py                        # CLI entry point
cli/pipeline_runner.py             # Run pipeline tests via PipelineRunService
cli/report_generator.py            # Generate reports from run results
cli/run_results_display.py         # Structured ANSI run results display (NEW 2026-06-02)
cli/color.py                       # ANSI colour helpers used by run_results_display
```

---

*Original Created: 2026-03-09*
*Original Author: Session 5 planning*
*Updated: 2026-06-02 — Status audit, architecture documentation, gap analysis, Gap 2 (Run Result Persistence) implementation*
