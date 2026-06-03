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

### Package Persistence (AI-026 — Step 4)

- `load_existing_packages(session: Session) -> None`:
  - Discovers previously generated test packages in `generated_tests/` directory.
  - Uses `src.pipeline_artifact_manager.find_existing_packages()` for discovery.
  - Renders a numbered list via `render_saved_package_list()` from `cli.menu_renderer`.
  - User selects a package index → loads manifest via `load_package_manifest()` and run history via `load_all_run_results()`.
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