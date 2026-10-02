# scripts/eval/eval_runner.py

The orchestration engine for the Evaluation Harness.

## Overview
`EvalRunner` is responsible for coordinating the evaluation process. It handles the loading of test datasets, the execution of the generation pipeline (either via static captures or live regeneration), and the persistence of results to SQLite.

## Key Features

### Dynamic Regeneration (`--regenerate`)
The runner can now bypass static capture files and generate fresh test code using the live system:
- **`_regenerate_code()`**: Iterates through the golden dataset and calls `TestOrchestrator.run_pipeline()` for each story.
- **RAG Integration**: When `RAG_ENABLED=1` is set in the environment, the regeneration process utilizes the RAG retriever to resolve placeholders, allowing for direct quantitative measurement of RAG's impact.

### Static Validation
When regeneration is disabled, the runner loads pre-generated Python files from the `captures/` directory, providing a fast, offline way to validate the `golden_validator` logic.

### Full Validation Mode (`--full`)
In `full` mode, the runner not only validates locators (static) but also executes the generated tests using `pytest` to measure the actual test pass rate and detect false positives.

## Module Logic Flow
1. **Initialization**: Sets up dataset, capture, and database paths.
2. **Code Acquisition**:
   - If `regenerate=True` $\rightarrow$ Call `_regenerate_code()` $\rightarrow$ Live pipeline run.
   - If `regenerate=False` $\rightarrow$ Call `_load_code_map()` $\rightarrow$ Load from `captures/`.
3. **Validation**:
   - `run_static_validation()`: compares extracted locators against golden keys.
   - `run_generated_tests()`: runs `pytest` on the output.
4. **Persistence**: Writes detailed metrics (accuracy, duration, mode) to the `eval_runs` table in SQLite.

## Integration
- **`TestOrchestrator`**: The primary engine used during regeneration.
- **`golden_validator`**: Used to parse and match the results of both static and regenerated code.
- **`HarnessReport`**: The final aggregated metric object returned by `run()`.

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `run_full_validation` (function): `run_full_validation(dataset_dir: Path, code_map: dict[str, str], durations: dict[str, float] | None = None, test_files: dict[str, Path] | None = None, pytest_timeout: float = 120.0, on_story: Callable[[str], None] | None = None, verdict_map: dict[str, list[dict[str, Any]]] | None = None, evidence_dir: Path | None = None, outcomes_out: dict[str, dict[str, str]] | None = None) -> list[StoryResult]` - Run full validation: static + test execution. Args: dataset_dir: Path to scripts/eval/dataset/ code_map: Dict mapping story_id to generated Python code string. durations: Optional dict mapping story_id to generation d...
- `persist_results` (function): `persist_results(db_path: Path, stories: list[StoryResult], mode: str = 'static', *, pipeline: str = 'linear', generation_mode: str = 'captured', rag_enabled: bool = False, pom_mode: bool = False, provider: str = '', model: str = '', git_commit: str = '', temperature_sent: float | None = None, server_defaults: str = '', thinking: str | None = '', code_map: dict[str, str] | None = None, outcomes: dict[str, dict[str, str]] | None = None) -> list[str]` - Write eval results to SQLite eval_runs table. Args: db_path: Path to SQLite database file. stories: List of StoryResult to persist. mode: "static", "resolver", "full", or "semantic". pipeline: "linear" or "graph" - wh...
- `load_eval_history` (function): `load_eval_history(db_path: Path, story_id: str | None = None) -> list[dict[str, Any]]` - Load eval history from SQLite. Args: db_path: Path to SQLite database file. story_id: Optional filter by story_id. Returns: List of dicts with eval_run data, oldest first.
- `rebuild_run_from_evidence` (function): `rebuild_run_from_evidence(evidence_dir: str | Path, db_path: str | Path, dataset_dir: Path | None = None) -> list[str]` - Rebuild an eval_runs row + its criteria from a run's kept evidence (B-093). The evidence was written by eval_harness run --evidence-dir (see eval_evidence.py). No model call, no browser: the kept emitted code is r...
- `eval_rollup` (function): `eval_rollup(db_path: str | Path, story_id: str | None = None) -> str` - One rollup over eval_runs + eval_criteria (B-093), answering the owner. Reuses load_eval_history (the history) and compare_criteria (the compare) - it is a view, not a parallel pipeline. Answers, in order: whi...
- `rag_enabled_by_config` (function): `rag_enabled_by_config() -> bool` - Deprecated local mirror - kept for import compatibility. The single source of truth now lives in src.orchestrator.rag_enabled_by_config (B-036 semantics: missing RAG_ENABLED means enabled; only =0 opts out).
- `EvalRunner.__init__` (method of `EvalRunner`): `EvalRunner.__init__(dataset_dir: Path, code_dir: Path, db_path: Path, test_output_dir: Path | None = None, regenerate: bool = False, use_graph: bool = False, evidence_dir: Path | None = None) -> None`
- `EvalRunner.regeneration_failures` (method of `EvalRunner`): `EvalRunner.regeneration_failures() -> tuple[str, ...]` - Story ids whose code regeneration failed in the last run.
- `EvalRunner.run_semantic_comparison` (method of `EvalRunner`): `EvalRunner.run_semantic_comparison() -> dict[str, Any]` - Locator-level comparison: golden keys vs capture files. Fast, no browser.
- `EvalRunner.print_semantic_report` (method of `EvalRunner`): `EvalRunner.print_semantic_report(results: dict[str, Any]) -> None` - Print the semantic comparison report.
- `PYTEST_TIMEOUT_MARKER` (constant): `PYTEST_TIMEOUT_MARKER = 'pytest execution timed out'`


## How It Works (Internals)

Private `_`-helpers - the module's real logic (20 items). Grouped under the public function that calls them.

### `EvalRunner.run(mode: str = 'static', pytest_timeout: float = 700.0, persist: bool = True) -> HarnessReport` - method of `EvalRunner`

- `_get_git_commit() -> str` (function): Return the current git HEAD commit hash, or empty string on failure.
- `_load_code_map() -> dict[str, str]` (method of `EvalRunner`): Load all captured code files into a map keyed by story_id.
- `_persist_verdicts() -> None` (method of `EvalRunner`): Write the run's verdicts beside the persisted tests (B-100). One file for the whole run, keyed by story id, so a story's test names cannot collide with another story's. Written whenever regeneration produced verdicts,...
- `_load_verdict_map() -> dict[str, list[dict[str, Any]]]` (method of `EvalRunner`): Load the verdict file beside the tests; {} when absent (B-100).
- `_persist_regenerated_tests(code_map: dict[str, str]) -> None` (method of `EvalRunner`): Write regenerated code to test_output_dir for the execution phase. One deterministic file per STORY (test_<story_id>.py, B-094) so full mode executes the JUST-regenerated tests and reports a pass rate instead...
- `_load_test_files() -> dict[str, Path]` (method of `EvalRunner`): Map each story_id to ITS OWN generated test file (B-094). Exact per-story filename (test_<story_id>.py) rather than a site-substring glob: two stories on one site must never resolve to the same file, or one story'...
- `_build_mock_dirs(repo_root: Path | None = None) -> dict[str, str]` (method of `EvalRunner`): Map each localhost-mock story to the directory it must be served from. A dataset opts in via base_url on http://localhost:8781 and an optional mock_dir field (served as the server root). Legacy datasets wi...
- `_loaded_model_identity() -> tuple[str, str]` (method of `EvalRunner`): Best-effort (provider, model) of the LLM that produced this run. Recorded into eval_runs so A/B runs across model swaps are comparable (the 3.6-vs-3.8 comparison this fix came from was hampered by an empty model...
- `_sampling_identity(use_graph: bool) -> tuple[float | None, str, str | None]` (method of `EvalRunner`): Resolved (temperature_sent, server_defaults, thinking) for a run. temperature_sent is the sampling temperature the pipeline actually delivers: graph runs always send 0 (agents pin temperature=0); linear runs s...
- `_regenerate_code() -> tuple[dict[str, str], dict[str, float]]` (method of `EvalRunner`): Regenerate code for all stories using the live pipeline. When self.use_graph is True, the multi-agent LangGraph pipeline is used for skeleton generation instead of the linear path. Each story gets a fresh orchestr...
- `_save_captures(code_map: dict[str, str]) -> None` (method of `EvalRunner`): Save regenerated code as capture files for future static CI comparison.

### `persist_results(db_path: Path, stories: list[StoryResult], mode: str = 'static', *, pipeline: str = 'linear', generation_mode: str = 'captured', rag_enabled: bool = False, pom_mode: bool = False, provider: str = '', model: str = '', git_commit: str = '', temperature_sent: float | None = None, server_defaults: str = '', thinking: str | None = '', code_map: dict[str, str] | None = None, outcomes: dict[str, dict[str, str]] | None = None) -> list[str]` - function

- `_ensure_eval_table(conn: sqlite3.Connection) -> None` (function): Create eval_runs table and index if they don't exist. Newer columns (temperature_sent, server_defaults, thinking) are added to pre-existing databases via ALTER TABLE so historical rows keep NULL (accurate: the deliver...

### `run_generated_tests(test_file: Path, pytest_timeout: float = 120.0, *, junit_dir: Path | None = None, log_dir: Path | None = None) -> tuple[int, int, int, int, float, str, dict[str, str]]` - function

- `_parse_per_test_results(output: str) -> dict[str, str]` (function): Map test function name -> pytest outcome from -v console output. Handles both the plain and the xdist line shapes. This is the FALLBACK: _parse_junit_xml is preferred, because under xdist the outcome and the node...
- `_parse_junit_xml(xml_path: Path) -> dict[str, str]` (function): Map test function name -> outcome from a pytest JUnit XML report. Machine-readable and independent of the console format, so it is the primary source for per-test outcomes. Returns an empty map on any parse failure - ...

### Internal utilities

- `_story_test_filename(story_id: str) -> str` (function): B-094: one emitted test file per STORY, never per site. Two golden stories can share a site (eval-007 and eval-008 both target banking_mock). Naming the file test_<site>.py made the later story overwrite the earli...
- `_collect_verdicts(story_id: str, orchestrator: Any) -> None` (method of `EvalRunner`): Record the pipeline's verification verdicts for one story (B-100). The orchestrator decides these at emit time; the harness reads them instead of re-deriving strength from the emitted code. A failed or missing run sto...
- `_ensure_conftest() -> None` (method of `EvalRunner`): Copy the repo generated_tests/conftest.py into the test output dir. B-061 (a): every generated test needs the evidence_tracker fixture, which lives in generated_tests/conftest.py. With a custom --test-ou...
- `_ensure_mock_serves(mock_dir: str | None) -> None` (method of `EvalRunner`): (Re)start the :8781 mock server when *mock_dir* differs from the current one. Stories that don't need the mock (live-site datasets) pass None and leave any running server untouched. Restarting is cheap (daemon thr...
- `_on_story_mock_swap(story_id: str) -> None` (method of `EvalRunner`): Execution-phase hook: serve the right mock root for *story_id*.
- `_regenerate_code_via_graph() -> tuple[dict[str, str], dict[str, float]]` (method of `EvalRunner`): Regenerate code using the LangGraph multi-agent pipeline. Each story gets a fresh orchestrator to prevent URL resolver state contamination. Stories are processed sequentially to avoid browser/resource conflicts.
