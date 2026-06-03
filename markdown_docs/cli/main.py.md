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

### Package Persistence (AI-026 — Step 4)

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
4. **Load Existing Generated Tests** — discovers and loads saved packages (AI-026)
5. **Show Saved Package Metadata** — displays loaded package details (AI-026)
6. **Re-run Saved Suite** — re-executes tests from loaded package (AI-026)
7. Generate & Run Tests
8. Run Saved Tests
9. View Report
10. View Failure Diagnostics
11. **View Saved Package Diagnostics** — displays evidence for loaded package (AI-026)
12. Exit

## Implementation details

- Forces UTF-8 output on Windows and Git Bash for box-drawing characters.
- Loads `.env` if available via `python-dotenv`.
- Reuses `cli.menu_renderer` for UI prompts and `cli.pipeline_runner` for pipeline execution.
- Keeps backward compatibility while exposing the newer interactive flow.
- Package persistence state stored in `Session.loaded_package_manifest` and `Session.loaded_package_run_results`.