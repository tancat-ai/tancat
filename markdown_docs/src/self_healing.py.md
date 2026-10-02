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
- `_evidence_context(test_path, test_name) -> (steps, base_url)` — reads the
  failing test's evidence sidecar (step labels + page URL), manifest fallback
- `_learn_from_patch(test_path, result, patch) -> bool` — AI-035 write-back:
  after a successful `replace_locator` patch, upserts the corrected locator
  to the RAG store (`source="self_healing"`, `confidence=1.0`, guarded —
  learning never breaks healing). Counted in `HealingReport.learned`.

## Integration Points

- **Streamlit:** `src/ui/ui_run_results.py` — "🩹 Self-Heal Failed Tests" button, healing results display
- **CLI:** `src/cli/pipeline_runner.py` — `self_heal_cli()` with menu-driven fallback to interactive repair
- **RAG:** `src/rag_learn.py` — `learn_from_patch` consumes the applied patch (AI-035 self-learning write-back)

## Tests

`tests/test_self_healing.py` — unit tests covering extraction, formatting, parsing, patching, evidence context, and the AI-035 learn-back.

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `load_scraped_manifest` (function): `load_scraped_manifest(package_dir: str | Path) -> dict[str, list[dict[str, Any]]]` - Load url -> elements from a package's scrape_manifest.json. The manifest records every page the pipeline scraped with full element records (selector, text, role, href, classes, aria, accessible name). The self...


## How It Works (Internals)

Private `_`-helpers - the module's real logic (12 items). Grouped under the public function that calls them.

### `SelfHealingRunner.heal(test_file: str | Path, *, test_names: list[str] | None = None, on_progress: Callable[[str], None] | None = None) -> HealingReport` - method of `SelfHealingRunner`

- `_run_pytest(test_path: Path, test_names: list[str] | None = None) -> RunResult` (method of `SelfHealingRunner`): Run pytest on a test file (optionally specific tests) and return parsed results.
- `_pre_screen_failure(detail: FailureDetail) -> bool` (method of `SelfHealingRunner`): Pre-screen: return True if failure is worth sending to the LLM. Skips the LLM call for failures that cannot be fixed by code changes: - ASSERTION_FAILURE: logic/test error, not a locator issue - NAVIGATION_ERROR: site...
- `_maybe_add_interactive_candidate(report: HealingReport, result: TestResult, detail: FailureDetail) -> None` (method of `SelfHealingRunner`): Add failure to interactive repair candidates if it's a locator-type failure. Only LOCATOR_TIMEOUT and STRICT_VIOLATION failures can benefit from interactive repair (open browser -> user clicks correct element -> capture...
- `_review_and_suggest(result: TestResult, detail: FailureDetail, test_source: str, test_path: Path | None = None, prior_attempts: list[dict[str, str]] | None = None) -> AppliedPatch | None` (method of `SelfHealingRunner`): Send failure context to the LLM reviewer and parse the suggested patch. Args: result: The failed test result. detail: Classified failure details. test_source: Full test file source code. test_path: Path of the test fi...
- `_learn_from_patch(test_path: Path, result: TestResult, patch: AppliedPatch) -> bool` (method of `SelfHealingRunner`): Write a self-healing-corrected locator to the RAG store. Returns True when the pattern was upserted (new or dedup'd hit). Best-effort and guarded: a learning failure never breaks healing. Only replace_locator patc...
- `_apply_patch(test_path: Path, test_source: str, patch: AppliedPatch) -> bool` (method of `SelfHealingRunner`): Apply a single patch to the test file. Returns True on success.

### Internal utilities

- `_derive_failure_url(test_path: Path | None, result_name: str, test_func: str) -> str` (method of `SelfHealingRunner`): Best-effort URL of the page a test failed on (B-068). classify_failure only sees the error text, so its failure_url is always None. The evidence sidecar records the real page.url at failure time; the packa...
- `_elements_for_url(url: str) -> list[dict[str, Any]]` (method of `SelfHealingRunner`): Scraped element candidates for a URL (B-068). Tolerates fragment / query / trailing-slash differences: manifest keys are normalised by :func:'load_scraped_manifest', while explicitly injected scraped_data may use...
- `_extract_test_function(source: str, test_name: str) -> str | None` (method of `SelfHealingRunner`): Extract a single test function from the test file source. test_name arrives as a pytest node id, so it may carry pytest's parametrisation suffix - pytest-playwright runs every test once per browser, giving test_...
- `_format_elements_for_prompt(elements: list[dict[str, Any]]) -> str` (method of `SelfHealingRunner`): Format scraped elements into a compact, LLM-friendly representation.
- `_parse_reviewer_response(response: str, test_name: str, test_func: str) -> AppliedPatch | None` (method of `SelfHealingRunner`): Parse the LLM reviewer's JSON response into an AppliedPatch.
- `_evidence_context(test_path: Path, test_name: str) -> tuple[list[dict[str, Any]], str]` (method of `SelfHealingRunner`): Recover (evidence_steps, base_url) for a failing test, best-effort. The evidence sidecar (<package>/evidence/<test>.evidence.json) records the resolved steps - labels carry the placeholder descriptions the resolve...
