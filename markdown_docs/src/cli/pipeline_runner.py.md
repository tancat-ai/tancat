# `src/cli/pipeline_runner.py` — CLI Pipeline Execution

## Purpose

Handles pipeline execution, test running, and report generation for the CLI. Extracted from `cli/main.py` for easier debugging — pure extraction, no refactoring.

## Export

### `export_clean_package(session) -> None`

Exports a clean test suite (flat or POM mode) using `export_clean_suite()` from `src.export_service`.

## Requirements Parsing

### `parse_requirements(raw: str) -> tuple[str, str]`

Delegates to `parse_requirements_text()` from `src.ui_pipeline`. Returns `(user_story, criteria)`.

## Living Test Plan

### `build_test_plan(session) -> None` (async)

Analyzes requirements and builds a living test plan via `ui_build_test_plan()`. Displays conditions in a table and prompts for sign-off.

### `_prompt_sign_off(session) -> None` (async)

Standalone sign-off prompt. Sets `session.plan_confirmed = True` on approval.

## Pipeline Execution

### `run_pipeline(session) -> None` (async)

Full pipeline orchestration:
1. Validates user story and criteria
2. Checks plan sign-off (prompts if unsigned)
3. Calls `ui_run_pipeline()` from `src.ui_pipeline`
4. Captures results into session state (`pipeline_results`, `pipeline_skeleton`, `pipeline_urls`, etc.)
5. Reports unresolved placeholders

## Test Running

### `run_generated_tests(session, rerun_failed=False) -> None`

Executes generated tests via `PipelineRunService().run_saved_test()`. Stores `RunResult` in session.

### `display_run_results(session) -> None`

Displays pytest results using `render_run_results()` followed by `render_run_history_summary()`.

## Reports

### `generate_reports(session) -> None`

Generates local, Jira, and HTML reports via `PipelineReportService().build_reports()`. Stores paths in session.

### `view_reports(session) -> None`

Menu-driven report viewer. Opens selected report in system default app and shows a 30-line preview.

### `_open_file(path) -> None`

Platform-aware file opener (`os.startfile`/`open`/`xdg-open`).

## Failure Diagnostics

### `view_failure_diagnostics(session) -> None`

Displays per-failure diagnostics from evidence JSON files. Shows:
- Test name, condition reference, duration, page URL/title
- Failed steps with labels, locators, error summaries
- Suggested alternative locators
- Available element role summary

### `view_saved_package_diagnostics(package_dir) -> None`

Same as above but for loaded saved packages (AI-026 Step 6). Also shows report and evidence paths from manifest.

## Skeleton / Scrape Views

### `show_skeleton(session) -> None`

Displays the generated skeleton (pre-resolution), truncated to 4000 chars.

### `show_scrape_summary(session) -> None`

Lists scraped URLs with element counts.

## AI-026: Saved Package Operations

### `run_saved_test_from_package(package_dir, session, rerun_failed=False) -> None`

Runs tests from a loaded saved package. Updates manifest's `last_run_at` after execution.

### `load_existing_packages(session) -> None`

Discovers and loads an existing package. Populates session with manifest, run results, and package path.

### `self_heal_cli(session) -> None` (added 2026-07-20)

Automated self-healing via CLI. Runs `SelfHealingRunner.heal()` on the saved test file, displays fix counts and per-patch diffs. If failures remain after healing, offers to re-run tests or try interactive locator repair (`repair_locator_cli`).

Phase 2 of the ML Engineering roadmap — see `src/self_healing.py`.
