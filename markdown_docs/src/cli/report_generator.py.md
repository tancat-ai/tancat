# `src/cli/report_generator.py` — Report Generator

## Purpose

Generates test execution reports in multiple formats: Confluence-compatible HTML, Jira XML, JSON, and Markdown. Used by CLI for legacy report generation (new pipeline uses `PipelineReportService`).

## Data Classes

### `JiraTestCase`

| Field | Type | Description |
|-------|------|-------------|
| `key` | `str` | Unique Jira key (e.g., `TEST-TC-0001`) |
| `summary` | `str` | Test case title |
| `description` | `str` | Full description |
| `test_steps` | `str` | Formatted HTML test steps |
| `expected_results` | `str` | Formatted HTML expected results |
| `screenshots` | `list[str]` | Screenshot paths |
| `execution_status` | `str` | `UNEXECUTED`, `PASSED`, `FAILED`, `BLOCKED`, `SKIPPED` |
| `attachments` | `list[str]` | File attachments |
| `custom_fields` | `dict` | Extra metadata (e.g., `failure_reason`) |

- `to_dict() -> dict` — Serialises for JSON output.

### `TestExecutionResult`

| Field | Type | Description |
|-------|------|-------------|
| `test_case` | `AnalyzedTestCase` | The analysed test case |
| `execution_time` | `float` | Duration in seconds |
| `status` | `str` | `PASSED`, `FAILED`, `BLOCKED`, `SKIPPED` |
| `failure_reason` | `str | None` | Root cause of failure |
| `screenshots` | `list[str]` | Screenshot paths |
| `console_logs` | `list[str]` | Console log entries |
| `network_errors` | `list[str]` | Network error entries |

## Class: `JiraReportGenerator`

### `__init__(output_dir="jira_reports")`

Creates output directory if it doesn't exist.

### `create_test_case(analyzed_case, screenshot_paths=None) -> JiraTestCase`

Converts an `AnalyzedTestCase` to a `JiraTestCase` with formatted steps and expectations.

### `add_execution_result(test_case, result) -> None`

Attaches execution status and screenshots to a test case.

### `generate_confluence_html(output_path) -> str`

Generates a Confluence-compatible HTML report with:
- Summary section (total/passed/failed/skipped counts)
- Per-test case cards with status colours
- Embedded screenshot references

### `generate_jira_xml(output_path) -> str`

Generates XML for Jira import with CDATA-wrapped descriptions.

### `save_test_cases(format: ReportFormat) -> str`

Routes to format-specific output:

| Format | Output |
|--------|--------|
| `CONFLUENCE` | HTML report |
| `JIRA_XML` | XML for Jira import |
| `JSON` | Structured JSON |
| `MARKDOWN` | Markdown document |
| `LOCAL` | HTML (same as Confluence) |
| `JIRA` | Markdown (Jira-friendly) |
| `SHAREABLE` | Markdown (shareable format) |
