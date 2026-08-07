# `src/ui/ui_run_comparison.py` — Run Comparison View

## Purpose

Streamlit component (Evidence & Reports page) that lets a user pick a package and two of its persisted runs, then shows per-test status deltas (Changed / Fixed / Regressed) so regression and fix history are visible without opening raw sidecars.

## Class: `RunComparison`

### `__init__()`

Initialises with the workspace `generated_tests/` directory via `get_storage()`.

### `render() -> None`

Renders the "🔀 Compare Runs" section:

1. Lists packages via `find_existing_packages()`; a `selectbox` picks one.
2. Loads **all** persisted runs (`load_all_run_results()` ignores its directory arg) and filters by `test_package` suffix match against the selected package name (Windows-path tolerant).
3. Requires ≥ 2 runs for the package, else shows an info hint to run the suite from Run & Fix.
4. Two run pickers (`Run A` / `Run B`, newest-first labels) and a per-test delta table:
   - `_delta_icon(sa, sb)` classifies each test as `=` unchanged, `⬆ fixed` (now passed), `⬇ regressed` (now failed), `↔ changed` (any other status flip)
   - counts by delta type (`fixed` / `regressed` / `changed`) shown as summary metrics

## Helper Functions

### `_run_label(run: PersistedRunResult) -> str`

Human-readable run label from the ISO-8601 `run_id` (e.g. `08-06 14:30 · 9✓ 2✗ ⏭ / 12`), including pass/fail/skip/total counts.

### `_status_label(run: PersistedRunResult) -> str`

Short status summary string for a run used in the delta table header.

## Integration Points

| Consumer | Integration |
|----------|-------------|
| `src/ui/ui_results.py` / Run & Fix page | Renders the comparison panel on the Evidence & Reports page |
| `src/pipeline_artifact_manager.py` | `find_existing_packages()` supplies the package list |
| `src/run_result_persistence.py` | `load_all_run_results()` supplies persisted runs |

## Design Notes

- **Filtering is in-memory, not SQL** — `load_all_run_results` ignores its `directory` argument, so runs are filtered by `test_package` suffix in Python (documented in the source, B-043 adjacent).
- Pure Streamlit rendering — no testable business logic lives here (per AGENTS.md, logic belongs in `src/` testable modules).
