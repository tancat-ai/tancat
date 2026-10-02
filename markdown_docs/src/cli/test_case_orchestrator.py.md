# `src/cli/test_case_orchestrator.py` — Test Case Orchestrator

## Purpose

Manages orchestration of test generation workflow: parsing → analysis → dependency ordering → file generation. Uses the same pipeline as the Streamlit app (`src.orchestrator.TestOrchestrator`) for feature parity.

## Data Class: `TestOrchestrationResult`

| Field | Type | Description |
|-------|------|-------------|
| `generated_files` | `list[str]` | Paths to generated test files |
| `summary` | `dict` | Orchestration summary |
| `errors` | `list[str]` | Error messages |

- `to_dict() -> dict` — Serialises with timestamp.

## Class: `TestCaseOrchestrator`

### `__init__(analysis_mode=AnalysisMode.FAST)`

Initialises with a `KeywordAnalyzer` instance.

### `process(raw_input, explicit_format=None, url=None, output_dir="generated_tests") -> TestOrchestrationResult`

Full pipeline: parse → analyze → order → generate. Accepts raw text input.

### `process_parsed(parsed, url=None, output_dir="generated_tests") -> TestOrchestrationResult`

Same as `process` but accepts a pre-parsed `ParsedInput` object.

### Private Methods

#### `_analyze_input(parsed) -> AnalysisResult`

Runs `KeywordAnalyzer.analyze()` on each test case in the parsed input.

#### `_order_test_cases(cases) -> list[AnalyzedTestCase]`

Topological sort by dependencies:
1. Cases with no dependencies first
2. Then cases whose dependencies are satisfied
3. Within same level: ordered by complexity (low → high)

#### `_check_dependencies_satisfied(case, completed_ids) -> bool`

Checks if `AnalyzedTestCase.dependencies` are met.

#### `_complexity_score(complexity: str) -> int`

Maps `"low" → 1`, `"medium" → 2`, `"high" → 3`.

#### `_generate_test_files(cases, url, output_dir, raw_requirements) -> list[str]`

Generates Playwright test files using:
1. `TestOrchestrator.run_pipeline()` (same as Streamlit)
2. `PipelineArtifactWriter.write_run_artifacts()` for saving

Supports two modes:
- **Feature spec mode**: Single pipeline run from parsed markdown spec (`FeatureParser`)
- **Per-case mode**: Individual pipeline runs per test case

#### `_build_feature_spec_request(raw_requirements) -> tuple[str, str] | None`

Parses raw markdown requirements into `(user_story, numbered_conditions)`.

#### `_generate_test_content(test_type, cases) -> str`

Generates full test file content (class header + fixtures + test methods).

#### `_generate_test_method(idx, case, total) -> str`

Generates a single test method from an `AnalyzedTestCase`.

#### `_generate_steps_from_description(case) -> list[str]`

Keyword-based step generation:
- "navigate"/"go to"/"open" → `page.goto()`
- "login"/"sign in" → fill credentials + click login
- "form"/"fill" → `page.fill()` for suggested data
- "click"/"submit" → `page.click()`
- "search" → fill + click search

#### `_sanitize_name(name) -> str`

Converts arbitrary text to valid Python identifier.

#### `_extract_url(text) -> str | None`

Regex-based URL extraction.

#### `_create_summary(analysis, files) -> dict`

Creates orchestration summary with counts, file names, complexity distribution, etc.

## How It Works (Internals)

Private `_`-helpers - the module's real logic (11 items). Grouped under the public function that calls them.

### `TestCaseOrchestrator.process_parsed(parsed: ParsedInput, url: str | None = None, output_dir: str = GENERATED_TESTS_DIR) -> TestOrchestrationResult` - method of `TestCaseOrchestrator`

- `_analyze_input(parsed: object) -> AnalysisResult` (method of `TestCaseOrchestrator`): Analyze parsed input using the keyword analyzer. Args: parsed: ParsedInput from src.cli.input_parser.InputParser Returns: AnalysisResult with analyzed test cases.
- `_order_test_cases(cases: list[AnalyzedTestCase]) -> list[AnalyzedTestCase]` (method of `TestCaseOrchestrator`): Order test cases based on dependencies and complexity. Topological sort approach: 1. Cases with no dependencies first 2. Then cases that depend on completed cases 3. Within same dependency level, order by complexity (...
- `_generate_test_files(cases: list[AnalyzedTestCase], url: str | None = None, output_dir: str = GENERATED_TESTS_DIR, raw_requirements: str = '') -> list[str]` (method of `TestCaseOrchestrator`): Generate Playwright test files from analyzed test cases. Uses the same TestOrchestrator pipeline as the Streamlit app for feature parity between CLI and Streamlit frontends.

### Internal utilities

- `_check_dependencies_satisfied(case: AnalyzedTestCase, completed_ids: set[int]) -> bool` (method of `TestCaseOrchestrator`): Check if all dependencies for a case are satisfied. The AnalyzedTestCase.dependencies field is a list of human-readable strings that may contain markers such as "Depends on: <title>". For orchestration we only...
- `_complexity_score(complexity: str) -> int` (method of `TestCaseOrchestrator`): Convert complexity to numeric score for sorting.
- `_build_feature_spec_request(raw_requirements: str) -> tuple[str, str] | None` (method of `TestCaseOrchestrator`): Return '(user_story, numbered_conditions)' for markdown-style requirement specs.
- `_generate_test_content(test_type: str, cases: list[AnalyzedTestCase]) -> str` (method of `TestCaseOrchestrator`): Generate Playwright test file content.
- `_generate_test_method(idx: int, case: AnalyzedTestCase, total: int) -> str` (method of `TestCaseOrchestrator`): Generate a single test method from an analyzed test case.
- `_generate_steps_from_description(case: AnalyzedTestCase) -> list[str]` (method of `TestCaseOrchestrator`): Generate Playwright steps from test case description.
- `_sanitize_name(name: str) -> str` (method of `TestCaseOrchestrator`): Convert name to valid Python identifier.
- `_extract_url(text: str) -> str | None` (method of `TestCaseOrchestrator`): Extract URL from text if present.
