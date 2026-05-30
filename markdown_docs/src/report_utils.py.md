# report_utils.py

## Purpose
Shared utility functions for report generation — path resolution, file I/O, and evidence data merging used across report builder and formatters.

## Location
`src/report_utils.py`

## Dependencies
- Standard library: `os`, `pathlib`, `json`

## Public API

### `ensure_screenshot_dir(path: str) -> None`
Create the screenshot output directory if it does not exist.

### `load_evidence_json(test_path: str) -> dict | None`
Load evidence JSON from a test package directory. Returns `None` when no evidence file exists.

### `merge_evidence_into_report(report: dict[str, Any], evidence: dict) -> dict[str, Any]`
Merge evidence data (failure notes, screenshots, diagnoses) into a report dict, producing an enriched report ready for formatting.

### `format_test_status(passed: bool) -> str`
Return a human-readable status label ("✅ PASSED" / "❌ FAILED").

## Design Notes
- Pure utility functions — no side effects except `ensure_screenshot_dir`
- Used by both `report_builder.py` and `report_formatters.py`
- Evidence merging preserves existing report fields while adding diagnostics keys

## Related Files
- `src/report_builder.py` — uses utilities for evidence merging
- `src/report_formatters.py` — uses utilities for status formatting
- `src/evidence_loader.py` — sibling evidence module