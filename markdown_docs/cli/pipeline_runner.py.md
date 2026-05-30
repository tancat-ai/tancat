# cli/pipeline_runner.py

## Purpose

Executes the intelligent pipeline and manages generated test execution and reporting from the CLI.
Provides glue between session state and core pipeline services.

## Key functions

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
  - Prints pytest summary metrics.

- `generate_reports(session: Any) -> None`
  - Builds local, Jira, and HTML reports using `PipelineReportService`.

- `parse_target_urls(base_url: str, urls_input: str) -> list[str]`
  - Normalizes the starting URL and additional URLs.

## Notes

- Runs the same test generation pipeline as the Streamlit app for feature parity.
- Saves generated test artifacts and report paths into the CLI session object.
- Contains both sign-off gating and fallback logic when the plan is not confirmed.
