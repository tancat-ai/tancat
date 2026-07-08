
# cli/color.py

## Purpose

ANSI color helper functions for CLI output. Wraps text in ANSI escape codes when stdout is a TTY and falls back to plain text otherwise.

## Public functions

- `_c(text: str, code: str) -> str`
  - Internal helper that applies an ANSI color code when stdout is a terminal.

- `cyan(text: str) -> str`
- `green(text: str) -> str`
- `red(text: str) -> str`
- `yellow(text: str) -> str`
- `bold(text: str) -> str`

- `phosphor_green(text: str) -> str`
  - Bright green used for selected/highlighted menu items.

- `dim_green(text: str) -> str`
  - Dim green used for non-selected items.

- `inverse_green(text: str) -> str`
  - Inverse-video green used for the cursor indicator.

- `phosphor_reset() -> str`
  - Returns the ANSI reset code as a standalone string.

## Notes

- Uses `os.isatty(1)` to detect terminal output.
- Catches exceptions to avoid failure when stdout is redirected or not available.





# cli/config.py

## Purpose

Compatibility shim that re-exports CLI-related enums and constants from `src.config`.

## Exports

- `AnalysisMode`
- `CaptureLevel`
- `DetectionMode`
- `ReportFormat`
- `ScreenshotNaming`
- `JIRA_PROJECT_KEY`

## Implementation details

- Imports the values directly from `src.config`.
- Defines `__all__` to preserve the public CLI API surface for legacy imports.





# cli/evidence_generator.py

## Purpose

Handles screenshot capture and evidence generation for CLI-driven test execution.
Provides metadata, reporting, and packaging of screenshots and bug evidence.

## Key classes

### `ScreenshotMetadata`
- Fields: `test_case_id`, `timestamp`, `file_path`, `capture_stage`, `description`, `file_size`, `dimensions`
- Method: `to_dict() -> dict`

### `EvidenceCollection`
- Fields: `screenshots`, `videos`, `console_logs`, `network_requests`
- Method: `to_dict() -> dict`

### `ScreenshotCapturer`
- Purpose: capture screenshots and save them to disk.
- Constructor: `__init__(self) -> None`
- Public method: `capture(page: Any, test_case: AnalyzedTestCase, capture_stage: str, step_description: str = "") -> str | None`
- Internal methods:
  - `_generate_filename(test_case, capture_stage, step_description) -> str`
  - `_save_screenshot(screenshot_bytes, filename, test_title) -> str`
  - `_get_screenshot_dimensions(screenshot_bytes) -> tuple`
  - `_generate_case_id(title) -> str`

### `EvidenceGenerator`
- Purpose: collect evidence during test execution, summarize it, create reports, and archive artifacts.
- Constructor: `__init__(self, capture_level: CaptureLevel | None = None) -> None`
- Public methods:
  - `capture_test_evidence(page, test_case, capture_stage='step', step_description='') -> str | None`
  - `generate_evidence_summary() -> dict`
  - `generate_evidence() -> None`
  - `create_visual_report(output_path: str, test_cases: list[AnalyzedTestCase]) -> str`
  - `create_evidence_zip(output_path: str) -> str`
- Internal methods:
  - `_should_capture(capture_stage: str) -> bool`
  - `_generate_html_report(test_cases) -> str`

### `BugEvidenceGenerator`
- Purpose: capture bug reproduction evidence separately from normal test evidence.
- Methods:
  - `capture_bug_evidence(page, description: str) -> dict`
  - `generate_bug_report(output_path: str) -> str`

## Notes

- Uses optional Pillow support (`PIL_AVAILABLE`) to obtain screenshot dimensions.
- Reads capture settings from `src.config` and CLI `CaptureLevel`.
- Generates HTML, ZIP archives, and plain-text bug reports.





# cli/input_parser.py

## Purpose

Parses multiple input formats into normalized test cases for the CLI pipeline.
Supports Jira-style text, Gherkin, bullet lists, plain text, and JSON input.

## Key dataclasses

### `TestCase`
- Fields: `title`, `description`, `preconditions`, `test_data`, `expected_outcome`, `test_type`, `priority`
- Method: `to_dict() -> dict`
- Method: `to_prompt() -> str`

### `ParsedInput`
- Fields: `test_cases`, `source_format`, `raw_input`, `metadata`
- Methods: `to_dict() -> dict`, `save_to_json(output_path: str) -> str`

## Format detection

### `FormatDetector`
- Public:
  - `detect(text: str, method: DetectionMode = DetectionMode.AUTO) -> tuple[str, float]`
- Uses regex patterns for:
  - `jira`
  - `gherkin`
  - `bullets`
  - `plain_text`

## Parsers

### `PlainTextParser`
- Extracts user story style sentences and falls back to a single scenario when no structured patterns are found.
- Methods:
  - `parse(text: str) -> list[TestCase]`
  - `_extract_test_case(text: str) -> TestCase`

### `JiraParser`
- Parses Jira-style issue metadata, description, and acceptance criteria.
- Methods:
  - `parse(text: str) -> list[TestCase]`
  - `_extract_from_acceptance_criteria(ac_text: str, metadata: dict) -> list[TestCase]`
  - `_determine_test_type(line: str) -> str`
  - `_generate_title(line: str, metadata: dict) -> str`
  - `_determine_priority(line: str) -> str`

### `GherkinParser`
- Parses Feature/Scenario/Given-When-Then text into test cases.
- Methods:
  - `parse(text: str) -> list[TestCase]`
  - `_extract_scenarios(text: str) -> list[dict]`
  - `_extract_steps(steps_text: str) -> list[dict]`
  - `_scenario_to_test_case(scenario: dict) -> TestCase`

### `BulletParser`
- Parses bullet lists and numbered criteria into test cases.
- Methods:
  - `parse(text: str) -> list[TestCase]`
  - `_generate_title(line: str) -> str`
  - `_determine_test_type(line: str) -> str`

## Main parser

### `InputParser`
- Constructor: `__init__(self, detection_method: DetectionMode | None = None) -> None`
- Methods:
  - `parse(text: str, explicit_format: str | None = None) -> ParsedInput`
  - `parse_json(json_str: str) -> ParsedInput`
  - `parse_and_save(text: str, output_dir: str | None = None) -> str`
- Convenience functions:
  - `parse_jira_format(text: str) -> list[TestCase]`
  - `parse_gherkin_format(text: str) -> list[TestCase]`
  - `parse_bullet_format(text: str) -> list[TestCase]`
  - `parse_plain_text(text: str) -> list[TestCase]`

## Notes

- `parse_json` supports both array and object payloads.
- The parser adds detection metadata including confidence and timestamp.





# cli/main.py

## Purpose

Interactive CLI entry point for the AI Playwright Test Generator.
Provides a classic menu-driven flow as well as legacy command-line compatibility.

## Key functions

### Interactive Session

- `interactive_session() -> None`:
  - Drives the main menu loop.
  - Builds available menu options based on session state.
  - Routes user actions to configuration, story input, URL input, authentication, journey builder, plan review, pipeline execution, report viewing, test execution, and package persistence commands.

### Inline Input Collectors

- `_configure_llm_inline(session: Session) -> None`
- `_collect_user_story_inline(session: Session) -> None`
- `_collect_urls_inline(session: Session) -> None`
- `_collect_authentication_inline(session: Session) -> None`
- `_collect_journey_inline(session: Session) -> None`

### Package Persistence (AI-026 â€” Step 4)

- `_handle_load_existing_packages(session: Session) -> None`:
  - Discovers previously generated test packages via `load_existing_packages()`.
  - Renders selectable list of packages with metadata (name, date, test count, run count).
  - Loads selected package manifest and run history into session state.

- `_handle_show_package_metadata(session: Session) -> None`:
  - Displays structured metadata table for the currently loaded package.
  - Shows run history summary and flakiness report when available.

- `_handle_rerun_saved_suite(session: Session) -> None`:
  - Re-runs tests from the loaded package without re-triggering the LLM pipeline.
  - Uses `run_saved_test_from_package()` to execute saved test files.

- `_handle_view_saved_diagnostics(session: Session) -> None`:
  - Displays failure diagnostics for a loaded saved package (AI-026 Step 6).
  - Uses `view_saved_package_diagnostics()` to load and display evidence from disk.
  - Shows report paths, evidence files, and per-test failure details.

### Legacy CLI Commands

- `cmd_generate(args: Any, parser: Any) -> int`
  - Legacy parameter-based generation path.
  - Parses input from CLI arguments or files, runs analysis, generates tests, captures evidence, and creates reports.

- `run_analysis(parsed: Any) -> Any`
- `run_generation(parsed: Any, output_dir: str, url: str | None = None) -> None`
- `run_evidence_generation(output_dir: str) -> None`
- `generate_reports_legacy(parsed: Any, analysis_result: Any, output_dir: str) -> None`

### Entry Point

- `main() -> int`
  - Argument parser entry point.
  - Supports interactive mode by default.
  - Provides legacy `generate`, `test`, and `help` subcommands.

## Menu Options

The main menu provides the following options (numbered):

1. Configure LLM Provider & Model
2. Enter User Story
3. Configure Target URL(s)
4. **Load Existing Generated Tests** â€” discovers and loads saved packages (AI-026)
5. **Show Saved Package Metadata** â€” displays loaded package details (AI-026)
6. **Re-run Saved Suite** â€” re-executes tests from loaded package (AI-026)
7. Generate & Run Tests
8. Run Saved Tests
9. View Report
10. View Failure Diagnostics
11. **View Saved Package Diagnostics** â€” displays evidence for loaded package (AI-026)
12. Exit

## Implementation details

- Forces UTF-8 output on Windows and Git Bash for box-drawing characters.
- Loads `.env` if available via `python-dotenv`.
- Reuses `cli.menu_renderer` for UI prompts and `cli.pipeline_runner` for pipeline execution.
- Keeps backward compatibility while exposing the newer interactive flow.
- Package persistence state stored in `Session.loaded_package_manifest` and `Session.loaded_package_run_results`.





# cli/menu_renderer.py

## Purpose

Renders the retro CLI menu system and collects user input for the interactive flow.
Implements CHOICE-inspired UI behavior, model selection, user story entry, URL collection, consent mode, authentication, journey building, and package persistence displays.

## Public API

### Core Menu Functions

- `print_header(title: str, subtitle: str = "") -> None`
- `print_menu(options: list[str], prompt: str = "Choose an option", shortcuts: list[tuple[str, str]] | None = None) -> int`
- `read_non_empty(prompt_text: str) -> str`
- `read_optional(prompt_text: str, default: str = "") -> str`

### Configuration Collectors

- `configure_llm(provider: str, base_url: str, model_name: str) -> tuple[str, str, str]`
- `collect_user_story() -> str`
- `collect_urls() -> tuple[str, str]`
- `collect_consent_mode() -> str`
- `collect_authentication() -> dict[str, str] | None`
- `collect_journey_steps() -> list[dict[str, str]]`

### Package Persistence Rendering (AI-026 â€” Step 4)

- `render_saved_package_list(packages: list[PackageManifest]) -> None`:
  - Renders a numbered list of discovered saved packages with key metadata.
  - Each entry shows: package name, created date, test file count, and run result count.
  - Used by `load_existing_packages()` in `cli/pipeline_runner.py`.

- `render_package_metadata(manifest: PackageManifest, run_results: list[dict] | None = None) -> None`:
  - Displays a structured metadata table for a loaded package.
  - Shows: package name, created date, source story, starting URL, provider, model, test files, page objects.
  - Optionally includes run history summary (aggregated pass/fail/skip counts) and flakiness report.
  - Used by `_handle_show_package_metadata()` in `cli/main.py`.

- `render_package_run_history(run_results: list[dict]) -> None`:
  - Renders a run-by-run table showing test outcomes across multiple executions.
  - Columns: Run #, Passed, Failed, Skipped, Duration, Timestamp.
  - Highlights flaky tests (tests that alternate between pass/fail across runs).
  - Used alongside `render_package_metadata()` for the "Show Saved Package Metadata" command.

### Utility

- `open_file(path: str) -> None`

## Helper functions

- `_get_available_models(provider_name: str, provider_url: str) -> list[str]`
- `_default_model(provider: str) -> str`
- `_get_baseline_text() -> str`

## Notes

- Supports model provider auto-detection for Ollama, LM Studio, OpenAI local, and OpenAI cloud.
- Handles pasted multi-line input and file uploads for user stories.
- Preserves keyboard shortcuts and menu navigation across different terminal environments.
- Includes a built-in baseline user story for automationexercise.com.
- Package persistence renderers delegate data fetching to `src.pipeline_artifact_manager.py` and `src.run_result_persistence.py` â€” this module only handles display formatting.





# cli/pipeline_runner.py

## Purpose

Executes the intelligent pipeline and manages generated test execution and reporting from the CLI.
Provides glue between session state and core pipeline services.

## Key functions

### Pipeline Execution

- `parse_requirements(raw: str) -> tuple[str, str]`
  - Extracts the user story and acceptance criteria from raw requirements text.

- `build_test_plan(session: Any) -> None`
  - Uses `src.llm_client.LLMClient` and `src.spec_analyzer.SpecAnalyzer` to derive a living test plan.
  - Displays conditions and prompts for sign-off.

- `run_pipeline(session: Any) -> None`
  - Validates session data.
  - Runs `src.orchestrator.TestOrchestrator` to generate tests.
  - Persists artifacts via `PipelineArtifactWriter`.

- `run_generated_tests(session: Any, rerun_failed: bool = False) -> None`
  - Executes generated tests using `PipelineRunService`.

- `display_run_results(session: Any) -> None`
  - Prints pytest summary metrics using structured run results display.

- `generate_reports(session: Any) -> None`
  - Builds local, Jira, and HTML reports using `PipelineReportService`.

- `parse_target_urls(base_url: str, urls_input: str) -> list[str]`
  - Normalizes the starting URL and additional URLs.

### Package Persistence (AI-026 â€” Step 4)

- `load_existing_packages(session: Session) -> None`:
  - Discovers previously generated test packages in `generated_tests/` directory.
  - Uses `src.pipeline_artifact_manager.find_existing_packages()` for discovery.
  - Renders a numbered list via `render_saved_package_list()` from `cli.menu_renderer`.
  - User selects a package index â†’ loads manifest via `load_package_manifest()` and run history via `load_all_run_results()`.
  - Populates `session.loaded_package_manifest` and `session.loaded_package_run_results`.

- `run_saved_test_from_package(session: Session) -> None`:
  - Re-runs tests from a previously loaded package without re-triggering the LLM pipeline.
  - Uses `src.pipeline_run_service.run_saved_test()` with the package's test files.
  - Supports `rerun_failed_only` option based on previous run results.
  - Updates session with new run results and displays structured output.

- `view_saved_package_diagnostics(session: Session) -> None`:
  - Displays failure diagnostics for a previously loaded saved package (AI-026 Step 6).
  - Loads `package_manifest.json` to retrieve report paths and evidence paths.
  - Scans `evidence/` subdirectory for `*.evidence.json` files matching test names.
  - Shows report locations, evidence file count, and per-test failure details.
  - For each failed step: displays locator, error message, and diagnosis data.
  - Extends existing `view_failure_diagnostics()` to work with loaded packages on disk.

## Notes

- Runs the same test generation pipeline as the Streamlit app for feature parity.
- Saves generated test artifacts and report paths into the CLI session object.
- Contains both sign-off gating and fallback logic when the plan is not confirmed.
- Package persistence functions delegate to `src.pipeline_artifact_manager.py` for manifest I/O and `src.run_result_persistence.py` for run history.





# CLI Documentation Summary

This directory documents the `cli/` package for the AI Playwright Test Generator.

## Purpose of the CLI package

The CLI package provides an interactive command-line interface and legacy compatibility layer for:

- configuring LLM providers
- collecting user stories and target URLs
- building living test plans
- running the AI test generation pipeline
- executing generated tests
- generating reports and evidence
- displaying failure diagnostics

## Major modules

- `cli/main.py` â€” interactive entry point and legacy command parser
- `cli/menu_renderer.py` â€” retro terminal menu and input collection
- `cli/retro_ui.py` â€” box-drawing UI rendering primitives
- `cli/session.py` â€” CLI session state and environment-backed defaults
- `cli/pipeline_runner.py` â€” pipeline execution, run management, and report lifecycle
- `cli/input_parser.py` â€” multi-format requirement parsing
- `cli/test_case_orchestrator.py` â€” legacy test case orchestration
- `cli/evidence_generator.py` â€” screenshot/evidence capture and packaging
- `cli/report_generator.py` â€” Jira and markdown report generation
- `cli/color.py` â€” ANSI styling helpers
- `cli/config.py` â€” backwards-compatible re-export of shared config values

## Notes

- The CLI shares pipeline behavior with the Streamlit app by invoking core services from `src/`.
- The interactive flow is designed for terminal users, with special handling for Windows Git Bash and ANSI compatibility.
- Legacy CLI commands are retained for backward compatibility while the interactive menu remains the primary experience.





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





# cli/retro_ui.py

## Purpose

Renders the CHOICE-inspired retro terminal UI used by the CLI.
Handles low-level screen control, box-drawing layout, and text styling.

## Key functions

- `clear_screen() -> None`
- `move_cursor(x: int = 0, y: int = 0) -> None`
- `hide_cursor() -> None`
- `show_cursor() -> None`

- `render_header(title: str, subtitle: str = "") -> None`
- `render_menu(items: Sequence[str], selected: int = 0, group_labels: list[str] | None = None) -> None`
- `render_state(state_lines: list[str]) -> None`
- `render_shortcut_bar(shortcuts: list[tuple[str, str]]) -> None`
- `render_separator() -> None`
- `render_status_bar(message: str, shortcuts: list[tuple[str, str]] | None = None) -> None`

- `prompt_input(prompt_text: str, default: str = "") -> str`

## Internal helpers

- `_green(text: str, bright: bool = False) -> str`
- `_dim(text: str) -> str`
- `_bold(text: str) -> str`
- `_inverse(text: str) -> str`
- `_visible_len(text: str) -> int`
- `_terminal_width() -> int`
- `_effective_width() -> int`

## Notes

- Uses ANSI escape codes and only applies them when stdout is a TTY.
- Supports safe output when terminal size cannot be determined.
- Provides a retro green-on-black interface for the CLI.





# cli/run_results_display.py

**Path:** `cli/run_results_display.py`  
**Created:** 2026-06-02  
**Status:** Stable â€” part of Run Results feature (AI-008)

---

## Overview

Provides structured, ANSI-colored CLI output for pytest run results. This module fills Gap 1 of the Run Results feature spec ([FEATURE_SPEC_run_results.md](../../docs/specs/FEATURE_SPEC_run_results.md)), bringing CLI run output to parity with the Streamlit UI's `RunResultsDisplay`.

## Purpose

When the CLI executes tests via `PipelineRunService.run_saved_test()`, it receives a `RunResult` object. Previously, this data was not presented in a structured way in the CLI â€” users saw raw pytest output. This module renders:
- A colored metrics summary line
- An ASCII table of per-test results
- Failure classification with actionable suggestions
- Optional raw pytest output view

## Dependencies

| Import | Source | Purpose |
|--------|--------|---------|
| `src.pytest_output_parser.RunResult` | `src/pytest_output_parser.py` | Dataclass containing test results |
| `src.pytest_output_parser.TestResult` | `src/pytest_output_parser.py` | Individual test result dataclass |
| `src.failure_classifier` | `src/failure_classifier.py` | `classify_failure()` and `FailureCategory` enum |
| `cli.color` | `cli/color.py` | ANSI color helper functions |

## Type Signatures

```python
def render_run_metrics(run: RunResult) -> None
def render_results_table(run: RunResult) -> None
def render_failure_details(run: RunResult) -> None
def render_raw_output(run: RunResult, expanded: bool = False) -> None
def render_run_results(run: RunResult, show_raw: bool = True) -> None
def _status_badge(status: str) -> str
def _suggestion_for_category(category: FailureCategory) -> str
```

## Functions

### `render_run_metrics(run: RunResult) -> None`

Renders a single-line colored summary of run outcomes.

**Format:** `ðŸŽ¯ Run Results: {pass_icon} Passed: X  {fail_icon} Failed: Y  {error_icon} Errors: Z  {skip_icon} Skipped: W â€” Duration: X.Xs`

**Color coding:**
- Pass count: green
- Fail count: red
- Error count: yellow
- Skipped count: cyan
- Duration: bold

**Example output:**
```
  ðŸŽ¯ Run Results:  âœ… Passed: 5  âŒ Failed: 1  âš ï¸ Errors: 0  â­ï¸ Skipped: 0 â€” Duration: 12.34s
```

### `render_results_table(run: RunResult) -> None`

Renders an ASCII table with columns: Test Name, Status Badge, Duration.

**Table format:**
```
  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  Test Name                    Status   Duration
  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  test_01_login_page_...       [PASS]   0.50s
  test_02_add_to_cart_...      [FAIL]   1.23s
                               AssertionError: Expected 'OK'...
  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
```

**Truncation rules:**
- Test names truncated to 30 chars with `...` suffix
- Error messages truncated to 80 chars with `...` suffix
- Max 3 error message lines shown per test

### `render_failure_details(run: RunResult) -> None`

Classifies each failed test using `classify_failure()` and displays categorized failures with suggestions.

**Format:**
```
  ðŸ” Failure Classification:
  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  â€¢ test_timeout (locator_timeout)
    Message: TimeoutError: waiting for locator('#btn')
    Suggestion: Check the locator exists on the page, or increase timeout

  â€¢ test_strict (strict_violation)
    Message: strict mode violation: resolved to 2 elements
    Suggestion: Use a more specific selector
  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
```

**Failure categories mapped (from `FailureCategory` enum):**
- `locator_timeout` â†’ "Check the locator exists on the page, or increase timeout"
- `strict_violation` â†’ "Use a more specific selector to avoid matching multiple elements"
- `navigation_error` â†’ "Check the URL is correct and the server is running"
- `assertion_failure` â†’ "Review the assertion â€” the page state may have changed"
- `other` â†’ "Review test output for details"

### `render_raw_output(run: RunResult, expanded: bool = False) -> None`

Optionally displays raw pytest output in a code block.

**Behavior:**
- If `expanded=True`: always show raw output
- If `expanded=False` and raw output exists: prompt user with "Show raw pytest output? [y/N]: "
- If no raw output: silently skip

### `render_run_results(run: RunResult, show_raw: bool = True) -> None`

Main entry point. Orchestrates all rendering functions in sequence:
1. Title separator
2. `render_run_metrics()`
3. `render_results_table()`
4. `render_failure_details()` (only if failures exist)
5. `render_raw_output()` (controlled by `show_raw`)
6. Bottom separator

### `_status_badge(status: str) -> str`

Internal helper. Maps test status strings to colored badge text.

| Status | Badge | Color |
|--------|-------|-------|
| `passed` | `[PASS]` | Green |
| `failed` | `[FAIL]` | Red |
| `error` | `[ERROR]` | Yellow |
| `skipped` | `[SKIP]` | Cyan |
| other | `[UNKNOWN]` | White |

### `_suggestion_for_category(category: FailureCategory) -> str`

Internal helper. Maps `FailureCategory` enum values to human-readable fix suggestions.

## Integration Points

### CLI Pipeline Runner

Called from `cli/pipeline_runner.py` after `PipelineRunService.run_saved_test()` returns:

```python
from cli.run_results_display import render_run_results

result = run_service.run_saved_test(...)
render_run_results(result.run_result, show_raw=False)
```

### Relationship to Streamlit UI

This module is the CLI equivalent of `src/ui_renderers.py` â†’ `RunResultsDisplay.render()`. Both consume the same `RunResult` type from `src/pytest_output_parser.py`, ensuring consistent output across interfaces.

## Design Decisions

1. **No dependency on Terminal classes** â€” Uses `print()` directly rather than `TestingTerminal.write()` to keep the module standalone and testable.
2. **Failure classification via existing module** â€” Reuses `src/failure_classifier.py` rather than duplicating logic.
3. **ANSI colors via `cli.color`** â€” Consistent with other CLI modules.
4. **Proportional column width** â€” Table adapts to terminal width (default 80, min 40).

## Testing

Covered by `tests/test_cli_run_results_display.py` (31 tests):
- Status badge rendering for all statuses
- Metrics line rendering (all passed, mixed, zero)
- Results table rendering (empty, single, long names, truncation)
- Failure classification (timeout, strict violation, assertion, navigation)
- Suggestion mapping for all categories
- Raw output display (expanded, interactive yes/no)
- Full integration tests (all passed, empty run)

## Error Handling

- Gracefully handles empty `RunResult` (0 tests) by displaying a "No test results" message
- Truncates long test names and error messages to prevent terminal overflow
- Strips trailing whitespace from error messages for clean output

## Related Files

- `src/pytest_output_parser.py` â€” `RunResult`, `TestResult` dataclasses
- `src/failure_classifier.py` â€” `classify_failure()`, `FailureCategory`
- `src/ui_renderers.py` â€” `RunResultsDisplay` (Streamlit equivalent)
- `cli/pipeline_runner.py` â€” Integration caller
- `cli/color.py` â€” ANSI color utilities

---

*Document created: 2026-06-02*





# cli/session.py

## Purpose

Defines the mutable session state for the interactive CLI flow.
Stores pipeline artifacts, LLM configuration, URLs, authentication, journey steps, reports, requirements, and package persistence data.

## Key dataclass

### `Session`
- Fields include:
  - `pipeline_results`, `pipeline_skeleton`, `pipeline_saved_path`, `pipeline_manifest_path`, `pipeline_error`
  - `pipeline_unresolved`, `pipeline_scraped_pages`, `pipeline_urls`, `pipeline_criteria`, `pipeline_conditions`
  - `pipeline_run_result`, `pipeline_run_output`, `pipeline_run_command`, `pipeline_run_return_code`
  - `pipeline_local_report`, `pipeline_jira_report`, `pipeline_html_report`, `pipeline_local_report_path`, `pipeline_jira_report_path`, `pipeline_html_report_path`
  - `test_plan`, `plan_confirmed`
  - `provider`, `provider_base_url`, `model_name`
  - `starting_url`, `additional_urls`, `consent_mode`, `raw_requirements`
  - `credential_profile`, `journey_steps`

### Package Persistence Fields (AI-026 â€” Step 4)

- `loaded_package_manifest: Optional[PackageManifest]` â€” stores the currently loaded package manifest when the user selects "Load Existing Generated Tests"
- `loaded_package_run_results: Optional[list[dict]]` â€” stores the run history for the currently loaded package
- `loaded_package_path: Optional[str]` â€” stores the filesystem path to the currently loaded package directory

## Factory functions

- `_env_or_default(key: str, default: str) -> str`
- `_session_defaults() -> dict[str, str]`
- `create_session() -> Session`
  - Initializes a `Session` with environment-backed defaults for LLM provider, base URL, and model.
  - Package persistence fields initialized to `None`.

## Notes

- Uses `src.journey_scraper.CredentialProfile` and `JourneyStep` for optional authentication and journey configuration.
- Uses `src.spec_analyzer.TestCondition` and `src.test_plan.TestPlan` for living test plan support.
- Uses `src.pytest_output_parser.RunResult` for pytest execution results.
- Uses `src.pipeline_artifact_manager.PackageManifest` for loaded package metadata.





# cli/test_case_orchestrator.py

## Purpose

Orchestrates legacy CLI test case generation from parsed requirements through analysis, ordering, and Playwright file creation.
Implements a simpler orchestration path that mirrors the Streamlit/primary pipeline while supporting older CLI patterns.

## Key classes

### `TestOrchestrationResult`
- Fields: `generated_files`, `summary`, `errors`
- Method: `to_dict() -> dict`

### `TestCaseOrchestrator`
- Constructor: `__init__(self, analysis_mode: AnalysisMode | None = None) -> None`
- Public entry points:
  - `process(raw_input: str, explicit_format: str | None = None, url: str | None = None, output_dir: str = GENERATED_TESTS_DIR) -> TestOrchestrationResult`
  - `process_parsed(parsed: ParsedInput, url: str | None = None, output_dir: str = GENERATED_TESTS_DIR) -> TestOrchestrationResult`

## Internal workflow

- `_analyze_input(parsed: object) -> AnalysisResult`
  - Converts parsed test cases into `AnalyzedTestCase` objects using `KeywordAnalyzer`.

- `_order_test_cases(cases: list[AnalyzedTestCase]) -> list[AnalyzedTestCase]`
  - Orders cases by dependency satisfaction and complexity.

- `_generate_test_files(cases: list[AnalyzedTestCase], url: str | None = None, output_dir: str = GENERATED_TESTS_DIR, raw_requirements: str = "") -> list[str]`
  - Generates test files via the shared `TestOrchestrator` pipeline.
  - Supports both batch generation from a full feature spec and individual-case generation.

- `_build_feature_spec_request(raw_requirements: str) -> tuple[str, str] | None`
  - Builds a `(user_story, numbered_conditions)` tuple from structured requirements.

- `_generate_test_content(test_type: str, cases: list[AnalyzedTestCase]) -> str`
  - Generates Python Playwright test content for a list of analyzed cases.

- `_generate_test_method(idx: int, case: AnalyzedTestCase, total: int) -> str`
  - Builds a test method string with placeholder page actions.

- `_generate_steps_from_description(case: AnalyzedTestCase) -> list[str]`
  - Generates simple Playwright step placeholders for navigation, login, forms, clicking, and search.

- `_sanitize_name(name: str) -> str`
- `_extract_url(text: str) -> str | None`
- `_create_summary(analysis: AnalysisResult, files: list[str]) -> dict`

## Notes

- Uses the same `src.orchestrator.TestOrchestrator` pipeline and `PipelineArtifactWriter` for file output.
- Compatible with legacy CLI generation flows while still leveraging the newer underlying pipeline.





# cli/__init__.py

## Purpose

Provides backwards-compatible re-exports for the CLI package.
This module exists so that `import cli` consumers can access common CLI constants and enums without importing from `src.config` directly.

## Exports

- `AnalysisMode`
- `CaptureLevel`
- `DetectionMode`
- `ReportFormat`
- `ScreenshotNaming`
- `JIRA_PROJECT_KEY`

## Implementation details

- Imports selected constants and enum types from `src.config`.
- Defines `__all__` so re-exports are explicit and importable by `from cli import *`.





# llm_providers/__init__.py

## Overview

This module provides a unified interface for interacting with different LLM backends in the AI-Playwright-Test-Generator project. It implements a provider abstraction pattern that supports multiple LLM services through a common interface.

**Supported Providers:**
- Ollama (native API)
- LM Studio (OpenAI-compatible API)
- OpenAI (cloud and local modes)
- Any OpenAI-compatible local server

## Architecture

The module follows an **Abstract Factory pattern** with the following components:

1. **Data Models**: `ChatMessage` and `ChatCompletion` dataclasses for type-safe message handling
2. **Abstract Base Class**: `LLMProvider` defines the contract all providers must implement
3. **Concrete Implementations**: Provider-specific classes that handle API communication
4. **Factory Functions**: Helper functions for provider instantiation and auto-detection

## Data Models

### ChatMessage
```python
@dataclass
class ChatMessage:
    role: str  # 'system', 'user', or 'assistant'
    content: str
```

Represents a single message in a chat conversation.

### ChatCompletion
```python
@dataclass
class ChatCompletion:
    content: str
    model: str
    usage: dict[str, int] | None = None  # {'prompt_tokens': int, 'completion_tokens': int}
```

Represents the response from an LLM completion request, including token usage metadata.

## Abstract Base Class

### LLMProvider
```python
class LLMProvider(ABC):
```

Abstract base class that defines the interface all LLM providers must implement.

**Properties:**
- `provider_name(self) -> str`: Returns the provider identifier (e.g., 'ollama', 'lm-studio')
- `base_url(self) -> str`: Returns the configured API base URL

**Methods:**
- `complete(self, messages: list[ChatMessage], model: str | None = None, timeout: int = 300) -> ChatCompletion`: Send a chat completion request
- `list_models(self, timeout: int = 30) -> list[str]`: List available models on the provider

## Provider Implementations

### OllamaProvider
```python
class OllamaProvider(LLMProvider):
    DEFAULT_BASE_URL = "http://localhost:11434"
    PROVIDER_NAME = "ollama"
    
    def __init__(self, base_url: str | None = None, **kwargs: Any) -> None
```

Native Ollama API provider implementation.

**Key Features:**
- Uses Ollama's native `/api/chat` endpoint
- Default model: `qwen2.5:7b` (configurable via `OLLAMA_MODEL` env var)
- Timeout configurable via `OLLAMA_TIMEOUT` env var (default: 300s)
- Token counting via `eval_count` field in response

**Environment Variables:**
- `OLLAMA_BASE_URL`: Override default base URL
- `OLLAMA_MODEL`: Override default model
- `OLLAMA_TIMEOUT`: Override request timeout

### LMStudioProvider
```python
class LMStudioProvider(LLMProvider):
    DEFAULT_BASE_URL = "http://localhost:1234"
    PROVIDER_NAME = "lm-studio"
    
    def __init__(self, base_url: str | None = None, **kwargs: Any) -> None
```

LM Studio provider implementation using OpenAI-compatible API.

**Key Features:**
- Uses OpenAI-compatible `/v1/chat/completions` endpoint
- Default model: `lmstudio-community/Qwen2.5-7B-Instruct-GGUF`
- Additional method: `get_loaded_model()` to query currently loaded model
- Native API endpoint at `/api/v0/models` for model state detection

**Environment Variables:**
- `LM_STUDIO_BASE_URL`: Override default base URL
- `LM_STUDIO_MODEL`: Override default model

### OpenAIProvider
```python
class OpenAIProvider(LLMProvider):
    PROVIDER_NAME = "openai"
    LOCAL_PROVIDER_NAME = "openai-local"
    LOCAL_DEFAULT_PORTS = [8080, 8000, 5000]  # llama.cpp, vLLM, text-gen-webui
    
    def __init__(self, api_key: str | None = None, base_url: str | None = None, is_local: bool = False)
```

OpenAI API provider supporting both cloud and local modes.

**Key Features:**
- **Cloud mode** (default): Requires API key, targets `api.openai.com`
- **Local mode** (`is_local=True`): No API key required, auto-detects local servers
- Auto-detection probes ports: 8080 (llama.cpp), 8000 (vLLM), 5000 (text-gen-webui)
- Default cloud model: `gpt-4o`
- Default local model: `llama`
- API key masking for security in logs

**Environment Variables:**
- `OPENAI_API_KEY`: Required for cloud mode
- `OPENAI_BASE_URL`: Override default base URL
- `OPENAI_MODEL`: Override default model

**Special Methods:**
- `get_loaded_model(timeout: int = 5) -> str | None`: Returns first available model from `/v1/models`
- `api_key(self) -> str | None`: Returns masked API key for logging

## Factory Functions

### auto_detect_provider()
```python
def auto_detect_provider() -> LLMProvider
```

Automatically detects and returns the first active local LLM provider.

**Detection Order:**
1. LM Studio (http://localhost:1234/v1/models)
2. Ollama (http://localhost:11434/api/tags)
3. OpenAI-compatible local servers (ports 8080, 8000, 5000)

**Raises:**
- `ConnectionError`: If no local providers are active

### get_provider()
```python
def get_provider(provider_name: str, **kwargs: Any) -> LLMProvider
```

Factory function to create a provider instance by name.

**Parameters:**
- `provider_name`: One of 'ollama', 'lm-studio', 'openai', 'openai-local'
- `**kwargs`: Additional arguments passed to provider constructor

**Raises:**
- `ValueError`: If provider name is unknown

### create_provider_from_env()
```python
def create_provider_from_env() -> LLMProvider
```

Creates a provider instance based on environment variables.

**Environment Variables:**
- `LLM_PROVIDER`: Provider name (default: 'ollama')
- Provider-specific variables (see individual provider sections)

**Raises:**
- `ValueError`: If required environment variables are missing or provider is unknown

## Design Patterns

### Provider Abstraction
All providers implement the same interface, allowing the rest of the application to work with any LLM backend without changing code.

### Environment-Based Configuration
Providers read configuration from environment variables, supporting the 12-factor app methodology.

### Auto-Detection
The `auto_detect_provider()` function enables zero-configuration startup by probing common local ports.

### Graceful Degradation
Local mode providers handle missing endpoints gracefully, falling back to defaults rather than crashing.

## Usage Example

```python
from src.llm_providers import get_provider, ChatMessage

# Create a provider
provider = get_provider("ollama")

# Send a completion request
messages = [
    ChatMessage(role="system", content="You are a helpful assistant."),
    ChatMessage(role="user", content="Generate a Playwright test.")
]
response = provider.complete(messages, model="qwen2.5:7b")
print(response.content)

# List available models
models = provider.list_models()
print(models)
```

## Exported Symbols

```python
__all__ = [
    "ChatMessage",
    "ChatCompletion",
    "LLMProvider",
    "OllamaProvider",
    "LMStudioProvider",
    "OpenAIProvider",
    "get_provider",
    "create_provider_from_env",
    "auto_detect_provider",
]
```

## Dependencies

- `abc`: Abstract base class support
- `dataclasses`: Data model definitions
- `httpx`: HTTP client for API communication (imported per-provider to minimize startup overhead)

## Notes

- All HTTP clients use a 300-second default timeout unless overridden
- Token usage tracking is optional and depends on provider response format
- Local OpenAI-compatible servers may return 401 for `/v1/models` (treated as success in local mode)
- Provider auto-detection uses 2-second timeouts for fast failure





# `src/accessibility_enricher.py`

## High-Level Purpose

Enriches scraped DOM element records with computed accessibility names from the browser's accessibility tree (`page.accessibility.snapshot()`). Merges computed names (derived from ARIA relationships like `aria-labelledby`, `aria-describedby`, parent label context, SVG `<title>` children, and implicit roles) back into element records produced by `PageScraper` so that `PlaceholderResolver` has additional text signals for matching placeholders like `{{CLICK:View Cart}}` against elements whose accessible name differs from raw HTML attributes.

**Key Design Principle:** Enrichment is additive-only â€” it never removes or overwrites existing data.

## Module Metadata

- **Lines:** 411
- **`__test__ = False`** â€” excluded from pytest collection
- **Imports:** `logging`, `typing.Any`

## Class: `AccessibilityEnricher`

```python
class AccessibilityEnricher:
    """Merge computed accessible names from an a11y tree into scraped elements."""
```

### Class Constants

| Constant | Type | Description |
|----------|------|-------------|
| `INTERACTIVE_ROLES` | `set[str]` | Roles considered "interactive" for document-order matching (button, link, checkbox, textbox, combobox, etc.) |

### Static Methods

#### `_transform_cdp_ax_tree(cdp_nodes: list[dict[str, Any]]) -> dict[str, Any]`
Transforms CDP `Accessibility.getFullAXTree` result into the format expected by `enrich()`. Converts nested role/name wrappers to flat values, wires children via `childIds`, and returns a single root node.

#### `enrich(elements: list[dict[str, Any]], a11y_tree: dict[str, Any]) -> list[dict[str, Any]]`
Main entry point. Merges computed accessible names from a11y tree into scraped elements using three matching strategies (priority order):
1. **Role + name** â€” match element text+role against a11y node name+role
2. **href** â€” match link elements by href value in a11y properties
3. **Document-order** â€” fallback positional matching

Returns the same element list mutated in-place.

#### `_flatten_a11y_tree(node: dict[str, Any]) -> list[dict[str, Any]]`
Flattens the a11y tree into a document-order list of interactive nodes (nodes with meaningful name or interactive role).

#### `_build_role_name_index(nodes: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]`
Builds an index of `(role, name)` tuples to lists of a11y nodes for fast lookup.

#### `_build_href_index(nodes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]`
Builds an index of href values to a11y nodes (extracted from `properties` array `url` entries).

#### `_match_by_role_and_name(element, role_name_index, used_indices) -> dict[str, Any] | None`
Strategy 1: match by element text against a11y node computed name, with role comparison to narrow false positives. Falls back to name-only match ignoring role.

#### `_match_by_href(element, href_index, used_indices) -> dict[str, Any] | None`
Strategy 3: match link elements by exact href, then partial path comparison.

#### `_match_by_document_order(element, a11y_nodes, used_indices) -> dict[str, Any] | None`
Strategy 2: fallback â€” find first unused a11y node whose name overlaps with element text or selector.

#### `_apply_enrichment(element: dict[str, Any], a11y_node: dict[str, Any]) -> None`
Applies computed fields from matched a11y node to scraped element:
- `accessible_name` added only if not present
- `computed_role` added unconditionally
- `aria_describedby` resolved from properties (describedby > labelledby > label)

## Dependencies
- `page.accessibility.snapshot()` output (Playwright)
- Element dicts from `PageScraper`





# `src/analyzer.py`

## High-Level Purpose

`src/analyzer.py` provides a fast, deterministic, keyword-based analyzer for enriching parsed user stories or test cases without calling an LLM. It identifies likely user actions, expected outcomes, suggested test data, and coarse complexity from plain text. The module is designed as reusable `src/` logic that can be called by CLI/UI layers instead of duplicating analyzer behavior there.

The analyzer produces serializable dataclass results:

- `AnalyzedTestCase`: one enriched test case.
- `AnalysisResult`: a container for one or more analyzed test cases plus summary metadata.
- `KeywordAnalyzer`: a stateless class-method utility that performs keyword matching and result construction.

## Imports

- `from __future__ import annotations`: postpones annotation evaluation.
- `dataclass`, `field` from `dataclasses`: defines result containers with default factories.
- `datetime` from `datetime`: creates generated timestamps and dynamic test email suffixes.
- `Any` from `typing`: allows flexible test-data payloads.

## Module Constants

### `COMMON_PRECONDITIONS: list[str]`

Common text fragments that imply setup or authentication prerequisites:

- login/authentication phrases
- account creation and registration phrases
- navigation to login

This constant is declared but not currently consumed inside the module.

### `COMMON_POSTCONDITIONS: list[str]`

Common text fragments that imply cleanup or end-state actions:

- logout
- clear/reset form
- return home navigation

This constant is declared but not currently consumed inside the module.

## Dataclass: `AnalyzedTestCase`

Enhanced test-case model containing the original test-case text plus keyword-analysis output.

### Signature

```python
@dataclass
class AnalyzedTestCase:
```

### Fields

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `title` | `str` | required | Test case title. |
| `description` | `str` | required | Test case description or scenario text. |
| `preconditions` | `list[str]` | `field(default_factory=list)` | Setup conditions attached to the case. |
| `test_data` | `dict[str, Any]` | `field(default_factory=dict)` | Existing or supplied test-data values. |
| `expected_outcome` | `str` | `""` | Expected result text. |
| `test_type` | `str` | `"functional"` | Classification of the test. |
| `priority` | `str` | `"medium"` | Priority label. |
| `identified_actions` | `list[str]` | `field(default_factory=list)` | Action categories detected from the description. |
| `identified_expectations` | `list[str]` | `field(default_factory=list)` | Expectation categories detected from the description. |
| `suggested_data` | `dict[str, Any]` | `field(default_factory=dict)` | Analyzer-generated data hints. |
| `dependencies` | `list[str]` | `field(default_factory=list)` | Related or prerequisite cases. |
| `estimated_complexity` | `str` | `"low"` | Coarse complexity estimate: typically `low`, `medium`, or `high`. |
| `analysis_confidence` | `float` | `1.0` | Confidence score, reduced when signals are missing. |

### Method: `to_dict`

```python
def to_dict(self) -> dict:
```

Returns a serialization-friendly `dict` containing most dataclass fields plus a generated `created_at` ISO timestamp.

Notable behavior:

- Includes `title`, `description`, preconditions, test data, outcome, type, priority, detected actions/expectations, suggested data, complexity, and confidence.
- Adds `created_at` via `datetime.now().isoformat()`.
- Does not include the `dependencies` field in the serialized output.
- Uses unparameterized `dict` as the return annotation.

## Dataclass: `AnalysisResult`

Container for analysis output across one or more test cases.

### Signature

```python
@dataclass
class AnalysisResult:
```

### Fields

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `analyzed_test_cases` | `list[AnalyzedTestCase]` | required | Enriched test cases. |
| `analysis_summary` | `dict` | `field(default_factory=dict)` | Aggregate summary metadata. |
| `detected_patterns` | `list[str]` | `field(default_factory=list)` | Flattened list of detected action categories. |

### Method: `to_dict`

```python
def to_dict(self) -> dict:
```

Returns a serialization-friendly `dict` with:

- `analyzed_test_cases`: each case converted through `AnalyzedTestCase.to_dict()`.
- `analysis_summary`: summary metadata as stored on the instance.
- `detected_patterns`: detected pattern list.
- `analysis_timestamp`: generated with `datetime.now().isoformat()`.

Uses unparameterized `dict` as the return annotation.

## Class: `KeywordAnalyzer`

Stateless keyword-analysis service implemented with class-level dictionaries and class methods. It does not require construction and keeps all matching configuration on the class.

### Class Attributes

#### `ACTION_KEYWORDS: dict[str, list[str]]`

Maps action categories to substrings used for matching:

- `navigation`
- `data_interaction`
- `confirmation`
- `search`
- `filter`
- `form`

#### `EXPECTATION_KEYWORDS: dict[str, list[str]]`

Maps expected-result categories to substrings used for matching:

- `success`
- `error`
- `redirect`
- `state_change`
- `visibility`
- `content`

The `redirect` keyword list contains a duplicated `"go to"` entry.

#### `DATA_PATTERNS: dict[str, str]`

Regular-expression patterns for structured data such as:

- email
- username
- password
- name
- URL
- ID/key
- amount

This mapping is declared but not currently used by `suggest_data` or other module logic. The amount pattern contains mojibake-looking currency characters in the source string.

#### `DATA_CATEGORIES: dict[str, list[str]]`

Maps broad data domains to detection keywords:

- `auth`
- `form`
- `navigation`
- `data`
- `error`

The `data` category includes a duplicated `"item"` keyword.

#### Complexity Keyword Lists

```python
LOW_COMPLEXITY_KEYWORDS: list[str]
MEDIUM_COMPLEXITY_KEYWORDS: list[str]
HIGH_COMPLEXITY_KEYWORDS: list[str]
```

These lists drive coarse complexity scoring by counting keyword occurrences in the lowercased input text.

## Function and Method Signatures

### `KeywordAnalyzer.identify_actions`

```python
@classmethod
def identify_actions(cls, text: str) -> list[str]:
```

Parameters:

- `text: str`: scenario or test-case text to inspect.

Returns:

- `list[str]`: action category names detected in `ACTION_KEYWORDS`.

Behavior:

- Lowercases input for case-insensitive substring checks.
- Appends each action category where any configured keyword is present.
- If no configured category matches but generic interaction words such as `click`, `enter`, `select`, or `choose` are present, returns `["general"]`.
- Returns an empty list when no action-like text is found.

### `KeywordAnalyzer.identify_expectations`

```python
@classmethod
def identify_expectations(cls, text: str) -> list[str]:
```

Parameters:

- `text: str`: scenario or test-case text to inspect.

Returns:

- `list[str]`: expectation category names detected in `EXPECTATION_KEYWORDS`.

Behavior:

- Lowercases input for case-insensitive substring checks.
- Appends each expectation category where any configured keyword is present.
- Falls back to `["result_display"]` when no expectation category is detected.

### `KeywordAnalyzer.suggest_data`

```python
@classmethod
def suggest_data(cls, text: str) -> dict[str, Any]:
```

Parameters:

- `text: str`: scenario or test-case text to inspect.

Returns:

- `dict[str, Any]`: suggested data values inferred from keywords, or `{}` when no data hints are found.

Behavior:

- Lowercases the input.
- Detects broad categories using `DATA_CATEGORIES`.
- If auth-related terms such as `email`, `register`, or `login` appear, generates:
  - `email`: timestamped test email using `datetime.now().strftime('%Y%m%d_%H%M%S')`
  - `password`: fixed strong-looking test password
- If form-related category or `submit` is detected, adds `form_data` with a name and email.
- If payment/amount terms appear, adds `amount` and `currency`.
- Returns an empty dictionary if no suggestions were generated.

### `KeywordAnalyzer.estimate_complexity`

```python
@classmethod
def estimate_complexity(cls, text: str) -> str:
```

Parameters:

- `text: str`: scenario or test-case text to inspect.

Returns:

- `str`: one of the coarse complexity labels currently returned by the method: `"low"`, `"medium"`, or `"high"`.

Behavior:

- Counts occurrences by checking whether each low/medium/high keyword appears as a substring of the lowercased input.
- Returns `"low"` when no complexity keywords are found.
- Returns `"high"` when high-complexity matches outnumber medium-complexity matches.
- Returns `"medium"` when any high-complexity keyword is present or at least three medium-complexity keywords are present.
- Returns `"low"` otherwise.

### `KeywordAnalyzer.analyze_parsed`

```python
@classmethod
def analyze_parsed(cls, parsed: object) -> AnalysisResult:
```

Parameters:

- `parsed: object`: flexible parsed input object. The docstring expects a `ParsedInput` from `src.cli.input_parser.InputParser`, but the method intentionally uses duck typing.

Returns:

- `AnalysisResult`: container with analyzed cases, summary metadata, and detected action patterns.

Behavior:

- Initializes `analyzed_cases: list[AnalyzedTestCase]` and `detected_patterns: list[str]`.
- If `parsed` has a truthy `test_cases` attribute:
  - Iterates each test case.
  - Derives `title` from `tc.title`, then `tc.name`, then `"Untitled"`.
  - Derives `desc` from `tc.description`, then `tc.step`, then `""`.
  - Calls `cls.analyze(title, desc)`.
  - Extends `detected_patterns` with each analyzed case's `identified_actions`.
- Else if `parsed` has a `story` attribute:
  - Uses `"User Story"` as the title.
  - Analyzes `str(parsed.story)`.
- Else:
  - Uses `"Input"` as the title.
  - Analyzes `str(parsed)`.
- Returns an `AnalysisResult` with:
  - `analysis_summary["total_cases"]`
  - empty `complexity_distribution`
  - `requires_auth` set to `False`
  - flattened detected action patterns

Architectural notes:

- Uses `hasattr` and `# type: ignore[attr-defined]` to support multiple parsed object shapes without importing their concrete types.
- The summary fields are placeholders rather than fully aggregated metrics.

### `KeywordAnalyzer.analyze`

```python
@classmethod
def analyze(cls, title: str, description: str) -> AnalyzedTestCase:
```

Parameters:

- `title: str`: title for the resulting analyzed test case.
- `description: str`: text to analyze.

Returns:

- `AnalyzedTestCase`: enriched result with detected actions, expectations, data suggestions, complexity, and confidence.

Behavior:

- Calls:
  - `cls.identify_actions(description)`
  - `cls.identify_expectations(description)`
  - `cls.suggest_data(description)`
  - `cls.estimate_complexity(description)`
- Starts with `base_confidence = 1.0`.
- Reduces confidence by:
  - `0.2` if no actions were found.
  - `0.2` if no expectations were found.
  - `0.1` if no suggested data was found.
- Clamps confidence to a minimum of `0.5`.
- Returns an `AnalyzedTestCase` populated with the original title/description and analysis results.

Because `identify_expectations` falls back to `["result_display"]`, the `if not expectations` confidence penalty is normally unreachable through `analyze`.

## Key Architectural Patterns

### Deterministic Keyword Pipeline

The module uses static keyword maps and substring checks instead of LLM calls. This makes the analyzer fast, predictable, and suitable for CLI preprocessing or lightweight enrichment.

### Dataclass Result Models

`AnalyzedTestCase` and `AnalysisResult` separate analysis data from analyzer logic. Both include `to_dict` helpers for JSON-compatible serialization and timestamp metadata.

### Stateless Class-Method Analyzer

`KeywordAnalyzer` stores configuration in class attributes and exposes only class methods. There is no instance state, dependency injection, I/O, or external service access.

### Duck-Typed Adapter Boundary

`analyze_parsed` accepts `object` and adapts several possible parsed-input shapes using `hasattr`. This avoids importing parser models while allowing the analyzer to work with test cases, user stories, or arbitrary objects.

### Fallback-Oriented Enrichment

The analyzer favors returning usable defaults:

- Missing expectations become `["result_display"]`.
- Missing complexity signals become `"low"`.
- Missing titles/descriptions in parsed test cases fall back to `"Untitled"` and `""`.
- Confidence bottoms out at `0.5`.

## Data Flow

```text
parsed object or title/description
        |
        v
KeywordAnalyzer.analyze_parsed(...) or KeywordAnalyzer.analyze(...)
        |
        v
identify_actions + identify_expectations + suggest_data + estimate_complexity
        |
        v
AnalyzedTestCase
        |
        v
AnalysisResult, when analyzing parsed multi-case input
```

## Serialization Shape

### `AnalyzedTestCase.to_dict()`

Produces keys:

- `title`
- `description`
- `preconditions`
- `test_data`
- `expected_outcome`
- `test_type`
- `priority`
- `identified_actions`
- `identified_expectations`
- `suggested_data`
- `estimated_complexity`
- `analysis_confidence`
- `created_at`

### `AnalysisResult.to_dict()`

Produces keys:

- `analyzed_test_cases`
- `analysis_summary`
- `detected_patterns`
- `analysis_timestamp`

## Notable Implementation Details

- Matching uses simple substring checks, so keywords can match inside longer words.
- `DATA_PATTERNS` is currently unused despite containing regex definitions.
- `COMMON_PRECONDITIONS` and `COMMON_POSTCONDITIONS` are currently unused.
- Timestamps are generated at serialization time and suggested email generation time, so repeated calls can produce different output.
- `analysis_summary` includes `complexity_distribution` and `requires_auth`, but those values are not computed from analyzed cases in the current implementation.
- Return annotations for `to_dict` methods are plain `dict`, while other dictionaries use more specific generic annotations.





# `src/browser_utils.py`

## High-Level Purpose

`src/browser_utils.py` contains synchronous Playwright browser utilities for clearing UI elements that can interfere with automated page interaction. Its public entry point, `dismiss_consent_overlays`, performs best-effort dismissal or removal of consent banners, cookie dialogs, ad overlays, and some overlay-like blockers.

The module is intentionally defensive: every interaction path catches broad exceptions and returns `None`, allowing callers to continue even when a page does not contain the expected overlay structures or when a dismissal attempt fails.

## Module Structure

- Imports `Page` from `playwright.sync_api`.
- Defines no classes.
- Exposes one public function.
- Keeps the implementation decomposed into four private helper functions, each responsible for one dismissal strategy.

## Public Function

### `dismiss_consent_overlays(page: Page) -> None`

Best-effort orchestration function for removing browser overlays before or during Playwright test execution.

Parameters:

- `page: Page` - A synchronous Playwright `Page` object representing the browser tab under automation.

Returns:

- `None`

Behavior:

- Calls `_dismiss_google_consent_tvm(page)`.
- Calls `_dismiss_structural_consent_banners(page)`.
- Calls `_dismiss_position_overlays(page)`.
- Calls `_remove_ad_overlays_js(page)`.

Architectural role:

- Acts as a facade over multiple overlay-dismissal strategies.
- Keeps caller-facing behavior simple: invoke once, ignore failures, and proceed.
- Uses synchronous Playwright APIs only.

## Private Helper Functions

### `_dismiss_google_consent_tvm(page: Page) -> None`

Handles Google consent UI patterns associated with `.fc-consent-root`.

Parameters:

- `page: Page` - A synchronous Playwright page.

Returns:

- `None`

Behavior:

- Looks for `.fc-consent-root button:has-text('Consent')` and clicks the first visible match.
- Looks for `.fc-consent-root button:has-text('Manage options')` and clicks the first visible match.
- Sends the `Escape` key.
- Uses `page.evaluate()` to remove `.fc-consent-root` and `.fc-dialog-overlay` elements from the DOM.
- Waits briefly after successful interactions to allow the page state to settle.

Failure handling:

- Each action is isolated in its own `try`/`except Exception` block.
- Exceptions are swallowed.

### `_dismiss_structural_consent_banners(page: Page) -> None`

Finds known consent or cookie banner containers and clicks dismissal controls inside those containers.

Parameters:

- `page: Page` - A synchronous Playwright page.

Returns:

- `None`

Behavior:

- Defines `container_selectors`, a list of known consent-provider, cookie-banner, modal, overlay, and ARIA dialog selectors.
- Defines `consent_button_patterns`, a list of button selectors for text and ARIA-label patterns such as consent, accept, agree, allow, close, dismiss, and X.
- Iterates through the container selectors.
- For the first visible matching container, searches only within that container for dismissal buttons.
- Clicks the first visible matching dismissal button and returns immediately.

Architectural pattern:

- Uses scoped selector matching to reduce false positives.
- Avoids matching generic dismissal text against the entire page.
- Treats known structural containers as the boundary for safe button matching.

Failure handling:

- Container lookup failures skip to the next container selector.
- Button lookup or click failures skip to the next button pattern.

### `_dismiss_position_overlays(page: Page) -> None`

Detects and dismisses overlay-like UI by layout and viewport position rather than by known provider selectors.

Parameters:

- `page: Page` - A synchronous Playwright page.

Returns:

- `None`

Behavior:

- Defines `dismiss_texts`, a list of accepted dismissal labels.
- Runs JavaScript through `page.evaluate()` to inspect `div`, `section`, `[role="dialog"]`, and `[role="alertdialog"]` elements.
- Filters out elements that are too small or off-screen.
- Computes CSS positioning and bounding rectangles for candidate overlay containers.
- Identifies fixed-position bottom banners and centered overlays.
- Searches candidate containers for `button`, `[role="button"]`, and `a[role="button"]` controls.
- Records matching button center coordinates when their visible text includes one of the dismissal labels.
- Clicks the first returned coordinate using `page.mouse.click(x, y)`.
- Expands collapsed Bootstrap-style panels by adding the `in` class and setting `display = 'block'` on `.panel-collapse.collapse` elements.

Implementation notes:

- The JavaScript computes `isSticky` and `hasBackdrop`, but the final overlay predicates use fixed-position bottom and centered overlay checks.
- The evaluated JavaScript returns an array of button metadata; the Python code stores it in `result: dict` and then treats it as a truthy sequence.

Failure handling:

- JavaScript evaluation, mouse click, and panel-expansion errors are swallowed.

### `_remove_ad_overlays_js(page: Page) -> None`

Removes known advertising overlay elements and ad containers using specific selectors.

Parameters:

- `page: Page` - A synchronous Playwright page.

Returns:

- `None`

Behavior:

- Sends the `Escape` key.
- Defines `ad_overlay_selectors` for Google vignette, Google ad iframes, ASWIFT iframes, and advertisement iframes.
- Checks each known selector and sends `Escape` again when a matching element exists.
- Runs JavaScript through `page.evaluate()` to hide and remove known consent, vignette, AdSense, ASWIFT, iframe, and ad container elements.
- Waits briefly after JavaScript cleanup.

Architectural pattern:

- Uses specific ad selectors instead of broad layout or z-index heuristics.
- Mutates the DOM directly only for known overlay and ad patterns.

Failure handling:

- Keyboard, selector lookup, and JavaScript evaluation failures are swallowed.

## Key Architectural Patterns

### Best-Effort Idempotent Cleanup

All functions return `None` and are written to tolerate absent elements, changed markup, hidden overlays, Playwright timing errors, and JavaScript failures. This makes the utilities suitable for repeated calls during browser automation.

### Public Facade With Private Strategies

`dismiss_consent_overlays` is the sole public facade. The concrete strategies are private helpers:

- Google consent-specific handling.
- Structural consent banner handling.
- Position-based overlay detection.
- Specific ad-overlay DOM cleanup.

### Scoped Matching Before Broad Detection

The module first attempts provider-specific and structural dismissal before using position-based detection. Structural dismissal scopes button text matching to candidate containers, reducing the chance of clicking ordinary page controls.

### Synchronous Playwright API

Every function accepts `playwright.sync_api.Page` and uses sync Playwright methods such as `locator()`, `click()`, `is_visible()`, `wait_for_timeout()`, `keyboard.press()`, `mouse.click()`, and `evaluate()`.

### DOM Mutation For Known Blockers

The module uses `page.evaluate()` to remove or hide specific overlay and ad elements when normal clicks or Escape-key dismissal may not be enough. The selectors are explicit and targeted rather than based on broad visual properties.

### Defensive Exception Suppression

Each dismissal attempt is wrapped in broad exception handling. The design favors forward progress in generated or automated tests over surfacing overlay-cleanup failures to callers.

## External Side Effects

- May click buttons on the current page.
- May press the `Escape` key.
- May move through short Playwright timeouts.
- May mutate the DOM by removing or hiding consent and ad elements.
- May expand collapsed Bootstrap panel elements.

## Dependencies

- `playwright.sync_api.Page`





# `src/code_normalizer.py`

## High-Level Purpose

`code_normalizer.py` provides deterministic post-processing transforms for LLM-generated Playwright pytest code. It normalizes whitespace, repairs common indentation defects, converts unresolved placeholder syntax into executable `pytest.skip(...)` statements, removes skeleton metadata, deduplicates skip calls, replaces incomplete ellipsis bodies, and injects missing navigation steps when enough URL context is available.

The module is designed as an independently testable normalization layer extracted from a larger post-processing pipeline. Its functions accept Python source code as plain strings and return transformed source code as strings, making the module easy to compose into ordered pipelines.

## Public API

The module defines `__all__` to export the following functions:

- `normalize_whitespace`
- `convert_standalone_placeholders`
- `replace_remaining_placeholders`
- `strip_pages_needed_block`
- `fix_module_scope_indentation`
- `fix_indentation`
- `dedent_indented_test_blocks`
- `deduplicate_skip_calls`
- `replace_bare_ellipsis`
- `ensure_test_navigation`

## Imports

```python
from __future__ import annotations

import re
```

The module depends only on Python's standard `re` module. Future annotations are enabled so modern type syntax can be used consistently.

## Constants

### `_STANDALONE_PLACEHOLDER_RE`

```python
_STANDALONE_PLACEHOLDER_RE = re.compile(
    r"^(\s*)\{\{(CLICK|FILL|GOTO|URL|ASSERT):([^}]+)\}\}\s*$",
    re.MULTILINE,
)
```

Matches lines containing only a supported placeholder token, preserving leading indentation and extracting the action plus description.

### `_CONTROL_FLOW_RE`

```python
_CONTROL_FLOW_RE = re.compile(r"^(if |for |while |with |try:|async with |async for )")
```

Identifies control-flow statements that can legitimately introduce nested indentation inside a function body.

## Functions

### `normalize_whitespace`

```python
def normalize_whitespace(code: str) -> str:
```

Parameters:

- `code: str` - Python source code that may contain tabs or mixed line endings.

Returns:

- `str` - Code with Windows and old-Mac line endings normalized to `\n`, and tabs expanded to four spaces.

Purpose:

This is intended as an early pipeline step. It standardizes indentation and line endings before later transforms reason about column counts or inject additional lines.

### `convert_standalone_placeholders`

```python
def convert_standalone_placeholders(code: str) -> str:
```

Parameters:

- `code: str` - Generated Python source code that may contain placeholder tokens.

Returns:

- `str` - Code where standalone placeholders and evidence-tracker-wrapped placeholders are unwrapped into raw placeholder lines.

Purpose:

Normalizes placeholder representation before later resolution or fallback conversion. It handles both bare standalone tokens such as `{{CLICK:...}}` and malformed calls such as `evidence_tracker.click({{CLICK:...}}...)`, emitting a single placeholder token at the original indentation level.

Key behavior:

- Preserves indentation.
- Recognizes `CLICK`, `FILL`, `GOTO`, `URL`, and `ASSERT` placeholders.
- Handles wrapper methods `click`, `fill`, `navigate`, and `assert_visible`.

### `replace_remaining_placeholders`

```python
def replace_remaining_placeholders(code: str) -> str:
```

Parameters:

- `code: str` - Generated Python source code that may still contain unresolved `{{ACTION:description}}` placeholders.

Returns:

- `str` - Code where unresolved placeholders are replaced by `pytest.skip(...)` calls.

Purpose:

Converts unresolved placeholder syntax into valid pytest code so generated tests remain syntactically executable and explicitly skipped rather than crashing at parse time.

Key behavior:

- Finds placeholders with `re.compile(r"\{\{[A-Z_]+:(.+?)\}\}", re.DOTALL)`.
- If a placeholder appears inside a function call, replaces the whole affected line with one `pytest.skip(...)`.
- If placeholders appear outside a function call, replaces each placeholder token with `pytest.skip('<placeholder>')`.
- Preserves leading indentation for generated skip lines.

Nested helper:

```python
def _handle_match(m: re.Match) -> str:
```

Parameters:

- `m: re.Match` - Placeholder regex match.

Returns:

- `str` - A `pytest.skip(...)` expression containing the placeholder text.

### `strip_pages_needed_block`

```python
def strip_pages_needed_block(code: str) -> str:
```

Parameters:

- `code: str` - Generated Python source code that may include skeleton metadata comments.

Returns:

- `str` - Code with a trailing `# PAGES_NEEDED:` metadata block removed.

Purpose:

Removes skeleton-generation metadata from final emitted code while preserving normal code that follows the metadata block.

Key behavior:

- Starts removal when a line exactly matches `# PAGES_NEEDED:`.
- Skips blank lines and `# -` entries while inside the block.
- Resumes preserving lines once a non-metadata line appears.

### `fix_module_scope_indentation`

```python
def fix_module_scope_indentation(code: str) -> str:
```

Parameters:

- `code: str` - Python source code that may have module-level declarations indented by mistake.

Returns:

- `str` - Code where imports, classes, test functions, and `@pytest.mark` decorators are forced to module scope.

Purpose:

Repairs common LLM output where top-level declarations are accidentally shifted right.

Module-level patterns:

- `import `
- `from `
- `def test_`
- `class `
- `@pytest.mark`

### `_is_control_flow_line`

```python
def _is_control_flow_line(line: str) -> bool:
```

Parameters:

- `line: str` - A stripped or unstripped source line.

Returns:

- `bool` - `True` when the line ends with `:` and matches a recognized control-flow opener.

Purpose:

Private indentation helper used by `fix_indentation` to distinguish legitimate nested blocks from accidental over-indentation.

### `fix_indentation`

```python
def fix_indentation(code: str) -> str:
```

Parameters:

- `code: str` - Python source code with potentially inconsistent indentation inside functions or methods.

Returns:

- `str` - Code with repaired indentation in function bodies.

Purpose:

Normalizes common indentation mistakes within test functions and class methods while preserving legitimate nested blocks.

Key behavior:

- Tracks whether iteration is inside a function.
- Computes expected function-body indentation from the `def` line.
- Forces under-indented non-declaration body lines up to the expected body indent.
- Normalizes comments to at least the function-body indent.
- Detects accidental extra indentation after non-control-flow lines and dedents those lines back to function-body indent.
- Resets function context on class definitions.

Architectural note:

This function is stateful over lines. It maintains `inside_function`, `func_indent`, `previous_significant_indent`, and `previous_significant_line` to make local indentation decisions without parsing the Python AST.

### `dedent_indented_test_blocks`

```python
def dedent_indented_test_blocks(code: str) -> str:
```

Parameters:

- `code: str` - Python source code where entire top-level test blocks may be shifted right.

Returns:

- `str` - Code where malformed test blocks starting with an indented evidence marker or `def test_` are dedented as a unit.

Purpose:

Repairs generated tests where a whole top-level test block is incorrectly nested.

Key behavior:

- Scans line-by-line using an index-based loop.
- Detects an indented block beginning with `@pytest.mark.evidence` or `def test_`.
- Removes the shared block indentation until the block ends.
- Preserves blank lines inside the dedented block.

### `deduplicate_skip_calls`

```python
def deduplicate_skip_calls(code: str) -> str:
```

Parameters:

- `code: str` - Python source code that may contain repeated `pytest.skip(...)` calls.

Returns:

- `str` - Code with consecutive skip calls reduced to one and navigation steps preserved before skip emission.

Purpose:

Prevents generated tests from being cluttered with duplicate skip calls and avoids skipping before an initial navigation line has executed.

Key behavior:

- Tracks when it is inside a `def test_` block.
- Buffers skip calls in `pending_skips`.
- Flushes only the first pending skip when a non-skip line is reached.
- Defers skip flushing across `navigate(...)` or `goto(...)` lines so navigation remains before the skip.

Nested helper:

```python
def _flush_skips() -> None:
```

Parameters:

- None.

Returns:

- `None`

Purpose:

Appends the first pending skip call to the output and clears the pending skip buffer.

### `replace_bare_ellipsis`

```python
def replace_bare_ellipsis(code: str) -> str:
```

Parameters:

- `code: str` - Python source code that may contain bare `...` statements in generated test bodies.

Returns:

- `str` - Code where incomplete test-body ellipses are replaced by `pytest.skip(...)`.

Purpose:

Converts placeholder ellipsis bodies into explicit skipped tests so the generated output remains meaningful and executable.

Key behavior:

- Applies only while inside a `def test_*` function.
- Replaces a line whose stripped content is exactly `...` unless the following line is a comment.
- Adds `import pytest` if a skip call was introduced and no existing exact `import pytest` line exists.
- Inserts `import pytest` before the first import line it finds.

### `ensure_test_navigation`

```python
def ensure_test_navigation(code: str, target_url: str | None = None) -> str:
```

Parameters:

- `code: str` - Python source code containing generated test functions.
- `target_url: str | None = None` - Optional URL to inject. If omitted, the function attempts to extract the first URL from a `# PAGES_NEEDED:` block.

Returns:

- `str` - Code where test functions that accept `evidence_tracker` receive an initial navigation sequence if they do not already navigate.

Purpose:

Ensures generated tests start from a known page when either a direct target URL or skeleton metadata provides one.

Key behavior:

- Uses `target_url` when provided.
- Otherwise searches for a `# PAGES_NEEDED:` block containing comment URLs.
- Returns the original code unchanged if no URL can be found.
- Matches test functions containing `evidence_tracker` in the signature.
- Skips injection when a matched test body already contains `navigate(` or `goto(`.
- Injects:

```python
evidence_tracker.navigate("<url>")
dismiss_consent_overlays(page)
```

Nested helper:

```python
def _detect_body_indent(body: str) -> str:
```

Parameters:

- `body: str` - Captured test function body text.

Returns:

- `str` - The indentation string from the first significant body line, or four spaces by default.

Purpose:

Mirrors the existing function body's indentation style when injecting navigation.

Nested helper:

```python
def _inject_nav(match: re.Match[str]) -> str:
```

Parameters:

- `match: re.Match[str]` - Regex match containing the test function signature and body.

Returns:

- `str` - The original matched test function if navigation exists, otherwise the signature plus injected navigation lines and original body.

Purpose:

Per-test replacement callback used by `re.sub`.

## Architectural Patterns

### String-In, String-Out Normalization Pipeline

Every public function accepts source text and returns source text. This keeps the normalizer simple to compose and allows callers to run only the transforms they need in a deliberate order.

### Regex-Based Repair Instead Of AST Rewriting

The module uses regular expressions and line scanning instead of `ast` parsing because it is intended to repair code that may be temporarily invalid Python. This lets it normalize malformed LLM output before stricter syntax-dependent tooling runs.

### Conservative Local State Machines

Several transforms use lightweight state while scanning lines:

- `fix_indentation` tracks function context and previous significant lines.
- `dedent_indented_test_blocks` tracks block boundaries with an explicit index.
- `deduplicate_skip_calls` tracks test context and pending skip lines.
- `replace_bare_ellipsis` tracks whether the current line is inside a test function.

These state machines are intentionally local and deterministic.

### Graceful Degradation For Unresolved Generation Artifacts

Unresolved placeholders and incomplete ellipses are not allowed to remain as invalid or misleading code. They are converted into `pytest.skip(...)` statements, preserving test executability while surfacing incomplete generated behavior.

### Playwright/Pytest Sync Assumptions

The module assumes generated tests are pytest-style synchronous tests. Navigation injection uses `evidence_tracker.navigate(...)` and `dismiss_consent_overlays(page)`, and test detection is centered on `def test_*` functions rather than async Playwright code.

### Metadata-Aware Generation Cleanup

`strip_pages_needed_block` and `ensure_test_navigation` both understand the `# PAGES_NEEDED:` skeleton metadata convention. One removes it from final code, while the other can use it as a fallback source for the initial navigation URL.

## Expected Usage

A typical caller would apply these transforms as an ordered post-processing pipeline after LLM generation and placeholder resolution. `normalize_whitespace` should run early because later indentation logic assumes spaces and normalized line endings. Placeholder and ellipsis cleanup should run before final syntax validation so unresolved generation artifacts become valid pytest code.

## Side Effects

The module itself has no filesystem, network, subprocess, or runtime test side effects. All transformations operate on in-memory strings.





# `src/code_postprocessor.py`

## High-Level Purpose

`code_postprocessor.py` contains pure string-transformation helpers for generated Playwright Python code. It normalizes LLM-produced test code into the project's expected pytest sync format, repairs common hallucinations, injects required imports and fixtures, converts placeholder tokens into executable evidence-tracker calls, and can strip evidence-tracking instrumentation back out for export.

The module is intentionally stateless: every function accepts a source-code string or single code line and returns a transformed string. It performs no filesystem I/O, subprocess work, or network access.

## Module Dependencies

- `re`: regular-expression engine used for most repairs and rewrites.
- `.code_normalizer`: supplies deterministic normalization utilities used by `normalise_generated_code()`, including whitespace normalization, indentation repair, placeholder cleanup, navigation injection, and skip-call deduplication.
- `.llm_reasoning_filter.strip_llm_reasoning`: removes leaked reasoning text before the rest of the post-processing pipeline runs.

## Classes

This module defines no classes.

## Public Functions

### `normalise_generated_code(code: str, consent_mode: str = "auto-dismiss", target_url: str = "") -> str`

Applies the main post-processing pipeline to generated test code.

Parameters:

- `code: str`: Raw generated Python code.
- `consent_mode: str`: Consent overlay behavior. When set to `"auto-dismiss"`, the function injects consent-helper imports and calls after navigation.
- `target_url: str`: Optional URL used by `ensure_test_navigation()` when inserting missing test navigation.

Returns:

- `str`: Normalized, repaired Python code.

Key behavior:

- Normalizes whitespace before other transforms.
- Strips leaked LLM reasoning text.
- Converts standalone placeholders and evidence-tracker-wrapped placeholders.
- Repairs malformed pytest evidence decorators.
- Injects `pytest` and `playwright.sync_api` imports when needed.
- Renames hallucinated `evidence_launcher` fixture references to `evidence_tracker`.
- Ensures test functions include required `page: Page` and `evidence_tracker` fixtures.
- Rewrites direct `page.goto()` calls to `evidence_tracker.navigate()`.
- Repairs hallucinated marker syntax, constructor names, page-object constructor arguments, and invalid decorator assignment lines.
- Normalizes several hallucinated type annotations to `Page`.
- Optionally injects consent-overlay dismissal support.
- Rewrites bare `page.` references inside non-test class instance methods to `self.page.`.
- Removes unsupported `evidence_tracker.record_condition(...)` calls.
- Ensures tests contain navigation, strips unresolved placeholders, fixes module/test indentation, deduplicates skips, and replaces bare ellipses.

Architectural note: ordering is important. Early cleanup prepares the code for import and fixture inference; late indentation and placeholder passes act as safety nets after regex rewrites have potentially changed structure.

### `replace_token_in_line(line: str, action: str, token: str, resolved_value: str, duplicate_selectors: set[str], description: str = "", fill_value: str = "") -> str`

Replaces one placeholder token within a single line of generated code.

Parameters:

- `line: str`: Source line containing, or potentially containing, a placeholder token.
- `action: str`: Placeholder action type. Recognized actions are `"CLICK"`, `"ASSERT"`, `"FILL"`, `"GOTO"`, and `"URL"`.
- `token: str`: Placeholder token to replace.
- `resolved_value: str`: Selector, URL, or replacement expression resolved for the token.
- `duplicate_selectors: set[str]`: Accepted by the signature but not used in the current function body.
- `description: str`: Optional human-readable label for evidence tracker calls. Falls back to `token`.
- `fill_value: str`: Value used when rewriting `"FILL"` actions.

Returns:

- `str`: The rewritten line, preserving original indentation where a whole-line replacement is emitted.

Key behavior:

- Converts `CLICK` placeholders to `evidence_tracker.click(...)`.
- Converts `ASSERT` placeholders and matching `expect(page.locator(...))` assertions to `evidence_tracker.assert_visible(...)`.
- Converts `FILL` placeholders to `evidence_tracker.fill(...)`, including repair of evidence-tracker calls missing the fill value.
- Converts `GOTO` and `URL` placeholders to `evidence_tracker.navigate(...)` or replaces quoted token references.
- Preserves `pytest.skip(...)` replacements as whole-line returns.

### `inject_import(code: str, import_line: str) -> str`

Injects an import line near the top of a Python code string.

Parameters:

- `code: str`: Python source text.
- `import_line: str`: Import statement to add.

Returns:

- `str`: Source text with the import added once.

Key behavior:

- Inserts after an opening module docstring when present.
- Uses normalized whitespace comparison to avoid duplicate imports.

### `strip_evidence_from_test_code(code: str) -> str`

Converts evidence-aware test code back into plain Playwright test code.

Parameters:

- `code: str`: Generated test code that may use `evidence_tracker`.

Returns:

- `str`: Test code using direct Playwright `page` and `expect` calls.

Key behavior:

- Rewrites evidence-tracker actions to Playwright equivalents:
  - `click()` -> `page.locator(...).click()`
  - `fill()` -> `page.locator(...).fill(...)`
  - `navigate()` -> `page.goto(...)`
  - `assert_visible()` -> `expect(page.locator(...)).to_be_visible()`
  - `select()` -> `page.locator(...).select_option(...)`
  - `get_text()` -> `page.locator(...).text_content()`
- Removes `evidence_tracker` parameters from test signatures.
- Removes `EvidenceTracker` and consent-helper imports.
- Removes `@pytest.mark.evidence` decorators.
- Ensures the Playwright import includes `expect` when assertions are present.
- Removes consent-helper calls and collapses excessive blank lines.

### `strip_evidence_from_pom(code: str) -> str`

Converts evidence-aware page-object-model code back into plain Playwright POM code.

Parameters:

- `code: str`: Page-object code that may use `self.tracker`.

Returns:

- `str`: Page-object code using direct `self.page` and `expect` calls.

Key behavior:

- Removes `EvidenceTracker` imports and constructor parameters.
- Removes `self.tracker = tracker` assignments.
- Rewrites tracker calls to direct Playwright calls on `self.page`.
- Ensures `expect` is imported when assertion rewrites require it.
- Collapses excessive blank lines.

### `flatten_inner_functions(code: str) -> str`

Removes nested function wrappers inside top-level test functions.

Parameters:

- `code: str`: Python source text that may contain nested helper/test functions.

Returns:

- `str`: Source text with nested function bodies lifted into the enclosing test block.

Key behavior:

- Scans line by line for top-level `def test_...` functions.
- Detects nested `def ...` blocks inside tests.
- Preserves nearby `@pytest.mark.evidence` decorators by moving them to the enclosing test indentation.
- Drops self-calls to the nested function when lifting the body.

### `rewrite_page_references_in_class_methods(code: str) -> str`

Rewrites bare page references inside non-test class instance methods.

Parameters:

- `code: str`: Python source text.

Returns:

- `str`: Source text with selected instance-method references rewritten.

Key behavior:

- Tracks whether the scan is inside a class and whether that class appears to be a test class.
- For non-test classes, detects instance methods whose first parameter is `self`.
- Replaces bare `page.` with `self.page.` inside those methods.
- Rewrites `evidence_tracker.` to `self.evidence_tracker.` when the method signature does not have an `evidence_tracker` parameter.
- Rewrites `dismiss_consent_overlays(page)` to `dismiss_consent_overlays(self.page)`.
- Replaces `(page)` and `Page(` patterns inside instance methods with self-page equivalents.

## Internal Helpers

### `_ensure_evidence_tracker_fixture(code: str) -> str`

Adds `page: Page` and `evidence_tracker` fixture parameters to test functions that need them.

Parameters:

- `code: str`: Python source text.

Returns:

- `str`: Source text with updated test function signatures.

Key behavior:

- Finds `def test_...(...)` signatures using regex.
- Reads each test body by scanning until the next top-level decorator, function, class, or import.
- Infers `evidence_tracker` need from `evidence_tracker.` usage and page-object instantiation.
- Infers `page` need from POM construction, bare `page.` usage, consent-helper usage, or evidence-tracker usage.
- Ensures `page: Page` appears first when required.
- Appends `evidence_tracker` when required and absent.

### `_inject_consent_helper(code: str) -> str`

Injects consent overlay dismissal support.

Parameters:

- `code: str`: Python source text.

Returns:

- `str`: Source text with the consent-helper import and calls inserted.

Key behavior:

- Adds `from src.browser_utils import dismiss_consent_overlays` after the Playwright import when possible, otherwise prepends it.
- Adds `dismiss_consent_overlays(page)` after lines that call `page.goto(...)` or `evidence_tracker.navigate(...)`.
- Avoids adding duplicate calls on lines already mentioning the helper.

## Architectural Patterns

- Functional pipeline: transformations are composed as string-in/string-out functions.
- Regex-first repair strategy: most changes are targeted text rewrites for recurring LLM output patterns.
- Late safety nets: indentation repair, unresolved-placeholder replacement, skip deduplication, and ellipsis replacement run after broader rewrites.
- Evidence instrumentation boundary: generated tests can be instrumented with `evidence_tracker`, then converted back to plain Playwright for export.
- Fixture inference by body scan: `_ensure_evidence_tracker_fixture()` uses local function-body text to infer required pytest fixtures without parsing the AST.
- Lightweight import management: `inject_import()` inserts imports idempotently and respects a leading module docstring.
- POM/test distinction: class-method rewriting deliberately skips classes whose names start with `Test` or end with `Test`.

## Side Effects and State

- No module-level mutable state.
- No classes or stored configuration.
- No direct file, network, subprocess, or test-run side effects.
- All transformations are deterministic for a given input string and argument set.





# `src/code_validator.py`

## High-Level Purpose

Validates generated Python test code before it is saved or executed. Catches syntax errors early via `ast.parse()` and detects known Playwright anti-patterns that LLMs commonly generate.

## Module Metadata

- **Lines:** 174
- **Imports:** `ast`, `re`

## Functions

### `validate_python_syntax(code: str) -> str | None`
Uses `ast.parse()` to validate Python syntax. Returns `None` if valid, or a descriptive error string with line number and message.

### `validate_test_function(code: str) -> str | None`
Extended validation for test functions:
1. Runs `validate_python_syntax()` first
2. Walks AST to detect `async def` (not allowed â€” must use sync pytest format)
3. Validates test function naming convention (`test_` prefix)

### `validate_generated_locator_quality(code: str) -> str | None`
Detects known flaky/invalid Playwright patterns. Returns `None` if all checks pass, or an error message. Checks for:

| Anti-pattern | Error |
|--------------|-------|
| `.should_be_visible()` | Not valid in Playwright Python â€” use `expect(locator).to_be_visible()` |
| `get_by_role('link')` without name | Ambiguous in strict mode |
| `page.locator("button")` â€” bare tag selectors | Too broad â€” use specific locators |
| `page.wait_for_load_state().status` | Returns `None`, not a response object |
| `to_have_url_containing()` / `to_have_title_containing()` | Invalid assertion methods |
| `expect(...)` without importing `expect` | Missing import |
| `expect(page.title())` / `expect(page.url())` | Not valid â€” use `expect(page).to_have_title(...)` |
| `expect(page).to_be_connected()` | Not a valid Playwright assertion |
| `re.compile(...)` without `import re` | Missing import |
| `screenshot` custom helpers/marks | Project-specific markers not available |
| Root URL assertion without trailing `/` | Use canonical URL with `/` |
| `sync_playwright()` | Use pytest-playwright fixture style |
| `except: pass` | Hides test failures |
| `not_to_have_url(...)` | Weak negative-only assertions |

## Key Design Decisions
- **AST-based validation** â€” uses `ast.parse()` for reliable syntax checking
- **Pattern-based quality checks** â€” regex-based detection of known LLM hallucination patterns
- **Fail-fast** â€” returns first error found; does not accumulate multiple errors

## Dependencies
- No project-internal dependencies â€” standalone validation module





# `src/config.py`

## High-Level Purpose

`src/config.py` centralizes project-wide configuration values and enum types for the AI Playwright Test Generator. It provides stable, typed names for analysis modes, report formats, input detection behavior, screenshot capture depth, screenshot naming style, output directories, and Jira project defaults.

The module is intentionally lightweight: it has no runtime functions, no classes with custom behavior, and no direct dependencies on other project modules. Its main role is to expose shared constants and `Enum` definitions that other parts of the application can import instead of duplicating string literals.

## Module Dependencies

```python
from __future__ import annotations

import os
from enum import Enum
```

- `os` is used to read the optional `JIRA_PROJECT_KEY` environment variable.
- `Enum` is used as the base class for all mode and format definitions.
- `annotations` future import keeps type annotation behavior modern and consistent.

## Classes

### `class AnalysisMode(Enum)`

```python
class AnalysisMode(Enum):
    FAST = "fast"
    THOROUGH = "thorough"
    AUTO = "auto"
```

Defines how user stories should be analyzed.

Members:

- `FAST: AnalysisMode` - Regex-based analysis without LLM usage.
- `THOROUGH: AnalysisMode` - LLM-powered analysis.
- `AUTO: AnalysisMode` - Fast analysis first, with thorough analysis available for complex inputs.

Constructor parameters and return value:

- Uses the inherited `Enum` construction behavior.
- No custom `__init__`, methods, parameters, or return values are defined.

### `class ReportFormat(Enum)`

```python
class ReportFormat(Enum):
    CONFLUENCE = "confluence"
    JIRA_XML = "jira_xml"
    JSON = "json"
    MARKDOWN = "markdown"
    LOCAL = "local"
    JIRA = "jira"
    SHAREABLE = "shareable"
```

Defines supported evidence and report output formats.

Members:

- `CONFLUENCE: ReportFormat` - HTML intended for Confluence or Confluence Cloud.
- `JIRA_XML: ReportFormat` - XML intended for Jira import.
- `JSON: ReportFormat` - Structured JSON data format.
- `MARKDOWN: ReportFormat` - Markdown documentation output.
- `LOCAL: ReportFormat` - Relative-path report output for local viewing.
- `JIRA: ReportFormat` - Absolute-path report output for Jira uploads.
- `SHAREABLE: ReportFormat` - Clean team documentation output.

Constructor parameters and return value:

- Uses the inherited `Enum` construction behavior.
- No custom `__init__`, methods, parameters, or return values are defined.

### `class DetectionMode(Enum)`

```python
class DetectionMode(Enum):
    AUTO = "auto"
    EXPLICIT = "explicit"
    FAST = "fast"
    THOROUGH = "thorough"
```

Defines how the application should detect an input format.

Members:

- `AUTO: DetectionMode` - Regex-first detection with LLM fallback.
- `EXPLICIT: DetectionMode` - User-specified input format.
- `FAST: DetectionMode` - Pure regex detection without LLM usage.
- `THOROUGH: DetectionMode` - LLM-based detection.

Constructor parameters and return value:

- Uses the inherited `Enum` construction behavior.
- No custom `__init__`, methods, parameters, or return values are defined.

### `class CaptureLevel(Enum)`

```python
class CaptureLevel(Enum):
    BASIC = "basic"
    STANDARD = "standard"
    THOROUGH = "thorough"
```

Defines how much screenshot evidence should be captured during generated test execution or reporting workflows.

Members:

- `BASIC: CaptureLevel` - Entry and outcome screenshots only.
- `STANDARD: CaptureLevel` - Entry, step, and outcome screenshots.
- `THOROUGH: CaptureLevel` - Screenshots for every major action.

Constructor parameters and return value:

- Uses the inherited `Enum` construction behavior.
- No custom `__init__`, methods, parameters, or return values are defined.

### `class ScreenshotNaming(Enum)`

```python
class ScreenshotNaming(Enum):
    SEQUENTIAL = "sequential"
    DESCRIPTIVE = "descriptive"
    HYBRID = "hybrid"
```

Defines available screenshot filename strategies.

Members:

- `SEQUENTIAL: ScreenshotNaming` - Sequential numeric naming, such as `test_entry_001.png`.
- `DESCRIPTIVE: ScreenshotNaming` - Descriptive timestamp-style naming, such as `login_success_20260303.png`.
- `HYBRID: ScreenshotNaming` - Descriptive plus sequence/timestamp-style naming, such as `login_success_001_20260303.png`.

Constructor parameters and return value:

- Uses the inherited `Enum` construction behavior.
- No custom `__init__`, methods, parameters, or return values are defined.

## Functions

No module-level functions are defined in `src/config.py`.

## Module Constants

### Jira Configuration

```python
JIRA_PROJECT_KEY: str = os.getenv("JIRA_PROJECT_KEY", "TEST")
```

- Type: `str`
- Value source: `JIRA_PROJECT_KEY` environment variable, defaulting to `"TEST"`.
- Purpose: Supplies the default Jira project key while allowing deployment or local environment overrides.

### Screenshot Storage Configuration

```python
STORAGE_MODE: str = "filesystem"
NAMING_CONVENTION: ScreenshotNaming = ScreenshotNaming.HYBRID
CAPTURE_LEVEL: CaptureLevel = CaptureLevel.STANDARD
SCREENSHOT_DIR: str = "screenshots"
```

- `STORAGE_MODE: str` - Selects screenshot storage backend. Current default is `"filesystem"`.
- `NAMING_CONVENTION: ScreenshotNaming` - Selects the default screenshot naming strategy. Current default is `ScreenshotNaming.HYBRID`.
- `CAPTURE_LEVEL: CaptureLevel` - Selects screenshot capture depth. Current default is `CaptureLevel.STANDARD`.
- `SCREENSHOT_DIR: str` - Directory name for screenshot output. Current default is `"screenshots"`.

### LLM Analysis Configuration

```python
LLM_ANALYSIS_MODE: AnalysisMode = AnalysisMode.THOROUGH
```

- Type: `AnalysisMode`
- Current default: `AnalysisMode.THOROUGH`
- Purpose: Preserves backward compatibility with older CLI configuration while exposing the default LLM analysis behavior.

### Output Directory Configuration

```python
GENERATED_TESTS_DIR: str = "generated_tests"
```

- Type: `str`
- Current default: `"generated_tests"`
- Purpose: Defines the output directory used for generated Playwright test files.

## Architectural Patterns

### Centralized Configuration Module

The file gathers shared settings into one importable module. This reduces repeated literals across UI, CLI, generation, screenshot, and reporting code.

### Typed Enum Boundaries

The module uses `Enum` classes to model constrained option sets instead of passing arbitrary strings throughout the codebase. This pattern gives downstream code named values for user story analysis, report rendering, input detection, screenshot capture, and screenshot naming.

### String Values for Interop

Each enum member stores a lowercase string value. This makes enum values suitable for serialization, command-line arguments, UI selections, configuration persistence, and report metadata while still giving Python callers strongly named members.

### Environment Override at Import Time

`JIRA_PROJECT_KEY` is read from the process environment when the module is imported. This supports local or deployment-specific Jira configuration without requiring a separate configuration file.

### Module-Level Defaults

Default configuration values are exposed as typed module-level constants. This keeps startup behavior simple and makes the current defaults discoverable from one place.

## Side Effects

Importing this module reads the `JIRA_PROJECT_KEY` environment variable once through `os.getenv`. No files are read or written, no network calls are made, and no application services are initialized.





# `src/coverage_utils.py`

## High-Level Purpose
Centralizes logic for turning acceptance criteria and generated test code into structured coverage information. Reusable by Streamlit UI, CLI, and reports.

## Module Metadata
- **Lines:** 188
- **Imports:** `__future__`, `re`, `collections.abc`, `dataclasses`, `typing`

## Classes

### `RequirementCoverage` (dataclass)
Tracks coverage for a single requirement.
- Fields: `id`, `description`, `status`, `linked_tests`

### `CoverageRunResult` (Protocol)
Protocol for minimal test-run result objects.
- Properties: `name`, `status`, `duration`

### `CoverageDisplayRow` (dataclass)
Display-compatible coverage row for UI tables.
- Fields: `criterion`, `status`, `test_name`, `duration`, `notes`

## Functions

### `extract_test_names(generated_code: str) -> list[str]`
Extracts pytest-style test function names from Python source using regex.

### `compute_coverage(criteria: list[str], code: str, run_results: Sequence[CoverageRunResult] | None) -> list[RequirementCoverage]`
Maps criteria to test names by number-based matching (TC-001 â†’ test_01_*) then keyword fallback.

### `coverage_to_display_rows(coverage: list[RequirementCoverage]) -> list[CoverageDisplayRow]`
Converts coverage data to UI-friendly display rows.

## Key Design Decisions
- Number-based matching before keyword fallback prevents false positives
- Protocol-based interface for run results enables duck typing
- Zero external dependencies â€” pure computation

## Dependencies
- None â€” stdlib only





# `src/element_enricher.py`

## High-Level Purpose
Enriches scraped DOM elements with visual and contextual metadata (icon detection, bounding box hints, parent context) to improve placeholder matching when descriptions are vague.

## Module Metadata
- **Lines:** 337
- **Imports:** `__future__`, `typing`, `bs4.BeautifulSoup` (lazy)

## Classes

### `ElementEnricher` (classmethod-only utility)
| Method | Description |
|--------|-------------|
| `enrich_element(element, html_snippet, parent_classes)` | Returns enriched element dict with `is_icon`, `icon_classes`, `icon_unicode`, `is_decorative`, `is_hover_reveal`, `parent_text`, `aria_icon_label`, `visual_description` |
| `enrich_batch(elements, html_snippets)` | Batch version; maps index â†’ html_snippet |
| `get_hover_reveal_selectors(elements)` | Extracts selectors for hover-reveal elements |
| `_detect_icon(element)` | Detects icon from class names (Font Awesome, Material, custom) |
| `_extract_parent_text(html_snippet)` | Uses BeautifulSoup to extract surrounding text |
| `_build_visual_description(element)` | Generates human-readable visual summary |

## Key Design Decisions
- Classmethod-only â€” no instance state needed
- Lazy import of BeautifulSoup to avoid hard dependency
- Enriches at scrape-time to avoid runtime overhead

## Dependencies
- `bs4` (lazy import)
- No project-internal dependencies





# `src/evidence_loader.py`

## Purpose
Loads evidence JSON from generated test packages. Evidence files are written by EvidenceTracker at runtime containing diagnostic context for failed steps.

## Metadata
- **Lines:** ~183
- **Imports:** json, logging, pathlib.Path, typing

## Functions
| Function | Description |
|----------|-------------|
| `load_evidence_for_package(package_dir)` | Scans `<package_dir>/evidence/` for `*.evidence.json`; returns dict mapping test name â†’ evidence |
| `get_failure_diagnostics(evidence)` | Extracts failure diagnostics: failed steps, page URL, title, duration |
| `get_screenshot_paths(evidence)` | Returns screenshot paths from failed steps |
| `match_evidence_to_test(evidence_map, test_name)` | Finds matching evidence via exact, prefix, and parameterized name matching |

## Key Logic
- Evidence files keyed by filename stem
- Failed steps filtered by result status
- Matching tries: exact name â†’ test name prefix â†’ parameterized pattern
- Returns None gracefully when no evidence found





# `src/evidence_report.py`

## High-Level Purpose
Evidence/annotated report generators that read `.evidence.json` sidecar files and produce interactive HTML visualizations with SVG overlays, heatmaps, and journey views.

## Module Metadata
- **Lines:** 760
- **Imports:** `__future__`, `base64`, `json`, `re`, `dataclasses`, `pathlib`, `typing`, `urllib.parse`, `src.report_builder.escape_html`

## Functions

### `generate_annotated_screenshot(*, sidecar_path, view_mode, title) -> str`
Returns interactive HTML with SVG overlay on a single screenshot. View modes: `annotated`, `heatmap`, `clean`.

### `generate_annotated_journey(*, sidecar_path, view_mode, title) -> str`
Multi-page journey viewer with segment selector for tests navigating across URLs.

### `list_evidence_from_package(package_dir: str) -> TestPackageEvidence`
Scans test package directory for `*.evidence.json` files, returns aggregated data.

### `generate_package_report(*, package_dir, view_mode, title) -> str`
Generates consolidated HTML report for an entire test package.

## Classes

### `EvidenceEntry` (dataclass)
Single evidence record: timestamp, action, selector, status, screenshot_path, notes.

### `TestPackageEvidence` (dataclass)
Aggregated evidence from a test package: test_files, entries, failures, total_duration.

## Key Design Decisions
- Base64-embedded screenshots for portable HTML reports
- SVG overlay for visual annotations on screenshots
- Three view modes for different analysis needs

## Dependencies
- `src.report_builder.escape_html`
- stdlib for everything else





# `src/evidence_serializer.py`

## Purpose
Serialization utilities for evidence sidecar JSON files. Handles writing and reading the structured evidence format used by EvidenceTracker.

## Metadata
- **Lines:** 64
- **Imports:** json, pathlib.Path, typing.Any

## Class
| Class | Description |
|-------|-------------|
| `EvidenceSerializer` | Static methods for reading/writing evidence JSON sidecar files |

## Methods
| Method | Description |
|--------|-------------|
| `serialize(test_name, condition_ref, story_ref, status, page_url, run_history, steps)` | Returns JSON string for evidence sidecar with schema version |
| `load(sidecar_path)` | Loads and returns sidecar contents as dict |
| `load_run_history(sidecar_path)` | Extracts run history dict from sidecar |
| `load_steps(sidecar_path)` | Extracts steps list from sidecar |
| `validate(payload)` | Checks required keys: schema_version, test, steps |

## Key Logic
- Schema version tracked as constant ("1.0")
- All methods are @staticmethod â€” no instance state needed
- JSON output uses 2-space indent, UTF-8 encoding
- Validates presence of schema_version, test, and steps keys





# `src/evidence_tracker.py`

## High-Level Purpose

Runtime evidence tracker â€” records each test step (navigate, click, fill, assert) with screenshots, element metadata, timing, and failure diagnostics. Writes per-test sidecar JSON files for evidence-based reporting.

## Module Metadata

- **Lines:** 426
- **Imports:** `re`, `time`, `pathlib.Path`, `typing.Any`, `playwright.sync_api.Page`, `src.evidence_serializer`, `src.failure_reporter`, `src.hover_click_utils`, `src.locator_fallback`

## Class: `EvidenceTracker`

### `__init__(page, test_name, condition_ref="unknown", story_ref="unknown", evidence_root=None, test_package_dir=None)`
- `test_package_dir` takes precedence over `evidence_root` for evidence directory
- Evidence written to `<test_package_dir>/evidence/`
- Sidecar: `{test_name}.evidence.json`
- Loads previous run history and step data for incremental run counts

### `_clean_label(label) -> str`
Converts `{{ACTION:description}}` tokens to human-readable `"Action: description"`.

### `_dismiss_consent_overlays()` / `_dismiss_ad_overlays()`
Delegates to `src.browser_utils.dismiss_consent_overlays`.

### `_load_previous_history() -> dict` / `_load_previous_steps() -> list`
Loads run history and step data from sidecar JSON for incremental counters.

### `_get_element_metadata(locator) -> dict`
Captures tag, id, data-testid, bounding box, and viewport percentages for an element. Uses full-document size for coordinates.

### `_record_step(step_type, label, locator, value, take_screenshot, error, matched_text, fallback_used, fallback_chain, elapsed_ms)`
Core recording method. Builds step dict with:
- Incremental `step_run_count` from previous runs
- Full-page screenshot when requested
- Element metadata (bbox, tag, attributes)
- Failure diagnosis via `FailureReporter.diagnose_failure()` on error
- Status: `"passed"`, `"partial_pass"` (when fallback used), `"failed"`

### `navigate(url, label="")` â€” Navigate + dismiss overlays + screenshot
### `fill(locator, value, label="")` â€” Fill form field
### `click(locator, label="")` â€” Click with layered fallback:
1. Scroll into view + direct click (`.first` to avoid strict-mode)
2. On visibility/timeout error: dismiss ads â†’ hover-reveal â†’ locator scoring fallback
3. Fallback success â†’ `"partial_pass"` status with audit trail
### `assert_visible(locator, label="")` â€” Wait for visible + screenshot + capture text
### `write(status="passed") -> str` â€” Serialize sidecar JSON, update run history counters, return path

## Dependencies

- `src.evidence_serializer.EvidenceSerializer`
- `src.failure_reporter.FailureReporter`
- `src.hover_click_utils.try_hover_and_click`
- `src.locator_fallback.LocatorFallback`
- `src.browser_utils.dismiss_consent_overlays`

## Depended On By

Generated test code (runtime), `evidence_loader.py`, report builders





# `src/export_service.py`

## High-Level Purpose

`export_service.py` builds clean, runnable exports from generated Playwright test packages. Its main responsibility is to copy and rewrite selected package artifacts into an `exported_tests`-style output directory while removing `EvidenceTracker` dependencies from test code and page object modules.

The module supports two export modes through `ExportMode`:

- `ExportMode.POM`: exports `test_*.py` files plus matching `pages/po_*.py` page object modules.
- Non-POM / flat mode: exports only cleaned `test_*.py` files plus shared metadata and support artifacts.

It also generates a clean `conftest.py`, updates or copies package metadata, optionally carries forward scrape and SQLite evidence artifacts, and writes an export-facing `README.md`.

## Imports and Dependencies

- `json`: parses and serializes `package_manifest.json`.
- `shutil`: copies manifest and SQLite files while preserving file metadata via `copy2`.
- `datetime.datetime`: creates timestamped export directories and export metadata.
- `pathlib.Path`: normalizes and manipulates filesystem paths.
- `typing.Any`: annotates decoded JSON manifest dictionaries.
- `.code_postprocessor.strip_evidence_from_pom`: removes evidence-related code from page object modules.
- `.code_postprocessor.strip_evidence_from_test_code`: removes evidence-related code from generated tests.
- `.pipeline_models.ExportMode`: controls whether the export is POM or flat.

## Public API

### `export_clean_suite`

```python
def export_clean_suite(
    *,
    source_package_dir: str | Path,
    export_mode: ExportMode,
    output_base_dir: str = "exported_tests",
    story_slug: str = "",
) -> ExportResult:
```

Exports a clean test suite from a generated package directory.

Parameters:

- `source_package_dir: str | Path`: path to the generated test package to export.
- `export_mode: ExportMode`: export shape, currently distinguishing POM exports from flat exports.
- `output_base_dir: str = "exported_tests"`: base directory where timestamped export folders are created.
- `story_slug: str = ""`: optional slug used in the export directory name. If omitted, the slug is inferred from the source package directory name.

Returns:

- `ExportResult`: object containing paths to the export directory, exported test files, exported page objects, generated `conftest.py`, and generated `README.md`.

Raises:

- `FileNotFoundError`: raised when `source_package_dir` does not exist.

Behavior:

1. Converts `source_package_dir` to `Path` and verifies it exists.
2. Creates a timestamped export directory under `output_base_dir`.
3. In POM mode, reads `pages/po_*.py`, strips evidence code, and writes cleaned page objects to `export_dir/pages/`.
4. Reads each root-level `test_*.py`, strips evidence code, and writes cleaned tests to the export directory.
5. Writes a clean `conftest.py` without custom evidence fixtures.
6. Copies `scrape_manifest.json` when present.
7. Copies `playwright_tests.db` and related WAL/SHM files when present under either `evidence/` or the package root.
8. Updates `package_manifest.json` with export metadata when valid JSON is available, or copies the original manifest if JSON decoding fails.
9. Generates an export `README.md`.
10. Returns an `ExportResult` with exported artifact paths.

## Classes

### `ExportResult`

```python
class ExportResult:
```

Simple result container for an export operation.

#### `__init__`

```python
def __init__(
    self,
    *,
    export_dir: str,
    test_files: list[str],
    page_objects: list[str],
    conftest: str,
    readme: str,
) -> None:
```

Parameters:

- `export_dir: str`: path to the export directory.
- `test_files: list[str]`: paths to exported test files.
- `page_objects: list[str]`: paths to exported page object files.
- `conftest: str`: path to generated `conftest.py`.
- `readme: str`: path to generated `README.md`.

Returns:

- `None`.

Attributes:

- `self.export_dir`
- `self.test_files`
- `self.page_objects`
- `self.conftest`
- `self.readme`

#### `summary`

```python
def summary(self) -> str:
```

Returns a human-readable multiline summary of the export.

Parameters:

- None.

Returns:

- `str`: summary containing export destination and counts for tests, page objects, conftest, and README.

## Private Helpers

### `_write_clean_conftest`

```python
def _write_clean_conftest(export_dir: Path, export_mode: ExportMode) -> None:
```

Writes a minimal generated `conftest.py` into the export directory.

Parameters:

- `export_dir: Path`: directory where `conftest.py` should be written.
- `export_mode: ExportMode`: mode used only to label the generated file as `POM` or `Flat`.

Returns:

- `None`.

Side effects:

- Writes `export_dir / "conftest.py"` using UTF-8.

### `_update_package_manifest`

```python
def _update_package_manifest(source: Path, export_dir: Path, export_mode: ExportMode) -> None:
```

Copies or updates `package_manifest.json` with export metadata.

Parameters:

- `source: Path`: generated package directory containing the source manifest.
- `export_dir: Path`: export directory where the updated manifest should be written.
- `export_mode: ExportMode`: determines whether `export_mode` metadata is written as `"pom"` or `"flat"`.

Returns:

- `None`.

Behavior:

- If `source / "package_manifest.json"` does not exist, returns without writing anything.
- If the manifest cannot be decoded as JSON, copies it unchanged into the export directory.
- If decoding succeeds, adds:
  - `export_mode`
  - `exported_at`
- Writes formatted JSON with two-space indentation.

Side effects:

- May copy or write `export_dir / "package_manifest.json"`.

### `_generate_export_readme`

```python
def _generate_export_readme(export_dir: Path, export_mode: ExportMode, source: Path) -> None:
```

Generates a README describing the exported test suite.

Parameters:

- `export_dir: Path`: directory where `README.md` should be written.
- `export_mode: ExportMode`: controls mode labels and whether a page object note is included.
- `source: Path`: source generated package used to read metadata from `package_manifest.json`.

Returns:

- `None`.

Behavior:

- Reads `source / "package_manifest.json"` when present and valid.
- Extracts optional metadata:
  - `source_story`
  - `starting_url`
  - `provider`
  - `model`
  - `created_at`
- Detects whether `export_dir / "evidence" / "playwright_tests.db"` exists.
- Writes a README with generation/export timestamps, mode, story and provider metadata, content notes, a basic pytest command, and export limitations.

Side effects:

- Writes `export_dir / "README.md"` using UTF-8.

## Key Architectural Patterns

### Export-Oriented Service Function

The module centers on `export_clean_suite` as a single orchestration function. It validates input, prepares the destination, delegates specialized writing tasks to private helpers, and returns a compact result object.

### Filesystem Transformation Pipeline

The export process is a filesystem pipeline:

1. Read generated package artifacts.
2. Transform code by stripping evidence-related dependencies.
3. Write cleaned artifacts into a new timestamped export directory.
4. Copy optional metadata and evidence database artifacts.
5. Generate export-specific support files.

### Mode-Based Branching

`ExportMode` gates POM-specific behavior. POM mode includes `pages/po_*.py` processing and page object README notes; flat mode skips page object export but otherwise uses the same evidence-stripping path for test files.

### Private Writer Helpers

Support-file generation is separated into private helpers:

- `_write_clean_conftest` owns conftest creation.
- `_update_package_manifest` owns manifest update/copy behavior.
- `_generate_export_readme` owns human-readable export documentation.

This keeps the public function focused on orchestration while leaving output-format details close to the writer functions.

### Defensive Metadata Handling

The manifest helpers tolerate missing or invalid `package_manifest.json` files:

- Missing manifests are ignored.
- Invalid JSON is copied unchanged for preservation.
- README metadata falls back to empty strings or `"Unknown"`.

### Lightweight Result Object

`ExportResult` is a manually defined container rather than a dataclass. It stores string paths and provides a `summary()` formatter for UI or CLI presentation.

## External Side Effects

This module performs direct filesystem writes and copies:

- Creates a timestamped export directory.
- Creates `pages/` and `evidence/` subdirectories when needed.
- Writes cleaned Python files.
- Writes generated `conftest.py`, `README.md`, and JSON metadata.
- Copies scrape manifests and SQLite database artifacts.

It does not run exported tests, invoke Playwright, or call an LLM.

## Notable Implementation Details

- Export directories are named with `datetime.now().strftime("%Y%m%d_%H%M%S")`.
- When `story_slug` is not provided, the slug is derived from the source directory name by dropping the first underscore-delimited segment when possible.
- Test files are discovered using `source.glob("test_*.py")`.
- Page object files are discovered using `source / "pages"` and `glob("po_*.py")`.
- SQLite evidence databases are searched in both `source / "evidence"` and the package root.
- WAL and SHM companion files are copied when present.
- Generated support files use UTF-8 encoding.





# `src/failure_classifier.py`

## High-Level Purpose
Classifies test failures into machine-readable categories for dashboard and trend analysis.

## Module Metadata
- **Lines:** 178
- **Imports:** `__future__`, `re`, `enum`, `dataclasses`, `typing`

## Enums

### `FailureCategory` (str, Enum)
Values: `NO_MATCH`, `MULTI_MATCH`, `TIMEOUT`, `ERROR`, `ASSERTION`, `PHANTOM`, `UNKNOWN`

## Functions

### `classify_failure(text: str, category: str | None = None) -> FailureCategory`
Maps pytest failure text to `FailureCategory` using keyword heuristics.

### `classify_failure_pattern(message: str) -> FailureCategory`
Pattern-based classifier for structured error messages.

### `classify_test_result(test: dict, *, category: str | None = None) -> FailureCategory`
Classifies a single test result dict.

### `summarize_failures(results: list[dict]) -> FailureSummary`
Aggregates categorized failures into counts and sorted lists.

## Classes

### `FailureSummary` (dataclass)
Aggregated failure summary: total_passed, total_failed, category_counts, top_categories.

## Key Design Decisions
- Keyword-based heuristics (no ML dependency)
- Categories align with strict-mode pytest errors
- Stateless pure functions â€” easy to test and compose

## Dependencies
- None â€” stdlib only





# `src/failure_reporter.py`

## Purpose
Generates self-diagnosing failure evidence for failed Playwright test steps. Captures diagnostic context (page state, available elements, suggested alternatives) without auto-recovering â€” tests still fail, but with actionable debug info.

## Metadata
- **Lines:** 468
- **Imports:** logging, typing.Any, playwright.sync_api.Page, src.locator_scorer.LocatorScorer

## Class
| Class | Description |
|-------|-------------|
| `FailureReporter` | Captures runtime diagnostics when a test step fails |

## Methods
| Method | Description |
|--------|-------------|
| `diagnose_failure(page, locator, step_type, error)` | Returns dict with url, title, available_elements, suggested_locators, page_snapshot, error_summary |
| `_categorize_elements(page, step_type, max_elements=20)` | Captures interactive elements via accessibility snapshot or JS fallback |
| `_flatten_accessibility_tree(node, max_count)` | Recursively flattens accessibility tree to flat list |
| `_suggest_locators(page, original_locator, step_type)` | Uses LocatorScorer to score and rank alternative locators |
| `_extract_raw_candidates(page)` | Extracts locator candidates from DOM via JS evaluation |
| `_capture_snapshot(page)` | Lightweight accessibility snapshot as text |
| `generate_failure_note(diagnosis)` | Human-readable failure note grouping elements by role |

## Key Logic
- Two-strategy element capture: accessibility snapshot first, then JS DOM query fallback
- Candidates scored by LocatorScorer with confidence levels (high/medium-high/medium)
- Failure note groups elements by role for readability
- Limited to top 15 suggestions and 20 elements to avoid bloating evidence





# `src/file_utils.py`

## Purpose
File operation helpers for the Playwright test generator. Handles saving generated tests, filename slugification, newline normalization, and file renaming.

## Metadata
- **Lines:** 145
- **Imports:** os, re, datetime, pathlib.Path, src.code_validator.validate_python_syntax

## Functions
| Function | Description |
|----------|-------------|
| `slugify(text)` | Converts text to filesystem-safe filename segment (lowercase, underscore-separated) |
| `save_generated_test(test_code, story_text, base_url, output_dir)` | Saves test code to `test_YYYYMMDD_HHMMSS_<slug>.py` with header comment |
| `normalise_code_newlines(code)` | Restores missing newlines before `import`/`from` keywords in LLM output |
| `rename_test_file(old_path, new_name)` | Renames test file with collision handling via timestamp |

## Key Logic
- Filename format: `test_YYYYMMDD_HHMMSS_<slug>.py`
- Syntax validation via `validate_python_syntax` before saving â€” rejects invalid Python
- Newline fix uses regex lookbehind: inserts `\n` before `import ` or `from ` when preceded by non-whitespace
- Rename handles collisions by appending timestamp
- Enforces `test_` prefix and strips `.py` extension





# `src/form_detector.py`

## High-Level Purpose

`form_detector.py` provides lightweight utilities for recognizing form-related elements and useful commerce actions from scraped page element metadata. It does not interact with Playwright or the browser directly. Instead, it consumes dictionaries produced elsewhere by a scraper and converts or ranks that metadata using deterministic heuristics.

The module focuses on three related tasks:

- Defining reusable selector priority lists for product, add-to-cart, and continue-shopping actions.
- Normalizing discovered form fields into a typed `FormField` dataclass.
- Offering stateless helper methods for input classification, submit-button detection, form grouping, and selector discovery.

## Module-Level Constants

### `PRODUCT_SELECTORS: list[str]`

Priority list of CSS-style selectors that may identify product links or product containers. The entries cover product-detail URL patterns, common product item classes, title links, and `data-product-id` attributes.

### `ADD_TO_CART_SELECTORS: list[str]`

Priority list of selectors that may identify add-to-cart or submit controls. The list mixes Playwright text selectors, button/input submit selectors, CSS classes, data attributes, and add-to-cart URL patterns.

This list is actively used by `FormDetector.identify_submit_button()`.

### `CONTINUE_SHOPPING_SELECTORS: list[str]`

Priority list of selectors that may identify continue-shopping or modal-close actions. It includes text selectors, modal-related classes, data-action attributes, and generic close-button classes.

This constant is defined for reuse but is not referenced by the functions in this module.

## Data Structures

### `@dataclass class FormField`

Represents a normalized form field discovered from scraped element metadata.

Signature:

```python
FormField(
    tag: str,
    field_type: str,
    selector: str,
    name: str,
    placeholder: str,
)
```

Fields:

- `tag: str` - Lowercase HTML tag name, expected to be `input`, `select`, or `textarea`.
- `field_type: str` - Canonical field category returned by `FormDetector.classify_input()`.
- `selector: str` - Primary selector for locating the field.
- `name: str` - Element `name` attribute, or an empty string if unavailable.
- `placeholder: str` - Element placeholder text, or an empty string if unavailable.

Return behavior:

- The dataclass generates the standard initializer, representation, comparison, and field storage methods.
- All fields are required and have no defaults.

## Classes

### `class FormDetector`

Stateless namespace for form and selector detection helpers. All methods are `@staticmethod`, so callers do not need to instantiate the class.

Expected input shape:

- Methods consume `list[dict[str, Any]]` or `dict[str, Any]` records.
- Common element keys include `selector`, `css_selectors`, `text`, `name`, `tag_name`, `input_type`, `placeholder`, `has_id`, and `has_name`.
- Missing optional values are generally handled with defaults, although values are expected to be string-like where string methods are called.

## Function and Method Signatures

### `FormDetector.classify_input(raw_type: str, element: dict[str, Any]) -> str`

Maps an HTML input `type` attribute to a canonical field category.

Parameters:

- `raw_type: str` - Raw input type value, such as `"email"`, `"password"`, or `"checkbox"`.
- `element: dict[str, Any]` - Scraped element metadata. Present for interface consistency and possible future use, but not used by the current implementation.

Returns:

- `str` - Canonical category.

Known mappings:

- `"email"` -> `"email"`
- `"password"` -> `"password"`
- `"tel"` -> `"phone"`
- `"number"` -> `"number"`
- `"date"` -> `"date"`
- `"checkbox"` -> `"checkbox"`
- `"radio"` -> `"radio"`
- `"file"` -> `"file"`
- `"hidden"` -> `"hidden"`
- `"submit"` -> `"submit"`
- `"button"` -> `"button"`
- `"reset"` -> `"reset"`
- Any unknown type -> `"text"`

Architectural notes:

- Uses a local dictionary lookup for deterministic normalization.
- Lowercases `raw_type` before lookup.
- Assumes `raw_type` behaves like a string.

### `FormDetector.identify_submit_button(elements: list[dict[str, Any]]) -> str | None`

Finds the best submit-like button selector from scraped element metadata.

Parameters:

- `elements: list[dict[str, Any]]` - Scraped element records.

Returns:

- `str | None` - The chosen element selector, or `None` if no submit-like candidate is found.

Selection behavior:

1. Iterates through `ADD_TO_CART_SELECTORS` in priority order.
2. For each selector, scans all elements.
3. Returns an element's `selector` when either:
   - `el["selector"]` exactly matches the prioritized selector.
   - The prioritized selector appears in `el["css_selectors"]`.
4. If no priority selector matches, falls back to text matching.
5. The fallback returns the first selector whose lowercase text contains one of:
   - `"submit"`
   - `"add"`
   - `"buy"`
   - `"checkout"`
   - `"proceed"`

Architectural notes:

- Encodes a two-stage heuristic: selector registry first, semantic text fallback second.
- Selector order in `ADD_TO_CART_SELECTORS` controls precedence.
- Depends on scraper records containing `selector`, optionally `css_selectors`, and optionally `text`.

### `FormDetector.detect_forms(elements: list[dict[str, Any]]) -> list[list[FormField]]`

Groups scraped field-like elements into simple form structures.

Parameters:

- `elements: list[dict[str, Any]]` - Scraped element records.

Returns:

- `list[list[FormField]]` - A list of detected forms, where each form is represented as a list of `FormField` values.
- Returns `[]` when no field-like elements are found.
- Returns `[form_fields]` when at least one field is found.

Detection behavior:

1. Iterates through every element.
2. Reads `tag_name`, lowercases it, and keeps only:
   - `input`
   - `select`
   - `textarea`
3. Reads `input_type`, defaulting to `"text"`.
4. Calls `FormDetector.classify_input()` to normalize the field type.
5. Builds a `FormField` with normalized and defaulted metadata:
   - `selector` defaults to `""`
   - `name` defaults to `""`
   - `placeholder` defaults to `""`
6. Groups all discovered fields into one form.

Architectural notes:

- Uses a deliberately simple grouping heuristic.
- Does not infer separate form boundaries.
- Treats consecutive or discovered field-like elements as a single form structure.

### `FormDetector.discover_selector(elements: list[dict[str, Any]], description: str) -> str | None`

Finds the best selector for a described element using a score-based heuristic.

Parameters:

- `elements: list[dict[str, Any]]` - Scraped element records.
- `description: str` - Human-readable description of the desired element.

Returns:

- `str | None` - Best matching selector if a positive-scoring candidate exists, otherwise `None`.

Scoring behavior:

- Starts each element at score `0`.
- Adds `10` if the lowercase description appears in the element text.
- Adds `8` if the lowercase description appears in the element name.
- Adds `5` if `has_id` is truthy.
- Adds `3` if `has_name` is truthy.
- Tracks the highest-scoring element and returns its selector only when the best score is greater than `0`.

Tie behavior:

- Ties keep the earlier best candidate because the method only replaces the winner when `score > best_score`.

Architectural notes:

- Combines semantic matching with selector-stability hints.
- Prefers elements with IDs or names when textual evidence is similar.
- Assumes text and name metadata are string-like after defaulting missing values to empty strings.

## Key Architectural Patterns

### Stateless Helper Class

`FormDetector` is used as a static utility namespace. There is no instance state, dependency injection, cache, or configuration object.

### Dictionary-Based Scraper Contract

The module expects upstream scraping code to provide element dictionaries with predictable keys. It keeps this contract flexible by using `dict[str, Any]`, while selectively defaulting missing fields.

### Heuristic-First Detection

The implementation favors transparent, deterministic heuristics:

- Ordered selector lists for known commerce controls.
- Keyword fallback for submit-button discovery.
- Tag filtering for form detection.
- Point scoring for free-text selector discovery.

### Normalized Field Model

`FormField` converts loose scraped dictionaries into a small typed structure. This creates a clearer downstream representation without requiring the detector to understand full DOM hierarchy.

### Conservative Form Grouping

`detect_forms()` intentionally avoids complex DOM reconstruction. It gathers all detected fields into a single form group and returns no forms when no field elements are present.

## Important Assumptions and Edge Cases

- `raw_type` in `classify_input()` is expected to be a string. Non-string values would not support `.lower()`.
- `detect_forms()` treats missing `tag_name` as an empty string and skips that element.
- `identify_submit_button()` may return any value stored under `selector`; the type hint expects this to be `str | None`.
- `discover_selector()` can match broad descriptions because it uses substring checks rather than tokenized or semantic matching.
- Empty or overly generic descriptions may produce weak matches because empty strings are substrings of all strings in Python.
- The selector constants are reusable module-level configuration, but only `ADD_TO_CART_SELECTORS` is used by current module logic.





# `src/form_login_utils.py`

## High-Level Purpose

`form_login_utils.py` centralizes best-effort login form detection and filling for stateful Playwright scraping flows. It was extracted from `stateful_scraper.py` so login-specific behavior can live in one small utility module instead of being embedded directly in scraper orchestration code.

The module focuses on common demo-site login shapes:

- Saucedemo-style credential fields using stable IDs or names.
- Generic HTML forms containing a text or email input, a password input, and a submit control.
- Detection-only behavior when no credential profile is available.

All operations use synchronous Playwright-style calls through a dynamically typed `page` object.

## Imports and Dependencies

```python
from typing import Any

from src.journey_models import CredentialProfile
```

- `Any`: used for the `page` parameter because the utility expects a Playwright-like page object without importing or binding to a concrete Playwright type.
- `CredentialProfile`: supplies `username` and `password` values when credentials are available.

## Public API

### `attempt_login(page: Any, credential_profile: CredentialProfile | None) -> None`

Detects and optionally fills a login form on the current page.

Parameters:

- `page: Any` - A Playwright-compatible page object. The function expects it to support `locator(...)` and `wait_for_load_state(...)`.
- `credential_profile: CredentialProfile | None` - Optional credentials. When provided, the profile's `username` and `password` are used for login attempts. When omitted, the module only detects login-like forms and does not fill or submit anything.

Returns:

- `None`

Behavior:

- If `credential_profile` is `None`, delegates to `_detect_login_forms_only(page)` and exits.
- If credentials are provided, reads `credential_profile.username` and `credential_profile.password`.
- Attempts saucedemo-style login selectors first.
- Attempts generic form-based login second.
- Does not report whether login succeeded; the function is intentionally fire-and-forget.

Architectural role:

- This is the module's only public entry point.
- It acts as a thin strategy coordinator over private helper functions.

## Private Helpers

### `_try_saucedemo_login(page: Any, username: str, password: str) -> None`

Attempts login using direct page-level selectors that match common demo and login-page conventions.

Parameters:

- `page: Any` - A Playwright-compatible page object.
- `username: str` - Username or email value to fill.
- `password: str` - Password value to fill.

Returns:

- `None`

Selector strategy:

- User field candidates:
  - `#user-name`
  - `#username`
  - `#email`
  - `[name='username']`
  - `[name='email']`
- Password field candidates:
  - `#password`
  - `[name='password']`
- Submit button candidates:
  - `#login-button`
  - `#login-btn`
  - `button[type='submit']`
  - Buttons containing login, log in, or sign in text.

Behavior:

- Locates the first matching user field, password field, and login button.
- Checks that user and password fields are visible within a 2000 ms timeout.
- Fills both credential fields.
- If the login button is visible, clicks it with a 5000 ms timeout.
- Waits for `networkidle` with a 10000 ms timeout after clicking.
- Suppresses all exceptions.

Architectural role:

- Implements the first, most specific login strategy.
- Optimized for sites with stable IDs and conventional names.

### `_try_generic_form_login(page: Any, username: str, password: str) -> None`

Attempts login by searching inside the first visible HTML form.

Parameters:

- `page: Any` - A Playwright-compatible page object.
- `username: str` - Username or email value to fill.
- `password: str` - Password value to fill.

Returns:

- `None`

Selector strategy:

- Uses the first `form` element on the page.
- Within that form, searches for:
  - `input[type="text"]`
  - `input[type="email"]`
  - `input[type="password"]`
  - `button[type="submit"]`
  - `input[type="submit"]`

Behavior:

- Checks the first form is visible within a 1000 ms timeout.
- Checks text/email and password inputs are visible within 1000 ms.
- Fills username and password values.
- If a submit control is visible, clicks it with a 5000 ms timeout.
- Waits for `networkidle` with a 10000 ms timeout after clicking.
- Suppresses all exceptions.

Architectural role:

- Provides a broader fallback after the saucedemo-specific selector strategy.
- Encapsulates generic form traversal so the public API does not need to know about DOM structure details.

### `_detect_login_forms_only(page: Any) -> None`

Detects login-like forms without filling or submitting credentials.

Parameters:

- `page: Any` - A Playwright-compatible page object.

Returns:

- `None`

Behavior:

- First checks for saucedemo-style user and password fields.
- If both fields are visible, returns immediately.
- Otherwise checks the first visible form for text/email and password inputs.
- If both generic inputs are visible, returns immediately.
- Does not fill fields, click buttons, or expose the detection result.
- Suppresses all exceptions.

Architectural role:

- Supports credential-less scraping flows where login forms may be present but should not be modified.
- Mirrors the two detection strategies used by credentialed login attempts.

## Key Architectural Patterns

### Strategy Pipeline

`attempt_login()` coordinates a simple ordered strategy pipeline:

1. Credential-less path: detect only.
2. Credentialed path: try specific saucedemo-style selectors.
3. Credentialed path: try generic form selectors.

The ordering favors precise, stable selectors before broader DOM heuristics.

### Best-Effort Failure Handling

Each private helper wraps its logic in `try` / `except Exception` and silently ignores failures. This makes login automation non-blocking for scraper flows: missing forms, locator failures, visibility timeouts, navigation timing issues, and selector mismatches do not stop the caller.

Tradeoff:

- Good for resilient scraping and demo-site automation.
- Weak for observability because callers cannot distinguish "no form found", "form found but login failed", and "exception swallowed".

### Playwright Locator-First Style

The module relies on Playwright locator composition:

- `page.locator(...).first`
- `form.locator(...).first`
- `is_visible(timeout=...)`
- `fill(...)`
- `click(timeout=...)`
- `page.wait_for_load_state("networkidle", timeout=...)`

It assumes synchronous Playwright APIs and does not use async Playwright calls.

### Credential Boundary

Credentials enter only through `CredentialProfile`. The module extracts `username` and `password` once in `attempt_login()` and passes plain strings into helper strategies.

### Detection Without State Reporting

The detection-only helper returns `None` regardless of whether a form is found. Its current value is side-effect control rather than result reporting: it proves the page can be probed safely without filling data, but it does not expose a boolean detection outcome.

## Side Effects

When credentials are provided, the module may:

- Fill username/email inputs.
- Fill password inputs.
- Click a login or submit control.
- Wait for page/network activity to settle.

When credentials are not provided, the module should only inspect element visibility.

## Error Handling

All private helper functions suppress broad `Exception`. The public function does not catch exceptions directly around credential extraction, but downstream Playwright interactions are swallowed inside helpers.

Potential uncaught errors:

- `credential_profile` object lacks `username` or `password` attributes despite being non-`None`.

## Type Surface

The module uses full function annotations:

```python
def attempt_login(page: Any, credential_profile: CredentialProfile | None) -> None: ...
def _try_saucedemo_login(page: Any, username: str, password: str) -> None: ...
def _try_generic_form_login(page: Any, username: str, password: str) -> None: ...
def _detect_login_forms_only(page: Any) -> None: ...
```

No classes are defined in this module.





# `src/gantt_utils.py`

## Purpose
Builds Gantt-style timelines from EvidenceTracker sidecars (.evidence.json). Visualizes test execution timeline using Plotly horizontal bar charts.

## Metadata
- **Lines:** 194
- **Imports:** json, dataclasses.dataclass, pathlib.Path, typing.Any|Literal, pandas, plotly.express, plotly.graph_objects

## Classes/Dataclasses
| Class | Description |
|-------|-------------|
| `GanttEntry` | Frozen dataclass: test_name, condition_ref, story_ref, status, duration_s |

## Type Aliases
| Type | Values |
|------|--------|
| `GroupingMode` | Literal["condition_type", "sprint", "source"] |

## Functions
| Function | Description |
|----------|-------------|
| `safe_read_sidecar(path)` | Reads JSON sidecar file â€” returns None if missing or invalid |
| `load_gantt_entries(evidence_dir)` | Loads all *.evidence.json from directory into GanttEntry list |
| `build_gantt_summary_sentences(entries, total_expected)` | Returns (fastest, slowest, coverage) summary tuple |
| `group_gantt_entries(entries, mode, condition_meta)` | Groups entries by condition_type/sprint/source with stable sorting |
| `build_gantt_chart(entries, grouping_mode, condition_meta)` | Builds Plotly horizontal bar chart (go.Figure) from entries |

## Key Logic
- Reads `.evidence.json` sidecars for test metadata (name, condition_ref, story_ref, status, duration_s)
- Summary sentences: fastest/slowest by duration_s, coverage as executed/expected percentage
- Grouping uses optional `condition_meta` dict keyed by condition_ref with type/sprint/source fields
- Sort within groups: status ASC, duration_s DESC, condition_ref ASC
- Chart uses `px.bar` with `base="Start"` for Gantt-style floating bars (avoids px.timeline date-casting issues)
- Color mapping: passed=green, failed=red, skipped=yellow, pending=gray, unknown=cyan
- Dynamic chart height: min(800, 300 + len(entries)*25)





# `src/heatmap_utils.py`

## Purpose
Coverage confidence heatmap aggregation from EvidenceTracker sidecars. Includes Tier 3 per-URL suite heatmap rendering (moved from `src/evidence_report.py`). Produces Plotly treemaps and interactive HTML heatmaps with SVG overlays.

## Metadata
- **Lines:** 719
- **Imports:** base64, json, dataclasses.dataclass, pathlib.Path, typing.Any|Literal, pandas, plotly.express, plotly.graph_objects, src.report_builder.escape_html

## Classes/Dataclasses
| Class | Description |
|-------|-------------|
| `StoryConfidence` | Frozen dataclass: story_ref, level, color, total/passed/failed/skipped_conditions |

## Type Aliases
| Type | Values |
|------|--------|
| `ConfidenceLevel` | Literal["tester_confirmed", "ai_covered_unreviewed", "partial_pending", "gap_open_question", "not_in_scope"] |

## Constants
| Constant | Description |
|----------|-------------|
| `CONFIDENCE_COLORS` | Maps ConfidenceLevel to hex colors (greenâ†’light greenâ†’yellowâ†’redâ†’secondary bg) |
| `_STATUS_COLORS` | passed=green, partial_pass=yellow, failed=red, skipped=gray |
| `_EVIDENCE_STEP_COLORS` | navigate=pink, fill=green, click=blue, assertion=brown |

## Functions
| Function | Description |
|----------|-------------|
| `_normalise_url(url)` | Normalizes URLs: lowercases scheme/netloc, strips trailing slashes |
| `_safe_read_json(path)` | Reads JSON file â€” returns None if missing or invalid |
| `_safe_embed_image_data_uri(image_path)` | Reads image file â†’ base64 data URI with correct MIME type |
| `_extract_confirmed_ids(test_plan_state, story_ref)` | Extracts confirmed condition IDs from test plan state |
| `build_story_confidence(evidence_dir, test_plan_state)` | Aggregates .evidence.json into StoryConfidence list per story |
| `build_confidence_heatmap(stories)` | Builds Plotly treemap for story confidence levels |
| `_extract_step_points_by_url(sidecar)` | Extracts (points_by_url, bg_screenshot_by_url) from one sidecar |
| `generate_suite_heatmap(evidence_dir, page_url)` | Renders per-URL heatmap as HTML with SVG circle overlays |

## Key Logic

### Story Confidence Aggregation
- Groups sidecars by `story_ref`, counts passed/failed/skipped per condition
- Confidence ladder: failed>0 â†’ gap_open_question; no sidecars â†’ partial_pending; all confirmed â†’ tester_confirmed; else â†’ ai_covered_unreviewed
- `confirmed_ids` from test_plan_state can be global set or per-story mapping

### Confidence Heatmap (Plotly)
- Uses `px.treemap` with path=["Confidence", "Story"] for hierarchical grouping
- Equal sizing per story (Value=1), colored by confidence level
- Hover shows Passed/Failed/Skipped/Total

### Tier 3 Per-URL Suite Heatmap
- Aggregates all evidence points across sidecars for one normalized URL
- Tracks current URL as navigate steps occur, groups screenshots into URL segments
- Background screenshot selection: assertion screenshots (priority 3) > meaningful interaction (2) > navigate (0)
- Deprioritizes consent/overlay/cookie screenshots
- Aggregates elements within 2% tolerance at same (x, y) position
- Status per point: passed, failed, partial_pass, skipped from step result
- Returns HTML with inline SVG overlay showing colored circles on screenshot
- Circle size proportional to run_count, colored by dominant status
- Filter buttons for all/passed/partial/failed views
- Element details table with hover highlighting
- Uses ResizeObserver for responsive SVG resizing





# `src/hover_click_utils.py`

## Purpose
Hover-reveal click strategies for hidden elements. Handles elements hidden via CSS (display:none, visibility:hidden, opacity:0) that only become visible on parent mouseenter events â€” common in e-commerce product grids and navigation menus.

## Metadata
- **Lines:** 208
- **Imports:** typing.Any

## Functions
| Function | Description |
|----------|-------------|
| `try_hover_and_click(page, loc, locator)` | Public entry â€” attempts 5 progressive hover strategies, returns True on first success |
| `_attempt_hover_then_click(loc)` | Strategy 1: hover element directly, then click |
| `_attempt_mouseenter_then_click(loc)` | Strategy 2: dispatch mouseenter via JS, then click |
| `_attempt_ancestors_mouseenter(page, locator, loc)` | Strategy 3: dispatch mouseenter on all ancestors up to BODY, then click |
| `_attempt_parent_category_hover(page, locator, loc)` | Strategy 4: find visible parent category triggers, hover them, then click |
| `_attempt_force_show_and_click(page, locator)` | Strategy 5: JS force-show all hidden ancestors + remove hidden CSS classes, then el.click() |
| `_try_click(loc)` | Helper: attempts loc.click(timeout=5000), returns True/False |

## Strategy Chain (executed in order)
1. **Direct hover** â€” `loc.hover(timeout=2000)` then click
2. **JS mouseenter** â€” dispatch `MouseEvent('mouseenter', bubbles=true)` on target, then click
3. **Ancestor mouseenter** â€” walk `parentElement` chain to BODY, dispatch mouseenter on each, then click
4. **Parent category hover** â€” finds visible sibling A/LI elements, dispatches mouseenter, checks if target becomes visible
5. **Force-show** â€” walks up ancestors, forces `display:block`, `visibility:visible`, `opacity:1` with `!important`, removes hidden/collapse/invisible CSS classes, calls `el.click()` directly

## Key Patterns
- All strategies are non-blocking â€” exceptions caught silently, returns False on failure
- Strategy 4 targets automationexercise.com-style sidebar menus (Womenâ†’Dress pattern)
- Strategy 5 is last resort: modifies DOM styles with `!important` override
- `_try_click` uses 5s timeout for the final click attempt





# `src/intent_matcher.py`

## High-Level Purpose

`intent_matcher.py` provides intent-based filtering for DOM elements during placeholder resolution. It decides whether a scraped element is a plausible match for an action and natural-language description such as clicking a cart button, filling an email field, asserting a popup, or rejecting newsletter elements for unrelated checkout flows.

The module uses a strategy-registry architecture. Each intent category is implemented as an `IntentStrategy`, and `IntentMatcher` dispatches through the registered strategies until one returns a definitive accept or reject decision. If no strategy has an opinion, matching defaults to accepting the element for backwards-compatible behavior.

## Dependencies

- `ABC`, `abstractmethod` from `abc` for the strategy base class.
- `Any` from `typing` for loosely shaped scraped element dictionaries.
- `SemanticMatcher` from `src.semantic_matcher` for token extraction and semantic similarity checks.

## Element Data Contract

Strategies expect `element` to be a `dict[str, Any]` containing scraped DOM metadata. Commonly inspected keys include:

- `selector`
- `text`
- `href`
- `classes`
- `icon_classes`
- `visual_description`
- `parent_text`
- `aria_icon_label`
- `value`
- `data_test`
- `name`
- `placeholder`
- `aria_label`
- `accessible_name`
- `role`
- `id`
- `tag`

Missing keys are handled defensively with `element.get(..., "")`.

## Module Helpers

### `_all_element_text(element: dict[str, Any]) -> str`

Concatenates searchable text-bearing fields from a scraped element into one lowercase string. This helper creates a broad haystack for intent strategies that match against visible text, selectors, labels, accessibility names, parent text, IDs, and test attributes.

Parameters:

- `element: dict[str, Any]` - Scraped DOM element metadata.

Returns:

- `str` - Lowercase concatenated text from the recognized element fields.

### `_is_fillable(element: dict[str, Any]) -> bool`

Determines whether an element supports text entry or selection. Hidden fields and CSRF/token/authenticity fields are rejected. Inputs, textareas, selects, textbox-like roles, and elements with a `name` or `placeholder` are accepted.

Parameters:

- `element: dict[str, Any]` - Scraped DOM element metadata.

Returns:

- `bool` - `True` if the element is treated as fillable, otherwise `False`.

### `_description_words(description: str) -> set[str]`

Tokenizes a natural-language description through `SemanticMatcher.get_words`.

Parameters:

- `description: str` - Natural-language action description.

Returns:

- `set[str]` - Significant description words as produced by `SemanticMatcher`.

## Base Class

### `class IntentStrategy(ABC)`

Abstract base class for all intent-matching strategies. Strategies use tri-state results:

- `True` - Accept the element.
- `False` - Reject the element.
- `None` - Strategy is indifferent and dispatch should continue.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Abstract method implemented by every concrete strategy.

Parameters:

- `action: str` - Placeholder action type such as `CLICK`, `FILL`, or `ASSERT`.
- `description: str` - Natural-language placeholder description.
- `element: dict[str, Any]` - Scraped DOM element metadata.

Returns:

- `bool | None` - Accept, reject, or no opinion.

## Strategy Implementations

### `class ExactIdStrategy(IntentStrategy)`

Matches elements when description tokens appear in element identifiers.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Builds an ID haystack from `id` and `data_test`, then checks for description words longer than three characters.

Returns:

- `True` if any significant description word appears in the identifier haystack.
- `None` otherwise.

### `class SemanticFillStrategy(IntentStrategy)`

Handles semantic matching for `FILL` actions against fillable form elements.

Class attributes:

- `FORM_FIELD_MAP: dict[str, set[str]]` - Maps common field descriptions such as `first name`, `zip code`, `email address`, and `phone number` to likely element IDs, names, or test identifiers.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies when `action == "FILL"` and `_is_fillable(element)` is true. It uses semantic similarity against element IDs, data-test attributes, names, placeholders, aria labels, and accessible names. It also includes explicit handling for username, password, and mapped form-field terms.

Returns:

- `True` for high-confidence semantic or explicit form-field matches.
- `None` when the action is not fill-related, the element is not fillable, or no fill match is found.

### `class LoginIntentStrategy(IntentStrategy)`

Matches login, logout, sign-in, sign-out, and submit-oriented intents.

Class attributes:

- `_LOGIN_TERMS`
- `_LOGIN_DESCRIPTION`
- `_LOGIN_BUTTON_DESCRIPTION`
- `_LOGIN_BUTTON_TEXT`

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Checks general login/logout descriptions against broad element text. For `CLICK` actions, it also recognizes login button descriptions and known button terms.

Returns:

- `True` for matching login/logout/sign-in elements.
- `None` otherwise. General login descriptions intentionally do not reject when no login element signal is found.

### `class SubscribeGuardStrategy(IntentStrategy)`

Prevents newsletter or subscribe elements from matching unrelated intents.

#### `_is_subscribe_element(self, element: dict[str, Any]) -> bool`

Detects subscribe/newsletter elements using broad element text and specific IDs.

Parameters:

- `element: dict[str, Any]` - Scraped DOM element metadata.

Returns:

- `bool` - `True` if the element appears to be a subscribe/newsletter element.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Rejects subscribe elements for cart, checkout, payment, dismissive, popup, modal, confirmation, and textless click intents.

Returns:

- `False` for subscribe elements that should not satisfy the requested intent.
- `None` when the element is not a subscribe element or no guard applies.

### `class PageStateAssertStrategy(IntentStrategy)`

Rejects element-level matches for page-state assertions.

Class attributes:

- `_PAGE_STATE_TERMS`

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies to `ASSERT` actions. Descriptions such as `home page`, `checkout page`, `cart page`, or `confirmation page` are treated as page-level assertions rather than element-level matches.

Returns:

- `False` for page-state assertion descriptions.
- `None` otherwise.

### `class ProductCardStrategy(IntentStrategy)`

Matches product card click intents.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies to `CLICK` actions whose description includes `product card`. It checks broad element text for card-related signals.

Returns:

- `bool` for product-card click descriptions, based on card text signals.
- `None` for non-click or non-product-card descriptions.

### `class CartIntentStrategy(IntentStrategy)`

Handles cart-related click matching.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies to `CLICK` actions. It distinguishes cart navigation, add-to-cart buttons, text-based add-to-cart matches, and cart links/icons. It explicitly rejects cart navigation links for add-to-cart intents.

Returns:

- `True` for recognized cart action matches.
- `False` for add-to-cart descriptions matched against cart navigation or elements without add-to-cart signals.
- `None` when no cart-specific rule applies.

### `class CheckoutIntentStrategy(IntentStrategy)`

Handles checkout navigation and order-completion click intents.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies to `CLICK` actions. It matches finish/complete/place/confirm order actions, checkout navigation descriptions, and general checkout clicks. It rejects payment elements when the description asks for checkout rather than payment.

Returns:

- `True` for recognized checkout or order-completion matches.
- `False` for checkout descriptions that point at payment elements or fail required signals.
- `None` when no checkout-specific rule applies.

### `class CartAssertStrategy(IntentStrategy)`

Matches cart, checkout, and item assertions against content elements.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies to `ASSERT` actions containing `cart`, `item`, or `checkout`. It looks for content-oriented signals such as cart descriptions, quantities, prices, summaries, products, orders, and payments. Search-only elements and cart navigation links are rejected.

Returns:

- `True` when the element appears to be relevant cart/checkout/item content.
- `False` for search-only non-cart elements or navigation-only cart links.
- `None` when the assertion is outside this strategy's scope.

### `class PopupAssertStrategy(IntentStrategy)`

Matches assertions for confirmation popups, modals, alerts, and notifications.

Class attributes:

- `_POPUP_KEYWORDS`
- `_POPUP_ELEMENT_SIGNALS`

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies to `ASSERT` actions with popup-related keywords. It accepts dialog/alert/status roles, modal-like classes or selectors, and content elements inside modal-like contexts with confirmation or success text.

Returns:

- `True` for popup/modal/alert-like elements.
- `None` when the description is not popup-related or no popup signal is found.

### `class GenericAssertStrategy(IntentStrategy)`

Fallback matching for high-level content-display assertions.

Class attributes:

- `_CONTENT_DISPLAY_TERMS`
- `_CONTENT_ROLES`
- `_CONTENT_TAGS`

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies to `ASSERT` actions whose description includes content-display terms such as `listed`, `displayed`, `appears`, `visible`, or `summary`. It accepts elements with content roles or tags when visible text is present.

Returns:

- `True` for text-bearing content display elements.
- `None` otherwise.

### `class SuccessAssertStrategy(IntentStrategy)`

Matches thank-you, order-confirmed, order-complete, and success message assertions.

Class attributes:

- `_SUCCESS_KEYWORDS`
- `_MESSAGE_KEYWORDS`
- `_SUCCESS_ELEMENT_TEXT`

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies to `ASSERT` actions. It requires both a success keyword and a message-like keyword in the description before checking element text for success or confirmation content.

Returns:

- `True` for matching success/confirmation message elements.
- `False` when both description gates pass but element text lacks required success signals.
- `None` when the assertion does not meet the success-message gates.

### `class ContinueShoppingStrategy(IntentStrategy)`

Matches continue shopping and continue checkout click intents.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies to `CLICK` actions. It recognizes `continue shopping`, `continue button`, and `continue checkout` descriptions.

Returns:

- `True` when broad element text contains appropriate continue/shopping terms.
- `False` when a continue-related description is in scope but element text lacks required terms.
- `None` for non-click or unrelated descriptions.

### `class ProductNameStrategy(IntentStrategy)`

Fallback matching based on product-name word overlap.

Class attributes:

- `_PRODUCT_INDICATORS`

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Applies to `CLICK` and `ASSERT` actions. It removes generic action words from the description, requires at least two remaining product words, and matches those words against element text, data-test attributes, IDs, names, and aria labels.

Returns:

- `True` when at least half the inferred product words are found in element content.
- `None` otherwise.

## Dispatcher

### `class IntentMatcher`

Thin public dispatcher over registered `IntentStrategy` instances. It centralizes the default strategy order and keeps backwards-compatible static helpers.

Class attributes:

- `FORM_FIELD_MAP: dict[str, set[str]]` - Alias to `SemanticFillStrategy.FORM_FIELD_MAP` for compatibility with external callers.
- `_all_element_text` - Static alias for module helper `_all_element_text`.
- `_is_fillable` - Static alias for module helper `_is_fillable`.

#### `__init__(self, strategies: list[IntentStrategy] | None = None) -> None`

Initializes the matcher with either a caller-supplied strategy list or the default strategy registry.

Parameters:

- `strategies: list[IntentStrategy] | None = None` - Optional explicit registry.

Returns:

- `None`

Default strategy order:

1. `ExactIdStrategy`
2. `SemanticFillStrategy`
3. `LoginIntentStrategy`
4. `SubscribeGuardStrategy`
5. `PageStateAssertStrategy`
6. `ProductCardStrategy`
7. `CartIntentStrategy`
8. `CheckoutIntentStrategy`
9. `CartAssertStrategy`
10. `PopupAssertStrategy`
11. `GenericAssertStrategy`
12. `SuccessAssertStrategy`
13. `ContinueShoppingStrategy`
14. `ProductNameStrategy`

#### `matches(action: str, description: str, element: dict[str, Any]) -> bool`

Backwards-compatible static API. It creates a default `IntentMatcher` instance and delegates to `match`.

Parameters:

- `action: str` - Placeholder action type.
- `description: str` - Natural-language placeholder description.
- `element: dict[str, Any]` - Scraped DOM element metadata.

Returns:

- `bool` - Final accept/reject result.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool`

Iterates through the configured strategies until one returns `True` or `False`. If all strategies return `None`, it accepts by default to preserve legacy behavior.

Parameters:

- `action: str` - Placeholder action type.
- `description: str` - Natural-language placeholder description.
- `element: dict[str, Any]` - Scraped DOM element metadata.

Returns:

- `bool` - Final accept/reject result.

## Key Architectural Patterns

### Strategy Registry

Each intent family is isolated in a small `IntentStrategy` implementation. `IntentMatcher` owns the strategy ordering and dispatches without embedding category-specific logic directly in the dispatcher.

### Tri-State Matching

Strategies return `True`, `False`, or `None`. This allows high-confidence strategies and guard strategies to make definitive decisions while unrelated strategies can stay indifferent.

### Guard Strategies

Some strategies are intentionally protective rather than affirmative. Examples include rejecting subscribe/newsletter elements for cart or checkout tasks and rejecting page-level assertions from element-level matching.

### Semantic Plus Heuristic Matching

The module combines semantic similarity, exact identifier matching, explicit keyword maps, role/tag checks, and broad text haystacks. This gives the resolver multiple ways to recognize intent without relying on a single matching technique.

### Backwards Compatibility

The dispatcher preserves older call shapes through `IntentMatcher.matches(...)`, `IntentMatcher.FORM_FIELD_MAP`, and static aliases for `_all_element_text` and `_is_fillable`. The final fallback also accepts elements when no strategy has an opinion, matching legacy behavior.

### Ordered Specificity

The default strategy list starts with exact and fill-specific matches, then applies domain-specific login, subscribe, cart, checkout, assertion, popup, success, continue, and product-name fallbacks. Because the first definitive result wins, ordering is part of the matching contract.





# journey_auth_detector.py

## Purpose
Authentication detection helpers for journey scraping. Extracted from `journey_scraper.py` to keep the scraper focused on its core responsibility (following user journeys). These functions detect unexpected auth redirects, SSO gateways, MFA prompts, and CAPTCHAs so the pipeline can surface meaningful errors instead of silently failing.

## Location
`src/journey_auth_detector.py` (69 lines)

## Dependencies
- **Standard library only**: `re`, `urllib.parse`

## Public API

### `detect_auth_redirect(page_url: str, intended_url: str, page_title: str, h1_text: str) -> bool`
Returns `True` if the current page appears to be an unexpected auth redirect. Checks:
- URL/domain mismatch after navigation
- Page title or H1 contains auth keywords (login, sign in, authenticate, session expired, etc.)

### `detect_sso(base_domain: str, current_url: str) -> bool`
Returns `True` if navigation left the base domain (likely SSO redirect).

### `detect_mfa(page_html: str) -> bool`
Returns `True` if the page contains MFA-related inputs. Detects:
- `type="tel"` inputs (phone code entry)
- Labels containing MFA keywords (verification code, authenticator, one-time, 2fa, two-factor)

### `detect_captcha(page_html: str) -> bool`
Returns `True` if the page contains CAPTCHA iframes or elements. Detects:
- Known CAPTCHA domains: `google.recaptcha.net`, `hcaptcha.com`, `captcha.`
- CAPTCHA-related element text (captcha, recaptcha, hcaptcha)

## Detection Patterns
| Pattern | Purpose |
|---------|---------|
| `_AUTH_REDIRECT_KEYWORDS` | Login/sign-in/authenticate/session expired keywords |
| `_MFA_LABEL_PATTERN` | MFA verification keywords |
| `_CAPTCHA_DOMAINS` | Known CAPTCHA service domains |
| `_CAPTCHA_ELEMENT_PATTERN` | CAPTCHA element text patterns |

## Design Notes
- All functions are pure (no side effects) â€” easy to test in isolation
- Regex patterns are pre-compiled at module level for performance
- Extracted from `journey_scraper.py` during refactoring to separate auth detection concerns from DOM scraping

## Related Files
- `src/journey_scraper.py` â€” consumer of these detection helpers
- `src/state_tracker.py` â€” DOM state tracking used during journey scraping





# `src/journey_executor.py`

## High-Level Purpose

`journey_executor.py` executes user-defined browser journeys through Playwright's synchronous Python API, with explicit detection for authentication-related blockers such as login redirects, SSO/OAuth redirects, CAPTCHA, and MFA prompts.

The module exposes `execute_journey()` as the public entry point. That public API serializes the journey into JSON, launches this same file as a subprocess, and parses the child process output back into a `JourneyResult`. The actual browser automation happens inside `_execute_journey_sync()`, which runs in the subprocess and owns the Playwright browser lifecycle.

This subprocess pattern isolates Playwright execution from the caller and is documented in the module as a Windows `ProactorEventLoop` avoidance strategy.

## External Dependencies

- `json`, `sys`, `Path`, `asdict`, `Any`, and `urlparse` from the standard library.
- `sync_playwright` from `playwright.sync_api` for synchronous Chromium automation.
- `AccessibilityEnricher` for enriching scraped elements with accessibility tree data.
- Auth detection helpers: `detect_auth_redirect`, `detect_captcha`, `detect_mfa`, and `detect_sso`.
- Journey model types: `CredentialProfile`, `JourneyResult`, `JourneyStep`, and `substitute_templates`.
- `PageScraper` for extracting elements from captured HTML.
- `src.browser_utils.dismiss_consent_overlays`, imported lazily inside `_dismiss_consent_overlays()`.

## Public API

### `execute_journey(...) -> JourneyResult`

```python
def execute_journey(
    journey_steps: list[JourneyStep],
    credential_profile: CredentialProfile | None = None,
    timeout_ms: int = 30_000,
    starting_url: str | None = None,
) -> JourneyResult:
```

Runs a journey through the subprocess-backed execution path.

Parameters:

- `journey_steps`: ordered list of `JourneyStep` objects to execute.
- `credential_profile`: optional credentials used for template substitution during `fill` steps.
- `timeout_ms`: default timeout for Playwright operations and subprocess scaling.
- `starting_url`: optional initial URL loaded before executing the journey steps.

Returns:

- `JourneyResult`: parsed result from the subprocess, including success state, captured pages, failed steps, error message, and redirected URLs.

Behavior:

- Converts each `JourneyStep` and optional `CredentialProfile` to dictionaries with `asdict()`.
- Builds a JSON payload containing steps, credentials, timeout, and starting URL.
- Resolves the subprocess target to this module's own `journey_executor.py` path.
- Calls `subprocess_run(...)` with the `--execute-journey` flag.
- Delegates result interpretation to `_parse_execute_result(...)`.

## Internal Execution Functions

### `_execute_journey_sync(...) -> JourneyResult`

```python
def _execute_journey_sync(
    journey_steps: list[JourneyStep],
    credential_profile: CredentialProfile | None = None,
    timeout_ms: int = 30_000,
    starting_url: str | None = None,
) -> JourneyResult:
```

Executes all journey steps inside a single Playwright browser session.

Parameters:

- `journey_steps`: ordered `JourneyStep` list to run.
- `credential_profile`: optional credentials for placeholder substitution.
- `timeout_ms`: default page timeout and scraper timeout.
- `starting_url`: optional URL visited before the first step.

Returns:

- `JourneyResult`: aggregate outcome of the journey.

State tracked during execution:

- `captured_pages: dict[str, list[dict[str, Any]]]`: scraped element data keyed by URL.
- `failed_steps: list[str]`: human-readable failures collected per step.
- `redirected_urls: list[str]`: detected login redirect destinations.
- `error_message: str | None`: terminal auth-blocking condition, such as SSO, CAPTCHA, or MFA.
- `base_domain: str`: domain used for SSO redirect detection.

Step handling:

- `goto` / `navigate`: requires `step.url`, navigates with `networkidle`, dismisses consent overlays, updates `base_domain`, detects auth redirects, detects SSO, checks page HTML for CAPTCHA and MFA.
- `click`: clicks by `step.selector` through `_click_with_locator()`, or by `step.text` with Playwright text lookup when no selector is provided.
- `fill`: requires `step.selector`, resolves credential templates in `step.text`, and fills through `_fill_with_locator()`.
- `submit`: tries a small ordered set of common submit button selectors and records a failure if none are found.
- `capture`: extracts elements from current HTML with `PageScraper._extract_elements_from_html(...)`, optionally enriches them with a CDP accessibility snapshot, and stores them under the current URL.
- `wait`: waits for a numeric duration from `step.description` with a default of `1.0` second, then optionally waits for `step.selector`.

Failure handling:

- Per-step exceptions are caught and appended to `failed_steps`.
- Once `error_message` is set by SSO, CAPTCHA, or MFA detection, later steps are skipped and recorded as stopped.
- Browser context and browser are closed in a `finally` block.
- `success` is true only when there is no `error_message` and no failed steps.

### `_parse_execute_result(completed: Any) -> JourneyResult`

```python
def _parse_execute_result(completed: Any) -> JourneyResult:
```

Converts a subprocess completion object into a `JourneyResult`.

Parameters:

- `completed`: expected to behave like `subprocess.CompletedProcess`, with `stderr`, `stdout`, and `returncode` attributes.

Returns:

- `JourneyResult`: parsed successful output, or a failure result for subprocess errors, invalid JSON, or unexpected payload shape.

Behavior:

- Prints subprocess stderr to the parent's stderr when present.
- Returns a failure result if the child process exit code is nonzero.
- Parses `completed.stdout` as JSON.
- Requires the parsed JSON to be a dictionary.
- Calls `JourneyResult.from_dict(data)` for valid dictionary output.

### `subprocess_run(...) -> Any`

```python
def subprocess_run(
    subprocess_path: str,
    flag: str,
    payload: dict,
    timeout_ms: int,
    step_count: int,
) -> Any:
```

Runs the child process that performs journey execution.

Parameters:

- `subprocess_path`: path to the Python file to execute.
- `flag`: command-line flag passed to the child process, currently `--execute-journey`.
- `payload`: JSON-serializable execution payload.
- `timeout_ms`: base timeout in milliseconds.
- `step_count`: number of journey steps, used to scale subprocess timeout.

Returns:

- `Any`: the result of `subprocess.run(...)`, typically a `subprocess.CompletedProcess[str]`.

Behavior:

- Imports `subprocess` lazily.
- Invokes `[sys.executable, subprocess_path, flag]`.
- Sends the JSON payload on standard input.
- Captures stdout and stderr as text.
- Uses `check=False`.
- Sets the subprocess timeout to `max(120, timeout_ms // 1000 * max(1, step_count))`.

## Browser Helper Functions

### `_dismiss_consent_overlays(page: Any) -> None`

```python
def _dismiss_consent_overlays(page: Any) -> None:
```

Dismisses cookie consent and ad overlays through a lazily imported browser utility.

Parameters:

- `page`: Playwright page-like object.

Returns:

- `None`.

### `_click_with_locator(page: Any, selector: str, timeout_ms: int) -> None`

```python
def _click_with_locator(page: Any, selector: str, timeout_ms: int) -> None:
```

Clicks the first element matching a selector.

Parameters:

- `page`: Playwright page-like object.
- `selector`: Playwright selector string.
- `timeout_ms`: operation timeout used with upper bounds for scroll and click.

Returns:

- `None`.

Behavior:

- Uses `page.locator(selector).first`.
- Returns without failure if no matching element exists.
- Attempts `scroll_into_view_if_needed(...)`, swallowing scroll errors.
- Clicks with `timeout=min(5000, timeout_ms)`.
- Waits 500 ms after the click.

### `_fill_with_locator(page: Any, selector: str, text: str, timeout_ms: int) -> None`

```python
def _fill_with_locator(page: Any, selector: str, text: str, timeout_ms: int) -> None:
```

Fills the first element matching a selector.

Parameters:

- `page`: Playwright page-like object.
- `selector`: Playwright selector string.
- `text`: text to enter.
- `timeout_ms`: accepted for signature consistency, but not used directly.

Returns:

- `None`.

Behavior:

- Uses `page.locator(selector).first`.
- Returns without failure if no matching element exists.
- Calls `locator.fill(text)`.

### `_capture_a11y_snapshot_sync(context: Any, page: Any) -> dict[str, Any] | None`

```python
def _capture_a11y_snapshot_sync(context: Any, page: Any) -> dict[str, Any] | None:
```

Captures a Chromium accessibility tree through a CDP session.

Parameters:

- `context`: Playwright browser context-like object.
- `page`: Playwright page-like object.

Returns:

- `dict[str, Any] | None`: an accessibility snapshot shaped as `{"nodes": [...]}`, or `None` if a CDP session cannot be created.

Behavior:

- Creates a CDP session with `context.new_cdp_session(page)`.
- Sends `Accessibility.getFullAXTree`.
- Stores `nodes` from the response when the response is a dictionary.
- Attempts to detach the CDP session before returning.
- Swallows accessibility capture and detach errors, returning the best available snapshot.

## Subprocess Entrypoint

### `_run_execute_journey_entry() -> int`

```python
def _run_execute_journey_entry() -> int:
```

Child-process entrypoint for `execute_journey()`.

Parameters:

- None.

Returns:

- `int`: process-style exit code, with `0` for successful execution and `1` for invalid payload shape.

Behavior:

- Reads JSON from `sys.stdin`.
- Validates that the payload is a dictionary.
- Reconstructs `JourneyStep` objects from `payload["journey_steps"]`, skipping non-dictionary entries.
- Reconstructs an optional `CredentialProfile` from `payload["credential_profile"]`.
- Reads `timeout_ms` and `starting_url`.
- Calls `_execute_journey_sync(...)`.
- Prints `result.to_dict()` as JSON to stdout.

### Module Main Guard

```python
if __name__ == "__main__":
    if "--execute-journey" in sys.argv:
        raise SystemExit(_run_execute_journey_entry())
```

When run as a script with `--execute-journey`, the module executes the child-process entrypoint and exits with its return code.

## Architectural Patterns

### Subprocess Boundary for Browser Automation

The public API is intentionally separate from direct Playwright execution. `execute_journey()` serializes dataclass-backed inputs and delegates to a subprocess. This creates a process boundary around browser automation and lets the parent process handle only orchestration and result parsing.

### JSON Serialization Contract

The parent and child communicate through JSON over standard input and standard output:

1. Parent converts `JourneyStep` and `CredentialProfile` instances to dictionaries.
2. Child reconstructs model objects from primitive dictionaries.
3. Child serializes `JourneyResult.to_dict()` to stdout.
4. Parent parses stdout and calls `JourneyResult.from_dict(...)`.

### Linear Step Interpreter

`_execute_journey_sync()` behaves as a compact interpreter over `JourneyStep.action`. Each supported action maps to a branch with specific validation, Playwright behavior, and failure recording.

### Explicit Auth Blocker Detection

Navigation steps are also guard checkpoints. After navigation, the executor inspects URL, page title, `h1` text, and HTML content to detect:

- login redirects,
- SSO/OAuth redirects,
- CAPTCHA pages,
- MFA prompts.

SSO, CAPTCHA, and MFA set a terminal `error_message`, causing subsequent steps to be recorded as stopped.

### Best-Effort Interaction Helpers

The click, fill, consent-dismissal, and accessibility helpers favor best-effort behavior:

- Missing click/fill locators return quietly at helper level.
- Scroll, accessibility, consent, and selector-wait failures are generally swallowed where they are nonessential.
- User-visible failure messages are collected at the journey-step level rather than raised directly.

### Capture With Optional Accessibility Enrichment

The `capture` step extracts DOM-derived element data from the current HTML, then attempts to capture the Chromium accessibility tree through CDP. If the snapshot succeeds, `AccessibilityEnricher.enrich(...)` augments the extracted elements. If accessibility capture fails, the module still preserves the HTML-derived capture.

### Resource Cleanup

The Playwright browser context and browser are closed in a `finally` block after journey execution, ensuring cleanup even when steps fail or auth detection stops progress.

## Error and Result Semantics

- A journey is successful only when no failed steps were recorded and no terminal `error_message` was set.
- Non-terminal step failures are accumulated in `failed_steps` and allow later steps to continue.
- Terminal auth blockers set `error_message` and cause remaining steps to be marked as stopped.
- Subprocess failures, invalid subprocess JSON, and unexpected subprocess output are converted into failure `JourneyResult` objects by the parent process.

## Classes

This module defines no classes. It coordinates imported model classes and dataclasses from other modules.





# `src/journey_models.py`

## High-Level Purpose

`journey_models.py` defines lightweight data models for journey-aware scraping. The module is intentionally limited to pure dataclasses and a small template-substitution helper so callers can import journey data structures without also loading Playwright, subprocess, UI, or pipeline execution dependencies.

The models describe:

- Planned journey actions, such as navigation, clicks, fills, waits, and scraping.
- Scraped output captured at a specific journey step.
- In-memory credential profiles used for authenticated journeys.
- Aggregate journey execution results that can be serialized to and from JSON-friendly dictionaries.

## Imports and Dependencies

- `from __future__ import annotations`
  - Allows forward references such as `JourneyResult` in type annotations.
- `dataclasses.asdict`
  - Used to serialize nested dataclass-compatible values in `JourneyResult.to_dict()`.
- `dataclasses.dataclass`
  - Used for all public model classes.
- `dataclasses.field`
  - Used for the `JourneyResult.redirected_urls` mutable default list.
- `typing.Any`
  - Used for loosely typed scraped element dictionaries and JSON-like output.

The module has no runtime dependency on Playwright, Streamlit, subprocess execution, filesystem access, or network access.

## Classes

### `JourneyStep`

```python
@dataclass
class JourneyStep:
    action: str
    url: str | None = None
    selector: str | None = None
    text: str | None = None
    description: str = ""
    timeout_ms: int = 30_000
```

Generated constructor signature:

```python
JourneyStep(
    action: str,
    url: str | None = None,
    selector: str | None = None,
    text: str | None = None,
    description: str = "",
    timeout_ms: int = 30000,
) -> None
```

Represents one action in a journey-aware scraping flow.

Fields:

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `action` | `str` | required | Action type, expected to represent values such as `"navigate"`, `"click"`, `"fill"`, `"wait"`, or `"scrape"`. |
| `url` | `str | None` | `None` | URL used by navigation steps. |
| `selector` | `str | None` | `None` | Element selector used by interaction steps such as click or fill. |
| `text` | `str | None` | `None` | Text entered during fill steps. |
| `description` | `str` | `""` | Human-readable step description. |
| `timeout_ms` | `int` | `30_000` | Per-step timeout in milliseconds. |

Methods:

- No custom methods are defined.
- Standard dataclass methods such as `__init__`, `__repr__`, and equality comparison are generated automatically.

### `ScrapedStep`

```python
@dataclass
class ScrapedStep:
    url: str
    elements: list[dict[str, Any]]
    step_index: int
    step_description: str = ""
```

Generated constructor signature:

```python
ScrapedStep(
    url: str,
    elements: list[dict[str, Any]],
    step_index: int,
    step_description: str = "",
) -> None
```

Represents the scraped result associated with a specific step in a journey.

Fields:

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `url` | `str` | required | URL that was scraped. |
| `elements` | `list[dict[str, Any]]` | required | Scraped element records for the URL. The element schema is intentionally flexible. |
| `step_index` | `int` | required | Index of the journey step that produced the scrape. |
| `step_description` | `str` | `""` | Human-readable description of the journey step. |

Methods:

- No custom methods are defined.
- Standard dataclass methods are generated automatically.

### `CredentialProfile`

```python
@dataclass
class CredentialProfile:
    label: str
    username: str
    password: str
```

Generated constructor signature:

```python
CredentialProfile(
    label: str,
    username: str,
    password: str,
) -> None
```

Represents user-provided credentials for authenticated journey scraping.

Fields:

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `label` | `str` | required | Human-readable name for the credential profile. |
| `username` | `str` | required | Username value used during templated fill steps. |
| `password` | `str` | required | Password value used during templated fill steps. |

Operational note:

- The source docstring states that credentials are stored in session state only and are never persisted to disk.

Methods:

- No custom methods are defined.
- Standard dataclass methods are generated automatically.

### `JourneyResult`

```python
@dataclass
class JourneyResult:
    success: bool
    captured_pages: dict[str, list[dict[str, Any]]]
    failed_steps: list[str]
    error_message: str | None = None
    redirected_urls: list[str] = field(default_factory=list)
```

Generated constructor signature:

```python
JourneyResult(
    success: bool,
    captured_pages: dict[str, list[dict[str, Any]]],
    failed_steps: list[str],
    error_message: str | None = None,
    redirected_urls: list[str] = <new empty list>,
) -> None
```

Represents the aggregate outcome of executing a journey through authenticated or multi-step pages.

Fields:

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `success` | `bool` | required | Indicates whether the journey completed successfully. |
| `captured_pages` | `dict[str, list[dict[str, Any]]]` | required | Mapping from URL to scraped element records. |
| `failed_steps` | `list[str]` | required | Human-readable descriptions of failed journey steps. |
| `error_message` | `str | None` | `None` | Top-level journey error, such as SSO, MFA, or CAPTCHA failure. |
| `redirected_urls` | `list[str]` | new empty list | URLs reached through redirects during the journey. |

#### `JourneyResult.to_dict`

```python
def to_dict(self) -> dict[str, Any]:
```

Serializes the dataclass instance to a plain dictionary.

Parameters:

| Parameter | Type | Purpose |
| --- | --- | --- |
| `self` | `JourneyResult` | Instance being serialized. |

Returns:

| Type | Description |
| --- | --- |
| `dict[str, Any]` | JSON-friendly dictionary produced by `dataclasses.asdict(self)`. |

Behavior:

- Converts the dataclass and contained dataclass-compatible structures into dictionaries and plain containers.
- Does not perform custom filtering, validation, or redaction.

#### `JourneyResult.from_dict`

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> JourneyResult:
```

Deserializes a dictionary into a `JourneyResult`.

Parameters:

| Parameter | Type | Purpose |
| --- | --- | --- |
| `cls` | `type[JourneyResult]` | Dataclass constructor target supplied by `@classmethod`. |
| `data` | `dict[str, Any]` | Dictionary containing serialized journey result fields. |

Returns:

| Type | Description |
| --- | --- |
| `JourneyResult` | New result instance built from the dictionary. |

Field mapping:

| Output Field | Source Expression | Fallback |
| --- | --- | --- |
| `success` | `bool(data.get("success", False))` | `False` |
| `captured_pages` | `data.get("captured_pages", {})` | `{}` |
| `failed_steps` | `data.get("failed_steps", [])` | `[]` |
| `error_message` | `data.get("error_message")` | `None` |
| `redirected_urls` | `data.get("redirected_urls", [])` | `[]` |

Behavior:

- Performs permissive dictionary loading with defaults for missing keys.
- Coerces `success` with `bool(...)`.
- Does not validate nested scraped element schemas.
- Does not copy or deep-copy dictionary values beyond the constructor assignment.

## Functions

### `substitute_templates`

```python
def substitute_templates(
    text: str,
    credential_profile: CredentialProfile | None,
) -> str:
```

Replaces supported credential placeholders in a text value.

Parameters:

| Parameter | Type | Purpose |
| --- | --- | --- |
| `text` | `str` | Input text that may contain credential placeholders. |
| `credential_profile` | `CredentialProfile | None` | Credentials used for replacement. If `None`, no substitution occurs. |

Returns:

| Type | Description |
| --- | --- |
| `str` | The original text when no profile is provided, otherwise a new string with supported placeholders replaced. |

Supported placeholders:

| Placeholder | Replacement |
| --- | --- |
| `{{username}}` | `credential_profile.username` |
| `{{password}}` | `credential_profile.password` |

Behavior:

- Returns `text` unchanged when `credential_profile is None`.
- Replaces username first, then password.
- Does not mutate the credential profile.
- Does not support arbitrary template variables, escaping, conditional logic, or validation of unresolved placeholders.

## Architectural Patterns

### Lightweight Model Boundary

The module isolates journey data structures from execution code. This keeps model imports inexpensive and allows CLI, UI, tests, and orchestration code to share the same representations without importing browser automation machinery.

### Dataclass-Centric Data Transfer

All public classes are dataclasses. They function as simple data transfer objects with generated constructors, representations, and equality behavior rather than encapsulating browser or pipeline behavior.

### Flexible Scraped Element Schema

Scraped element collections use `list[dict[str, Any]]`. This preserves flexibility for DOM-derived records whose exact fields may vary across pages, scraping strategies, or downstream consumers.

### JSON-Friendly Serialization

`JourneyResult.to_dict()` and `JourneyResult.from_dict()` provide a small serialization boundary for storing or passing journey results as plain dictionaries. The implementation favors permissive defaults over strict validation.

### Safe Mutable Defaults

`JourneyResult.redirected_urls` uses `field(default_factory=list)` to avoid sharing one mutable list across instances.

### Explicit Credential Templating

`substitute_templates()` implements a narrow, predictable placeholder mechanism for credential injection. It intentionally only handles the two recognized placeholders, `{{username}}` and `{{password}}`.

## Side Effects

- Importing this module has no side effects beyond defining classes and functions.
- The module does not read or write files.
- The module does not access network resources.
- The module does not launch browsers or subprocesses.






# `src/journey_scraper.py`

## High-Level Purpose

`journey_scraper.py` provides a journey-aware Playwright scraping layer. Instead of scraping only static URLs, it follows a sequence of user-like actions such as navigation, clicks, fills, waits, scrapes, and transient captures so that dynamic elements are present before element extraction runs.

The module now acts partly as a compatibility facade. Core journey data models are imported from `src.journey_models`, and authenticated journey execution is re-exported from `src.journey_executor`. The scraper classes and subprocess entry point remain defined here.

Primary responsibilities:

- Execute scripted journeys in sync Playwright while exposing an async public API.
- Avoid Windows and Streamlit nested event loop issues by running sync Playwright scraping in a subprocess.
- Scrape and enrich page elements after initial load, navigation, click-driven navigation, explicit scrape steps, and capture steps.
- Discover selectors from natural-language step descriptions using local DOM extraction, heuristic scoring, robust locator construction, and resolver fallback.
- Track skipped steps and locator failures for diagnostics.
- Provide a cart-seeding convenience scraper for flows that require cart state before scraping cart or checkout pages.

## Public Exports

`__all__` exports:

- `CartSeedingScraper`
- `CredentialProfile`
- `JourneyResult`
- `JourneyScraper`
- `JourneyStep`
- `ScrapedStep`
- `execute_journey`

Compatibility aliases and re-exports:

- `execute_journey` is imported from `src.journey_executor`.
- `CredentialProfile`, `JourneyResult`, `JourneyStep`, `ScrapedStep`, and `substitute_templates` are imported from `src.journey_models`.
- `_substitute_templates = substitute_templates` preserves older imports used by legacy tests.

## Top-Level Helper Functions

### `_capture_element_visibility_sync(page: Any, elements: list[dict[str, Any]]) -> list[dict[str, Any]]`

Checks each scraped element's runtime visibility with Playwright.

Parameters:

- `page: Any` - live Playwright page-like object.
- `elements: list[dict[str, Any]]` - extracted element dictionaries, expected to contain optional `selector` keys.

Returns:

- `list[dict[str, Any]]` - the same element list, with `is_visible` added or updated when selector lookup succeeds.

Behavior:

- Iterates through elements.
- Skips elements without a selector.
- Uses `page.locator(selector).first.is_visible()`.
- Suppresses selector or visibility failures so enrichment remains additive.

### `_capture_a11y_snapshot_sync(context: Any, page: Any) -> dict[str, Any] | None`

Captures a Chromium accessibility tree through Chrome DevTools Protocol.

Parameters:

- `context: Any` - Playwright browser context.
- `page: Any` - live Playwright page.

Returns:

- `dict[str, Any] | None` - `{"nodes": [...]}` when a CDP session can be created, or `None` when CDP is unavailable.

Behavior:

- Opens a CDP session for the page.
- Sends `Accessibility.getFullAXTree`.
- Stores returned `nodes` when the response is a dictionary.
- Detaches the CDP session when possible.
- Returns an empty-node snapshot on CDP command failure, and `None` only when session creation fails.

### `_run_subprocess_entry() -> int`

Subprocess entry point used when the module is executed with `--journey-scrape`.

Parameters:

- None directly. Reads JSON payload from `sys.stdin`.

Returns:

- `int` - process-style status code. Returns `0` after successful scrape output, `1` for invalid payload shape.

Behavior:

- Parses stdin JSON into scraper configuration and serialized steps.
- Reconstructs `JourneyStep` instances from step dictionaries.
- Instantiates `JourneyScraper`.
- Calls private sync scraping method `_scrape_journey_sync`.
- Prints JSON output to stdout.

## Class: `JourneyScraper`

Scrapes pages by following a user journey step-by-step.

### Constructor

```python
def __init__(
    self,
    starting_url: str,
    *,
    timeout_ms: int = 30_000,
    max_retries: int = 2,
    base_backoff_ms: int = 1000,
    headless: bool = True,
    credential_profile: CredentialProfile | None = None,
) -> None:
```

Parameters:

- `starting_url: str` - starting page URL; stripped before storage.
- `timeout_ms: int` - default Playwright timeout in milliseconds.
- `max_retries: int` - number of attempts per journey step.
- `base_backoff_ms: int` - retry backoff base in milliseconds.
- `headless: bool` - whether Chromium launches headless.
- `credential_profile: CredentialProfile | None` - optional profile retained for later journey execution.

Returns:

- `None`

Initialized state:

- `self.starting_url: str`
- `self.timeout_ms: int`
- `self.max_retries: int`
- `self.base_backoff_ms: int`
- `self.headless: bool`
- `self._credential_profile: CredentialProfile | None`
- `self._html_scraper: PageScraper`
- `self._resolver: PlaceholderResolver`
- `self._captured_pages: dict[str, list[dict[str, Any]]]`
- `self._context_log: list[dict[str, Any]]`

### `_debug(self, message: str) -> None`

Prints a debug message to stderr when `PIPELINE_DEBUG=1`.

Parameters:

- `message: str` - debug text.

Returns:

- `None`

### `async scrape_journey(self, steps: list[JourneyStep], *, credential_profile: CredentialProfile | None = None) -> dict[str, list[dict[str, Any]]]`

Public async API for following a journey and returning scraped elements per URL.

Parameters:

- `steps: list[JourneyStep]` - journey steps to execute.
- `credential_profile: CredentialProfile | None` - optional per-call credential profile overriding the instance profile.

Returns:

- `dict[str, list[dict[str, Any]]]` - mapping from URL to scraped element dictionaries.

Behavior:

- Filters steps to supported actions: `navigate`, `click`, `fill`, `wait`, `scrape`, `capture`.
- Returns `{}` if no supported steps remain.
- Resolves the effective credential profile.
- Uses `asyncio.to_thread` to run `_scrape_journey_via_subprocess` without blocking the event loop.

### `_scrape_journey_via_subprocess(self, steps: list[JourneyStep], credential_profile: CredentialProfile | None = None) -> dict[str, list[dict[str, Any]]]`

Runs the sync Playwright journey in a clean subprocess.

Parameters:

- `steps: list[JourneyStep]` - cleaned journey steps.
- `credential_profile: CredentialProfile | None` - optional credential profile serialized into the payload.

Returns:

- `dict[str, list[dict[str, Any]]]` - URL-to-elements mapping, or `{}` on subprocess failure or invalid output.

Behavior:

- Serializes steps and scraper configuration to JSON.
- Invokes the current file with `[sys.executable, subprocess_path, "--journey-scrape"]`.
- Passes payload through stdin.
- Captures stdout and stderr.
- Prints subprocess stderr to the parent stderr for debugging.
- Parses stdout JSON into a typed dictionary.
- Stores successful output in `self._captured_pages`.

### `_scrape_journey_sync(self, steps: list[JourneyStep]) -> dict[str, list[dict[str, Any]]]`

Core synchronous Playwright journey executor used by the subprocess.

Parameters:

- `steps: list[JourneyStep]` - journey steps to run.

Returns:

- `dict[str, list[dict[str, Any]]]` - URL-to-elements mapping captured during the journey.

Behavior:

- Launches Chromium through `sync_playwright`.
- Creates a browser context and page.
- Sets the default timeout.
- Optionally navigates to `starting_url`, dismisses overlays, and scrapes the starting page.
- Iterates steps with retry and exponential backoff plus jitter.
- Handles supported actions:
  - `navigate` - navigate through `_navigate_to`.
  - `click` - dismiss overlays, discover missing selector if possible, then click.
  - `fill` - discover missing selector if possible, then fill with provided text.
  - `wait` - wait for seconds parsed from `description`, defaulting to 1.0.
  - `scrape` - scrape the current page.
  - `capture` - scrape transient page content without visibility enrichment, then optionally add accessibility enrichment.
- Auto-scrapes after explicit navigation.
- Detects click-driven URL changes and auto-scrapes the new page.
- Logs relaxed selector fallback and skipped-step events in `_context_log`.
- Closes browser context and browser in `finally`.
- Stores output in `self._captured_pages`.

### `get_pages_visited(self) -> list[str]`

Returns unique URLs captured during the journey.

Parameters:

- None.

Returns:

- `list[str]` - insertion-ordered unique URLs from `self._captured_pages`.

### `get_skipped_steps(self) -> list[dict]`

Returns logged skipped journey steps.

Parameters:

- None.

Returns:

- `list[dict]` - context log entries where `event == "step_skipped"`.

### `get_locator_warnings(self) -> list[dict]`

Returns locator-not-found warnings.

Parameters:

- None.

Returns:

- `list[dict]` - context log entries where `event == "locator_not_found"`.

### `@staticmethod _list_available_elements(page: Any, limit: int = 10) -> list[dict]`

Collects a small diagnostic sample of clickable/link-like elements.

Parameters:

- `page: Any` - live Playwright page.
- `limit: int` - maximum number of elements to inspect.

Returns:

- `list[dict]` - dictionaries containing `tag`, truncated `text`, `id`, and first CSS class.

### `_discover_selector_relaxed(self, page: Any, action: str, description: str) -> str | None`

Fallback selector discovery using relaxed text matching.

Parameters:

- `page: Any` - live Playwright page.
- `action: str` - intended action, currently not used in the relaxed scoring logic.
- `description: str` - natural-language description to match against element text or labels.

Returns:

- `str | None` - robust locator or existing selector for the first relaxed match; `None` when no match is found.

Behavior:

- Waits briefly for network idle.
- Extracts elements from current HTML through `PageScraper`.
- Normalizes description into keywords.
- Looks for any keyword in each candidate's accessible name, aria label, or text.
- Prefers `build_robust_locator(element)` and falls back to `element["selector"]`.

### `_discover_selector(self, page: Any, action: str, description: str) -> str | None`

Primary selector discovery for natural-language journey steps.

Parameters:

- `page: Any` - live Playwright page.
- `action: str` - action such as `click` or `fill`.
- `description: str` - natural-language target description.

Returns:

- `str | None` - selected robust locator or selector, or `None` when no usable candidate is found.

Behavior:

- Waits briefly for page stability.
- Extracts elements from current page HTML.
- Applies visibility enrichment.
- Scores all candidates with `PlaceholderScorer.compute_element_score`.
- Applies action-specific penalties:
  - `fill` heavily penalizes non-input roles.
  - `click` moderately penalizes non-interactive roles.
- Returns the best robust locator or selector when available.
- Falls back to `PlaceholderResolver.rank_candidates`.
- Logs `locator_not_found` events with a diagnostic sample when no usable candidate exists.

### `_navigate_to(self, page: Any, url: str, timeout_ms: int) -> str`

Navigates to a URL and returns the final page URL.

Parameters:

- `page: Any` - live Playwright page.
- `url: str` - absolute or relative URL.
- `timeout_ms: int` - navigation timeout.

Returns:

- `str` - final `page.url` when navigation returns a response; otherwise the attempted full URL.

Behavior:

- Resolves leading-slash relative URLs with `urljoin(page.url, url)`.
- Calls `page.goto(..., wait_until="networkidle")`.
- Waits for network idle and an additional 1 second for DOM stability.
- Dismisses consent overlays after navigation.

### `_click_selector(self, page: Any, selector: str, timeout_ms: int) -> None`

Clicks an element by selector.

Parameters:

- `page: Any` - live Playwright page.
- `selector: str` - selector or locator string.
- `timeout_ms: int` - timeout budget for scroll and click.

Returns:

- `None`

Behavior:

- Uses the first matching locator.
- Returns without raising when no locator exists.
- Scrolls into view with a capped timeout.
- Clicks with a capped timeout.
- Waits 500 ms after click for page transition.
- Re-raises click exceptions after debug logging.

### `_fill_selector(self, page: Any, selector: str, text: str, timeout_ms: int) -> None`

Fills an input-like element by selector.

Parameters:

- `page: Any` - live Playwright page.
- `selector: str` - selector or locator string.
- `text: str` - value to fill.
- `timeout_ms: int` - accepted for signature consistency; not directly used by `locator.fill`.

Returns:

- `None`

Behavior:

- Uses the first matching locator.
- Returns without raising when no locator exists.
- Calls `locator.fill(text)`.
- Re-raises fill exceptions after debug logging.

### `_scrape_current_page(self, page: Any, url: str, context: Any | None = None) -> list[dict[str, Any]]`

Extracts and enriches elements from the current page state.

Parameters:

- `page: Any` - live Playwright page.
- `url: str` - base URL used during extraction.
- `context: Any | None` - optional browser context for accessibility snapshot capture.

Returns:

- `list[dict[str, Any]]` - extracted elements, enriched when possible.

Behavior:

- Reads `page.content()`.
- Extracts elements through `PageScraper._extract_elements_from_html`.
- Adds runtime visibility through `_capture_element_visibility_sync`.
- Adds accessibility enrichment through `AccessibilityEnricher.enrich` when a context and a CDP snapshot are available.
- Falls back to raw extracted elements if enrichment fails.

### `@staticmethod _dismiss_consent_overlays(page: Any) -> None`

Delegates consent-overlay dismissal to a shared browser utility.

Parameters:

- `page: Any` - live Playwright page.

Returns:

- `None`

Behavior:

- Imports `dismiss_consent_overlays` lazily.
- Calls it with the Playwright page.

## Class: `CartSeedingScraper(JourneyScraper)`

Specialized journey scraper for cart-dependent pages.

Purpose:

- Seed a cart by visiting products, selecting a product, adding it to the cart, capturing the confirmation state, dismissing the modal, then navigating to requested cart or checkout URLs.

Class attributes:

- `PRODUCT_SELECTORS: list[str]`
- `ADD_TO_CART_SELECTORS: list[str]`
- `CONTINUE_SHOPPING_SELECTORS: list[str]`

These constants are assigned from imported selector lists for compatibility.

### Constructor

```python
def __init__(
    self,
    starting_url: str,
    products_url: str | None = None,
    **kwargs: Any,
) -> None:
```

Parameters:

- `starting_url: str` - home page URL used to establish session.
- `products_url: str | None` - optional explicit products page URL.
- `**kwargs: Any` - forwarded to `JourneyScraper.__init__`.

Returns:

- `None`

Behavior:

- Initializes the base `JourneyScraper`.
- Stores `self.products_url`, deriving it from `starting_url` when not provided.

### `@staticmethod _derive_products_url(home_url: str) -> str`

Derives a products URL from a home URL.

Parameters:

- `home_url: str` - base home URL.

Returns:

- `str` - URL joined with `/products`.

### `async scrape_cart_pages(self, cart_urls: list[str]) -> dict[str, list[dict[str, Any]]]`

Seeds cart state and scrapes target cart-related pages.

Parameters:

- `cart_urls: list[str]` - cart or checkout URLs to visit after seeding.

Returns:

- `dict[str, list[dict[str, Any]]]` - output from `scrape_journey`.

Behavior:

- Builds a journey with:
  - navigate to products page,
  - click first product selector,
  - click first add-to-cart selector,
  - capture confirmation popup state,
  - click first continue-shopping selector,
  - wait for modal disappearance,
  - navigate to each requested cart URL.
- Calls `self.scrape_journey(steps)`.

### `@staticmethod _ensure_full_url(url: str) -> str`

Normalizes a target URL for cart scraping.

Parameters:

- `url: str` - absolute or relative URL.

Returns:

- `str` - the input URL unchanged.

Behavior:

- Explicitly returns absolute URLs unchanged.
- Also returns relative URLs unchanged because `JourneyScraper._navigate_to` handles relative navigation.

## Runtime Entry Point

```python
if __name__ == "__main__":
    if "--journey-scrape" in sys.argv:
        raise SystemExit(_run_subprocess_entry())
```

The file can be invoked directly as a subprocess worker. Parent code calls it with `--journey-scrape`, sends JSON payload on stdin, and expects JSON scrape output on stdout.

## Key Architectural Patterns

### Async facade over sync Playwright

The public `scrape_journey` method is async, but browser automation uses Playwright's synchronous API. The code bridges the two with `asyncio.to_thread` and a subprocess so callers can use an async interface without running sync Playwright in a problematic nested event loop.

### Subprocess isolation

The module serializes journey configuration and steps into JSON, invokes itself as a subprocess, and deserializes JSON output. This isolates Playwright execution from Streamlit or Windows event loop constraints.

### Compatibility facade

The module preserves older import paths by re-exporting journey models and `execute_journey` while keeping scraper logic local. This reduces downstream churn after extracting models and executor behavior into separate modules.

### Additive enrichment

Visibility and accessibility enrichment are best-effort. Failures are swallowed and raw extracted elements are returned. This keeps scraping resilient even when selectors are stale, CDP is unavailable, or enrichment encounters unexpected page state.

### Selector discovery pipeline

Selector discovery uses a staged approach:

1. Extract the current DOM with `PageScraper`.
2. Enrich candidate elements with visibility information.
3. Score candidates using `PlaceholderScorer`.
4. Apply action-aware penalties to avoid selecting display-only elements for interactive steps.
5. Build a robust locator from the best candidate.
6. Fall back to `PlaceholderResolver.rank_candidates`.
7. Fall back further to relaxed keyword matching when the main discovery method returns `None` during click or fill execution.

### Journey-state capture

The scraper captures pages at several moments:

- Starting URL load.
- Explicit navigation steps.
- Explicit scrape steps.
- Capture steps for transient states such as popups.
- Click steps that change the current page URL.

Captured data is stored in `self._captured_pages`, allowing later retrieval of visited URLs.

### Diagnostic context log

The private `_context_log` accumulates events such as:

- `locator_relaxed_fallback`
- `step_skipped`
- `locator_not_found`

Public diagnostic accessors expose skipped steps and locator warnings.

### Cart-specific journey composition

`CartSeedingScraper` composes a fixed journey using selector constants and then delegates execution to `JourneyScraper`. It does not override scraping mechanics; it only builds the domain-specific sequence needed to make cart and checkout pages meaningful.

## External Dependencies Used By This Module

- Standard library: `asyncio`, `json`, `os`, `random`, `re`, `sys`, `time`, `dataclasses.asdict`, `pathlib.Path`, `typing.Any`.
- Playwright sync API: `sync_playwright`.
- Project collaborators imported by name:
  - `AccessibilityEnricher`
  - selector constants from `form_detector`
  - `execute_journey`
  - journey model classes and `substitute_templates`
  - `build_robust_locator`
  - `PlaceholderResolver`
  - `PlaceholderScorer`
  - `PageScraper`
  - lazily imported `dismiss_consent_overlays`

## Notable Error-Handling Choices

- Visibility, accessibility, load-state waits, and overlay dismissal paths are generally best-effort.
- Subprocess failures return `{}` rather than raising.
- Invalid subprocess JSON output returns `{}`.
- Missing click or fill locator count logs debug output and returns without raising.
- Click and fill runtime exceptions are re-raised after debug logging.
- Step-level exceptions are retried with exponential backoff and then logged only when debug mode is enabled.

## Data Flow Summary

1. Caller creates `JourneyScraper` or `CartSeedingScraper`.
2. Caller passes `JourneyStep` objects to `scrape_journey`, or cart URLs to `scrape_cart_pages`.
3. Steps are filtered and serialized.
4. The module invokes itself with `--journey-scrape`.
5. The subprocess reconstructs steps and runs sync Playwright.
6. Each page state is scraped through `PageScraper`.
7. Element lists are optionally enriched with visibility and accessibility data.
8. JSON output is returned to the parent process.
9. Parent process stores the captured URL-to-elements mapping and returns it to the caller.





---
purpose: >
  High-level LLM client that wraps multiple providers (Ollama, LM Studio, OpenAI cloud/local).
  Handles provider selection, model auto-detection, conversation management, and code extraction.
  Supports both sync and async generation, plus vision capabilities.
lines: ~403
created: "2026-05-30"
---

# `src/llm_client.py`

## High-Level Purpose

Provider-agnostic LLM client that wraps the `src.llm_providers` module. Provides a unified `generate()` interface for creating Playwright test code. Handles provider selection (explicit, session-level, auto-detect, or environment-based), model auto-detection, conversation history, and response code extraction.

## Class: `LLMClient`

### `__init__(provider=None, provider_name=None, model=None, base_url=None, api_key=None)`
- Provider selection priority:
  1. Explicit `provider`/`provider_name` parameter
  2. Session-level provider set via `set_session_provider()` (CLI/Streamlit UI)
  3. Auto-detect local providers via `auto_detect_provider()`
  4. Fallback to environment via `create_provider_from_env()`
- Model selection priority:
  1. Explicit `model` parameter
  2. Session-level model set via `set_session_provider()`
  3. Provider-specific env vars (`OLLAMA_MODEL`, `LM_STUDIO_MODEL`, `OPENAI_MODEL`)
  4. Loaded model query (LM Studio, OpenAI local)
  5. First available model via `list_models()`
  6. Hardcoded fallbacks per provider

### `set_session_provider(provider, base_url=None, model=None)` (classmethod)
- Sets session-level provider selection used by all subsequent `LLMClient()` instances
- Called by CLI/Streamlit after user selects a provider

### Properties
- `provider_name(self) -> str`: Returns the configured provider name
- `model(self) -> str`: Returns the active model name
- `base_url(self) -> str`: Returns the provider base URL

### Key Methods

| Method | Description |
|--------|-------------|
| `generate(prompt, timeout=600, system_prompt=None) -> str` | Async generation â€” used by intelligent pipeline |
| `generate_test(prompt, timeout=300, system_prompt=None) -> str` | Sync generation â€” retained for tests/utilities |
| `generate_tests(acceptance_criteria, timeout=300) -> dict` | Generate from list of criteria, returns code + metadata |
| `create_vision_completion(image_base64, prompt) -> str` | Vision-capable completion for image+text prompts |
| `list_models(timeout=30) -> list[str]` | List models from current provider |
| `reset_conversation(system_instruction=None, system_prompt=None)` | Reset conversation history |
| `get_conversation_summary() -> dict` | Debug metadata for current conversation |

### Internal Methods
- `_get_default_model() -> str`: Multi-strategy model resolution
- `_complete_sync(prompt, timeout, system_prompt) -> ChatCompletion`: Core sync completion
- `_extract_code(raw_text) -> str`: Strip prose/fences from LLM output
- `normalise_code_newlines(code) -> str`: Minimal whitespace cleanup
- `_debug(message)`: Conditional debug logging via `PIPELINE_DEBUG=1`

## Provider Support

| Provider | Selection | Key Details |
|----------|-----------|-------------|
| Ollama | `ollama` | Native API, default model `qwen2.5:7b` |
| LM Studio | `lm-studio` | OpenAI-compatible API, probes `/api/v0/models` for loaded model |
| OpenAI (cloud) | `openai` | Requires `OPENAI_API_KEY`, default `gpt-4o` |
| OpenAI (local) | `openai-local` | No API key, probes ports 8080/8000/5000, default `llama` |

## Environment Variables

- `OLLAMA_MODEL` â€” override default Ollama model
- `LM_STUDIO_MODEL` â€” override default LM Studio model
- `OPENAI_MODEL` â€” override default OpenAI model
- `OPENAI_API_KEY` â€” required for cloud OpenAI provider
- `PIPELINE_DEBUG=1` â€” enable debug logging

## Dependencies

- `src.llm_providers` â€” provider implementations (Ollama, LM Studio, OpenAI)
- `asyncio` â€” async generation support
- `re` â€” code extraction from LLM responses

## Depended On By

- `src/orchestrator.py` â€” pipeline orchestration
- `src/test_generator.py` â€” skeleton generation
- `src/placeholder_orchestrator.py` â€” placeholder resolution
- CLI/Streamlit UI â€” provider selection and session management

## Notes

- Uses `httpx` (via `llm_providers`) instead of `requests`
- No longer uses `dotenv` â€” environment loading handled elsewhere
- Session provider state is class-level, shared across all instances
- Vision completion uses base64-encoded PNG images
- Code extraction handles markdown fences, `<channel|>` tags, and





# llm_errors.py

## Purpose
Lightweight error structures for LLM-backed test generation. Provides typed error categorization and result wrapping for all LLM interactions.

## Location
`src/llm_errors.py` (29 lines)

## Dependencies
- **Standard library only**: `dataclasses`, `enum`

## Public API

### `class LLMErrorType(StrEnum)`
High-level categories for LLM failures. Inherits from `StrEnum` for serializable values.

| Value | Meaning |
|-------|---------|
| `EMPTY_RESPONSE` | LLM returned an empty or whitespace-only response |
| `UNKNOWN` | Catch-all for unexpected errors |

### `@dataclass LLMError`
Structured error information for callers.

| Field | Type | Description |
|-------|------|-------------|
| `error_type` | `LLMErrorType` | Category of the error |
| `message` | `str` | Human-readable error description |

### `@dataclass LLMResult`
Wrapper for LLM generation results. Allows callers to handle success and failure uniformly.

| Field | Type | Description |
|-------|------|-------------|
| `code` | `str \| None` | Generated code on success, `None` on failure |
| `error` | `LLMError \| None` | Error details on failure, `None` on success |

## Design Notes
- `LLMErrorType` extends `StrEnum` (Python 3.11+) for JSON-serializable enum values
- Simple, focused module â€” no business logic, just data structures
- Used by `llm_client.py` to return structured results instead of raising exceptions
- Enables graceful error handling in the pipeline without crash-on-failure

## Related Files
- `src/llm_client.py` â€” primary consumer; wraps LLM responses in `LLMResult`
- `src/orchestrator.py` â€” handles `LLMResult.error` for fallback behavior





# llm_reasoning_filter.py

## Purpose
Detect and strip LLM reasoning text from generated code. Extracted from `code_postprocessor.py` to separate reasoning detection into its own independently testable module.

## Location
`src/llm_reasoning_filter.py` (142 lines)

## Dependencies
- **Standard library only**: `re`

## Public API

### `strip_llm_reasoning(code: str) -> str`
Removes lines that look like LLM reasoning/thinking text. LLMs sometimes output their internal chain-of-thought as part of the code block. This function detects and removes such lines while preserving valid Python code, comments, and blank lines.

### `_is_llm_reasoning_line(line: str) -> bool` (private)
Returns `True` if the line looks like LLM reasoning text rather than Python code. Uses a multi-stage detection pipeline:

1. **Empty line check** â€” blank lines are never reasoning
2. **Python keyword whitelist** â€” lines starting with valid Python constructs are preserved (def, class, import, from, return, if, else, for, while, try, except, assert, page., self., etc.)
3. **Reasoning prefix match** â€” lines starting with known reasoning prefixes (Wait, Note, Actually, Hmm, Okay, Sure, Let's, I will, Self-Correction, etc.)
4. **Comment-pattern match** â€” `# Word,` style reasoning comments
5. **Bullet-pattern match** â€” `- Actually`, `- I will`, numbered reasoning bullets
6. **Heuristic fallback** â€” short lines (<80 chars) starting with `CapitalizedWord,` that aren't variable assignments

## Detection Patterns
| Pattern Group | Examples |
|---------------|----------|
| `_LLM_REASONING_PREFIXES` | "Wait,", "Note,", "Actually,", "I will ", "Self-Correction" |
| `_LLM_REASONING_PATTERNS` | `# Word,` comments, bare reasoning words |
| `_BULLET_REASONING_PATTERNS` | `- Actually`, `- I need`, numbered reasoning lists |

## Design Notes
- Extracted from `code_postprocessor.py` for independent testing
- Line-by-line processing â€” no state carried between lines
- Python keyword whitelist includes runtime objects (`page.`, `self.`, `evidence_tracker`) to avoid false positives
- Heuristic for short natural-language lines catches edge cases not covered by prefixes

## Related Files
- `src/code_postprocessor.py` â€” consumer; calls `strip_llm_reasoning()` as a post-processing step
- `src/code_normalizer.py` â€” sibling post-processing module (newline normalization)





# `src/locator_builder.py`

## High-Level Purpose

Builds robust Playwright locators from scraped element metadata. Transforms brittle CSS selectors into stable, specific locators by prioritizing ID > href > data-attrs > class > text > aria-label patterns. Used during placeholder resolution to produce reliable selectors.

## Module Metadata

- **Lines:** 182
- **Imports:** `re`

## Functions

### `build_robust_locator(element: dict) -> str | None`

Build a robust Playwright locator from scraped element metadata. Prefers stable, specific selectors over text-based locators.

**Priority order** (most specific first):
1. ID-based (e.g. `#buy`)
2. href-based for links (e.g. `a[href="/view_cart"]`)
3. Data attribute with specific value (e.g. `[data-product-id="1"]`)
4. Class-based without brittle framework prefixes (e.g. `.cart_description`)
5. Tag + :has-text (e.g. `a:has-text("Add to cart")`)
6. Role + :has-text (e.g. `button:has-text("Submit")`)
7. Aria-label based (e.g. `[aria-label="Submit"]`)
8. `None` â€” falls back to raw selector

Strips common UI framework class prefixes (`btn-`, `fa-`, `fas`, `far`, `bi-`, `mdi-`, `icon-`, `css-`) that add no semantic value.

**Args:** `element` â€” Dict with keys: `tag`, `text`, `role`, `selector`, `id`, `aria_label`, `classes`, `href`.
**Returns:** Robust locator string, or `None` if nothing stable can be built.

### `build_selector_relaxed(description: str, page_elements: list[dict]) -> str | None`

Build a selector with relaxed matching criteria. Used as fallback when strict selector build fails. Tokenizes the description and scores elements by token overlap across text, attributes, and role. Uses 0.2 confidence threshold (vs 0.3 strict).

**Args:** `description` â€” Human-readable target description; `page_elements` â€” Element metadata from scraper.
**Returns:** Relaxed locator string, or `None` if no element meets threshold.

### `_css_escape_id(value: str) -> str`

Escape a value for safe use as a CSS ID selector.

### `_token_overlap(description_tokens: set[str], element_tokens: set[str]) -> float`

Compute Jaccard-like overlap between two token sets. Returns a value in [0, 1].

## Dependencies

None (stdlib only).

## Depended On By

`placeholder_resolver.py`, `placeholder_orchestrator.py`





# `src/locator_fallback.py`

## High-Level Purpose

Provides higher-scoring locator alternatives when the primary locator fails at runtime. Part of the Tier 2: Locator Scoring + Controlled Fallback architecture. Builds candidate selectors from the current page DOM, scores them with `LocatorScorer`, and tries the top alternatives with full audit trail.

## Module Metadata

- **Lines:** 204
- **Imports:** `typing.Any`, `src.locator_scorer.LocatorScorer`

## Class: `LocatorFallback`

Controlled locator fallback with scoring and audit trail. When a primary locator fails, this class:
1. Builds candidate selectors from the current page DOM
2. Scores candidates using `LocatorScorer`
3. Tries the top 2 higher-scoring alternatives
4. Returns an audit trail with scores and confidence levels

### `build_candidates(primary_locator, el_metadata, page) -> list[dict]`

Build a list of locator candidates from the current page DOM. Uses JavaScript to extract candidate selectors (id, testid, name, aria-label, role, classes, text) for the same element or similar elements.

**Args:** `primary_locator` â€” Original selector that failed; `el_metadata` â€” Element metadata; `page` â€” Playwright Page.
**Returns:** List of candidate dicts with `selector` and `element` keys.

### `try_fallback(loc, primary_locator, label, el_metadata, primary_error, page, record_step, max_fallbacks=2, elapsed_ms=0) -> None`

Try higher-scoring locator alternatives when the primary locator fails. Builds candidates, scores them, and tries top `max_fallbacks` in score-descending order. Records full fallback chain with scores and confidence levels.

**Args:** `loc` â€” Playwright locator; `primary_locator` â€” Failed selector; `label` â€” Step label; `el_metadata` â€” Element metadata; `primary_error` â€” Exception; `page` â€” Playwright Page; `record_step` â€” Step recorder callable; `max_fallbacks` â€” Max candidates to try (default 2).
**Raises:** The primary error is re-raised after all fallbacks fail.

## Dependencies

`src.locator_scorer` (LocatorScorer)

## Depended On By

Runtime test execution (generated tests with fallback support)





# `src/locator_repair.py`

## High-Level Purpose

Surgical replacement of a broken locator in a generated test file. Replaces only the locator string while preserving the surrounding action (`.click()`, `.fill()`, etc.). Design-time only â€” not used at test runtime.

## Module Metadata

- **Lines:** 151
- **Imports:** `re`, `dataclasses`, `pathlib.Path`

## Data Classes

### `LocatorPatch`

Describes a single locator replacement.
- `original_locator: str` â€” The broken locator string from the error
- `repaired_locator: str` â€” The corrected locator (e.g., from codegen)
- `line_number: int` â€” 1-based line in the generated test to patch
- `test_file: str | Path` â€” Path to the generated test file

### `LocatorRepairError(Exception)`

Raised when the target locator could not be found on the expected line.

## Functions

### `apply_patch(patch: LocatorPatch) -> str`

Apply a locator patch to the test source and return the patched source. Finds the line containing `original_locator`, replaces only the locator string inside `.locator("...")`, preserves the action. Searches +/- 10 lines around reported line number since Playwright error lines don't always match the locator call line.

### `apply_patch_to_file(patch: LocatorPatch) -> None`

Apply a locator patch and write the result back to disk.

### `extract_locator_from_line(line: str) -> str | None`

Extract the locator string from a single line of test code. Looks for `.locator("...")` pattern.

## Dependencies

None (stdlib only).

## Depended On By

Test repair workflows, CI auto-fix pipelines





# locator_scorer.py

## Purpose
Score Playwright selectors by reliability/fragility based on locator type to enable controlled fallbacks, coverage validation, and suite heatmaps.

## Location
`src/locator_scorer.py` (321 lines)

## Dependencies
- `re` (standard library)
- `typing.Any` (standard library)

## Public API

### `LocatorScorer.score_locator(selector: str, element: dict | None = None, action_description: str = "") -> dict[str, Any]`
Score a single locator and return metadata including `selector`, `type`, `score`, `confidence`, and `fragility_reason`.

### `LocatorScorer.score_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]`
Score a list of locator candidates and return them sorted by score descending (shorter selectors preferred as tiebreaker).

### `LocatorScorer.get_fallback_candidates(failed_locator: str, all_candidates: list[dict[str, Any]], max_fallbacks: int = 2) -> list[dict[str, Any]]`
Return the top N fallback candidates that score higher than the failed locator.

## Scoring Hierarchy
| Locator Type | Base Score | Confidence |
|--------------|------------|------------|
| data-testid  | 100        | Excellent  |
| id           | 85         | High       |
| name         | 70         | Good       |
| aria-label   | 60         | Good       |
| role         | 55         | Fair       |
| css-class    | 40         | Fair       |
| text         | 35         | Low        |
| xpath        | 20         | Low        |

## Design Notes
- Higher score = more stable selector
- Specificity modifier penalizes overly-specific CSS paths
- Confidence labels derived from score ranges
- Used by `locator_fallback.py` at runtime and `failure_reporter.py` for diagnostics
- NOT used by design-time `placeholder_resolver.py` (uses `placeholder_scorers.py` instead)

## Related Files
- `src/locator_fallback.py` â€” consumes scores for runtime fallback selection
- `src/failure_reporter.py` â€” uses scores for diagnostic alternatives
- `src/placeholder_scorers.py` â€” sibling scoring module for design-time resolution (separate concern)





# `src/orchestrator.py`

## High-Level Purpose

Primary intelligent generation pipeline for the Streamlit app. Coordinates the full skeleton-first test generation workflow: parses user stories into test conditions, generates skeleton code with placeholders, scrapes target URLs for DOM metadata, resolves placeholders to real selectors, post-processes code, and saves output. Supports both single-condition and multi-condition (combined) skeleton generation.

## Module Metadata

- **Lines:** 791
- **Key imports:** `asyncio`, `dataclasses`, `json`, `logging`, `os`, `pathlib.Path`, `re`, `time`, `traceback`, `typing`
- **Project imports:** 
  - `src.code_postprocessor.normalise_generated_code`
  - `src.journey_scraper.*` (CredentialProfile, JourneyResult, JourneyScraper, JourneyStep, execute_journey)
  - `src.page_object_builder.PageObjectBuilder`
  - `src.pipeline_models.*` (GeneratedPageObject, PageRequirement, ScrapedPage, TestJourney)
  - `src.placeholder_orchestrator.PlaceholderOrchestrator`
  - `src.placeholder_resolver.PlaceholderResolver`
  - `src.prerequisite_injector.PrerequisiteInjector`
  - `src.prompt_utils.*` (build_retry_conditions, build_single_condition_skeleton_prompt, count_conditions, prepare_conditions_for_generation)
  - `src.scraper.PageScraper, scrape_with_enrichment`
  - `src.semantic_candidate_ranker.SemanticCandidateRanker`
  - `src.skeleton_parser.SkeletonParser`
  - `src.skeleton_validator.SkeletonValidator`
  - `src.spec_analyzer.TestCondition, infer_condition_intent`
  - `src.test_generator.TestGenerator`
  - `src.url_utils.build_common_path_candidates, extract_route_concepts`

## Data Models

### PipelineRunResult
```python
@dataclass
class PipelineRunResult:
    skeleton_code: str = ""
    final_code: str = ""
    pages_to_scrape: list[str] = field(default_factory=list)
    scraped_pages: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    scraped_errors: dict[str, str] = field(default_factory=dict)
    page_requirements: list[PageRequirement] = field(default_factory=list)
    journeys: list[TestJourney] = field(default_factory=list)
    scraped_page_records: list[ScrapedPage] = field(default_factory=list)
    generated_page_objects: list[GeneratedPageObject] = field(default_factory=list)
    unresolved_placeholders: list[str] = field(default_factory=list)
    pages_visited: list[str] = field(default_factory=list)
    pom_mode: bool = False
```

Captured metadata for the most recent pipeline run.

## Class: `TestOrchestrator`

### `__init__(test_generator, *, credential_profile=None, journey_steps=None, pom_mode=False, provider="", model="")`
- Accepts `TestGenerator` instance (no longer accepts raw LLM client or model/provider strings)
- Configures `SkeletonParser`, `PlaceholderOrchestrator`
- Stores credential profile and journey steps for authenticated scraping
- Supports POM mode flag
- Stores provider/model for vision enrichment
- Debug mode via `PIPELINE_DEBUG=1` environment variable
- Maintains pipeline diagnostics dict

### Backwards-Compatible Properties
- `resolver` â†’ delegates to `PlaceholderOrchestrator.resolver`
- `scraper` â†’ delegates to `PlaceholderOrchestrator.scraper`
- `page_object_builder` â†’ delegates to `PlaceholderOrchestrator.page_object_builder`
- `semantic_ranker` â†’ delegates to `PlaceholderOrchestrator.semantic_ranker`

These allow existing test code to mock directly on orchestrator instance without reaching into `_placeholder_orchestrator`.

### `run_pipeline(user_story, conditions, target_urls=None, consent_mode="auto-dismiss", reviewed_conditions=None) -> str`
- **Main entry point** â€” async pipeline execution
- Sets starting URL from target_urls
- Updates placeholder orchestrator with starting URL
- Returns final generated code as string

### Pipeline Phases

**Phase 1: Generate Skeleton**
- Parse conditions via `prepare_conditions_for_generation()`
- If reviewed_conditions provided and >1: generate combined skeleton via `_generate_combined_skeleton_for_conditions()`
- Otherwise: generate single skeleton via `test_generator.generate_skeleton()`
- Normalize placeholders via `parser.normalise_placeholder_actions()`
- Validate skeleton structure via `parser.validate_skeleton()`
- Validate no hallucinated selectors via `SkeletonValidator`
- **Phase 3.5:** Detect zero-placeholder skeletons and retry once with stricter prompt
- Parse placeholders and test journeys from skeleton
- Retry once if journey count mismatch

**Phase 2: Build Candidate URLs**
- Combine static seed URLs with page requirements and journeys
- URL guessing via common path patterns (uses `url_utils.build_common_path_candidates()`)

**Phase 3: Scrape Pages**
- Initial static scrape via `scraper.scrape_all()`
- **AI-027:** Apply vision enrichment to scraped elements when possible
- Re-extract elements from enriched ScrapeResult objects
- Fall back to raw_scraped_data if last_scrape_results is empty (mocked tests)

**Phase 4: Journey Execution (Phase B)**
- If journey_steps provided: execute authenticated journey via `execute_journey()`
- Captures pages during authenticated flow
- Records diagnostics

**Phase 5: Resolve Placeholders**
- Delegates to `PlaceholderOrchestrator` for placeholder resolution
- Combines static and journey-scraped data

**Phase 6: Post-Process and Save**
- Post-process code via `normalise_generated_code()`
- Save generated test file(s)

### `_build_generation_conditions(conditions, reviewed_conditions) -> list[TestCondition]`
- Prepares conditions for skeleton generation
- Uses reviewed_conditions if provided, otherwise parses from text

### `_generate_combined_skeleton_for_conditions(user_story, conditions, target_urls) -> str`
- Generates one skeleton fragment per condition
- Combines fragments into single module
- Strips duplicate imports and PAGES_NEEDED blocks

### `_generate_single_condition_fragment(...)`
- Generates skeleton for single condition
- Retries with correction prompt if fragment doesn't contain exactly one test function
- Validates no hallucinated selectors

### `_combine_condition_fragments(fragments) -> str`
- Strips imports and PAGES_NEEDED from each fragment
- Combines into single module with standard header

### `_build_candidate_urls(seed_urls, page_requirements, journeys, user_story, conditions) -> list[str]`
- Returns deduplicated seed URLs
- URL guessing via common path patterns using `url_utils`

### `_debug(message)`
- Conditional debug logging via `PIPELINE_DEBUG=1`

## Key Data Flow

```
User Story â†’ Conditions â†’ Skeleton (placeholders) â†’ DOM Scraped â†’ Resolved Code â†’ Saved Test
```

With optional:
- Journey execution for authenticated flows
- Vision enrichment for scraped elements
- POM mode for Page Object Model generation

## Dependencies

- `src.test_generator.TestGenerator` â€” LLM code generation
- `src.skeleton_parser.SkeletonParser` â€” skeleton parsing & normalization
- `src.skeleton_validator.SkeletonValidator` â€” validates no hallucinated selectors
- `src.placeholder_orchestrator.PlaceholderOrchestrator` â€” resolves {{TOKEN}} to real selectors
- `src.journey_scraper.JourneyScraper` â€” stateful DOM scraping
- `src.scraper.PageScraper, scrape_with_enrichment` â€” static scraping with vision enrichment
- `src.semantic_candidate_ranker.SemanticCandidateRanker` â€” semantic ranking of candidates
- `src.page_object_builder.PageObjectBuilder` â€” POM generation
- `src.prompt_utils.*` â€” prompt building
- `src.code_postprocessor.normalise_generated_code` â€” post-processing
- `src.url_utils.build_common_path_candidates, extract_route_concepts` â€” URL discovery
- `src.test_plan.review_and_fix_conditions` â€” condition parsing via LLM

## Depended On By

- `src/ui_pipeline.py` â€” Streamlit UI calls `run_pipeline()`
- `cli/pipeline_runner.py` â€” CLI calls `run_pipeline()`
- `tests/test_orchestrator*.py` â€” unit tests

## Notes

- Constructor signature changed: now accepts `TestGenerator` instance directly instead of raw LLM client parameters
- Supports both legacy single-condition and new multi-condition combined skeleton generation
- Vision enrichment (AI-027) runs after initial scrape, before placeholder resolution
- Journey execution (Phase B) enables authenticated scraping for login-required flows
- POM mode generates Page Object Models instead of direct Playwright code
- Debug output controlled by `PIPELINE_DEBUG=1` environment variable





# page_context_tracker.py

## Purpose
Page context tracking for journey-aware placeholder resolution. Tracks which page the resolver is operating on as it processes journey steps sequentially, using both URL inference from element hrefs and action-based heuristics to maintain accurate page state.

## Location
`src/page_context_tracker.py` (218 lines)

## Dependencies
- `__future__.annotations` (standard library)
- `logging` (standard library)
- `urllib.parse.urljoin, urlparse` (standard library)

## Module Constants
- `NAVIGATION_ACTIONS: set[str]` â€” Action words implying page transitions (login, sign in, submit, checkout, etc.)
- `TRANSITION_URL_PATTERNS: dict[str, tuple[str, ...]]` â€” Keyword-to-URL-pattern mappings for inferring page transitions

## Public API

### `PageContextTracker`

#### `__init__(self, scraped_urls: list[str]) -> None`
Initialize with list of all discovered/scraped URLs.

#### `current_url` (property)
The currently active page URL.

#### `set_initial_url(self, url: str | None) -> None`
Set the initial page URL before processing begins.

#### `track_url_transition(self, from_url: str, to_url: str) -> None`
Track a URL transition.

#### `infer_next_url(self, action_description: str, current_element: dict | None = None) -> str | None`
Infer the next page URL based on action description and current element context. Uses element hrefs when available, falls back to action-based URL pattern matching.

#### `get_history(self) -> list[str]`
Return the URL navigation history.

#### `on_page_navigate(self, url: str) -> None`
Record that a page navigation occurred (called after `page.goto()` or navigation click).

#### `on_action_complete(self) -> None`
Record that a non-navigation action completed on the current page.

## Design Notes
- Maintains URL history for diagnostics
- Infers URL transitions from action verbs and element hrefs
- Used by `placeholder_orchestrator.py` for page-context validation

## Related Files
- `src/placeholder_orchestrator.py` â€” consumes page context tracking
- `src/url_inference.py` â€” sibling URL inference module





---
purpose: >
  Generates Page Object Model (POM) classes from resolved journey data.
  Creates reusable locator methods for each page, producing clean, maintainable test code.
lines: ~300
created: "2026-05-30"
---

# `src/page_object_builder.py`

## High-Level Purpose

Converts resolved TestJourney data into Page Object Model classes. Each unique page URL gets a class with typed locator properties and action methods.

## Output Format

Generates Python classes like:
```python
class LoginPage:
    def __init__(self, page: Page):
        self.page = page

    @property
    def username(self) -> Locator:
        return self.page.locator("#username")

    @property
    def password(self) -> Locator:
        return self.page.locator("#password")

    def click_login(self):
        self.page.locator("#login-btn").click()
```

## Key Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `build_pom_code(journeys, page_urls)` | `str` | Generate full POM class code |
| `_extract_unique_locators(journey)` | `dict[str, str]` | Deduplicated locator map per page |
| `_generate_class_name(url)` | `str` | URL â†’ PascalCase class name |

## Dependencies

- `src.pipeline_models` â€” `TestJourney`, `TestStep`

## Depended On By

- `src/orchestrator.py` â€” writes POM code to generated test file





# `src/pipeline_artifact_manager.py` â€” Package Artifact Manager

**Module:** Persist and load generated test package metadata  
**Created:** 2026-06-02  
**Status:** Stable  
**Feature:** AI-026 â€” Persist Generated Tests (Step 1)

---

## Overview

Provides package-level metadata persistence for generated test suites. Complements `run_result_persistence.py` (which handles pytest run outcomes) by managing the higher-level package context: user stories, LLM provider/model, report paths, and evidence locations.

Each generated package in `generated_tests/` receives a `package_manifest.json` file describing the suite. The module discovers existing packages, loads their manifests, and reconstructs minimal metadata for legacy packages that predate this feature.

No Streamlit imports â€” fully unit-testable in isolation. Shared between CLI and Streamlit UI.

---

## Dependencies

| Import | Source | Purpose |
|--------|--------|---------|
| `from __future__ import annotations` | stdlib | Postponed evaluation of annotations |
| `json` | stdlib | JSON serialization/deserialization |
| `dataclasses` | stdlib | `PackageManifest` dataclass |
| `datetime` | stdlib | Timestamp handling |
| `pathlib.Path` | stdlib | File system operations |
| `typing` | stdlib | Type hints (`List`, `Dict`, `Any`) |

---

## Data Structures

### `PackageManifest`

Core dataclass representing a single generated test package. Maps directly to `package_manifest.json` on disk.

| Field | Type | Description |
|-------|------|-------------|
| `package_name` | `str` | Package directory name (e.g., `test_20260602_143022_login_flow`) |
| `created_at` | `str` | ISO-8601 timestamp of pipeline run |
| `source_story` | `str` | Original user story text |
| `starting_url` | `str` | Entry URL for the journey |
| `additional_urls` | `list[str]` | Extra URLs scraped during pipeline |
| `provider` | `str` | LLM provider name (`ollama`, `lm-studio`, `openai`) |
| `model` | `str` | LLM model identifier |
| `generated_test_files` | `list[str]` | Test file paths in package |
| `page_object_files` | `list[str]` | Page Object file paths |
| `scrape_manifest_path` | `str` | Relative path to `scrape_manifest.json` |
| `reports` | `list[dict[str, str]]` | Report records: `{"format", "path", "generated_at"}` |
| `evidence_paths` | `list[str]` | Screenshot/evidence file paths |
| `run_results_count` | `int` | Number of `run_results_*.json` files |
| `last_run_at` | `str` | ISO-8601 timestamp of last pytest run |

**Methods:**
- `to_dict() -> dict[str, Any]` â€” Serialize to plain dict (uses `dataclasses.asdict`)
- `from_dict(data: dict[str, Any]) -> PackageManifest` â€” Class method; constructs from dict with defaults for missing fields

---

## Public API

### Core Persistence

| Function | Signature | Description |
|----------|-----------|-------------|
| `save_package_manifest` | `(package_root: Path, manifest: PackageManifest) -> None` | Write `package_manifest.json` to `package_root`. Creates parent directories if needed. |
| `load_package_manifest` | `(package_root: Path, reconstruct: bool = False) -> PackageManifest` | Load manifest from `package_root/package_manifest.json`. If `reconstruct=True` and file is missing, build minimal manifest from disk scan. |
| `find_existing_packages` | `(base_dir: Path) -> list[PackageManifest]` | Discover packages in `base_dir`. Prefers canonical manifests, falls back to reconstruction for legacy packages. Returns list sorted by `created_at` descending. |

### Report & Evidence Helpers

| Function | Signature | Description |
|----------|-----------|-------------|
| `add_report_to_manifest` | `(manifest: PackageManifest, report_format: str, report_path: str) -> None` | Append a report record to `manifest.reports` with current timestamp. |
| `update_last_run_at` | `(manifest: PackageManifest, timestamp: str \| None = None) -> None` | Update `last_run_at` and increment `run_results_count`. Uses current time if `timestamp` is `None`. |

---

## File Format

Each generated package stores metadata as:

```
generated_tests/<package_name>/
â”œâ”€â”€ test_*.py
â”œâ”€â”€ conftest.py
â”œâ”€â”€ page_objects/
â”‚   â””â”€â”€ po_*.py
â”œâ”€â”€ scrape_manifest.json         # existing â€” written by pipeline_writer.py
â”œâ”€â”€ package_manifest.json        # THIS module â€” package metadata
â”œâ”€â”€ run_results_*.json           # existing â€” written by run_result_persistence.py
â””â”€â”€ evidence/
    â””â”€â”€ screenshot_*.png
```

**`package_manifest.json` example:**

```json
{
  "package_name": "test_20260602_143022_login_flow",
  "created_at": "2026-06-02T14:30:22+01:00",
  "source_story": "As a user, I want to login to the app...",
  "starting_url": "https://example.com/login",
  "additional_urls": ["https://example.com/dashboard"],
  "provider": "ollama",
  "model": "qwen3.5:35b",
  "generated_test_files": ["test_01_login.py", "test_02_dashboard.py"],
  "page_object_files": ["page_objects/po_login_page.py"],
  "scrape_manifest_path": "scrape_manifest.json",
  "reports": [
    {
      "format": "jira",
      "path": "reports/report_jira.md",
      "generated_at": "2026-06-02T14:35:00+01:00"
    }
  ],
  "evidence_paths": ["evidence/screenshot_01.png"],
  "run_results_count": 3,
  "last_run_at": "2026-06-02T15:00:00+01:00"
}
```

---

## Package Discovery Logic

`find_existing_packages()` uses a two-phase discovery:

1. **Canonical scan** â€” Look for directories containing `package_manifest.json`. Load via `load_package_manifest()`.
2. **Legacy reconstruction** â€” For directories without a manifest but with `test_*.py` files, reconstruct a minimal manifest from disk.

**Excluded directories:** `__pycache__`, `.git`, and any directory without test files or a manifest.

**Sort order:** `created_at` descending (newest first).

---

## Legacy Package Reconstruction

When `reconstruct=True` and no `package_manifest.json` exists, the module scans the package directory:

| Reconstructed Field | Source |
|---------------------|--------|
| `package_name` | Parent directory name |
| `created_at` | Oldest file modification timestamp in package |
| `source_story` | `"unknown"` |
| `starting_url` | `"unknown"` |
| `provider` | `""` |
| `model` | `""` |
| `generated_test_files` | Glob `test_*.py` at package root |
| `page_object_files` | Scan `pages/`, `page_objects/` subdirectories for `*.py` (excluding `__init__.py`) |
| `scrape_manifest_path` | `"scrape_manifest.json"` if file exists, else `""` |
| `reports` | `[]` |
| `evidence_paths` | `[]` |
| `run_results_count` | Count of `run_results_*.json` files |
| `last_run_at` | `""` |

---

## Integration Points

| Consumer | Integration |
|----------|-------------|
| `src/pipeline_writer.py` (Step 3) | Will call `save_package_manifest()` after writing test files |
| `cli/main.py` (Step 4) | Will call `find_existing_packages()` for "Load Existing" menu |
| `streamlit_app.py` via `ui_renderers.py` (Step 5) | Will call `find_existing_packages()` for "Load Saved Package" sidebar |
| `src/run_result_persistence.py` | Complementary module â€” handles run outcomes; `update_last_run_at()` bridges the two |

---

## Relationship with `run_result_persistence.py`

| Module | Handles |
|--------|---------|
| `run_result_persistence.py` | Pytest run outcomes (pass/fail/skip per test, retry tracking, flakiness) |
| `pipeline_artifact_manager.py` | Package metadata (user story, provider/model, report paths, evidence paths) |

Both modules write to the same package directory but manage different concerns. `update_last_run_at()` in this module provides a bridge, updating manifest metadata when a new pytest run completes.

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| JSON over database | Consistent with `scrape_manifest.json` and `run_results_*.json` â€” no new dependencies |
| `reconstruct` flag on `load_package_manifest` | Keeps backward compatibility with legacy packages without requiring migration |
| Manifest lives in package root | Co-located with test files, scrape manifest, and run results â€” single source of truth per package |
| `find_existing_packages` returns manifests, not paths | Consumers get structured data immediately, not raw paths to parse |
| Discovery prefers canonical over reconstructed | Ensures accurate metadata when available, falls back gracefully |

---

## Test Coverage

22 unit tests in `tests/test_pipeline_artifact_manager.py` covering:
- PackageManifest to_dict/from_dict round-trip
- from_dict with missing fields (defaults)
- save and load round-trip
- All fields persisted in JSON
- FileNotFoundError for missing manifest
- Package name populated from parent directory
- find_existing_packages with canonical manifests
- Legacy package discovery (no manifest, test files only)
- Non-package directories skipped
- Canonical manifest preferred over reconstruction
- Reconstruct from package root
- __init__.py excluded from page_object_files
- reconstruct=True with canonical present
- reconstruct=True with no manifest
- reconstruct=False with no manifest raises
- add_report_to_manifest
- update_last_run_at with default and explicit timestamp
- run_results_count in package root
- run_results_count in evidence subdirectory

---

## Notes

- Module is fully synchronous â€” no async I/O
- Thread-safe for single-writer scenarios (typical for test pipeline)
- No file locking â€” not designed for concurrent writers
- `MANIFEST_FILENAME` constant (`"package_manifest.json"`) is exported for consumers





---
purpose: >
  Data models for the skeleton-first test generation pipeline.
  Defines PlaceholderUse, PageRequirement, TestJourney, TestStep, and pipeline run state.
lines: ~200
created: "2026-05-30"
---

# `src/pipeline_models.py`

## High-Level Purpose

Core data structures that flow through the skeleton-first pipeline: skeleton generation â†’ placeholder extraction â†’ DOM scraping â†’ placeholder resolution â†’ code generation.

## Key Data Models

### `PlaceholderUse`
A single `{{ACTION:description}}` token found in skeleton code.
- `action`: str â€” CLICK, FILL, GOTO, URL, ASSERT
- `description`: str â€” human-readable element description
- `token`: str â€” full placeholder string e.g. `{{CLICK:Login button}}`
- `line_number`: int â€” line in generated code
- `raw_line`: str â€” full source line containing placeholder

### `PageRequirement`
A page the test needs to navigate to (from PAGES_NEEDED block).
- `keyword`: str â€” short keyword e.g. "cart", "checkout"
- `description`: str â€” parenthetical description from skeleton

### `TestJourney`
Structured representation of one generated test function.
- `test_name`: str â€” function name e.g. "test_01_login"
- `start_line`, `end_line`: int â€” code boundaries
- `page_object_names`: list[str] â€” page objects referenced
- `steps`: list[TestStep] â€” ordered steps with placeholders

### `TestStep`
A single executable line within a test function.
- `line_number`: int
- `raw_line`: str
- `placeholders`: list[PlaceholderUse]

## Dependencies

- None (pure data models)

## Depended On By

- `src/skeleton_parser.py` â€” populates models
- `src/placeholder_orchestrator.py` â€” consumes PlaceholderUse
- `src/orchestrator.py` â€” orchestrates pipeline using all models
- `src/page_object_builder.py` â€” uses TestJourney





# `src/pipeline_report_service.py`

## High-Level Purpose

Build report artifacts for generated pipeline test packages. Orchestrates coverage analysis and report generation in three formats (local MD, Jira MD, HTML), then saves them into the test package directory.

## Module Metadata

- **Lines:** 69
- **Imports:** `dataclasses.dataclass`, `pathlib.Path`, `src.coverage_utils`, `src.pytest_output_parser.RunResult`, `src.report_utils`

## Data Classes

### `PipelineReportBundle` (frozen)
Report content and saved paths for one pipeline run.
- `coverage_rows: list[dict]` â€” Per-criterion coverage rows
- `local_report: str` â€” Local markdown report
- `jira_report: str` â€” Jira markdown report
- `html_report: str` â€” HTML report
- `local_report_path: str` â€” Absolute path to saved local report (empty if no package_dir)
- `jira_report_path: str` â€” Absolute path to saved Jira report
- `html_report_path: str` â€” Absolute path to saved HTML report

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





# `src/pipeline_run_service.py`

## High-Level Purpose

Execute saved generated test packages via pytest and parse their output. Handles subprocess invocation, PYTHONPATH setup, timeout enforcement, and failed-test rerun.

## Module Metadata

- **Lines:** 71
- **Imports:** `os`, `subprocess`, `sys`, `dataclasses.dataclass`, `pathlib.Path`, `src.pytest_output_parser`, `src.run_utils`

## Data Classes

### `PipelineExecutionResult` (frozen)
Structured result for one generated-package pytest execution.
- `command: list[str]` â€” Full command executed
- `run_result: RunResult` â€” Parsed pytest results (pass/fail/skip per test)
- `display_output: str` â€” Formatted pytest output for display
- `return_code: int` â€” Process exit code

## Class: `PipelineRunService`

### `run_saved_test(saved_path, rerun_failed_only=False, previous_run=None, cwd=None) -> PipelineExecutionResult`
1. Extract failed nodeids from `previous_run` if `rerun_failed_only`
2. Build pytest command via `build_pytest_run_command`
3. Set PYTHONPATH to include project root + package directory
4. Run `subprocess.run` with hard timeout (default 300s, configurable via `PIPELINE_TEST_TIMEOUT`)
5. Parse stdout/stderr via `parse_pytest_output`
6. Return `PipelineExecutionResult`

## Dependencies

- `src.pytest_output_parser.parse_pytest_output`, `format_pytest_output_for_display`, `RunResult`
- `src.run_utils.build_pytest_run_command`, `get_failed_nodeids`

## Depended On By

`orchestrator.py`, `ui_pipeline.py`, `cli/pipeline_runner.py`





# `src/pipeline_writer.py`

## High-Level Purpose

Writes intelligent-pipeline outputs as a structured artifact package. Persists final test code, page objects, manifest, and coverage summary into a timestamped package directory under `generated_tests/`.

## Module Metadata

- **Lines:** ~270
- **Imports:** `json`, `re`, `datetime`, `pathlib.Path`, `typing.TYPE_CHECKING`, `src.code_validator`, `src.file_utils.slugify`, `src.pipeline_models.ManifestRecord`, `src.pipeline_models.PipelineArtifactSet`, `src.pipeline_artifact_manager.PackageManifest`, `src.pipeline_artifact_manager.save_package_manifest`

## Class: `PipelineArtifactWriter`

### `__init__(output_dir="generated_tests")`
Sets output directory for artifact packages.

### `write_run_artifacts(run_result, story_text, base_url="", provider_name="", model_name="", additional_urls=[]) -> PipelineArtifactSet`
Main entry point. Writes one structured artifact package:
1. Validates generated code syntax â€” raises `ValueError` if invalid
2. Creates package directory with timestamp + story slug
3. Creates `pages/` subdirectory with `__init__.py`
4. Writes page object modules to `pages/`
5. Builds packaged test code (rewrites inline page object classes to imports from `pages/`)
6. Writes test file with header comment
7. Writes `coverage_summary.json`
8. Writes `scrape_manifest.json` with full run metadata
9. **Writes `package_manifest.json`** via `save_package_manifest()` (AI-026)
10. Returns `PipelineArtifactSet` with paths and records

### `_build_package_dir(story_text) -> Path`
Creates `test_{timestamp}_{story_slug}` directory.

### `_build_test_file_content(test_code, base_url) -> str`
Wraps test code with docstring header (generation timestamp, base URL).

### `_build_packaged_test_code(test_code, generated_page_objects) -> str`
Rewrites test code to import page objects from `pages/` package instead of inline class definitions. Removes inline class blocks, inserts `from pages.<module> import <Class>` imports.

### `_remove_class_definition(code, class_name) -> str`
Regex-based removal of top-level class block.

### `_build_manifest_records(run_result) -> list[ManifestRecord]`
Builds manifest records from unresolved placeholders.

### `_build_manifest_dict(...) -> dict`
Builds full JSON-serializable manifest: generation timestamp, URLs, page records, journeys, page objects, unresolved records.

### `_build_coverage_summary_dict(run_result) -> dict`
Lightweight coverage summary: journey count, page count, page object count, unresolved placeholders, test names.

## Package Manifest Persistence (AI-026, added 2026-06-02)

After writing all artifact files, `write_run_artifacts()` calls `save_package_manifest()` to persist a `package_manifest.json` inside the package directory. This manifest captures:

- **Package metadata:** name, created timestamp, source story text
- **Pipeline context:** starting URL, additional URLs scraped, provider name, model name
- **Artifact inventory:** generated test files, page object files, scrape manifest path
- **Extensibility points:** reports list, evidence paths, run results count, last run timestamp

The manifest is loaded by `pipeline_artifact_manager.load_package_manifest()` to enable "Load Existing Generated Tests" in both CLI and Streamlit UI.

### New Parameters (AI-026)

| Parameter | Type | Default | Source |
|-----------|------|---------|--------|
| `provider_name` | `str` | `""` | `session.provider` (CLI) or UI provider selection |
| `model_name` | `str` | `""` | `session.model_name` (CLI) or UI model selection |
| `additional_urls` | `list[str]` | `[]` | `session.additional_urls` (CLI) or UI URL inputs |

## Dependencies

- `src.code_validator.validate_python_syntax`
- `src.file_utils.slugify`
- `src.pipeline_models.ManifestRecord`, `PipelineArtifactSet`
- `src.pipeline_artifact_manager.PackageManifest`, `save_package_manifest` (AI-026)
- `src.orchestrator.PipelineRunResult` (TYPE_CHECKING)

## Depended On By

`orchestrator.py`, `ui_pipeline.py`





# `src/placeholder_orchestrator.py`

## High-Level Purpose

Coordinates placeholder resolution, scraping, and page artifact generation. Transforms AI-generated test code with `{{ACTION:description}}` placeholders into complete, runnable tests by orchestrating scraping, placeholder resolution, and Page Object Model (POM) generation. Supports both flat `evidence_tracker` style and POM-mode output.

## Module Metadata

- **Lines:** 1828
- **Imports:** `re`, `logging`, `typing`, `urllib.parse`, `src.code_postprocessor`, `src.journey_models`, `src.journey_scraper`, `src.locator_builder`, `src.page_object_builder`, `src.pipeline_models`, `src.placeholder_resolver`, `src.scraper`, `src.semantic_candidate_ranker`, `src.semantic_matcher`, `src.stateful_scraper`, `src.url_inference`, `src.url_resolver`, `src.url_utils`

## Constants

- `DISPLAY_ROLES`: Frozenset of ARIA roles for ASSERT filtering (heading, paragraph, text, status, alert, listitem, cell, etc.)
- `ROLE_FALLBACK_GAP`: Maximum score gap before falling back to non-display elements (default: 3)

## Class: `PlaceholderOrchestrator`

### `__init__(starting_url=None, credential_profile=None, pom_mode=False, generator=None)`
- `starting_url`: Base URL for session-aware scraping
- `credential_profile`: Credentials for stateful scraping (authenticated flows)
- `pom_mode`: When True, generate tests using evidence-aware POM classes instead of flat `evidence_tracker` calls
- `generator`: LLM generator for semantic candidate ranking (B-020). When None, ASSERT resolution falls back to mechanical `toBeVisible`

### Properties
- `pom_mode(self) -> bool`: Whether POM-mode output is enabled

### Key Methods

#### Scraping & State Management
- `_ensure_scraped(url, scraped_data, scraped_errors=None)`: Scrape URL once and cache into scraped_data
- `_upgrade_stateful_pages(scraped_data) -> dict`: Replace stateless scrapes with session-backed scrapes for cart/checkout pages
- `_build_scraped_page_records(pages_to_scrape, scraped_data, scraped_errors=None, redirects=None) -> list[ScrapedPage]`: Build typed scraped-page records in journey order

#### Page Object Model (POM) Helpers
- `_build_page_object_artifacts(scraped_pages) -> list[GeneratedPageObject]`: Generate page objects from scraped pages
- `_build_pom_url_map(page_objects) -> dict[str, GeneratedPageObject]`: Map URLs to page objects
- `_build_pom_imports(page_objects) -> list[str]`: Generate import statements for POM mode
- `_build_pom_instantiation(page_objects, use_evidence_tracker=True) -> list[str]`: Generate POM instance instantiation lines
- `_get_pom_instance_name(url, page_objects) -> str | None`: Get POM instance variable name for URL
- `_get_pom_method_call(action, description, resolved_selector, pom_instance_name, fill_value="") -> str | None`: Generate POM method call (CLICK/FILL only; ASSERT/GOTO remain direct)

#### Placeholder Resolution
- `_replace_placeholders_sequentially(skeleton_code, journeys, page_requirements, seed_urls, scraped_data, scraped_errors=None) -> str`: Main resolution method â€” resolves placeholders step-by-step while tracking active page
  - Phase 1: Resolve placeholders inside test functions with journey context
  - Phase 2: Resolve remaining placeholders using fallback context
  - Phase 3: Apply line-level replacements (supports POM mode)
  - Phase 4: Insert consolidated pytest.skip() per journey
  - Phase 5: Remove old per-placeholder skip lines
  - Phase 6: Remove raw placeholder lines

#### Helper Methods
- `_extract_fill_text(line) -> str | None`: Extract second argument from evidence_tracker.fill() call
- `_all_placeholder_uses(code) -> list`: Parse all placeholder uses from code
- `_remove_old_placeholder_skips(lines, journeys) -> list[str]`: Filter out old per-placeholder skip lines
- `_remove_raw_placeholder_lines(lines) -> list[str]`: Remove remaining raw placeholder tokens

## Key Features

### Placeholder Resolution Strategy
1. **Journey-aware resolution**: Resolves placeholders in journey step order, tracking current URL
2. **Selector tracking**: Tracks last interactive selector for ASSERT exclusion (B-014)
3. **LLM semantic context**: Records resolved steps for LLM-assisted ASSERT resolution (B-020)
4. **Fallback resolution**: Unresolved placeholders use fallback page URL
5. **Consolidated skips**: Groups unresolved placeholders into single pytest.skip() at test top

### POM Mode
- Generates tests that import and use evidence-aware Page Object Model classes
- Assertions remain as direct `evidence_tracker` calls regardless of POM mode
- CLICK/FILL actions delegate to POM methods (e.g., `home_page.click("label")`)
- GOTO/URL remain as direct `page.goto()` calls

### Stateful Scraping
- **Cart/checkout pages**: Uses `CartSeedingScraper` for session-backed scraping
- **Stateful re-scrape**: Re-scrapes pages that returned 0 elements
- **Journey execution**: Supports authenticated flows via `execute_journey()`
- **URL matching**: Matches on both domain and path to avoid mixing data from different sites

### ASSERT Resolution (B-014, B-016, B-020)
- **B-014**: Excludes last interactive selector from ASSERT candidates
- **B-016**: Filters by display roles (heading, paragraph, text, etc.) to avoid matching interactive elements
- **B-020**: Uses LLM semantic candidate ranking for ASSERT resolution when generator provided

## Dependencies

- `src.code_postprocessor.replace_token_in_line` â€” token replacement logic
- `src.journey_scraper.CartSeedingScraper, execute_journey` â€” cart seeding and journey execution
- `src.locator_builder.build_robust_locator` â€” locator construction
- `src.page_object_builder.PageObjectBuilder` â€” POM generation
- `src.pipeline_models.*` â€” data models
- `src.placeholder_resolver.PlaceholderResolver` â€” core placeholder resolution
- `src.scraper.PageScraper` â€” static scraping
- `src.semantic_candidate_ranker.SemanticCandidateRanker` â€” LLM-assisted ranking
- `src.semantic_matcher.SemanticMatcher` â€” semantic matching
- `src.stateful_scraper.StatefulPageScraper` â€” stateful scraping
- `src.url_inference.infer_next_page_url` â€” URL inference
- `src.url_resolver.UrlResolver` â€” URL resolution
- `src.url_utils.*` â€” URL utilities

## Depended On By

- `src/orchestrator.py` â€” core pipeline orchestration
- `src/ui_pipeline.py` â€” Streamlit UI pipeline execution

## Notes

- Largest module in the project (1828 lines)
- Extracted from `TestOrchestrator` to separate concerns
- Supports both legacy flat mode and modern POM mode
- Handles complex stateful scraping scenarios (cart, checkout, authentication)
- B-014/B-016/B-020 improvements for ASSERT resolution quality
- Consolidated skip logic reduces noise in generated tests





# `src/placeholder_resolver.py`

## High-Level Purpose
Core placeholder resolution engine that matches `{{TOKEN:description}}` tokens against scraped DOM candidates using semantic matching, confidence scoring, and page-context validation.

## Module Metadata
- **Lines:** ~520
- **Imports:** `re`, `logging`, `dataclasses`, `typing`, `src.semantic_matcher`, `src.placeholder_scorers`, `src.page_context_tracker`

## Classes

### `PlaceholderContext` (dataclass)
Holds token, description, and resolved selector for a single placeholder.

### `PlaceholderResolver`
Main resolution class.
| Method | Description |
|--------|-------------|
| `resolve(code: str, pages: list[PageData]) -> list[PlaceholderContext]` | Finds all placeholder tokens and resolves each against page candidates |
| `resolve_single(token: str, candidates: list[Element]) -> ScoreResult` | Resolves one token against candidate elements |
| `_find_candidates(token: str, pages: list[PageData]) -> list[Element]` | Scrapes matching elements across pages |
| `_apply_page_context(token: str, candidates: list[Element]) -> list[Element]` | Filters candidates by page-context rules |

## Functions

### `resolve_placeholders(code: str, pages: list[PageData]) -> tuple[str, list[PlaceholderContext]]`
Top-level function â€” returns resolved code and context list.

### `extract_placeholders(code: str) -> list[PlaceholderContext]`
Regex-based extraction of `{{TOKEN:description}}` patterns.

## Key Design Decisions
- Token-only placeholders in skeleton phase (no real selectors)
- Page-context validation prevents cross-page mismatches
- Confidence threshold gate before accepting a match

## Dependencies
- `src.semantic_matcher`, `src.placeholder_scorers`, `src.page_context_tracker`





# `src/placeholder_scorers.py`

## High-Level Purpose
Composite scoring engine for placeholder resolution â€” provides individual testable scoring functions that evaluate candidate elements against placeholder descriptions.

## Module Metadata
- **Lines:** ~380
- **Imports:** `re`, `math`, `dataclasses`, `typing`, `src.semantic_matcher`

## Classes

### `ScoreResult` (dataclass)
Single scoring result: selector, score, breakdown dict, matched_attributes.

### `ScoreBreakdown` (dataclass)
Individual score components: attribute_score, text_score, specificity_bonus, etc.

## Functions

### `aggregate_score(candidates: list[Element], description: str) -> list[ScoreResult]`
Main entry â€” scores all candidates, returns sorted list.

### `score_attribute_match(element: Element, description: str) -> float`
Scores based on attribute overlap (id, name, class, data-*).

### `score_text_match(element: Element, description: str) -> float`
Semantic text-content matching using token overlap.

### `score_specificity(selector: str) -> float`
Locator specificity bonus: data-testid > id > name > css-class > xpath.

### `score_proximity(element: Element, context: str) -> float`
Proximity bonus for elements near related context elements.

## Key Design Decisions
- Composable scoring functions â€” each testable in isolation
- Weighted sum model with configurable weights
- Locator type hierarchy mirrors strict-mode reliability

## Dependencies
- `src.semantic_matcher`





# `src/prerequisite_injector.py`

## High-Level Purpose
Injects prerequisite setup code (fixtures, page navigation, auth state) into generated test functions before test body execution.

## Module Metadata
- **Lines:** ~180
- **Imports:** `re`, `dataclasses`, `typing`

## Classes

### `Prerequisite` (dataclass)
Single prerequisite block: type (goto, login, setup), code snippet, insert position.

## Functions

### `inject_prerequisites(code: str, prerequisites: list[Prerequisite]) -> str`
Injects prerequisite code blocks before test function body.

### `infer_prerequisites(story: UserStory) -> list[Prerequisite]`
Infers required prerequisites from user story (e.g., login before checkout).

### `_format_goto(url: str) -> str`
Generates `page.goto(url)` prerequisite line.

### `_format_login(credentials: dict) -> str`
Generates login prerequisite block.

## Key Design Decisions
- Prerequisite inference from story context, not manual config
- Insertion before first test assertion to preserve setup order
- No modification of test function signature

## Dependencies
- None from `src/` â€” stdlib only





# `src/prompt_utils.py`

## High-Level Purpose
Utilities for building, formatting, and managing LLM prompts used in skeleton generation and placeholder resolution phases.

## Module Metadata
- **Lines:** ~250
- **Imports:** `dataclasses`, `typing`, `src.pipeline_models`

## Functions

### `build_skeleton_prompt(story: UserStory, page_count: int) -> str`
Builds Phase 1 prompt for skeleton generation with placeholder tokens.

### `build_resolution_prompt(code: str, candidates: list[Element]) -> str`
Builds Phase 2 prompt for LLM-assisted resolution (fallback mode).

### `format_criteria_list(criteria: list[str]) -> str`
Formats acceptance criteria with numbered list and total count.

### `inject_placeholder_rules(prompt: str) -> str`
Appends allowed placeholder types and usage rules to a prompt.

## Key Design Decisions
- Prompt templates separated from orchestration logic
- Explicit "DO NOT skip" rules baked into templates
- Placeholder syntax enforced at prompt level

## Dependencies
- `src.pipeline_models`





# `src/pytest_output_parser.py`

## High-Level Purpose
Parses raw pytest output to extract test results, failures, durations, and error classifications for reporting.

## Module Metadata
- **Lines:** ~200
- **Imports:** `re`, `dataclasses`, `typing`

## Classes

### `TestResult` (dataclass)
Parsed result: test_id, status (PASSED/FAILED/SKIPPED), duration, error_message, error_type.

### `SuiteSummary` (dataclass)
Aggregate: total, passed, failed, skipped, errors list.

## Functions

### `parse_pytest_output(output: str) -> SuiteSummary`
Main parser â€” processes full pytest text output into structured results.

### `extract_failure_details(output: str) -> list[dict]`
Extracts per-test failure details: traceback, error type, error message.

### `parse_duration(line: str) -> float`
Extracts test duration from pytest result line (e.g., `0.42s`).

## Key Design Decisions
- Regex-based parsing â€” no dependency on pytest internal APIs
- Handles both verbose and quiet pytest output formats
- Error classification by type (TimeoutError, NoTimeout, etc.)

## Dependencies
- None from `src/` â€” stdlib only





# Source Module Documentation

This directory contains per-module documentation for all 66 source files in `src/`.

## How to Read These Docs

Each `<module_name>.py.md` file covers:
- **Purpose** â€” what the module does in one sentence
- **Dependencies** â€” other modules it imports
- **Module Constants** â€” top-level enums, Literal types, defaults
- **Public API** â€” classes, methods, and standalone functions with signatures
- **Design Notes** â€” patterns, gotchas, and architectural decisions
- **Related Files** â€” modules that depend on or are depended upon

## Module Index (66 files)

### Pipeline Core (5)
| Doc | Module |
|-----|--------|
| [orchestrator.py.md](./orchestrator.py.md) | Core pipeline orchestration â€” skeleton-first test generation |
| [pipeline_models.py.md](./pipeline_models.py.md) | Data models for pipeline (JourneyPage, Skeleton, etc.) |
| [pipeline_writer.py.md](./pipeline_writer.py.md) | Writes generated test files to disk |
| [pipeline_run_service.py.md](./pipeline_run_service.py.md) | Pipeline execution service |
| [pipeline_report_service.py.md](./pipeline_report_service.py.md) | Pipeline report generation service |

### Scraper Chain (6)
| Doc | Module |
|-----|--------|
| [scraper.py.md](./scraper.py.md) | DOM metadata scraper â€” extracts locatable elements |
| [journey_scraper.py.md](./journey_scraper.py.md) | Journey-aware stateful scraping across page navigations |
| [stateful_scraper.py.md](./stateful_scraper.py.md) | State-aware scraping fallback for placeholder orchestrator |
| [state_tracker.py.md](./state_tracker.py.md) | DOM state tracking across page transitions |
| [form_detector.py.md](./form_detector.py.md) | Form detection and selector constants |
| [page_context_tracker.py.md](./page_context_tracker.py.md) | Page-level context tracking for scraper |

### Placeholder System (9)
| Doc | Module |
|-----|--------|
| [placeholder_orchestrator.py.md](./placeholder_orchestrator.py.md) | Per-page placeholder resolution orchestration |
| [placeholder_resolver.py.md](./placeholder_resolver.py.md) | Resolves LLM-generated placeholders to real locators |
| [placeholder_scorers.py.md](./placeholder_scorers.py.md) | Composite scoring engine for placeholder candidates |
| [intent_matcher.py.md](./intent_matcher.py.md) | Intent classification for placeholders |
| [semantic_candidate_ranker.py.md](./semantic_candidate_ranker.py.md) | Context candidate prioritization |
| [semantic_matcher.py.md](./semantic_matcher.py.md) | Token-based semantic similarity |
| [url_inference.py.md](./url_inference.py.md) | URL inference from page context |
| [url_resolver.py.md](./url_resolver.py.md) | Resolves URLs for navigation placeholders |
| [url_utils.py.md](./url_utils.py.md) | URL normalization and comparison utilities |

### Code Pipeline (7)
| Doc | Module |
|-----|--------|
| [test_generator.py.md](./test_generator.py.md) | Working test generation pipeline (PROTECTED) |
| [skeleton_parser.py.md](./skeleton_parser.py.md) | Parses basic skeleton structures from LLM output |
| [code_normalizer.py.md](./code_normalizer.py.md) | Code normalization transforms |
| [code_postprocessor.py.md](./code_postprocessor.py.md) | Post-processing for generated code + export stripping |
| [code_validator.py.md](./code_validator.py.md) | Validates generated test code structure |
| [export_service.py.md](./export_service.py.md) | Exports clean test suites stripping EvidenceTracker |
| [page_object_builder.py.md](./page_object_builder.py.md) | Page Object Model generation |

### Evidence / Reports (9)
| Doc | Module |
|-----|--------|
| [evidence_tracker.py.md](./evidence_tracker.py.md) | Captures runtime diagnostics and evidence |
| [evidence_loader.py.md](./evidence_loader.py.md) | Loads evidence JSON from test packages |
| [evidence_serializer.py.md](./evidence_serializer.py.md) | Evidence JSON serialization |
| [evidence_report.py.md](./evidence_report.py.md) | Evidence report generation |
| [failure_classifier.py.md](./failure_classifier.py.md) | Classifies test failure types |
| [failure_reporter.py.md](./failure_reporter.py.md) | Generates failure diagnostic reports |
| [report_builder.py.md](./report_builder.py.md) | Builds report dictionaries merging evidence data |
| [report_formatters.py.md](./report_formatters.py.md) | Renders reports (local MD, Jira MD, HTML) |
| [report_utils.py.md](./report_utils.py.md) | Shared report formatting utilities |

### Locator System (4)
| Doc | Module |
|-----|--------|
| [locator_builder.py.md](./locator_builder.py.md) | Builds Playwright locator strings |
| [locator_fallback.py.md](./locator_fallback.py.md) | Runtime locator fallback chain |
| [locator_repair.py.md](./locator_repair.py.md) | Repairs broken locators after test failures |
| [locator_scorer.py.md](./locator_scorer.py.md) | Scores locators by reliability ranking |

### LLM (4)
| Doc | Module |
|-----|--------|
| [llm_client.py.md](./llm_client.py.md) | Multi-provider LLM client (Ollama, LM Studio, OpenAI) |
| [llm_errors.py.md](./llm_errors.py.md) | LLM-specific error types and handling |
| [llm_reasoning_filter.py.md](./llm_reasoning_filter.py.md) | LLM reasoning text detection and stripping |
| [prompt_utils.py.md](./prompt_utils.py.md) | LLM prompt construction utilities |

### UI (2)
| Doc | Module |
|-----|--------|
| [ui_pipeline.py.md](./ui_pipeline.py.md) | Pipeline execution for Streamlit UI |
| [ui_renderers.py.md](./ui_renderers.py.md) | Streamlit rendering helpers |

### Test Planning (3)
| Doc | Module |
|-----|--------|
| [test_plan.py.md](./test_plan.py.md) | Test plan data structures and generation |
| [spec_analyzer.py.md](./spec_analyzer.py.md) | Derives test conditions from feature specifications |
| [user_story_parser.py.md](./user_story_parser.py.md) | Parses Gherkin-style user stories |

### Utilities (18)
| Doc | Module |
|-----|--------|
| [__init__.py.md](./__init__.py.md) | Package initialization |
| [accessibility_enricher.py.md](./accessibility_enricher.py.md) | Adds ARIA attributes to scraped elements |
| [analyzer.py.md](./analyzer.py.md) | General-purpose code and test analysis |
| [browser_utils.py.md](./browser_utils.py.md) | Browser interaction helpers |
| [config.py.md](./config.py.md) | Configuration loading and defaults |
| [coverage_utils.py.md](./coverage_utils.py.md) | Test coverage analysis utilities |
| [element_enricher.py.md](./element_enricher.py.md) | Enriches scraped elements with additional metadata |
| [failure_classifier.py.md](./failure_classifier.py.md) | Test failure classification |
| [file_utils.py.md](./file_utils.py.md) | File I/O helpers (save, rename, normalize) |
| [form_login_utils.py.md](./form_login_utils.py.md) | Form login detection and handling |
| [gantt_utils.py.md](./gantt_utils.py.md) | Gantt chart generation for test execution |
| [heatmap_utils.py.md](./heatmap_utils.py.md) | Heatmap visualization for test coverage |
| [hover_click_utils.py.md](./hover_click_utils.py.md) | Hover-and-click interaction utilities |
| [journey_auth_detector.py.md](./journey_auth_detector.py.md) | Detects authentication pages in journeys |
| [prerequisite_injector.py.md](./prerequisite_injector.py.md) | Injects prerequisite setup into test code |
| [pytest_output_parser.py.md](./pytest_output_parser.py.md) | Parses pytest CLI output for results |
| [run_utils.py.md](./run_utils.py.md) | Test execution runtime utilities |
| [screenshot_capture.py.md](./screenshot_capture.py.md) | Screenshot capture utilities |
| [skeleton_validator.py.md](./skeleton_validator.py.md) | Validates skeleton structure before resolution |
| [vision_enricher.py.md](./vision_enricher.py.md) | Vision-based element enrichment |

### LLM Providers
| Doc | Module |
|-----|--------|
| [llm_providers/__init__.py.md](./llm_providers/__init__.py.md) | Provider package initialization |

## Generation Info
- **Generated:** 2026-05-30
- **Updated:** 2026-06-08 â€” added `export_service.py`
- **Total modules:** 67
- **Status:** Complete





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
Main builder â€” merges pytest results with evidence JSON sidecar data.

### `merge_evidence(test_id: str, evidence: dict) -> TestReportEntry`
Merges runtime evidence (failure_note, diagnosis, screenshots) into test entry.

### `classify_failures(report: ReportData) -> dict[str, int]`
Groups failures by error type and returns classification counts.

## Key Design Decisions
- Evidence loading deferred until report build time (lazy)
- Report data is format-agnostic â€” formatters handle rendering
- Failure classification uses error type hierarchy

## Dependencies
- `src.pytest_output_parser`, `src.evidence_loader`, `src.failure_classifier`





# report_formatters.py

## Purpose
Renders test execution reports in three output formats: local Markdown, Jira Markdown, and base64-embedded HTML. Includes failure diagnostics section with page URL, failure note, suggested alternatives, and screenshot paths.

## Location
`src/report_formatters.py`

## Dependencies
- `src.report_builder` â€” consumes report dicts built by pipeline_report_service
- `src.evidence_loader` â€” loads evidence JSON for diagnostics enrichment

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
- `src/report_builder.py` â€” produces report dicts consumed by formatters
- `src/evidence_loader.py` â€” provides evidence data for diagnostics
- `src/pipeline_report_service.py` â€” orchestrates report generation pipeline





# report_utils.py

## Purpose
Shared utility functions for report generation â€” path resolution, file I/O, and evidence data merging used across report builder and formatters.

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
Return a human-readable status label ("âœ… PASSED" / "âŒ FAILED").

## Design Notes
- Pure utility functions â€” no side effects except `ensure_screenshot_dir`
- Used by both `report_builder.py` and `report_formatters.py`
- Evidence merging preserves existing report fields while adding diagnostics keys

## Related Files
- `src/report_builder.py` â€” uses utilities for evidence merging
- `src/report_formatters.py` â€” uses utilities for status formatting
- `src/evidence_loader.py` â€” sibling evidence module





# `src/run_result_persistence.py` â€” Run Result Persistence

**Module:** Persist run results to disk for historical comparison and flaky-test tracking  
**Created:** 2026-06-02  
**Status:** Stable

---

## Overview

Provides thin JSON persistence for `RunResult` objects so that consecutive pytest runs can be compared over time. Stored artifacts live under `evidence/run_results/` as one file per run, named by ISO-8601 timestamp.

No Streamlit imports â€” fully unit-testable in isolation.

---

## Dependencies

| Import | Source | Purpose |
|--------|--------|---------|
| `json` | stdlib | Serialization |
| `dataclasses` | stdlib | Data structure definitions |
| `datetime` | stdlib | Timestamp generation |
| `pathlib.Path` | stdlib | File system operations |
| `src.pytest_output_parser.RunResult` | `src/pytest_output_parser.py` | Source data for persistence |

---

## Data Structures

### `PersistedTestResult`

Serializable mirror of `TestResult` from the parser module.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Test function name (e.g., `test_01_login_page_displayed`) |
| `status` | `str` | `"passed"`, `"failed"`, `"error"`, `"skipped"` |
| `duration` | `float` | Execution time in seconds |
| `error_message` | `str` | Error text (empty string if passed) |
| `file_path` | `str` | Relative path to test file |

### `PersistedRunResult`

Serializable mirror of `RunResult` with persistence metadata.

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | `str` | ISO-8601 timestamp, unique per file |
| `test_package` | `str` | Path to the test package that was run |
| `results` | `list[PersistedTestResult]` | Per-test results |
| `total` | `int` | Total test count |
| `passed` | `int` | Passed count |
| `failed` | `int` | Failed count |
| `skipped` | `int` | Skipped count |
| `errors` | `int` | Error count |
| `duration` | `float` | Total run duration in seconds |
| `raw_output` | `str` | Preserved pytest stdout for reference |
| `flaky_tests` | `list[str]` | Computed on load (not stored on disk) |

### `RunHistory`

Aggregated statistics across multiple persisted runs.

| Field | Type | Description |
|-------|------|-------------|
| `total_runs` | `int` | Number of runs in history |
| `total_passed` | `int` | Cumulative passed count |
| `total_failed` | `int` | Cumulative failed count |
| `total_skipped` | `int` | Cumulative skipped count |
| `total_errors` | `int` | Cumulative error count |
| `test_flakiness` | `dict[str, dict[str, int]]` | Maps test name â†’ `{"passed": N, "failed": N, "skipped": N, "error": N}` |

### `RunComparison`

Side-by-side comparison of two runs.

| Field | Type | Description |
|-------|------|-------------|
| `older` | `PersistedRunResult` | Earlier run |
| `newer` | `PersistedRunResult` | Later run |
| `improved` | `list[str]` | Tests that went from fail/error to pass |
| `regressed` | `list[str]` | Tests that went from pass to fail/error |
| `new_failures` | `list[str]` | Tests not in older run but failing in newer |

---

## Public API

### Persistence Operations

| Function | Signature | Description |
|----------|-----------|-------------|
| `persist_run_result` | `(run_result: RunResult, test_package: str = "", directory: Path \| None = None) -> Path` | Write a single `RunResult` to disk as timestamped JSON. Returns absolute path to written file. |
| `load_run_result` | `(filepath: Path) -> PersistedRunResult` | Load a single persisted run result from disk. |
| `list_run_results` | `(directory: Path \| None = None) -> list[Path]` | Return sorted list of persisted run-result file paths (oldest first). |
| `load_all_run_results` | `(directory: Path \| None = None) -> list[PersistedRunResult]` | Load every persisted run result (oldest first). |

### History & Flakiness Analysis

| Function | Signature | Description |
|----------|-----------|-------------|
| `compute_run_history` | `(runs: list[PersistedRunResult] \| None = None, directory: Path \| None = None) -> RunHistory` | Aggregate statistics across all persisted runs. When `runs` is `None`, loads all persisted runs from `directory`. |
| `get_flaky_tests` | `(runs: list[PersistedRunResult] \| None = None, directory: Path \| None = None, min_runs: int = 2) -> list[tuple[str, dict[str, int]]]` | Return tests with inconsistent results across runs. A test is flaky when it has both passes and failures across at least `min_runs` observations. Sorted by flakiness ratio (descending). |

### Run Comparison

| Function | Signature | Description |
|----------|-----------|-------------|
| `compare_runs` | `(older: PersistedRunResult, newer: PersistedRunResult) -> RunComparison` | Compare two runs and classify per-test changes (improved, regressed, new_failures). |
| `compare_latest_runs` | `(n: int = 2, directory: Path \| None = None) -> RunComparison \| None` | Compare the latest `n` runs. Returns `None` when fewer than 2 runs available. |

### Housekeeping

| Function | Signature | Description |
|----------|-----------|-------------|
| `delete_old_runs` | `(keep: int = 50, directory: Path \| None = None) -> int` | Delete oldest run-result files, keeping the most recent `keep` runs. Returns number of files deleted. |
| `to_dict` | `(run: PersistedRunResult) -> dict[str, Any]` | Convert to plain dict for API/serialization. |
| `from_dict` | `(data: dict[str, Any]) -> PersistedRunResult` | Construct from plain dict. |

---

## File Format

Each persisted run is stored as a JSON file in `evidence/run_results/`:

```
evidence/
  â””â”€â”€ run_results/
      â”œâ”€â”€ run_2026-06-02T18-30-00-000000.json
      â”œâ”€â”€ run_2026-06-02T19-15-30-000000.json
      â””â”€â”€ ...
```

Filename format: `run_{iso_timestamp}.json` where colons are replaced with hyphens for Windows compatibility.

JSON structure:
```json
{
  "run_id": "2026-06-02T18:30:00.000000",
  "test_package": "generated_tests/test_tc_001_login",
  "results": [
    {
      "name": "test_01_login_page_displayed",
      "status": "passed",
      "duration": 1.23,
      "error_message": "",
      "file_path": "generated_tests/test_tc_001_login/test_01_login_page_displayed.py"
    }
  ],
  "total": 5,
  "passed": 4,
  "failed": 1,
  "skipped": 0,
  "errors": 0,
  "duration": 8.45,
  "raw_output": "...",
  "flaky_tests": []
}
```

---

## Integration Points

| Consumer | Integration |
|----------|-------------|
| `src/pipeline_run_service.py` | `PipelineExecutionResult.persist` parameter triggers `persist_run_result()` after test execution |
| Future UI/CLI | `load_all_run_results()` + `compute_run_history()` for trending dashboards |
| Future CI | `compare_latest_runs()` for regression detection in CI pipelines |

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| JSON format over SQLite | Simple, human-readable, git-tracked, no migration needed |
| Timestamp in filename | Natural sort order matches chronological order, no index needed |
| Default retention of 50 runs | Balances history depth with disk usage |
| Flakiness = both pass AND fail across runs | Catches intermittent failures, not consistently broken tests |
| `min_runs=2` threshold | Requires at least 2 observations before flagging flakiness |

---

## Test Coverage

32 unit tests in `tests/test_run_result_persistence.py` covering:
- Persist/load round-trip
- Empty runs
- Sorted listing
- History computation
- Flakiness detection with min_runs threshold
- Run comparison (improve, regress, new failures)
- Latest run comparison edge cases
- Retention deletion
- Serialization round-trip

---

## Notes

- Module is fully synchronous â€” no async I/O
- Thread-safe for single-writer scenarios (typical for test pipeline)
- No locking for concurrent writers â€” not designed for parallel persistence
- `flaky_tests` field on `PersistedRunResult` is computed on load, not persisted





# run_utils.py

## Purpose
Pytest command utilities â€” builds pytest CLI commands, parses raw pytest output to extract failed test node IDs, and defines the `RunTestRecord` protocol for test execution results.

## Location
`src/run_utils.py`

## Dependencies
- `re` (standard library)
- `typing.Protocol, runtime_checkable` (standard library)

## Public API

### `RunTestRecord` (Protocol)
Protocol defining the shape of a test execution result record. Fields: `test_path`, `passed`, `duration`, `error_message`.

### `get_failed_nodeids(output: str) -> list[str]`
Parse pytest terminal output and extract failed test node IDs (e.g., `test_file.py::test_function`).

### `extract_failed_nodeids_from_raw_output(output: str) -> list[str]`
Legacy name for `get_failed_nodeids`. Parses raw pytest output using regex to find failed test identifiers.

### `build_pytest_run_command(test_paths: list[str], failed_ids: list[str] | None = None, verbose: bool = False, parallel: bool = True) -> list[str]`
Build a pytest CLI command list suitable for `subprocess.run()`. Supports parallel execution (`-n auto`), verbose mode, and test selection via failed node IDs.

## Design Notes
- All functions are pure â€” no side effects
- Regex-based parsing for pytest output is fragile but sufficient for controlled CI environments
- `build_pytest_run_command` returns a list for safe subprocess invocation (no shell injection)
- Used by pipeline runner and CLI to execute generated tests

## Related Files
- `src/orchestrator.py` â€” uses run utilities for test execution
- `cli/pipeline_runner.py` â€” builds pytest commands for CLI runs
- `src/pytest_output_parser.py` â€” sibling output parsing module





# `src/scraper.py`

## High-Level Purpose

Playwright-based DOM scraper that discovers real element selectors from live web pages. Uses a headless Chromium browser to render JavaScript, extract interactive elements, capture accessibility trees via CDP, and record screenshots with bounding boxes. Runs scraping in a subprocess to avoid asyncio event loop conflicts on Windows.

## Module Metadata

- **Lines:** 657
- **Key imports:** `base64`, `json`, `os`, `subprocess`, `sys`, `dataclasses.dataclass`, `pathlib.Path`, `typing`, `urllib.parse`, `playwright.sync_api`
- **Project imports:** `src.accessibility_enricher.AccessibilityEnricher`, `src.element_enricher.ElementEnricher`, `src.vision_enricher.VisionEnricher`

## Dataclass: `ScrapeResult`

Fields: `url`, `elements`, `title`, `html_snippet`, `error`, `final_url`, `a11y_snapshot`, `screenshot_bytes`, `element_boxes`

## Class: `PageScraper`

### `__init__(timeout_ms=30000)`
- Configures timeout, stores last scrape results

### `scrape_url(url) -> tuple[list[dict], str|None, str]`
- **Public async API** â€” delegates to `_scrape_url_via_subprocess()`
- Returns: (elements_list, error_message, final_url)

### `_scrape_url_via_subprocess(url)` 
- Runs sync Playwright scrape in a clean subprocess to avoid Windows nested event loop issues
- Parses JSON output from subprocess, enriches elements with accessibility data and bounding boxes

### `_scrape_url_sync(url)` 
- Core sync scraping logic executed in subprocess
- Launches headless Chromium, navigates with `networkidle` wait, extracts elements, captures CDP accessibility tree

### `_scrape_url_sync_result(url) -> ScrapeResult`
- Full scrape result including screenshot bytes and element bounding boxes

### `_extract_elements_from_html(html, base_url) -> list[dict]`
- Uses BeautifulSoup to parse HTML after removing consent overlays
- Extracts interactive elements: `button`, `a`, `input`, `select`, `textarea`
- Builds CSS selectors with priority: id > data-testid > data-test > data-qa > data-product-id > href > name > classes > tag

### `_build_selector(tag, href) -> str`
- Builds best CSS selector for a live Playwright tag using same priority as above

### `_capture_element_visibility(page, elements) -> list[dict]`
- Adds `is_visible` boolean to each element using Playwright `is_visible()` at runtime

### `_remove_consent_overlays(html) -> str`
- Strips cookie/consent banner elements (IAB GVL, cc-banner, etc.) before extraction to prevent element pollution

### `scrape_all(urls) -> dict[str, tuple[...]]`
- Scrapes multiple URLs sequentially

## Standalone Functions

### `capture_page_screenshot(page, url, full_page=True) -> tuple[bytes, list[dict]]`
- Captures page screenshot plus bounding boxes for all interactive elements

### `scrape_with_enrichment(scrape_results, provider, model, timeout) -> list[ScrapeResult]`
- Applies vision enrichment from VisionEnricher to results that include screenshot data

### `_subprocess_entrypoint()`
- Entry point when module is run as `python scraper.py --scrape`
- Reads JSON payload from stdin, runs scrape, writes JSON result to stdout

## Key Design Decisions

- **Subprocess isolation:** Playwright runs in a separate process to avoid asyncio conflicts with Streamlit/Jupyter event loops
- **Consent overlay removal:** Cookie banners are stripped before element extraction to prevent hundreds of irrelevant elements
- **CDP accessibility tree:** Uses Chrome DevTools Protocol `Accessibility.getFullAXTree` since `page.accessibility.snapshot()` is unavailable in Python Playwright
- **Vision enrichment:** Screenshots and element boxes enable vision-capable LLMs to enrich element metadata

## Dependencies

- `playwright.sync_api` â€” browser automation
- `bs4.BeautifulSoup` â€” HTML parsing
- `src.accessibility_enricher` â€” merges CDP accessibility data into elements
- `src.element_enricher` â€” adds visual/contextual metadata
- `src.vision_enricher` â€” optional vision-based enrichment

## Depended On By

- `src/journey_scraper.py` â€” uses PageScraper for initial page scrapes
- `src/placeholder_orchestrator.py` â€” fallback scraper
- `src/orchestrator.py` â€” calls via JourneyScraper





# screenshot_capture.py

## Purpose
Screenshot capture utilities extracted from evidence_tracker. Provides Playwright page screenshot functions with consistent naming conventions and file path management for test evidence.

## Location
`src/screenshot_capture.py`

## Dependencies
- `playwright.sync_api.Page` (external)
- `pathlib.Path` (standard library)
- `logging` (standard library)

## Public API

### `capture_screenshot(page: Page, test_name: str, suffix: str, output_dir: str = "screenshots") -> Path | None`
Take a full-page screenshot and save it to the output directory. Returns the `Path` to the saved file, or `None` on failure. Creates the output directory if it does not exist.

### `normalize_screenshot_path(path: str | Path) -> str`
Normalize a screenshot path for embedding in reports (converts to relative path where possible).

### `embed_screenshot_as_base64(path: str | Path) -> str | None`
Read a screenshot file and return it as a base64-encoded data URI suitable for embedding in HTML reports. Returns `None` if the file does not exist or cannot be read.

## Design Notes
- Extracted from `evidence_tracker.py` to separate screenshot I/O from evidence tracking logic
- Uses Playwright's `page.screenshot(full_page=True)` for consistent captures
- Files named as `{test_name}_{suffix}.png` for predictable lookups
- Base64 embedding enables self-contained HTML reports

## Related Files
- `src/evidence_tracker.py` â€” parent module from which this was extracted
- `src/report_formatters.py` â€” consumes base64 screenshots for HTML reports
- `src/failure_reporter.py` â€” captures screenshots on test failures





# semantic_candidate_ranker.py

## Purpose
Context candidate prioritization engine for placeholder resolution. Scores and ranks DOM element candidates based on their relevance to a placeholder's semantic description, using token overlap, attribute quality, and positional heuristics.

## Location
`src/semantic_candidate_ranker.py`

## Dependencies
- `src.semantic_matcher` â€” token-based semantic similarity scoring
- `dataclasses` (standard library)
- `logging` (standard library)

## Module Constants
- `TEXT_MATCH_WEIGHT: float` â€” Weight for text-content overlap score
- `ATTRIBUTE_MATCH_WEIGHT: float` â€” Weight for attribute-based similarity
- `POSITION_PENALTY: float` â€” Penalty for elements deep in the DOM tree

## Public API

### `rank_candidates(action_description: str, candidates: list[dict[str, Any]], page_url: str | None = None) -> list[dict[str, Any]]`
Score and rank a list of element candidates by their suitability for resolving a placeholder. Returns candidates sorted by descending score, each enriched with a `_rank_score` key.

### `compute_candidate_score(description_tokens: set[str], element: dict[str, Any]) -> float`
Compute a raw relevance score for a single candidate element based on token overlap with element attributes (text, attributes, tag name).

### `apply_positional_bonus(score: float, depth: int) -> float`
Apply a small bonus for shallow DOM elements (preferred for stability).

## Design Notes
- Token-based approach: splits action description into words, counts overlap with element text and attribute values
- Page-aware: candidates from the expected page get a small bonus
- Positional bonus: shallow elements score higher (more stable across page changes)
- Used by `placeholder_orchestrator.py` during candidate selection phase

## Related Files
- `src/semantic_matcher.py` â€” provides low-level token similarity used by ranker
- `src/placeholder_orchestrator.py` â€” consumer of ranked candidates
- `src/placeholder_resolver.py` â€” sibling resolution module





# semantic_matcher.py

## Purpose
Token-based semantic similarity scoring extracted from placeholder_resolver. Computes overlap between a description (e.g., placeholder action text) and an element's textual representation using normalized token sets.

## Location
`src/semantic_matcher.py`

## Dependencies
- `re` (standard library)
- `string` (standard library)

## Module Constants
- `STOP_WORDS: set[str]` â€” Common English stop words removed before token comparison
- `MIN_TOKEN_LENGTH: int` â€” Minimum token length (2) to ignore single characters

## Public API

### `normalize_text(text: str) -> str`
Lowercase, strip whitespace, and remove punctuation from input text.

### `tokenize(text: str) -> set[str]`
Split text into a set of meaningful tokens, filtering out stop words and short tokens.

### `semantic_similarity(description: str, element_text: str) -> float`
Compute Jaccard-like similarity between description tokens and element text tokens. Returns a float in [0.0, 1.0] where 1.0 means all description tokens appear in element text.

### `tokens_match(description: str, target: str, threshold: float = 0.3) -> bool`
Convenience wrapper that returns `True` when `semantic_similarity` meets or exceeds the threshold.

## Design Notes
- Pure functions â€” no side effects, fully testable
- Token-based approach avoids expensive NLP dependencies
- Threshold of 0.3 is the default; callers can adjust for stricter/looser matching
- Used by both `semantic_candidate_ranker.py` and `placeholder_resolver.py`

## Related Files
- `src/semantic_candidate_ranker.py` â€” uses similarity scoring for candidate ranking
- `src/placeholder_resolver.py` â€” parent module from which this was extracted
- `src/intent_matcher.py` â€” sibling matching module for placeholder intent classification





---
purpose: >
  Extract placeholders, page requirements, and structured journey data from LLM-generated skeleton code.
  Validates skeleton output to catch hallucinated selectors, unsupported actions, and malformed placeholders.
lines: 463
created: "2026-05-30"
---

# `src/skeleton_parser.py`

## High-Level Purpose

Parses skeleton code produced by the LLM to extract `{{ACTION:description}}` placeholders, page requirements, and structured test journeys. Provides validation to reject malformed skeletons.

## Key Patterns

- **Placeholder regex:** `\{\{(CLICK|FILL|GOTO|URL|ASSERT):([^}]+)\}\}`
- **Single-brace placeholder:** `(?<!\{)\{ACTION:(.+)\}(?!\})` â€” repaired to double-brace
- **Test definition:** `^\s*def\s+(test_\w+)\s*\(`
- **Page reference:** `#\s*[-*]?\s*(\w+)(?:\s+(?:\((.*?)\)|â€”\s*(.*?)))?\s*$`

## Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `normalise_placeholder_actions(code)` | `str` | Repairs single-brace â†’ double-brace, maps synonyms (ADDâ†’CLICK, VERIFYâ†’ASSERT, etc.) |
| `parse_placeholders(code)` | `list[tuple[str,str]]` | All (action, description) pairs |
| `parse_placeholder_uses(code)` | `list[PlaceholderUse]` | PlaceholderUses with line numbers |
| `parse_pages_needed(code)` | `list[tuple[str,str]]` | PAGES_NEEDED keywords (DEPRECATED) |
| `parse_page_requirements(code)` | `list[PageRequirement]` | Typed page requirements |
| `parse_test_journeys(code)` | `list[TestJourney]` | Structured journey with steps per test function |
| `get_test_class_names(code)` | `list[str]` | Class names declared in skeleton |
| `find_malformed_placeholders(code)` | `list[str]` | Single-brace placeholders that need repair |
| `validate_skeleton(code)` | `str \| None` | Validation error message or None |

## Synonym Mapping

- NAVIGATE/GO/OPEN/VISIT â†’ GOTO
- ADD/REMOVE/DELETE/SUBMIT/PRESS/TAP/SELECT/CHOOSE â†’ CLICK
- VERIFY/CHECK/CONFIRM/ENSURE â†’ ASSERT
- TYPE/ENTER â†’ FILL

## Validation Checks

1. Malformed single-brace placeholders
2. Unsupported action types (not CLICK/FILL/GOTO/URL/ASSERT)
3. Python format-string variables inside placeholders (`{item_name}`)
4. URLs in PAGES_NEEDED block (must be keywords)
5. Hallucinated raw selectors in evidence_tracker calls
6. `pytest.skip()` in non-statement positions

## Dependencies

- `src.pipeline_models` â€” `PageRequirement`, `PlaceholderUse`, `TestJourney`, `TestStep`

## Depended On By

- `src/orchestrator.py` â€” parses skeletons after LLM generation
- `src/code_validator.py` â€” uses `validate_skeleton()`





# skeleton_validator.py

## Purpose
Validates skeleton output for forbidden patterns (CSS selectors, XPath, etc.). Ensures LLM-generated test skeletons use ONLY placeholder syntax (`{{CLICK:description}}`, `{{FILL:description}}`, etc.) and contain no real locators. Real locators are resolved in Phase 2 by the placeholder resolver.

## Location
`src/skeleton_validator.py`

## Dependencies
- `re` (standard library)
- `dataclasses` (standard library)

## Public API

### `SkeletonValidationResult` (dataclass)
Result of validating a skeleton for forbidden patterns.
- `is_valid: bool` â€” Whether the skeleton passes validation
- `violations: list[str]` â€” List of violation descriptions found
- `suggestion: str` â€” Human-readable suggestion for fixing violations

### `SkeletonValidator.validate(skeleton_code: str) -> SkeletonValidationResult`
Validate skeleton code for forbidden locator patterns. Scans each line for CSS class selectors, CSS ID selectors, CSS attribute selectors, XPath expressions, CSS descendant combinators, `page.locator()` with real selectors, and `get_by_role/get_by_text/get_by_label` with literal arguments. Skips comment lines, import lines, placeholder lines, and URL contexts (avoids false positives on `https://`).

## Design Notes
- URL-aware: `://` contexts are excluded from XPath pattern matching to avoid flagging `https://` URLs
- Deduplicates violations while preserving order
- Returns actionable suggestion text when violations are found
- Enforces the two-phase skeleton-first pipeline: Phase 1 = placeholders only, Phase 2 = real selectors

## Related Files
- `src/skeleton_parser.py` â€” sibling module that parses skeleton structure
- `src/test_generator.py` â€” uses validator before accepting skeleton output
- `src/placeholder_resolver.py` â€” Phase 2 resolver that substitutes real selectors





# spec_analyzer.py

## Purpose
Derives `TestCondition` objects from a test specification by analyzing feature specs. Supports two modes: deterministic parsing of explicit numbered acceptance criteria, and LLM-driven spec analysis for free-form specifications.

## Location
`src/spec_analyzer.py`

## Dependencies
- `src.llm_client` â€” LLMClient for spec analysis when no explicit criteria exist

## Module Constants
- `ConditionType` â€” Literal type: `"happy_path" | "boundary" | "negative" | "exploratory" | "regression" | "ambiguity"`
- `ConditionSrc` â€” Literal type: `"ai" | "manual" | "automation"`
- `ConditionIntent` â€” Literal type: `"element_presence" | "element_behavior" | "state_assertion" | "journey_step" | "journey_outcome"`

## Public API

### `infer_condition_intent(text: str) -> ConditionIntent`
Heuristic function that infers the best-fit intent category from condition text using keyword phrase matching. Priority order: journey_step phrases â†’ journey_outcome phrases â†’ state_assertion phrases â†’ element_presence â†’ element_behavior â†’ defaults to journey_step.

### `TestCondition` (dataclass)
A single verifiable condition derived from spec analysis.
- `id: str` â€” Unique identifier (e.g., "BC01.02")
- `type: ConditionType` â€” Category of condition
- `text: str` â€” Plain English description
- `expected: str` â€” Expected result
- `source: str` â€” Spec clause that drove this condition
- `flagged: bool` â€” True if type is "ambiguity"
- `src: ConditionSrc` â€” Origin ("ai", "manual", "automation")
- `intent: ConditionIntent` â€” Inferred intent category
- `to_dict() -> dict` â€” Returns dict representation

### `SpecAnalyzer.__init__(llm_client: LLMClient | None = None)`
Initialize with an LLM client (creates default if not provided).

### `SpecAnalyzer.analyze(spec_text: str) -> list[TestCondition]`
Analyze spec text and return list of test conditions. Prefers deterministic parsing of explicit numbered acceptance criteria over LLM analysis. Falls back to LLM-driven analysis for free-form specs.

### `SpecAnalyzer._extract_numbered_criteria(spec_text: str) -> list[str]`
Extract numbered acceptance criteria lines from spec text. Handles common headings ("## Acceptance Criteria", "Acceptance Criteria:") and parses `N. criterion` format.

## Design Notes
- Two-mode design: explicit criteria â†’ deterministic mapping, free-form spec â†’ LLM analysis
- LLM output parsing includes JSON repair for common mistakes (trailing commas, unquoted keys, single quotes, raw newlines)
- Fallback parsing extracts individual `{...}` objects when the overall JSON array is malformed
- `__test__ = False` on TestCondition prevents pytest from collecting it as a test
- System prompt enforces strict JSON output with no markdown fences

## Related Files
- `src/test_plan.py` â€” consumes TestCondition objects for test planning
- `src/llm_client.py` â€” LLM interface used for spec analysis
- `src/orchestrator.py` â€” orchestrator may use spec analysis results





---
purpose: >
  State-aware DOM scraper used as fallback in placeholder_orchestrator.py.
  Tracks form state, visible elements, and DOM mutations across interactions.
lines: ~350
created: "2026-05-30"
---

# `src/stateful_scraper.py`

## High-Level Purpose

Fallback scraper that maintains DOM state awareness across page interactions. Tracks which forms are visible, which elements changed after actions, and provides context-rich element data for placeholder resolution.

## Key Features

- **Form state tracking:** Records form field values before/after interactions
- **Visibility detection:** Only considers visible elements for candidate matching
- **DOM mutation awareness:** Detects elements added/removed after user actions
- **Context preservation:** Carries page URL, title, and visible text for LLM reasoning

## Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `scrape_page(url)` | `ScrapeResult` | Navigate and scrape with state awareness |
| `record_interaction(action, selector)` | `dict` | Record DOM state after click/fill |
| `get_visible_elements()` | `list[dict]` | Only visible, interactable elements |

## Dependencies

- `src.scraper.PageScraper` â€” base scraping
- `src.state_tracker.StateTracker` â€” state persistence

## Depended On By

- `src/placeholder_orchestrator.py` â€” fallback when journey_scraper unavailable





# state_tracker.py

## Purpose
State tracking utilities for detecting DOM changes and URL transitions across page interactions during journey scraping.

## Location
`src/state_tracker.py` (122 lines)

## Dependencies
- `hashlib` (standard library)
- `dataclasses.dataclass, field` (standard library)
- `urllib.parse.urlparse` (standard library)

## Public API

### `DOMState` (dataclass)
Snapshot of page DOM state at a point in time. Fields: `url`, `dom_hash`, `element_count`, `title`.

### `StateChange` (dataclass)
Represents detected changes between two DOM states. Fields: `change_type` ("initial" | "url" | "content" | "navigation" | "none"), `description`, `from_state`, `to_state`.

### `StateTracker` (dataclass)
Track DOM and URL state changes across page interactions.

#### `StateTracker.compute_dom_hash(content: str) -> str`
Return a SHA-256 hash of the page HTML content.

#### `StateTracker.capture_state(url: str, html_content: str, element_count: int = 0, title: str = "") -> DOMState`
Capture and store the current page state.

#### `StateTracker.detect_changes(new_state: DOMState) -> StateChange`
Compare new state against the previous one and return the change.

#### `StateTracker.track_url_transition(from_url: str, to_url: str) -> StateChange | None`
Track a URL transition and classify it.

#### `StateTracker.get_history() -> list[DOMState]`
Return the full state history.

#### `StateTracker.get_changes() -> list[StateChange]`
Return all detected state changes.

#### `StateTracker.urls_are_same_domain(url_a: str, url_b: str) -> bool`
Check if two URLs share the same domain.

## Design Notes
- Uses SHA-256 hashing for DOM content comparison
- Classifies changes into: initial, url, content, navigation, none
- Maintains full history for replay/debugging
- Used by `journey_scraper.py` to detect SPA navigation vs server-side redirects

## Related Files
- `src/journey_scraper.py` â€” consumes state tracking for journey awareness
- `src/stateful_scraper.py` â€” sibling stateful scraping module





# `src/test_generator.py`

## High-Level Purpose

Test generation helpers for both direct generation and skeleton-first pipeline flows. Orchestrates LLM calls for skeleton generation and direct code generation, validates output, and persists generated tests to disk.

## Module Metadata

- **Lines:** 107
- **Imports:** `os`, `pathlib.Path`, `typing.Any`, `src.code_validator`, `src.file_utils`, `src.llm_client.LLMClient`, `src.prompt_utils`

## Class: `TestGenerator`

### `__init__(client=None, *, output_dir="generated_tests", model_name=None, provider_name=None, base_url=None, api_key=None)`
- Wraps `LLMClient` (or creates one from env/config)
- Ensures `output_dir` exists on disk
- Tracks `generated_files` list
- Default model: `qwen2.5:7b` (from `OLLAMA_MODEL` env var or hardcoded fallback)

### `generate_skeleton(user_story, conditions, target_urls=None, expected_count=None) -> str`
- Phase 1 of skeleton-first pipeline: generates placeholder-based skeleton code
- Builds prompt using `get_skeleton_prompt_template()` with user story, conditions, known URLs
- Appends explicit count instruction when `expected_count` is set
- Returns LLM response with `{{ACTION:description}}` placeholder tokens

### `generate_resolved_test(skeleton_code, pages_to_scrape) -> str`
- Compatibility seam for post-resolution polishing
- Currently returns skeleton code as-is (resolver does replacement work)

### `generate_and_save(request_text, page_context_or_base_url="") -> str`
- Direct (non-skeleton) generation: generates code, validates, and saves to disk
- Validates Python syntax via `validate_python_syntax()`
- Validates locator quality via `validate_generated_locator_quality()`
- Saves via `save_generated_test()` with slugified filename
- Returns path to saved test file

## Dependencies

- `src.code_validator.validate_generated_locator_quality`, `validate_python_syntax`
- `src.file_utils.save_generated_test`, `slugify`
- `src.llm_client.LLMClient`
- `src.prompt_utils.build_page_context_prompt_block`, `get_skeleton_prompt_template`

## Depended On By

- `src/orchestrator.py` â€” core pipeline orchestration
- `src/ui_pipeline.py` â€” Streamlit UI pipeline execution
- Generated test pipeline (both skeleton-first and direct modes)

## Notes

- Default model updated to `qwen2.5:7b` (was `qwen3.5:35b`)
- Supports both legacy direct generation and modern skeleton-first pipeline
- Validates generated code before saving to disk





# `src/test_plan.py`

## Purpose
Living test plan models and helpers for tester review/sign-off before test generation.

## Metadata
- **Lines:** 217
- **Imports:** dataclasses, datetime, src.spec_analyzer

## Classes
- **`TestPlan`** (frozen dataclass): Tester-reviewed plan of conditions. Supports confirm/remove/add/sign-off of conditions.

## Functions
| Function | Description |
|----------|-------------|
| `build_story_ref(user_story)` | Derives stable story ref slug from user-story text |
| `next_condition_id(existing, prefix)` | Returns next sequential condition id (e.g., MAN01) |
| `build_manual_condition(...)` | Creates tester-authored condition with stable id |
| `apply_editor_rows(plan, rows)` | Updates plan from editable table rows |

## Dependencies
- `src.spec_analyzer` (TestCondition, ConditionIntent, infer_condition_intent)





# `src/ui_pipeline.py`

## Purpose
Pipeline execution helpers for Streamlit UI â€” business logic only (no rendering). Extracted from streamlit_app for testability.

## Metadata
- **Lines:** 341
- **Imports:** pathlib, src.code_validator, src.journey_scraper, src.llm_client, src.orchestrator, src.pipeline_report_service, src.pipeline_run_service, src.pipeline_writer, src.pytest_output_parser, src.spec_analyzer, src.test_generator, src.test_plan

## Classes
- **`PipelineSessionState`**: Thin wrapper around Streamlit session state for testability

## Functions
| Function | Description |
|----------|-------------|
| `_get_provider_defaults(provider)` | Returns (base_url, model) defaults per provider |
| `parse_requirements_text(raw_text)` | Parses raw text into (user_story, criteria) |
| `parse_target_urls(base_url, urls_input)` | Deduplicates and orders target URLs |
| `build_test_plan(...)` | Analyzes requirements, returns TestPlan for review |
| `plan_rows_from_plan(plan)` | Returns editable table rows from plan |
| `run_pipeline(...)` | Async: executes full skeleton-first pipeline |
| `execute_saved_test(saved_path)` | Runs saved test file, returns result |
| `execute_failed_only(saved_path, previous_run)` | Re-runs only failed tests |
| `build_report_bundle(...)` | Builds report artifacts for pipeline run |
| `store_report_bundle(bundle, session)` | Persists reports in session state |
| `safe_read_text(path)` | Reads text file safely |
| `find_evidence_sidecars(base_dir)` | Finds all evidence JSON sidecars |
| `find_all_evidence_dirs(base_dir)` | Returns all evidence directories |
| `find_sidecar_for_test(base_dir, test_name)` | Finds sidecar by test name |

## Dependencies
- `src.code_validator`, `src.orchestrator`, `src.spec_analyzer`, `src.test_generator`, `src.test_plan`, `src.pipeline_*` services





# `src/ui_renderers.py`

## Purpose
Streamlit rendering helpers â€” pure UI, no business logic. Extracted from streamlit_app for testability.

## Metadata
- **Lines:** 1106
- **Imports:** streamlit, src.coverage_utils, src.failure_classifier, src.gantt_utils, src.heatmap_utils, src.pytest_output_parser, src.report_utils, src.journey_scraper

## Classes
| Class | Description |
|-------|-------------|
| `SidebarConfig` | Renders configuration sidebar, returns provider dict |
| `RequirementsInput` | Renders requirements input with paste/upload modes |
| `ResultsPanel` | Renders pipeline results tabs (Final Code, Skeleton, Scrape) |
| `RunResultsDisplay` | Renders test run results with failure classification and repair buttons |
| `RenderDownloads` | Renders report download buttons (Manifest, Local, Jira, HTML) |
| `EvidenceViewer` | Renders evidence viewer: annotated screenshots, Gantt, heatmap |
| `SavedPackagePanel` | Renders saved package panel: load/reload saved test packages with metadata, run history, and flakiness (AI-026) |

## Functions
| Function | Description |
|----------|-------------|
| `render_credential_profiles()` | Renders auth section, returns active CredentialProfile |
| `render_journey_builder(additional_urls)` | Renders journey builder, returns list[JourneyStep] |
| `_render_single_step(idx, step)` | Renders single journey step row |
| `_urls_to_journey_step_dicts(urls)` | Converts URLs to goto+capture step dicts |
| `_dict_to_journey_step(d)` | Converts dict to JourneyStep dataclass |
| `run_codegen_session(url, timeout)` | Launches headed Playwright codegen, captures locator |
| `_handle_run_tests()` / `_handle_rerun_failed()` | Button handlers for test execution |
| `_render_repair_*` | Locator repair panel rendering (waiting, browser, result) |

## Dependencies
- `streamlit`, `src.coverage_utils`, `src.failure_classifier`, `src.gantt_utils`, `src.heatmap_utils`, `src.locator_repair`, `src.ui_pipeline`, `src.pipeline_artifact_manager`, `src.run_result_persistence`





# `src/url_inference.py`

## Purpose
URL transition inference for journey-aware placeholder resolution. Infers next page URL after navigation clicks.

## Metadata
- **Lines:** 108
- **Imports:** logging, urllib.parse.urljoin

## Functions
| Function | Description |
|----------|-------------|
| `infer_next_page_url(action, description, matched_element, scraped_data, current_url)` | Main entry: infers next page after a resolved step |
| `_infer_click_transition_url(description, matched_element, scraped_data, current_url)` | Infers common transitions (loginâ†’inventory, checkoutâ†’step-two, etc.) |
| `_find_discovered_url(scraped_data, preferred_terms)` | Returns best scraped URL matching preferred terms |

## Key Logic
- CLICK with href â†’ returns href (resolved against current_url if relative)
- CLICK without href â†’ uses keyword matching on description/selector/id to infer transitions
- Add to cart clicks â†’ returns None (stays on same page)
- Navigation clicks (cart, checkout, home) â†’ falls back to PlaceholderResolver.resolve_url

## Dependencies
- `src.placeholder_resolver` (conditional import for resolve_url fallback)





# `src/url_resolver.py`

## Purpose
Resolves page keywords to actually discovered URLs from journey scraping. Bridges LLM-generated page keywords (e.g., "cart", "checkout") with real URLs.

## Metadata
- **Lines:** 221
- **Imports:** logging, urllib.parse.urlparse, src.url_utils

## Classes
| Class | Description |
|-------|-------------|
| `UrlResolver` | Builds keywordâ†’URL mapping from journey scraping results |

## Functions
| Function | Description |
|----------|-------------|
| `UrlResolver.build_mapping(keywords, scraped_urls, seed_url, concepts)` | Match keywords to discovered URLs |
| `UrlResolver.resolve(keyword)` | Resolve a keyword to an actual URL |
| `UrlResolver.get_seed_url()` | Return seed URL as fallback |
| `UrlResolver.get_all_mappings()` | Return copy of all keywordâ†’URL mappings |
| `UrlResolver._match_keyword_to_url(kw_lower, scraped_urls)` | Static: match single keyword using 4-tier strategy |
| `resolve_keywords_to_urls(keywords, scraped_urls, seed_url, concepts)` | Convenience: creates and populates UrlResolver |

## Matching Strategy (priority order)
1. Exact path match: "cart" â†’ `/cart`
2. Direct path segment match: "cart" â†’ `/shop/cart`
3. Normalized substring: "checkout overview" â†’ `/checkout-overview`
4. Prefix match: "product" â†’ `/products` (shortest path wins)

## Fallback
When no scraped URLs available, uses `build_common_path_candidates` from `src.url_utils` to generate common e-commerce paths.





# `src/url_utils.py`

## Purpose
Pure URL manipulation helpers extracted from TestOrchestrator. Validates domains, filters to allowed domains, extracts route concepts, and provides URL fallback guesses.

## Metadata
- **Lines:** 87
- **Imports:** logging, urllib.parse (urljoin, urlparse)

## Functions
| Function | Description |
|----------|-------------|
| `extract_seed_domain(seed_urls)` | Extract normalized domain strings from seed URLs |
| `filter_urls_to_allowed_domain(urls, allowed_domains)` | Keep only URLs matching allowed domains or subdomains |
| `extract_route_concepts(texts)` | Extract e-commerce concepts (home, products, cart, checkout) from text |
| `build_common_path_candidates(seed_urls, concepts)` | Stub â€” returns empty list (journey scraper replaces guessing) |
| `heuristic_url_from_description(current_url, description)` | Best-effort URL guess from description keywords |

## Key Logic
- Domain validation allows exact match or subdomain match
- Route concepts extracted via keyword presence: "product"/"shop" â†’ products, "cart"/"basket" â†’ cart, "checkout"/"payment" â†’ checkout
- `build_common_path_candidates` is deprecated â€” journey scraper replaces URL guessing
- `heuristic_url_from_description` maps keywords to common paths: productsâ†’`/products`, cartâ†’`/view_cart`, checkoutâ†’`/checkout`





# `src/user_story_parser.py`

## Purpose
Parses user story text into structured `FeatureSpecification` with user story and acceptance criteria. Supports multiple input formats (Markdown headings, plain text, "As a" format).

## Metadata
- **Lines:** 288
- **Imports:** re, dataclasses, typing (Any, Literal)

## Classes
| Class | Description |
|-------|-------------|
| `FeatureSpecification` | Parsed result: user_story, acceptance_criteria list, raw_input |
| `ParseResult` | Success flag, specification, error_message |
| `RequirementModel` | Normalized requirement list with source tracking |
| `FeatureParser` | Main parser class |

## Functions
| Function | Description |
|----------|-------------|
| `FeatureParser.parse(text)` | Parse raw text â†’ ParseResult with FeatureSpecification |
| `FeatureParser.build_requirement_model(spec)` | Build RequirementModel from specification |
| `FeatureParser._clean_criterion(stripped)` | Remove bullets, numbers, "Total: N criteria" markers |

## Parsing Strategy
1. Detect section headings (STORY_HEADINGS / CRITERIA_HEADINGS) with variable whitespace
2. Collect lines under active section into user_story or acceptance_criteria
3. Fallback: no headings found â†’ collect all meaningful lines as story
4. `_clean_criterion` strips bullets (`-`, `*`, `â€¢`), numbered lists, and "(Total: N criteria)"

## RequirementModel Sources
- `acceptance_criteria` â€” explicit AC section found
- `derived_from_story` â€” story lines used (skip "As a..." wrapper)
- `story_fallback` â€” single story line as sole requirement





# `src/vision_enricher.py`

## Purpose
Vision-based element enrichment service. Uses vision-capable LLMs to analyze cropped element screenshots and return structured text metadata (product_name, price, visual_label) for improved placeholder resolution. Vision is a metadata enricher, not a matcher â€” text-based resolver always does matching.

## Metadata
- **Lines:** 307
- **Imports:** base64, io, json, re, typing, PIL.Image

## Classes
| Class | Description |
|-------|-------------|
| `VisionEnricher` | Static methods for vision detection, cropping, enrichment |

## Key Constants
| Constant | Description |
|----------|-------------|
| `VISION_MODEL_PATTERNS` | Regex patterns for vision-capable model names (qwen-vl, llava, gpt-4v, gemini, claude, glm-4v, internvl, llama-3.2-vl) |

## Methods
| Method | Description |
|--------|-------------|
| `is_vision_capable(provider, model)` | Detect vision support by matching model name against known patterns |
| `crop_element_from_screenshot(screenshot_bytes, bbox, padding=2)` | Crop element from full-page screenshot using bounding box |
| `enrich_elements(elements, screenshot_bytes, provider, model, timeout=60)` | Main enrichment pipeline: crop â†’ vision LLM â†’ parse â†’ merge metadata |
| `_build_vision_prompt(element)` | Build prompt asking vision LLM for structured JSON metadata |
| `_parse_enrichment_response(response_text)` | Parse vision LLM response: JSON first, then regex fallback |

## Enrichment Flow
1. Check `is_vision_capable` â€” skip if no vision model
2. For each element with `_bbox`: crop from screenshot â†’ base64 encode
3. Call `LLMClient.create_vision_completion()` with cropped image + prompt
4. Parse structured response â†’ merge into element dict
5. Set `_enriched=True` on success, `_enriched=False` + `_enrichment_error` on failure

## Design Principles
- Zero regression: users without vision LLMs get unchanged behavior
- Auto-detection: no user config needed
- In-memory only: images stored as base64, discarded after enrichment
- Graceful degradation: per-element errors don't fail the batch





# `src/__init__.py`

## High-Level Purpose

This file serves as the package initialization module for the `src` package in the Playwright test generator project. It establishes the `src` directory as a Python package and provides a top-level documentation string describing the module's purpose.

## Module Docstring

```python
"""Source module for Playwright test generator."""
```

## Class/Function Signatures

**None.** This file contains no class or function definitions.

## Key Architectural Patterns

- **Package Initialization**: This minimal `__init__.py` file marks the `src` directory as a Python package, enabling imports from the module namespace.
- **Clean Namespace**: The file does not expose any public symbols via `__all__`, meaning all submodules must be imported explicitly by their full path.

## Dependencies

None declared in this file.




