# `src/self_healing.py`

## High-Level Purpose

`self_healing.py` implements Phase 2 of the ML Engineering roadmap — automated test repair using an LLM reviewer. When generated Playwright tests fail, this module runs a reflection loop: execute tests → classify failures → feed context to LLM → apply suggested patches → re-run failed tests. Repeats up to a configurable maximum iteration count.

Created **2026-07-20**.

## Dependencies

- `src.failure_classifier` — `classify_failure()`, `FailureDetail`
- `src.llm_client` — `LLMClient` for reviewer LLM calls
- `src.pytest_output_parser` — `parse_pytest_output()`, `RunResult`, `TestResult`
- `json`, `re`, `subprocess` — stdlib

## Data Types

### `AppliedPatch`

Records a single code change applied during healing.

Fields:
- `test_name: str` — test function name
- `line_number: int` — approximate line in test file
- `old_text: str` — original code line
- `new_text: str` — replacement code line
- `diagnosis: str` — LLM's explanation of the failure
- `strategy: str` — one of `"replace_locator"`, `"add_navigation"`, `"add_wait"`, `"skip_test"`

### `HealingReport`

Result of a self-healing run.

Fields:
- `total_failures: int` — initial failure count
- `fixed: int` — how many were fixed
- `remaining: int` — still failing after max iterations
- `unfixable: int` — classified as not automatically fixable
- `iterations: int` — how many loops ran
- `patches: list[AppliedPatch]` — all applied patches
- `final_results: list[TestResult]` — last test run results
- `all_fixed: bool` (property) — True when remaining == 0 and total > 0

### `REVIEWER_SYSTEM_PROMPT: str`

Module-level constant — the system prompt sent to the LLM reviewer. Instructs the LLM to analyze failures and return structured JSON with `fixable`, `diagnosis`, `strategy`, `old_line`, `new_line`, and `confidence` fields.

## Classes

### `SelfHealingRunner`

Automated test repair loop.

#### `__init__(self, llm_client: LLMClient | None = None, max_iterations: int = 3, scraped_data: dict | None = None) -> None`

Args:
- `llm_client`: LLM client for reviewer calls. Defaults to `LLMClient()`.
- `max_iterations`: Maximum repair loops (default 3).
- `scraped_data`: Page element data keyed by URL, used to provide context to the reviewer.

#### `heal(self, test_file: str | Path, *, test_names: list[str] | None = None) -> HealingReport`

Runs the self-healing loop. For each iteration:
1. Runs pytest on the test file
2. Classifies each failure via `classify_failure()`
3. Sends failure context (test source + error + scraped elements) to LLM reviewer
4. Parses reviewer's JSON response into `AppliedPatch`
5. Applies patch to test file
6. Re-runs only previously-failed tests

Stops when all tests pass or max iterations reached.

Raises `FileNotFoundError` if test file doesn't exist.

#### Internal Methods

- `_run_pytest(test_path, test_names) -> RunResult` — runs pytest via subprocess
- `_review_and_suggest(result, detail, test_source) -> AppliedPatch | None` — sends context to LLM
- `_extract_test_function(source, test_name) -> str | None` — extracts single test from file
- `_format_elements_for_prompt(elements) -> str` — formats scraped elements for LLM context
- `_parse_reviewer_response(response, test_name, test_func) -> AppliedPatch | None` — parses LLM JSON
- `_apply_patch(test_path, test_source, patch) -> bool` — applies patch to file

## Integration Points

- **Streamlit:** `src/ui/ui_run_results.py` — "🩹 Self-Heal Failed Tests" button, healing results display
- **CLI:** `src/cli/pipeline_runner.py` — `self_heal_cli()` with menu-driven fallback to interactive repair

## Tests

`tests/test_self_healing.py` — 28 unit tests covering extraction, formatting, parsing, patching, and integration.
