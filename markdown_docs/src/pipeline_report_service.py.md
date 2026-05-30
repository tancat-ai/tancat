# `src/pipeline_report_service.py`

## High-Level Purpose

Build report artifacts for generated pipeline test packages. Orchestrates coverage analysis and report generation in three formats (local MD, Jira MD, HTML), then saves them into the test package directory.

## Module Metadata

- **Lines:** 69
- **Imports:** `dataclasses.dataclass`, `pathlib.Path`, `src.coverage_utils`, `src.pytest_output_parser.RunResult`, `src.report_utils`

## Data Classes

### `PipelineReportBundle` (frozen)
Report content and saved paths for one pipeline run.
- `coverage_rows: list[dict]` — Per-criterion coverage rows
- `local_report: str` — Local markdown report
- `jira_report: str` — Jira markdown report
- `html_report: str` — HTML report
- `local_report_path: str` — Absolute path to saved local report (empty if no package_dir)
- `jira_report_path: str` — Absolute path to saved Jira report
- `html_report_path: str` — Absolute path to saved HTML report

## Class: `PipelineReportService`

### `build_reports(criteria_text, generated_code, run_result, package_dir="") -> PipelineReportBundle`
1. Parse criteria lines from `criteria_text`
2. Build coverage analysis via `build_coverage_analysis`
3. Build report dicts via `build_report_dicts` (merges coverage with pytest results)
4. Generate three report formats
5. If `package_dir` given, save all three reports to disk and record paths
6. Return `PipelineReportBundle`

## Dependencies

- `src.coverage_utils.build_coverage_analysis`
- `src.pytest_output_parser.RunResult`
- `src.report_utils.build_report_dicts`, `generate_html_report`, `generate_jira_report`, `generate_local_report`

## Depended On By

`orchestrator.py`, `ui_pipeline.py`, `cli/pipeline_runner.py`