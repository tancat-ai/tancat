# `src/report_builder.py`

## High-Level Purpose
Builds structured report dictionaries by merging pytest results, evidence data, and failure diagnostics into a unified report format.

## Module Metadata
- **Lines:** ~300
- **Imports:** `dataclasses`, `typing`, `src.pytest_output_parser`, `src.evidence_loader`, `src.failure_classifier`

## Classes

### `ReportData` (dataclass)
Unified report structure: suite summary, per-test results, evidence references, failure diagnostics.

### `TestReportEntry` (dataclass)
Single test entry: test_id, status, duration, evidence_data, failure_note, screenshots.

## Functions

### `build_report(suite_summary: SuiteSummary, test_dir: str) -> ReportData`
Main builder — merges pytest results with evidence JSON sidecar data.

### `merge_evidence(test_id: str, evidence: dict) -> TestReportEntry`
Merges runtime evidence (failure_note, diagnosis, screenshots) into test entry.

### `classify_failures(report: ReportData) -> dict[str, int]`
Groups failures by error type and returns classification counts.

## Key Design Decisions
- Evidence loading deferred until report build time (lazy)
- Report data is format-agnostic — formatters handle rendering
- Failure classification uses error type hierarchy

## Dependencies
- `src.pytest_output_parser`, `src.evidence_loader`, `src.failure_classifier`