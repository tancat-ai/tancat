# cli/report_generator.py

## Purpose

Generates test reports for CLI workflows, including Jira-compatible output and markdown/html export.

## Key classes

### `JiraTestCase`
- Fields: `key`, `summary`, `description`, `test_steps`, `expected_results`, `screenshots`, `execution_status`, `attachments`, `custom_fields`
- Method: `to_dict() -> dict`

### `TestExecutionResult`
- Fields: `test_case`, `execution_time`, `status`, `failure_reason`, `screenshots`, `console_logs`, `network_errors`
- Method: `to_dict() -> dict`

### `JiraReportGenerator`
- Constructor: `__init__(self, output_dir: str = "jira_reports") -> None`
- Public methods:
  - `create_test_case(analyzed_case: AnalyzedTestCase, screenshot_paths: list[str] | None = None) -> JiraTestCase`
  - `add_execution_result(test_case: JiraTestCase, result: TestExecutionResult) -> None`
  - `generate_confluence_html(output_path: str) -> str`
  - `generate_jira_xml(output_path: str) -> str`
  - `save_test_cases(format: ReportFormat = ReportFormat.CONFLUENCE) -> str`

- Internal methods:
  - `_format_test_steps(analyzed_case: AnalyzedTestCase) -> str`
  - `_format_expected_results(analyzed_case: AnalyzedTestCase) -> str`
  - `_save_json(output_path: str) -> str`
  - `_save_local(output_path: str) -> str`
  - `_save_markdown(output_path: str) -> str`
  - `_save_jira_markdown(output_path: str) -> str`
  - `_save_shareable_markdown(output_path: str) -> str`

## Notes

- Produces Confluence-compatible HTML as the default format.
- Also supports Jira XML, JSON, plain markdown, and shareable markdown exports.
- Formats test step and expectation content for human-readable export.
