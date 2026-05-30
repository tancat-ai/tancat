# report_formatters.py

## Purpose
Renders test execution reports in three output formats: local Markdown, Jira Markdown, and base64-embedded HTML. Includes failure diagnostics section with page URL, failure note, suggested alternatives, and screenshot paths.

## Location
`src/report_formatters.py`

## Dependencies
- `src.report_builder` — consumes report dicts built by pipeline_report_service
- `src.evidence_loader` — loads evidence JSON for diagnostics enrichment

## Public API

### `format_local_markdown(report: dict[str, Any], evidence_data: dict | None = None) -> str`
Generate a local Markdown report with test results, pass/fail summary, and failure diagnostics section.

### `format_jira_markdown(report: dict[str, Any], evidence_data: dict | None = None) -> str`
Generate a Jira-formatted Markdown report using Jira-compatible syntax (code blocks, tables, macros).

### `format_html(report: dict[str, Any], evidence_data: dict | None = None) -> str`
Generate an HTML report with embedded base64 screenshots for self-contained viewing.

## Design Notes
- All formatters accept a `report` dict produced by `report_builder.py`
- Evidence data is optional; when absent, failure diagnostics section is omitted
- HTML formatter embeds screenshots as base64 data URIs for portability
- Jira formatter uses Jira wiki markup conventions

## Related Files
- `src/report_builder.py` — produces report dicts consumed by formatters
- `src/evidence_loader.py` — provides evidence data for diagnostics
- `src/pipeline_report_service.py` — orchestrates report generation pipeline