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
