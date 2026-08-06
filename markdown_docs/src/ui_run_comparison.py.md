# `src/ui/ui_run_comparison.py`

## Purpose
Run comparison view on the Evidence & Reports page — pick a package and two persisted runs, and see per-test status deltas (Changed / Fixed / Regressed). Uses `run_result_persistence` data; added 2026-08-06.

## Metadata
- **Lines:** ~110
- **Imports:** re, streamlit, src.pipeline_artifact_manager, src.run_result_persistence, src.storage

## Classes
- **`RunComparison`**: renders the package selector, Run A / Run B pickers, the delta table, and summary metrics. Filters runs by package (`load_all_run_results` ignores its directory argument).

## Functions
| Function | Description |
|----------|-------------|
| `_run_label(run)` | Human-readable run label (date/time · passed/failed counts) |
| `_delta_icon(sa, sb)` | Status delta: `=` unchanged, `⬆ fixed`, `⬇ regressed`, `↔ changed` |
| `_status_label(run)` | Short `passed✓/failed✗` label for the table columns |

## Notes
- Runs must be **persisted** (UI-driven runs via Run & Fix persist; raw CLI pytest runs do not) — the view says so when a package has fewer than two runs.
