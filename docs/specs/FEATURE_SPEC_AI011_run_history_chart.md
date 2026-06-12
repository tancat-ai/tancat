# FEATURE SPEC — AI-011: Run History Chart

**Status:** Complete — 2026-06-12
**Created:** 2026-06-11
**Supersedes:** N/A
**Depends on:** `src/run_result_persistence.py` (stable), `src/ui_renderers.py`, `cli/run_results_display.py`
**Related:** AI-026 (persist generated tests — provides the data layer), AI-022 (coverage heatmap — consumes run history trends)
**Priority:** Medium — Feeds coverage heatmap story; sprint-over-sprint trends for QA persona

---

## Problem Statement

The tool persists run results to `evidence/run_results/` as JSON files (one per run, named by ISO-8601 timestamp). The data layer in `src/run_result_persistence.py` already provides:

- `compute_run_history()` — aggregates pass/fail/skip counts across runs
- `get_flaky_tests()` — identifies tests with alternating pass/fail
- `compare_runs()` — diffs two consecutive runs (improved/regressed/new_failures)
- `load_all_run_results()` — loads all persisted runs from disk

However, there is **no visualization** of this historical data. Users cannot see:
- How pass rates trend over time
- Which tests are flaky
- How two runs compare (improvements vs. regressions)

This limits the tool's value for QA/Engineering Manager personas who need sprint-over-sprint trend analysis and feeds into AI-022 (coverage heatmap) story.

---

## Proposed Solution

Add a **Run History Chart** using Plotly (already a dependency) with three complementary views:

1. **Stacked bar chart** — pass/fail/skip/error counts per run with pass-rate line overlay
2. **Flaky test table** — expandable list of tests with inconsistent results
3. **Run comparison panel** — side-by-side diff of last two runs

### Architecture

```
EvidenceViewer (Streamlit tabs)
├── Tab 1: Annotated Screenshot  (existing)
├── Tab 2: Gantt Timeline        (existing)
├── Tab 3: Coverage Heat Map     (existing)
└── Tab 4: Run History           (NEW)
     ├── Scope selector: Current Package / All Runs
     ├── Stacked bar chart (Plotly)
     ├── Flaky test indicators (❗ markers + expandable table)
     └── Run comparison panel (improved/regressed/new_failures)

CLI Run Results Display
└── History summary section (NEW)
    ├── ASCII table: last N runs with pass/fail/skip/error/rate
    ├── Flaky test list
    └── Last run comparison (improved/regressed/new_failures)
```

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Chart type | Stacked bar + line overlay | Most intuitive for discrete runs; pass-rate line shows trend |
| Flaky indicators | Chart markers + expandable table | Both visual cue and detailed breakdown |
| Streamlit placement | New EvidenceViewer tab | Consistent with Gantt/Heatmap pattern |
| CLI support | ASCII table (upgradeable to rich) | Minimal VSE, no new deps, design path for future enhancement |
| Run comparison | Last 2 runs panel | Low effort (function exists), high value for QA persona |
| Data scope | Current package default, "All Runs" option | Supports both single-project and multi-project workflows |

---

## Data Layer (No Changes Required)

The existing `src/run_result_persistence.py` provides all needed functions:

| Function | Returns | Used For |
|----------|---------|----------|
| `load_all_run_results(directory)` | `list[PersistedRunResult]` | Loading all runs from disk |
| `compute_run_history(runs)` | `RunHistory` | Aggregated stats, flakiness computation |
| `get_flaky_tests(runs, min_runs)` | `list[tuple[str, dict]]` | Flaky test identification |
| `compare_runs(older, newer)` | `RunComparison` | Two-run diff |
| `compare_latest_runs(n, directory)` | `RunComparison \| None` | Quick last-2-runs comparison |

Key data structures:

```python
@dataclass
class PersistedRunResult:
    run_id: str                          # ISO-8601 timestamp
    test_package: str                    # path to test package (for filtering)
    results: list[PersistedTestResult]   # per-test results
    total: int
    passed: int
    failed: int
    skipped: int
    errors: int
    duration: float
    raw_output: str

@dataclass
class RunComparison:
    older: PersistedRunResult
    newer: PersistedRunResult
    improved: list[str]                  # fail/error → pass
    regressed: list[str]                 # pass → fail/error
    new_failures: list[str]              # absent → fail/error
```

**Session reload compatibility:** Runs are stored as JSON files on disk. `load_all_run_results()` scans the directory on-demand with no caching. Data survives session restarts and can be filtered by `test_package` field.

---

## Implementation Details

### 1. Chart Builder (`src/run_history_chart.py`)

**Purpose:** Pure Plotly Figure factory. No Streamlit or CLI dependencies.

```python
def build_run_history_chart(
    runs: list[PersistedRunResult],
    include_flaky_markers: bool = True,
) -> go.Figure:
    """Build a stacked bar chart with pass-rate line overlay.
    
    X-axis: run timestamp (chronological)
    Primary Y-axis: test count (stacked bars: pass/fail/skip/error)
    Secondary Y-axis: pass rate percentage (line)
    
    Args:
        runs: Sorted list of run results (oldest first).
        include_flaky_markers: Add ❗ annotations for runs with flaky tests.
    
    Returns:
        Plotly Figure ready for st.plotly_chart().
    """
```

**Chart specifications:**
- **Colors:** Pass=green (#2ecc71), Fail=red (#e74c3c), Skip=yellow (#f1c40f), Error=gray (#95a5a6)
- **Bar width:** Auto-scaled based on run count
- **Pass rate line:** Dark blue (#2c3e50) with circle markers, right Y-axis (0-100%)
- **Flaky markers:** ❗ unicode character positioned above bars where flaky tests occurred
- **Empty state:** Returns figure with "No run history available" message
- **Single run:** Shows one bar with pass rate at 100% or computed rate

**Test strategy:**
- `test_chart_empty_runs()` — graceful empty state
- `test_chart_single_run()` — single bar renders correctly
- `test_chart_multiple_runs()` — stacked bars with correct counts
- `test_chart_pass_rate_line()` — line overlay matches computed rates
- `test_chart_flaky_markers()` — markers appear on correct bars
- `test_chart_chronological_order()` — runs sorted oldest-first

---

### 2. CLI Renderer (`src/run_history_cli.py`)

**Purpose:** Text-based run history summary for CLI. No external dependencies beyond stdlib.

```python
def format_run_history_table(
    runs: list[PersistedRunResult],
    max_rows: int = 10,
) -> str:
    """Format run history as an ASCII table string.
    
    Returns a formatted string with columns:
    Date | Package | Pass | Fail | Skip | Error | Pass Rate
    """

def format_flaky_tests_table(
    flaky: list[tuple[str, dict[str, int]]],
) -> str:
    """Format flaky tests as an ASCII table string.
    
    Returns a formatted string with columns:
    Test Name | Pass | Fail | Flakiness Score
    """

def format_run_comparison(
    comparison: RunComparison | None,
) -> str:
    """Format run comparison as an ASCII summary.
    
    Returns sections for Improved, Regressed, New Failures.
    """
```

**Output format:**
```
=== Run History (last 10 runs) ===
Date                  Package     Pass  Fail  Skip  Error  Pass Rate
2026-06-11 21:00:00   pkg_a       15    2     1     0      83.3%
2026-06-11 20:00:00   pkg_a       14    3     1     0      77.8%

=== Flaky Tests ===
Test Name                         Pass  Fail  Flakiness Score
test_02_add_to_cart               5     3     0.38 ❗
test_05_checkout                  4     2     0.33 ❗

=== Last Run Comparison ===
Improved:  [test_03_login]
Regressed: [test_07_search]
New Failures: (none)
```

**Design note:** Uses plain `print()` with formatted strings. Future upgrade path: swap to `rich` library for colored tables without changing the data layer or function signatures.

**Test strategy:**
- `test_format_empty_history()` — graceful empty message
- `test_format_single_run()` — one row renders correctly
- `test_format_truncation()` — long test names truncated to ~40 chars
- `test_format_flaky_empty()` — "(none)" when no flaky tests
- `test_format_comparison_none()` — "(insufficient data)" when < 2 runs

---

### 3. Streamlit Integration (`src/ui_renderers.py`)

**Changes to EvidenceViewer class:**

Add a fourth tab in the `_render_evidence_viewer()` method:

```python
# Existing tabs
tab_screenshot, tab_gantt, tab_heatmap, tab_history = st.tabs([
    "Annotated Screenshot",
    "Gantt Timeline",
    "Coverage Heat Map",
    "Run History",  # NEW
])

with tab_history:
    self._render_run_history()
```

**New method: `_render_run_history()`**

```python
def _render_run_history(self) -> None:
    """Render the Run History tab with chart, flaky tests, and comparison."""
    from src.run_result_persistence import (
        compare_latest_runs,
        get_flaky_tests,
        load_all_run_results,
    )
    from src.run_history_chart import build_run_history_chart
    
    runs = load_all_run_results()
    
    if not runs:
        st.info("No run history available. Run tests first to see trends here.")
        return
    
    # Scope selector
    packages = list(set(r.test_package for r in runs if r.test_package)) or ["All"]
    scope = st.selectbox("Scope", ["Current Package" if packages else "All"], 
                         key="run_history_scope")
    filtered_runs = self._filter_runs(runs, scope)
    
    # Chart
    fig = build_run_history_chart(filtered_runs, include_flaky_markers=True)
    st.plotly_chart(fig, use_container_width=True)
    
    # Flaky tests (expandable)
    flaky = get_flaky_tests(filtered_runs)
    with st.expanded(f"Flaky Tests ({len(flaky)})", len(flaky) > 0):
        if flaky:
            # Render as Streamlit table
            ...
        else:
            st.success("No flaky tests detected ✅")
    
    # Run comparison
    comparison = compare_latest_runs(directory=None)
    if comparison:
        with st.expanded("Last Run Comparison"):
            self._render_comparison(comparison)
```

**Comparison rendering:**
- Improved tests: green checkmark list
- Regressed tests: red warning list
- New failures: orange alert list

---

### 4. CLI Integration (`cli/run_results_display.py`)

**Changes:** After rendering single-run results, append the history summary:

```python
def display_run_results(...) -> None:
    # ... existing single-run display ...
    
    # NEW: Run history summary
    from src.run_history_cli import (
        format_run_history_table,
        format_flaky_tests_table,
        format_run_comparison,
    )
    from src.run_result_persistence import (
        compare_latest_runs,
        get_flaky_tests,
        load_all_run_results,
    )
    
    runs = load_all_run_results()
    if len(runs) > 1:
        print()
        print(format_run_history_table(runs, max_rows=10))
        flaky = get_flaky_tests(runs)
        if flaky:
            print(format_flaky_tests_table(flaky))
        comparison = compare_latest_runs()
        if comparison:
            print(format_run_comparison(comparison))
```

---

### 5. Export Service Verification (`src/export_service.py`)

**Check:** Ensure `evidence/run_results/` directory is included when exporting packages.

Current behavior: `export_service.py` copies `scrape_manifest.json` from the source package. Need to verify it also copies the `run_results/` subdirectory so historical data travels with exported packages.

**If not included:** Add logic to copy `evidence/run_results/` into the export directory alongside other evidence artifacts.

---

## File Structure

```
New files:
  src/run_history_chart.py                        # Plotly Figure factory
  src/run_history_cli.py                          # ASCII table renderer
  tests/test_run_history_chart.py                 # Chart builder unit tests
  tests/test_run_history_cli.py                   # CLI renderer tests

Updated files:
  src/ui_renderers.py                             # + Run History tab in EvidenceViewer
  cli/run_results_display.py                      # + History summary section
  src/export_service.py                           # + run_results/ in exports (if needed)

Documentation:
  docs/specs/FEATURE_SPEC_AI011_run_history_chart.md  # This file
  docs/plans/ROADMAP_ROADTO_PRODUCTION.md             # Status update: [x] Complete
```

---

## Protected Files

No protected files are modified. All changes are in:
- `src/ui_renderers.py` — UI rendering only, no pipeline logic
- `cli/run_results_display.py` — CLI display only, no session logic
- `src/export_service.py` — Export path addition only

---

## Test Summary

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_run_history_chart.py` | ~8 | Chart builder edge cases, data mapping |
| `tests/test_run_history_cli.py` | ~6 | ASCII formatting, truncation, empty states |
| **Total** | **~14** | **New modules fully tested** |

Integration verification: EvidenceViewer tab renders without errors when no run history exists (empty state test).

---

## Verification Criteria

- [x] `ruff check src/run_history_chart.py src/run_history_cli.py` — clean
- [x] `mypy src/run_history_chart.py src/run_history_cli.py` — clean
- [x] `pytest tests/test_run_history_chart.py tests/test_run_history_cli.py -v` — 29 pass
- [x] Full test suite: `pytest -x -q` — 1166 passed, 1 skipped, no regressions
- [x] Streamlit UI: Run History tab renders with scope selector, chart, flaky tests, comparison
- [x] CLI: History summary displays after test run with 2+ runs
- [x] Empty state: Graceful message when no runs exist
- [x] Export: run_results/ included in exported packages (verified existing behavior)

**Session notes:**
- Run single-process (`pytest -x -q`) to avoid VS Code crashes with parallel xdist workers
- `_render_run_history()` uses `st.expander()` (not `st.expanded()`), `compare_runs()` (not `compare_latest_runs()`)
- Scope selector filters by package: "Current Package" default, "All Runs" option
- Flaky tests shown in expandable section with pass/fail counts and flakiness score
- Run comparison shows improved/regressed/new_failures between last 2 runs

---

## Estimated Effort

**Actual: 2 sessions (~3 hours total):**
- Session 1: `src/run_history_chart.py` (10 tests) + `src/run_history_cli.py` (19 tests)
- Session 2: Streamlit tab integration (`src/ui_renderers.py`), CLI integration verification, export verification
- ruff → mypy → pytest (single-process) → commit

---

*Last updated: 2026-06-12*
