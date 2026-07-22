
# `cli/main.py`

## High-Level Purpose

This file is a **backwards-compatible shim** that serves as a legacy entry point for the CLI. The actual CLI implementation has been moved to `src/cli/main.py`, and this file simply re-exports the `main` function for compatibility with existing scripts and workflows that invoke `python -m cli.main`.

## File Content (verbatim)

```python
"""Backwards-compatible shim â€” CLI entry point moved to src.cli.main."""

import sys

from src.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
```

## Functions

| Name | Signature | Description |
|------|-----------|-------------|
| `main` | Imported from `src.cli.main` | The actual CLI entry point function. |

## Module-Level Attributes

| Name | Type | Value | Description |
|------|------|-------|-------------|
| `__doc__` | `str` | `"Backwards-compatible shim..."` | Module docstring explaining the file's purpose. |

## Imports

| Module | Purpose |
|--------|---------|
| `sys` | Provides `sys.exit()` for process exit. |
| `src.cli.main` | Imports the actual `main` function from the new location. |

## Architectural Patterns & Observations

| Aspect | Observation |
|--------|-------------|
| **Shim / Compatibility Layer** | This file exists solely to maintain backwards compatibility. It allows existing scripts to continue using `python -m cli.main` while the actual implementation lives in `src/cli/main.py`. |
| **No Logic** | The file contains no business logic; it is purely a re-export. |
| **Entry Point** | When run as `__main__`, it invokes `main()` and exits with the returned status code. |

## Dependencies

- `src.cli.main` â€” The actual CLI implementation.

## Related Files

- `src/cli/main.py` â€” The real CLI entry point.
- `launch_cli.sh` â€” Shell script that launches the CLI.





# Structural Summary: `cli/__init__.py`

## High-Level Purpose

This file is the **package initializer** for the `cli` package. Its sole responsibility is to **force UTF-8 encoding on stdout and stderr** before any other module in the package is imported. This is a critical bootstrapping step for the CLI's retro-styled terminal UI, which relies on box-drawing Unicode characters (e.g., â”Œ, â”€, â”) that cannot be represented in the Windows default cp1252 encoding.

The file is designed to be imported **first** when the CLI is launched via `python -m cli.main`, ensuring the encoding fix is in place before `retro_ui` or `menu_renderer` are loaded.

---

## Imports

| Module | Alias | Purpose |
|--------|-------|---------|
| `io`   | â€”     | Provides `TextIOWrapper` for re-wrapping stdout/stderr with UTF-8 encoding. |
| `sys`  | â€”     | Provides access to `sys.stdout`, `sys.stderr`, and `sys.stdout.encoding`. |

---

## Logic / Execution Flow (module-level, no classes or functions)

The file contains **no classes** and **no function definitions**. All logic runs at **module import time** as a side effect of the `import cli` statement.

### Step-by-step flow

1. **Check encoding**  
   `if sys.stdout.encoding and sys.stdout.encoding.upper() not in ("UTF-8", "UTF8", "CP65001"):`  
   - Guard: only proceed if stdout has a known encoding **and** that encoding is not already a UTF-8 variant.
   - `CP65001` is Windows code page for UTF-8.

2. **Re-wire stdout and stderr**  
   Inside the `if` block:
   ```python
   sys.stdout = io.TextIOWrapper(
       open(sys.stdout.fileno(), "wb"),
       encoding="utf-8",
       write_through=True
   )
   sys.stderr = io.TextIOWrapper(
       open(sys.stderr.fileno(), "wb"),
       encoding="utf-8",
       write_through=True
   )
   ```
   - `open(sys.stdout.fileno(), "wb")` â€” re-opens the underlying raw file descriptor in binary-write mode.
   - `io.TextIOWrapper(..., encoding="utf-8", write_through=True)` â€” wraps the binary stream in a UTF-8 text layer. `write_through=True` flushes immediately on every write, avoiding buffering issues.

3. **Fallback on failure**  
   `except (OSError, io.UnsupportedOperation):`  
   - If the re-wrapping fails (e.g., stdout is not a real file descriptor, or the TTY doesn't support it), the exception is silently caught and the original streams are left untouched.

---

## Key Architectural Patterns

| Pattern | Description |
|---------|-------------|
| **Bootstrapping / Early initialization** | The encoding fix runs at module-import time, before any dependent modules are loaded. This is a deliberate ordering dependency. |
| **Monkey-patching of stdlib streams** | `sys.stdout` and `sys.stderr` are replaced in-place. This is a pragmatic, non-invasive approach that affects all downstream code in the process without requiring changes to how those streams are used. |
| **Defensive guard clause** | The encoding check prevents unnecessary re-wrapping when the environment already uses UTF-8, avoiding potential side effects on systems that work correctly. |
| **Silent fallback** | The `except` clause swallows `OSError` and `io.UnsupportedOperation` without logging or re-raising, ensuring the CLI can still start (albeit with potentially garbled output) on environments where the re-wrap is impossible. |

---

## Dependencies / Side Effects

- **Side effect on import**: Replaces `sys.stdout` and `sys.stderr` with UTF-8 wrappers if the current encoding is not UTF-8.
- **No public API**: The file exports nothing; it exists purely for its import-time side effect.
- **Ordering requirement**: Must be imported before `cli.retro_ui` and `cli.menu_renderer`.

---

## Summary of Signatures

There are **no classes** and **no functions** defined in this file. The entire module is a single imperative block executed at import time.

| Element | Kind | Signature / Description |
|---------|------|------------------------|
| (module-level) | Guard + re-wire | `if sys.stdout.encoding not in ("UTF-8", "UTF8", "CP65001"):` â†’ re-wrap stdout/stderr with UTF-8 `TextIOWrapper` |





# scripts/eval/eval_harness.py

The CLI entry point for the Automated Evaluation Harness.

## Overview
This module provides a command-line interface to execute the evaluation pipeline, manage baselines, and validate the golden dataset.

## Subcommands

### `run`
Executes the evaluation against golden keys.
- `--mode`: `static` (resolution only) or `full` (resolution + test execution).
- `--regenerate`: **(New)** When set, the harness bypasses static captures and runs the actual `TestOrchestrator` pipeline to generate fresh code. This is essential for measuring the impact of RAG or prompt changes.
- `--min-accuracy`: Sets a threshold for the resolution accuracy.

### `baseline`
- `--save`: Captures the current run results and saves them as `baseline.json` for future comparison.

### `compare`
Compares the current run results against the saved baseline, calculating delta (pp) for key metrics.

### `dataset`
- `--validate`: Validates the JSON schema and content of the golden keys in `scripts/eval/dataset/`.

## Workflow for RAG Evaluation
To measure RAG improvements:
1. **Baseline**: `RAG_ENABLED=0 python scripts/eval/eval_harness.py run --mode static --regenerate`
2. **RAG Test**: `RAG_ENABLED=1 python scripts/eval/eval_harness.py run --mode static --regenerate`
3. **Analysis**: `python scripts/eval/eval_harness.py compare`





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





# `scripts/rag_ingest.py`

## High-Level Purpose

RAG Ingestion CLI â€” builds or rebuilds the RAG vector store from two knowledge sources:

1. **Golden patterns** from `scripts/eval/dataset/` â€” verified placeholder â†’ selector mappings (4 sites, 43 placeholders)
2. **Playwright documentation** from `docs/rag_corpus/playwright/` â€” curated markdown files chunked by heading

The store file is written to `<workspace>/evidence/rag_store.db` via `get_storage().rag_path()`.

**Runs fully offline** â€” no LLM or browser needed. SentenceTransformer downloads the embedding model on first use (~80 MB, cached by Hugging Face).

## Module Metadata

- **Lines:** ~270
- **Imports:** `argparse`, `json`, `logging`, `re`, `pathlib.Path`, `src.rag_store`, `src.storage`
- **Spec:** `docs/specs/FEATURE_SPEC_phase3_rag.md` Â§3c
- **Shipped:** 2026-07-21

## CLI Usage

```bash
python scripts/rag_ingest.py --golden --docs    # Full rebuild
python scripts/rag_ingest.py --golden             # Golden patterns only
python scripts/rag_ingest.py --docs               # Docs only
```

## Key Functions

### `load_golden_patterns(dataset_dir: Path) -> list[GoldenPattern]`
Parse golden eval dataset JSON files (`eval-*.json`) into `GoldenPattern` entries. Each dataset file contains `golden_resolutions` â€” a list of criterion-level objects, each with a `placeholders` array containing `action`, `description`, `expected_locator`, `tolerance_selectors`, and `expected_page`.

### `chunk_markdown_file(filepath: Path) -> list[DocChunk]`
Split a markdown file into chunks at `##` heading boundaries. Each chunk targets ~500 tokens with ~50 tokens of overlap between consecutive chunks. The heading path (doc title + section headings) is stored as metadata for prompt citations.

**Chunking strategy:**
- Split on `##` heading boundaries
- Skip bare `# Title` lines (no useful retrieval signal beyond subsequent sections)
- Sections â‰¤ target tokens: use as-is
- Larger sections: split further at paragraph boundaries (`\n\n+`)
- Overlap: keep last ~50 tokens worth of text between consecutive chunks

### `load_docs(docs_dir: Path) -> list[DocChunk]`
Load and chunk all `.md` files from the docs directory. Logs per-file chunk counts.

### `rebuild_store(patterns, docs) -> dict[str, int]`
(Re)build the vector store from patterns and docs. Deletes any existing store file, creates a fresh `MilvusLiteBackend` + `RAGStore`, and upserts both knowledge sources. Returns a count summary: `{"golden": N, "docs": M}`.

### `main(argv=None) -> dict[str, int]`
CLI entry point. Parses args, loads data, calls `rebuild_store()`. Returns count summary.

## Token Estimation

| Constant | Value | Purpose |
|----------|-------|---------|
| `CHARS_PER_TOKEN` | `4` | Rough estimate for GPT-style tokenizers |
| `CHUNK_TARGET_TOKENS` | `500` | Target size per chunk |
| `CHUNK_OVERLAP_TOKENS` | `50` | Overlap between consecutive chunks |

`_estimate_tokens(text)` returns `max(1, len(text) // CHARS_PER_TOKEN)` â€” fast, offline character-based estimate.

## Key Design Decisions

- **Fully offline:** No network calls at runtime (model download cached by Hugging Face)
- **Deterministic rebuild:** Deletes existing store before rebuild â€” no incremental updates (store is small enough for full rebuild)
- **Path resolution relative to repo root:** `Path(__file__).resolve().parent.parent` â€” works regardless of CWD
- **Store location:** `get_storage().rag_path()` â€” workspace-aware via AI-029

## Dependencies

- `src.rag_store` â€” `RAGStore`, `MilvusLiteBackend`, `SentenceTransformerEmbedder`, data classes
- `src.storage.get_storage()` â€” workspace-aware path resolution
- `scripts/eval/dataset/` â€” golden pattern JSON files
- `docs/rag_corpus/playwright/` â€” curated markdown doc files

## Depended On By

- Manual/automated setup step (run once after repo clone or after golden dataset updates)
- `tests/test_rag_ingest.py` â€” 15 unit tests





# `src/cli/color.py` â€” ANSI Colour Helpers

## Purpose

Wraps text in ANSI colour codes when stdout is a terminal (`os.isatty(1)`); falls back to plain text when piped or redirected.

## Internal Helper

### `_c(text: str, code: str) -> str`

Wraps text with `\033[{code}m{text}\033[0m` only when stdout is a TTY.

## Standard Colours

| Function | ANSI Code | Description |
|----------|-----------|-------------|
| `cyan(text)` | `36` | Bright cyan |
| `green(text)` | `32` | Green |
| `red(text)` | `31` | Red |
| `yellow(text)` | `33` | Yellow |
| `bold(text)` | `1` | Bold |

## Retro (CHOICE-style) Phosphor Colours

| Function | ANSI Code | Usage |
|----------|-----------|-------|
| `phosphor_green(text)` | `100` | Bright green â€” selected/highlighted menu items |
| `dim_green(text)` | `2;32` | Dim/half-bright green â€” non-selected items |
| `inverse_green(text)` | `7;32` | Inverse video â€” green background, black text â€” the `>` cursor |
| `phosphor_reset()` | â€” | Returns `\033[0m` reset code as standalone string |

## Design Patterns

- **Conditional formatting**: All colours are no-ops when piped â€” prevents ANSI codes in redirected output.
- **Retro terminal aesthetic**: Phosphor colours match the CHOICE-style retro UI in `retro_ui.py`.





# `src/cli/config.py` â€” CLI Config Re-exports

## Purpose

Backwards-compatible re-export layer. All enums and defaults are defined in `src/config.py`; this module re-exports them so existing CLI code continues to work without updating import paths.

## Re-exports from `src/config`

| Symbol | Type | Description |
|--------|------|-------------|
| `AnalysisMode` | Enum | Test analysis modes |
| `CaptureLevel` | Enum | Screenshot capture levels (`BASIC`, `STANDARD`, `THOROUGH`) |
| `DetectionMode` | Enum | Element detection strategies |
| `JIRA_PROJECT_KEY` | `str` | Default Jira project key |
| `ReportFormat` | Enum | Output report formats |
| `ScreenshotNaming` | Enum | Filename conventions for screenshots |

## Design Patterns

- **Alias module**: Zero logic â€” pure re-exports to maintain import compatibility during refactoring.





# `src/cli/evidence_generator.py` â€” Evidence Generator

## Purpose

Handles screenshot capture and evidence generation for test execution verification, bug reproduction evidence, visual regression testing, and test documentation.

## Data Classes

### `ScreenshotMetadata`

| Field | Type | Description |
|-------|------|-------------|
| `test_case_id` | `str` | Unique test case identifier |
| `timestamp` | `str` | ISO-8601 capture time |
| `file_path` | `str` | On-disk path |
| `capture_stage` | `str` | Stage label (`entry`, `step`, `outcome`, `bug`) |
| `description` | `str` | Human-readable description |
| `file_size` | `int` | Bytes |
| `dimensions` | `tuple[int, int]` | Width Ã— height (from PIL, `(0,0)` if unavailable) |

- `to_dict() -> dict` â€” Serialises metadata to a plain dict.

### `EvidenceCollection`

| Field | Type | Description |
|-------|------|-------------|
| `screenshots` | `list[ScreenshotMetadata]` | Collected screenshots |
| `videos` | `list[dict]` | Video evidence (reserved) |
| `console_logs` | `list[dict]` | Console log entries |
| `network_requests` | `list[dict]` | Network request captures |

- `to_dict() -> dict` â€” Full serialisation including collection timestamp.

## Classes

### `ScreenshotCapturer`

Handles screenshot capture and disk storage.

**Configuration:** Reads `STORAGE_MODE`, `NAMING_CONVENTION`, `CAPTURE_LEVEL`, `SCREENSHOT_DIR` from `src.config`.

**Methods:**

#### `capture(page: Any, test_case: AnalyzedTestCase, capture_stage: str, step_description: str = "") -> str | None`

Captures full-page screenshot from a Playwright page. Saves to disk and records metadata. Returns file path or `None` on failure.

#### `_generate_filename(test_case, capture_stage, step_description) -> str`

Generates filename based on `ScreenshotNaming` convention:
- `SEQUENTIAL`: `{stage}_{NNN}.png`
- `DESCRIPTIVE`: `{title}_{date}.png`
- `HYBRID` (default): `{title_short}_{NNN}_{date}.png`

#### `_save_screenshot(screenshot_bytes, filename, test_title) -> str`

Saves to disk with three storage modes:
- `organized`: `{screenshots_dir}/{test_type}/{date}/{filename}`
- `flatten`: `{screenshots_dir}/{filename}`
- `by_title` (default): `{screenshots_dir}/{title_safe}/{filename}`

#### `_get_screenshot_dimensions(screenshot_bytes) -> tuple`

Uses PIL to extract dimensions. Returns `(0, 0)` if PIL unavailable.

#### `_generate_case_id(title) -> str`

Generates `test_{safe_title}_{timestamp}` identifier.

### `EvidenceGenerator`

Orchestrates comprehensive evidence collection.

**Methods:**

#### `capture_test_evidence(page, test_case, capture_stage="step", step_description="") -> str | None`

Conditional capture based on `CaptureLevel`:
- `BASIC`: `entry`, `outcome` only
- `STANDARD`: `entry`, `step`, `outcome`
- `THOROUGH`: all stages

#### `generate_evidence_summary() -> dict`

Returns serialised evidence summary.

#### `create_visual_report(output_path, test_cases) -> str`

Generates an HTML report with test case details and metadata.

#### `create_evidence_zip(output_path) -> str`

Creates a ZIP archive of all screenshots plus `evidence_summary.json`.

### `BugEvidenceGenerator`

Specialised evidence capture for bug reporting.

**Methods:**

#### `capture_bug_evidence(page, description) -> dict`

Captures screenshot, URL, and timestamp for a bug reproduction.

#### `generate_bug_report(output_path) -> str`

Writes a plain-text bug report with all captured evidence.

## Module-Level Functions

### `capture_screenshot(page, test_case, capture_stage="step") -> str | None`

Convenience wrapper â€” creates an `EvidenceGenerator` and captures a single screenshot.

### `generate_test_evidence(test_cases, output_path) -> str`

Convenience wrapper â€” creates a visual HTML report.

## Dependencies

- `src.analyzer.AnalyzedTestCase`
- `src.cli.config.CaptureLevel`
- `src.config` (constants)
- `PIL` (optional, for dimension extraction)





# `src/cli/input_parser.py` â€” Multi-Format Input Parser

## Purpose

Intelligent parsing of various input formats into standardised `TestCase` objects. Designed with hybrid detection (regex-first, LLM fallback) for speed and accuracy.

## Data Classes

### `TestCase`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `title` | `str` | â€” | Test case title |
| `description` | `str` | â€” | Full description |
| `preconditions` | `list[str]` | `[]` | Prerequisites |
| `test_data` | `dict` | `{}` | Test data inputs |
| `expected_outcome` | `str` | `""` | Expected result |
| `test_type` | `str` | `"functional"` | `happy_path`, `validation`, `error_handling`, `edge_case` |
| `priority` | `str` | `"medium"` | `high`, `medium`, `low` |

- `to_dict() -> dict` â€” Serialises with `created_at` timestamp.
- `to_prompt() -> str` â€” Converts to LLM-friendly prompt string.

### `ParsedInput`

| Field | Type | Description |
|-------|------|-------------|
| `test_cases` | `list[TestCase]` | Extracted test cases |
| `source_format` | `str` | Detected format name |
| `raw_input` | `str` | Original text |
| `metadata` | `dict` | Confidence, detection method, timestamp |

- `to_dict() -> dict` â€” Serialises with raw input sample (truncated to 200 chars).
- `save_to_json(output_path) -> str` â€” Writes to JSON file.

## Classes

### `FormatDetector`

Auto-detects input format using regex patterns.

**Supported formats:**
- **Jira**: `Issue`, `Summary`, `Acceptance Criteria`, `Description` headers
- **Gherkin**: `Feature:`, `Scenario:`, `Given/When/Then`
- **Bullets**: Lines starting with `-`, `*`, or `1.`

#### `detect(text, method=DetectionMode.AUTO) -> tuple[str, float]`

Returns `(format_name, confidence_score)`. Confidence thresholds:
- Jira: 0.9 (3+ pattern matches)
- Gherkin: 0.9 (2+ pattern matches)
- Bullets: 0.8 (3+ bullet lines)
- Plain text: 0.5 (default)

### `PlainTextParser`

Parses plain text user stories.

#### `parse(text) -> list[TestCase]`

Looks for patterns like "As a...", "I want to...", "Users can...". Falls back to treating entire text as a single "Main Flow" scenario.

### `JiraParser`

Parses Jira-style copy-paste format.

#### `parse(text) -> list[TestCase]`

Extracts metadata (issue key, summary), then generates `TestCase` objects from acceptance criteria lines. Uses keyword-based heuristics to determine `test_type`:
- **error_handling**: "error", "invalid", "fail"
- **happy_path**: "valid", "successful", "logged", "redirect"
- **validation**: "empty", "missing", "null"
- **functional**: default

Priority from keywords: "required"/"must" â†’ high, "should" â†’ medium, else â†’ low.

### `GherkinParser`

Parses Gherkin/BDD format.

#### `parse(text) -> list[TestCase]`

Extracts `Scenario:` blocks, splits steps into `Given`/`When`/`Then` groups. Maps `Given` â†’ preconditions, `Then` â†’ expected outcome.

### `BulletParser`

Parses bullet-point style acceptance criteria.

#### `parse(text) -> list[TestCase]`

Extracts lines starting with `-`, `*`, or `1.`. Uses same keyword heuristics as `JiraParser` for test type classification.

### `InputParser`

Main orchestrator â€” multi-format parser with auto-detection.

#### `__init__(detection_method=DetectionMode.AUTO)`

#### `parse(text, explicit_format=None) -> ParsedInput`

Routes to appropriate parser based on auto-detection or explicit override.

#### `parse_json(json_str) -> ParsedInput`

Parses JSON strings â€” handles both list and dict formats (including wrapper `{"test_cases": [...]}`).

#### `parse_and_save(text, output_dir=None) -> str`

Parses and saves to timestamped JSON file in `EVIDENCE_DIR` or custom directory.

## Module-Level Functions

| Function | Description |
|----------|-------------|
| `parse_jira_format(text)` | Convenience wrapper for Jira parsing |
| `parse_gherkin_format(text)` | Convenience wrapper for Gherkin parsing |
| `parse_bullet_format(text)` | Convenience wrapper for bullet parsing |
| `parse_plain_text(text)` | Convenience wrapper for plain text parsing |

## Design Patterns

- **Strategy pattern**: `InputParser._parse_by_format` routes to format-specific parser implementations.
- **Keyword-based classification**: Test type and priority derived from acceptance criterion content.





# `src/cli/main.py` â€” CLI Interactive Entry Point

## Purpose

Menu-driven CLI for the full test generation pipeline. Slim orchestrator that delegates to extracted modules.

## Module Dependencies

| Module | Role |
|--------|------|
| `src/cli/color.py` | ANSI colour helpers |
| `src/cli/session.py` | Session dataclass and factory |
| `src/cli/menu_renderer.py` | Menu rendering, input prompts, LLM config |
| `src/cli/pipeline_runner.py` | Pipeline execution, test running, reports |
| `src/cli/retro_ui.py` | Retro CHOICE-style UI rendering |

## Functions

### `interactive_session() -> None` (async)

Main CLI loop. Builds a dynamic menu based on `Session` state:

**Pre-requirements menu:**
- Configure LLM
- Enter User Story

**Post-requirements menu:**
- Re-configure LLM
- Enter/Re-enter Target URLs
- Consent Mode
- POM Mode (toggle)
- Configure/Re-configure Authentication (shows credential label if set)
- Configure/Re-configure Journey (shows step count if set)
- Build/Review Living Test Plan
- Run Intelligent Pipeline

**Post-pipeline menu:**
- View Generated Code
- View Skeleton
- View Scrape Summary
- Run Generated Tests
- Re-run Failed Only
- Generate Reports
- View Reports
- View Failure Diagnostics
- Export Clean Package

**Persisted-package commands (AI-026):**
- Load Existing Generated Tests
- Show Package Metadata
- Re-run Saved Suite
- View Saved Package Diagnostics
- Clear Loaded Package

### `_apply_session_llm_config(session: Session) -> None`

Propagates session LLM settings to `LLMClient.set_session_provider()` and cloud auth.

### Inline Wrappers

Each menu item has a corresponding `_..._inline` function that calls the appropriate `menu_renderer` or `pipeline_runner` function and mutates the session:

| Wrapper | Delegates To |
|---------|-------------|
| `_configure_llm_inline` | `configure_llm()` |
| `_collect_user_story_inline` | `collect_user_story()` |
| `_collect_urls_inline` | `collect_urls()` |
| `_collect_authentication_inline` | `collect_authentication()` |
| `_collect_journey_inline` | `collect_journey_steps()` |
| `_load_saved_packages_inline` | `list_saved_packages()` + `load_package_manifest()` |
| `_show_package_metadata_inline` | `show_package_metadata()` |
| `_rerun_saved_suite` | `run_saved_test_from_package()` |
| `_view_saved_package_diagnostics_inline` | `view_saved_package_diagnostics()` |
| `_clear_loaded_package` | Resets session package state |

### `cmd_generate(args, parser) -> int`

Legacy parameter-based command. Parses input â†’ runs analysis â†’ generates tests â†’ evidence â†’ reports.

### `main() -> int`

Entry point with `argparse`:
- No arguments â†’ `interactive_session()` (default)
- `generate` subcommand â†’ legacy parameter-based generation
- `test` subcommand â†’ placeholder for test suite

## Legacy Functions

| Function | Description |
|----------|-------------|
| `run_analysis(parsed)` | Runs `KeywordAnalyzer.analyze_parsed()` |
| `run_generation(parsed, output_dir, url)` | Orchestrates test generation via `TestCaseOrchestrator` |
| `run_evidence_generation(output_dir)` | Generates evidence via `EvidenceGenerator` |
| `generate_reports_legacy(parsed, analysis_result, output_dir)` | Generates Jira reports |

## Architecture

- **Slim orchestrator**: Main loop is purely routing â€” all logic lives in `menu_renderer` and `pipeline_runner`.
- **UTF-8 handling**: Dual encoding fix (module-level + `__init__` import) for Windows Git Bash.
- **Context-sensitive menu**: Items appear/disappear based on `Session` state flags.





# `src/cli/menu_renderer.py` â€” CLI Menu Rendering and Input Helpers

## Purpose

Renders a CHOICE-inspired retro terminal UI: green-on-black phosphor aesthetic with box-drawing borders and a `>` selection indicator. Handles all input logic (LLM config, user story, URLs, auth, journey).

## Terminal Input Handling

### Git Bash Detection

#### `_running_in_git_bash() -> bool`

Checks `terminal_adapter.terminal.running_in_git_bash()`. In Git Bash, `msvcrt` functions don't work â€” must use `select`-based fallback.

### Input Drain Functions

| Function | Purpose |
|----------|---------|
| `_drain_stdin_immediate()` | Non-blocking drain using `select.select` with 0 timeout |
| `_flush_msvcrt_buffer()` | Quick-flush residual keystrokes via `msvcrt` (no-ops in Git Bash) |
| `_drain_msvcrt_buffer_aggressive()` | Aggressive drain for multi-line paste |
| `_read_key()` | Single keypress via `msvcrt` (Windows) or `select` fallback (Git Bash) |
| `_read_key_git_bash()` | Non-blocking reader using background thread + `select` |

### `set_terminal_adapter(adapter: TerminalAdapter) -> None`

Replaces the active terminal adapter (for testing/injection).

## Menu Functions

### `print_menu(options, prompt="Choose an option", shortcuts=None) -> int`

Renders a numbered retro menu and returns 0-based index. Supports:
- Arrow keys (Up/Down to navigate, Enter to select)
- Numbered input (`1`, `2`, etc. + Enter)
- Shortcut keys (single-letter keys from `shortcuts` list)
- `Q` key always available as Quit (returns `-1`)

### `print_header(title, subtitle="") -> None`

Prints a CHOICE-style section header with box-drawing borders. Clears screen first.

### Text Input

| Function | Description |
|----------|-------------|
| `read_non_empty(prompt_text)` | Blocks until non-empty input |
| `read_optional(prompt_text, default="")` | Returns `default` on empty input |

## LLM Configuration

### `configure_llm(provider, base_url, model_name) -> tuple[str, str, str]`

Interactive LLM provider picker. Returns `(provider_key, url, model_name)`.

**Provider options:**
1. Ollama (`localhost:11434`)
2. LM Studio (`localhost:1234`)
3. OpenAI-Compatible (`localhost:8080`)
4. OpenAI Cloud (`api.openai.com`)

Auto-detects available models via HTTP GET to provider's `/v1/models` or `/api/tags` endpoint. For cloud OpenAI, prompts for API key via `getpass`.

### `_get_available_models(provider_name, provider_url) -> list[str]`

HTTP-based model discovery for each provider type.

### `_prompt_openai_api_key() -> str`

Prompts for cloud OpenAI API key. Reuses existing env var if present.

## User Story Collection

### `collect_user_story() -> str`

Interactive input with three modes:
1. Paste text (multi-line, ends on empty line or EOF)
2. Upload file (reads from path)
3. Load baseline (pre-defined automationexercise.com user story)

## URL Collection

### `collect_urls() -> tuple[str, str]`

Returns `(starting_url, additional_urls)`. Supports manual entry or baseline load.

### `parse_target_urls(base_url, urls_input) -> list[str]`

Merges base URL and additional URLs into a deduplicated list.

## Consent Mode

### `collect_consent_mode() -> str`

Returns one of: `"auto-dismiss"`, `"leave-as-is"`, `"test-consent-flow"`.

## Authentication / Journey

### `collect_authentication() -> dict[str, str] | None`

Interactive credential profile builder. Returns `{"label", "username", "password"}` or `None` to skip.

### `collect_journey_steps() -> list[dict[str, str]]`

Interactive journey step builder. Supports actions: `navigate`, `click`, `fill`, `wait`, `scrape`. Each step has `action`, `description`, `selector`, `text`, `url` fields.

## Saved Package Management (AI-026)

### `list_saved_packages() -> list[dict[str, str]]`

Discovers saved test packages in `generated_tests/`. Returns summary dicts with `name`, `created_at`, `test_count`, `run_count`, `path`.

### `select_saved_package(packages) -> int`

Renders a numbered list of saved packages and returns the selected index.

### `show_package_metadata(package) -> None`

Displays package metadata from `package_manifest.json`.

## Utility

### `open_file(path) -> None`

Opens a file using the system default application (`os.startfile` on Windows, `open` on macOS, `xdg-open` on Linux).





# `src/cli/pipeline_runner.py` â€” CLI Pipeline Execution

## Purpose

Handles pipeline execution, test running, and report generation for the CLI. Extracted from `cli/main.py` for easier debugging â€” pure extraction, no refactoring.

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

Phase 2 of the ML Engineering roadmap â€” see `src/self_healing.py`.





# `src/cli/report_generator.py` â€” Report Generator

## Purpose

Generates test execution reports in multiple formats: Confluence-compatible HTML, Jira XML, JSON, and Markdown. Used by CLI for legacy report generation (new pipeline uses `PipelineReportService`).

## Data Classes

### `JiraTestCase`

| Field | Type | Description |
|-------|------|-------------|
| `key` | `str` | Unique Jira key (e.g., `TEST-TC-0001`) |
| `summary` | `str` | Test case title |
| `description` | `str` | Full description |
| `test_steps` | `str` | Formatted HTML test steps |
| `expected_results` | `str` | Formatted HTML expected results |
| `screenshots` | `list[str]` | Screenshot paths |
| `execution_status` | `str` | `UNEXECUTED`, `PASSED`, `FAILED`, `BLOCKED`, `SKIPPED` |
| `attachments` | `list[str]` | File attachments |
| `custom_fields` | `dict` | Extra metadata (e.g., `failure_reason`) |

- `to_dict() -> dict` â€” Serialises for JSON output.

### `TestExecutionResult`

| Field | Type | Description |
|-------|------|-------------|
| `test_case` | `AnalyzedTestCase` | The analysed test case |
| `execution_time` | `float` | Duration in seconds |
| `status` | `str` | `PASSED`, `FAILED`, `BLOCKED`, `SKIPPED` |
| `failure_reason` | `str | None` | Root cause of failure |
| `screenshots` | `list[str]` | Screenshot paths |
| `console_logs` | `list[str]` | Console log entries |
| `network_errors` | `list[str]` | Network error entries |

## Class: `JiraReportGenerator`

### `__init__(output_dir="jira_reports")`

Creates output directory if it doesn't exist.

### `create_test_case(analyzed_case, screenshot_paths=None) -> JiraTestCase`

Converts an `AnalyzedTestCase` to a `JiraTestCase` with formatted steps and expectations.

### `add_execution_result(test_case, result) -> None`

Attaches execution status and screenshots to a test case.

### `generate_confluence_html(output_path) -> str`

Generates a Confluence-compatible HTML report with:
- Summary section (total/passed/failed/skipped counts)
- Per-test case cards with status colours
- Embedded screenshot references

### `generate_jira_xml(output_path) -> str`

Generates XML for Jira import with CDATA-wrapped descriptions.

### `save_test_cases(format: ReportFormat) -> str`

Routes to format-specific output:

| Format | Output |
|--------|--------|
| `CONFLUENCE` | HTML report |
| `JIRA_XML` | XML for Jira import |
| `JSON` | Structured JSON |
| `MARKDOWN` | Markdown document |
| `LOCAL` | HTML (same as Confluence) |
| `JIRA` | Markdown (Jira-friendly) |
| `SHAREABLE` | Markdown (shareable format) |





# `src/cli/retro_ui.py` â€” CHOICE-Style Retro Terminal UI

## Purpose

Renders green-on-black, box-drawing menus reminiscent of the classic CHOICE mainframe menu system. Cross-platform using ANSI escape codes â€” no curses dependency.

## Screen Management

| Function | Description |
|----------|-------------|
| `clear_screen()` | Clears terminal (`\033[H\033[J`) or writes `=` separator when piped |
| `move_cursor(x, y)` | Absolute cursor positioning (`\033[{y};{x}H`) |
| `hide_cursor()` | Hides terminal cursor (`\033[?25l`) |
| `show_cursor()` | Shows terminal cursor (`\033[?25h`) |

All functions detect TTY vs pipe â€” non-TTY output uses fallback separators for CI readability.

## Box Drawing

### `_BoxChars` dataclass

Unicode box-drawing characters: `â”Œ`, `â”`, `â””`, `â”˜`, `â”€`, `â”‚`, `â”¤`, `â”œ`, `â”¬`, `â”´`, `â”¼`.

### `_color_line(line, bright=False) -> str`

Applies green ANSI colour to an entire line. Wraps the full line in one ANSI pair to avoid per-character escapes breaking border alignment.

### `_visible_len(text) -> int`

Strips ANSI escapes and returns visible character length.

### Width helpers

| Function | Description |
|----------|-------------|
| `_terminal_width()` | Actual terminal width (default 78) |
| `_effective_width()` | Usable width minus 2-column border margin (min 40) |

## Colour Helpers

| Function | ANSI Code | Usage |
|----------|-----------|-------|
| `_green(text, bright=False)` | `32` / `1;32` | Standard / bold green |
| `_dim(text)` | `2` | Half-bright |
| `_bold(text)` | `1` | Bold |
| `_inverse(text)` | `7;32` | Inverse video (green bg, black fg) |

## Public API

### `render_header(title, subtitle="") -> None`

Renders a CHOICE-style header box with title and optional subtitle:
```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚  AI PLAYWRIGHT TEST GENERATOR                              â”‚
â”‚  Generate Playwright tests from user stories with AI       â”‚
â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
```

### `render_menu(items, selected=0, group_labels=None) -> None`

Renders numbered menu items with `>` selection indicator. Selected item in inverse video + bright green; others in standard green.

### `render_state(state_lines) -> None`

Renders dim green key-value state summary (e.g., `LLM : ollama / qwen3.5:35b`).

### `render_shortcut_bar(shortcuts) -> None`

Renders a bottom shortcut bar with `[key]label` pairs, truncated to fit terminal width.

### `render_separator() -> None`

Horizontal rule inside a box: `â”‚â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”‚`

### `render_status_bar(message, shortcuts=None) -> None`

Full screen wrapper: header + message + shortcut bar.

## Text Input

### `prompt_input(prompt_text, default="") -> str`

Retro-styled input prompt. Returns `default` on empty input.

### `prompt_non_empty(prompt_text) -> str`

Like `prompt_input` but rejects empty values with a retry loop.





# `src/cli/run_results_display.py` â€” Structured Run Results Display

## Purpose

ANSI-formatted rendering of pytest run results for the CLI. Includes metrics summary, per-test table, failure classification, and re-run suggestions.

## Functions

### `_status_badge(status: str) -> str`

Returns a coloured status badge: `[PASS]` (green), `[FAIL]` (red), `[ERROR]` (red), `[SKIP]` (yellow).

### `render_run_metrics(run: RunResult) -> None`

Single-line coloured summary:
```
âœ… Run Results: âœ… 5 passed, 1 failed, 0 errors, 2 skipped in 12.34s
```

Uses `phosphor_green` for the overall badge when all tests pass.

### `render_results_table(run: RunResult) -> None`

ASCII table of per-test results:
```
  STATUS   TEST NAME                                DUR
  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  [PASS]   test_01_navigate_to_home                0.45s
  [FAIL]   test_02_login_with_valid_credentials     1.23s
           AssertionError: Expected "Welcome" to be visible...
```

- Dynamic column width (clamped 40â€“80 chars)
- Failed tests show truncated error messages (3 lines max)

### `render_failure_details(run: RunResult) -> None`

Classified failure details using `classify_failure()`:
```
  Failure Classification:
  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  [1] test_02_login_with_valid_credentials
      Category:  locator_timeout
      Locator:   `input[name="email"]`
      Suggestion: Check that the element exists on the page...
```

### `_suggestion_for_category(category: FailureCategory) -> str`

Returns human-readable remediation suggestions:

| Category | Suggestion |
|----------|-----------|
| `LOCATOR_TIMEOUT` | Check element existence; increase timeout or use fallback |
| `STRICT_VIOLATION` | Make locator more specific (add ID/data-testid) |
| `NAVIGATION_ERROR` | Verify URL, check redirects/auth requirements |
| `ASSERTION_FAILURE` | Check for page state changes or dynamic content |
| `OTHER` | Review error message |

### `render_raw_output(run: RunResult, expanded=False) -> None`

Prints raw pytest output. If `expanded=False`, prompts user with `[y/N]` first.

### `render_run_results(run: RunResult, show_raw=False) -> None`

Combined display: metrics â†’ table â†’ failure details â†’ optional raw output.

### `render_run_history_summary() -> None`

Displays run history using `format_full_history_summary()` from `src.run_history_cli`.





# `src/cli/session.py` â€” CLI Session State Management

## Purpose

Holds all mutable state across interactive prompts so the main menu loop and pipeline handlers share a single, well-typed context.

## Data Class: `Session`

### Pipeline Artifacts

| Field | Type | Description |
|-------|------|-------------|
| `pipeline_results` | `str \| None` | Generated test code |
| `pipeline_skeleton` | `str` | Pre-resolution skeleton |
| `pipeline_saved_path` | `str \| Path` | Output directory path |
| `pipeline_manifest_path` | `str` | Package manifest path |
| `pipeline_error` | `str` | Last error message |
| `pipeline_unresolved` | `list[str]` | Unresolved placeholders |
| `pipeline_scraped_pages` | `dict[str, list[dict]]` | Scraped DOM per URL |
| `pipeline_urls` | `list[str]` | URLs that were scraped |
| `pipeline_criteria` | `str` | Acceptance criteria text |
| `pipeline_conditions` | `list[TestCondition]` | Derived test conditions |
| `pipeline_run_result` | `RunResult \| None` | Latest pytest results |
| `pipeline_run_output` | `str` | Raw pytest output |
| `pipeline_run_command` | `str` | pytest command string |
| `pipeline_run_return_code` | `int \| None` | Exit code |

### Reports

| Field | Type | Description |
|-------|------|-------------|
| `pipeline_local_report` | `str` | Local report content |
| `pipeline_jira_report` | `str` | Jira report content |
| `pipeline_html_report` | `str` | HTML report content |
| `pipeline_local_report_path` | `str` | File path |
| `pipeline_jira_report_path` | `str` | File path |
| `pipeline_html_report_path` | `str` | File path |

### Test Plan

| Field | Type | Description |
|-------|------|-------------|
| `test_plan` | `TestPlan \| None` | Living test plan |
| `plan_confirmed` | `bool` | Signed-off flag |

### LLM Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | `str` | `""` | Provider key (`ollama`, `lm-studio`, etc.) |
| `provider_base_url` | `str` | `""` | Base URL |
| `model_name` | `str` | `""` | Model identifier |

### Target Site

| Field | Type | Default |
|-------|------|---------|
| `starting_url` | `str` | `""` |
| `additional_urls` | `str` | `""` |

### Pipeline Settings

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `consent_mode` | `str` | `"auto-dismiss"` | Consent banner handling |
| `pom_mode` | `bool` | `False` | Page Object Model generation |

### Requirements

| Field | Type | Default |
|-------|------|---------|
| `raw_requirements` | `str` | `""` | Raw user story text |

### Authentication / Journey (AI-009 Phase B)

| Field | Type | Default |
|-------|------|---------|
| `credential_profile` | `CredentialProfile \| None` | `None` |
| `journey_steps` | `list[JourneyStep]` | `[]` |

### Persisted Package State (AI-026)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `loaded_package_manifest` | `PackageManifest \| None` | `None` | Loaded package metadata |
| `loaded_package_run_results` | `list[PersistedRunResult] \| None` | `None` | Run history for loaded package |
| `loaded_package_flaky_tests` | `list[tuple[str, dict]]` | `[]` | Flaky tests in loaded package |

## Factory Functions

### `_env_or_default(key: str, default: str) -> str`

Returns env var value or `default` when empty/missing.

### `_session_defaults() -> dict[str, str]`

Computes defaults from environment variables:

| Env Var | Maps To |
|---------|---------|
| `LLM_PROVIDER` | `session.provider` |
| `OLLAMA_BASE_URL` / `LM_STUDIO_BASE_URL` / `OPENAI_BASE_URL` | `session.provider_base_url` |
| `OLLAMA_MODEL` / `LM_STUDIO_MODEL` / `OPENAI_MODEL` | `session.model_name` |

Falls back to `get_provider_defaults(provider)` from `src.provider_config`.

### `create_session() -> Session`

Factory that creates a `Session` populated with environment-based defaults.





# `src/cli/terminal_adapter.py` â€” Terminal Abstraction

## Purpose

Centralises TTY/PTY handling for key reading and buffer flushing. Provides a single `terminal` module-level instance used by CLI code, making TTY interaction testable via `QueueTerminal`.

## Class: `TerminalAdapter`

### `running_in_git_bash() -> bool`

Detects Git Bash (MINGW64) via `MSYSTEM` or `MSYS_WINVERSION` environment variables. In Git Bash, `msvcrt` functions don't work â€” must use `select`-based fallback.

### `flush() -> None`

Drains residual keystrokes from `msvcrt` buffer (up to 10 pending chars via `kbhit`/`getwch`). No-ops in Git Bash.

### `read_key() -> str`

Platform-aware single keypress reader:

**Windows (native):**
- Uses `msvcrt.getwch()`
- Detects arrow keys via `\x00`/`\xe0` prefix + `H` (Up â†’ `^`) / `P` (Down â†’ `v`)
- Falls back to `sys.stdin.read(1)`

**Git Bash:**
- Uses `_read_key_git_bash()` â€” threaded `select`-based byte-level read
- Fast path: direct `sys.stdin.readline()` (works for StringIO tests and piped input)
- Slow path: background thread with `os.read()` and 0.5s select timeout, 3s total timeout

### `_read_key_git_bash() -> str`

Threaded key reader for Git Bash. Collects bytes from stdin, handles escape sequences (`\x1b[`), and returns normalised key tokens.

### `_normalize_git_bash_input(raw: str) -> str`

Normalises raw input:
- `\r`, `\n`, `\r\n` â†’ `\r`
- `\x1b[A` â†’ `^` (Up arrow)
- `\x1b[B` â†’ `v` (Down arrow)
- `\x1bOA` / `\x1bOB` â†’ `^` / `v` (alternate arrow key sequences)

## Module-Level Instance

```python
terminal = TerminalAdapter()
```

Singleton used by `menu_renderer.py`. Can be replaced via `set_terminal_adapter()` for testing.





# `src/cli/testing_terminal.py` â€” Testing Terminal Adapter

## Purpose

Queue-based terminal input for automated tests. Allows headless tests to drive interactive menus without a PTY.

## Class: `QueueTerminal(TerminalAdapter)`

Extends `TerminalAdapter` with a simple string queue.

### `__init__(inputs=None, git_bash=False)`

| Parameter | Description |
|-----------|-------------|
| `inputs` | Iterable of strings â€” `read_key()` returns them in order |
| `git_bash` | If `True`, simulates Git Bash environment |

### `read_key() -> str`

Pops and returns the first item from the queue. Returns `""` when empty.

### `push(value: str) -> None`

Appends a single value to the queue (for mid-test injection).

### `extend(values: Iterable[str]) -> None`

Extends the queue with multiple values.

### `flush() -> None`

No-op (no actual terminal buffer to flush).

## Usage

```python
from src.cli.terminal_adapter import terminal
from src.cli.testing_terminal import QueueTerminal
from src.cli.menu_renderer import set_terminal_adapter

adapter = QueueTerminal(inputs=["\n", "1", "\r", "Q"])
set_terminal_adapter(adapter)
# Now interactive menus will consume from the queue
```





# `src/cli/test_case_orchestrator.py` â€” Test Case Orchestrator

## Purpose

Manages orchestration of test generation workflow: parsing â†’ analysis â†’ dependency ordering â†’ file generation. Uses the same pipeline as the Streamlit app (`src.orchestrator.TestOrchestrator`) for feature parity.

## Data Class: `TestOrchestrationResult`

| Field | Type | Description |
|-------|------|-------------|
| `generated_files` | `list[str]` | Paths to generated test files |
| `summary` | `dict` | Orchestration summary |
| `errors` | `list[str]` | Error messages |

- `to_dict() -> dict` â€” Serialises with timestamp.

## Class: `TestCaseOrchestrator`

### `__init__(analysis_mode=AnalysisMode.FAST)`

Initialises with a `KeywordAnalyzer` instance.

### `process(raw_input, explicit_format=None, url=None, output_dir="generated_tests") -> TestOrchestrationResult`

Full pipeline: parse â†’ analyze â†’ order â†’ generate. Accepts raw text input.

### `process_parsed(parsed, url=None, output_dir="generated_tests") -> TestOrchestrationResult`

Same as `process` but accepts a pre-parsed `ParsedInput` object.

### Private Methods

#### `_analyze_input(parsed) -> AnalysisResult`

Runs `KeywordAnalyzer.analyze()` on each test case in the parsed input.

#### `_order_test_cases(cases) -> list[AnalyzedTestCase]`

Topological sort by dependencies:
1. Cases with no dependencies first
2. Then cases whose dependencies are satisfied
3. Within same level: ordered by complexity (low â†’ high)

#### `_check_dependencies_satisfied(case, completed_ids) -> bool`

Checks if `AnalyzedTestCase.dependencies` are met.

#### `_complexity_score(complexity: str) -> int`

Maps `"low" â†’ 1`, `"medium" â†’ 2`, `"high" â†’ 3`.

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
- "navigate"/"go to"/"open" â†’ `page.goto()`
- "login"/"sign in" â†’ fill credentials + click login
- "form"/"fill" â†’ `page.fill()` for suggested data
- "click"/"submit" â†’ `page.click()`
- "search" â†’ fill + click search

#### `_sanitize_name(name) -> str`

Converts arbitrary text to valid Python identifier.

#### `_extract_url(text) -> str | None`

Regex-based URL extraction.

#### `_create_summary(analysis, files) -> dict`

Creates orchestration summary with counts, file names, complexity distribution, etc.





# `src/cli/__init__.py` â€” CLI Module Entry Point

## Purpose

UTF-8 encoding fix for Windows Git Bash (MINGW64). This file is imported **first** when `python -m cli.main` runs to force UTF-8 output before any other CLI module loads.

## Problem Solved

On Windows Git Bash, `sys.stdout.encoding` defaults to `cp1252`, which cannot encode box-drawing characters (`â”Œ`, `â”€`, `â”`, etc.) used by the retro UI (`src/cli/retro_ui.py`) and menu renderer.

## Mechanism

Checks if stdout encoding is **not** UTF-8/UTF8/CP65001. If so, re-wraps `sys.stdout` and `sys.stderr` as `io.TextIOWrapper` with UTF-8 encoding and `write_through=True`.

Catches `OSError` / `io.UnsupportedOperation` silently when stdout is already a TTY or pipe (cannot be re-wrapped).

## Key Notes

- Must be imported before `retro_ui` or `menu_renderer`.
- No-ops on native Linux/macOS environments (already UTF-8).





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





# `src/ui/shared.py` â€” Shared UI Constants and Helpers

## Purpose

Shared constants and helper functions for Streamlit UI modules. Manages session state key whitelisting to prevent Streamlit's "cannot be modified after widget instantiation" crash.

## Constants

### `PIPELINE_KEYS: set[str]`

Whitelist of session state keys the pipeline is allowed to overwrite. Includes all `pipeline_*` keys:
- `pipeline_results`, `pipeline_skeleton`, `pipeline_saved_path`, `pipeline_manifest_path`
- `pipeline_error`, `pipeline_unresolved`, `pipeline_scraped_pages`, `pipeline_urls`
- `pipeline_criteria`, `pipeline_conditions`
- `pipeline_run_result`, `pipeline_run_output`, `pipeline_run_command`, `pipeline_run_return_code`
- `pipeline_local_report`, `pipeline_jira_report`, `pipeline_html_report`
- `pipeline_local_report_path`, `pipeline_jira_report_path`, `pipeline_html_report_path`

## Functions

### `sync_pipeline_keys(session: PipelineSessionState) -> None`

Syncs pipeline-managed keys from a `PipelineSessionState` wrapper back to `st.session_state`. Uses the `PIPELINE_KEYS` whitelist to avoid overwriting widget-owned keys (which would crash Streamlit).

### `store_run_report(*, criteria_text, generated_code, run_result, saved_path) -> None`

Builds and stores the report bundle after a test run:
1. Persists `RunResult` to SQLite via `persist_run_result()`
2. Creates a `PipelineSessionState` from current `st.session_state`
3. Builds report bundle via `build_report_bundle()`
4. Stores bundle via `store_report_bundle()`
5. Syncs keys back to `st.session_state`





# `src/ui/ui_downloads.py` â€” Report Download Buttons

## Purpose

Streamlit component that renders download buttons for all generated reports.

## Class: `RenderDownloads`

### `render() -> None` (static)

Renders a 4-column row of download buttons:

| Button | File | MIME | Data Source |
|--------|------|------|-------------|
| Download Manifest | `scrape_manifest.json` | `application/json` | Reads file from `pipeline_manifest_path` |
| Download Local Report | `report_local.md` | `text/markdown` | `pipeline_local_report` |
| Download Jira Report | `report_jira.md` | `text/markdown` | `pipeline_jira_report` |
| Download HTML Report | `report.html` | `text/html` | `pipeline_html_report` |

Buttons are disabled when the corresponding session state key is empty.

Also displays report file paths as `st.caption` when available.





# `src/ui/ui_evidence.py` â€” Evidence Viewer

## Purpose

Streamlit component for viewing test execution evidence: annotated screenshots, Gantt timelines, coverage heatmaps, and run history charts.

## Class: `EvidenceViewer`

### `__init__(base_dir: Path)`

Initialises with the base output directory (typically `generated_tests/`).

### `render() -> None`

Renders the evidence viewer section with 4 tabs:

1. **Annotated Screenshot**: Selectable evidence sidecars with view modes (annotated/heatmap/clean)
2. **Gantt Timeline**: Plotly Gantt chart with grouping modes and execution details
3. **Coverage Heat Map**: Story confidence heatmap with tester-confirmed/unreviewed/gap metrics
4. **Run History**: Stacked bar chart with pass-rate overlay and flaky test detection

Plus a suite heatmap overview section.

### `_render_annotated_screenshot(sidecars) -> None`

Dropdown to select an evidence sidecar. View modes:
- **annotated**: Numbered step overlays on screenshots
- **heatmap**: Density rings showing interaction hotspots
- **clean**: Screenshot only, no annotations

Uses `generate_annotated_journey()` to produce HTML rendered via `st.components.v1.html()`.

### `_render_gantt_timeline(evidence_dirs) -> None`

Gantt chart from evidence data:
- **Grouping modes**: `condition_type`, `sprint`, `source`
- Summary metrics: fastest test, slowest test, coverage
- Condition metadata from `test_plan.conditions` (type, sprint, source)
- Test execution details panel with sidecar step-by-step view
- Raw execution data table (sortable)

### `_render_sidecar_details(sidecar) -> None`

Detailed view of a single evidence sidecar:
- Condition ref, story ref, status, duration, test name
- Step-by-step breakdown with pass/fail icons and error messages

### `_render_coverage_heatmap(evidence_dirs) -> None`

Story confidence heatmap:
- Metrics: total stories, tester confirmed, gaps/failures, unreviewed
- Plotly heatmap visualisation
- Detailed dataframe with per-story pass/fail/skip counts

### `_render_suite_heatmap(sidecars, evidence_dirs) -> None`

Suite-wide coverage overview:
- Extracts unique URLs from all evidence sidecars (navigate steps)
- Selectable page URL with full-page heatmap rendering

### `_render_run_history() -> None`

Run history with Plotly chart:
- Scope selector: All packages or individual package
- Metrics: total runs, avg pass rate, total passed/failed
- Flaky test checkbox with expanded dataframe
- Last run comparison (improved/regressed/new failures)

### `_filter_runs_by_package(runs, scope) -> list`

Filters runs by test package scope. Returns all runs when scope is `"All"`.

### `_render_run_comparison(comparison) -> None`

Renders improved (âœ“), regressed (âœ—), and new failures (âš ) lists.





# `src/ui/ui_journey.py` â€” Credential Profiles and Journey Builder UI

## Purpose

Streamlit components for authentication credential profiles and journey step builder. Used for navigating dynamic or authenticated pages during scraping.

## Type Aliases

| Alias | Description |
|-------|-------------|
| `_CredentialProfileDict` | `dict[str, str]` with keys: `label`, `username`, `password` |
| `_JourneyStepDict` | `dict[str, str]` with keys: `action`, `url`, `selector`, `text`, `label`, `description` |

## Functions

### `render_credential_profiles() -> CredentialProfile | None`

Renders the authentication section (expander) with:
- Toggle to enable/disable authentication
- Dynamic profile list (add/remove)
- Per-profile fields: label, username, password (masked)
- Active profile selector (dropdown)
- Returns `CredentialProfile` for the active profile, or `None` if disabled

Credentials stored in `st.session_state` only â€” never persisted to disk.

### `render_journey_builder(additional_urls: list[str]) -> list[JourneyStep] | None`

Renders the journey builder section with:
- "Build from URL list" button (auto-populates goto+capture steps)
- Toggle to enable/disable journey builder
- Dynamic step list with add/remove
- Returns list of `JourneyStep` objects, or `None` if disabled

**Step types:**
- `goto`: URL + description
- `click`: selector + description
- `fill`: selector + value (supports `{{username}}`/`{{password}}` templates)
- `capture`: label + description (marks a page for DOM scraping)
- `wait`: selector (optional) + duration in seconds

### `_render_single_step(idx, step) -> _JourneyStepDict`

Renders a single journey step row with action selector and contextual fields.

### `_urls_to_journey_step_dicts(urls) -> list[_JourneyStepDict]`

Converts a URL list into `goto` + `capture` step pairs.

### `_dict_to_journey_step(d) -> JourneyStep`

Converts a session state dict to `JourneyStep`. Maps UI action names: `goto` â†’ `navigate`.





# `src/ui/ui_requirements.py` â€” Requirements Input Panel

## Purpose

Streamlit component for entering user story requirements via text paste or file upload.

## Class: `RequirementsInput`

### Constants

| Constant | Description |
|----------|-------------|
| `BASELINE_STARTING_URL` | `"https://automationexercise.com/"` |
| `BASELINE_ADDITIONAL_URLS` | `""` |
| `BASELINE_REQUIREMENTS` | Pre-defined automationexercise.com user story with 8 acceptance criteria |

### `render(base_url, urls_input) -> tuple[str, str, str, str]` (static)

Renders requirements input with two modes:

| Mode | Widget | Description |
|------|--------|-------------|
| Paste Text | `st.text_area` | Free-form requirements input with placeholder example |
| Upload File | `st.file_uploader` | Upload `.md` or `.txt` file, displayed in read-only text area |

Returns `(input_mode, raw_text, base_url, urls_input)`.





# `src/ui/ui_results.py` â€” Results Display Panel and Run Handlers

## Purpose

Streamlit component for displaying pipeline results and running generated tests.

## Class: `ResultsPanel`

### `render_tabs(results, skeleton, saved_path, manifest_path) -> None` (static)

Renders 3 tabs:

| Tab | Content |
|-----|---------|
| Final Code | Python code display + download button + saved path/manifest captions |
| Skeleton | Pre-resolution skeleton code display |
| Scrape Summary | List of scraped URLs with element counts + unresolved placeholders warning |

### `render_run_section() -> None` (static)

Renders "Run Generated Tests" and "Re-run Failed Only" buttons. Both are disabled when `pipeline_saved_path` is empty. Re-run also requires a previous `pipeline_run_result`.

## Functions

### `_handle_run_tests() -> None`

Handles the "Run Generated Tests" button:
1. Calls `PipelineRunService().run_saved_test()`
2. Stores results in `st.session_state` (`pipeline_run_result`, `pipeline_run_output`, etc.)
3. Calls `_store_run_report()`
4. Triggers `st.rerun()`

### `_handle_rerun_failed() -> None`

Handles the "Re-run Failed Only" button:
1. Passes `rerun_failed_only=True` and `previous_run` to `run_saved_test()`
2. Same storage and rerun logic as `_handle_run_tests()`

### `_store_run_report() -> None`

Delegates to `src.ui.shared.store_run_report()` with current session state values.





# `src/ui/ui_run_results.py` â€” Run Results Display, Failure Classification, and Locator Repair

## Purpose

Streamlit component for displaying test run results with failure classification, coverage analysis, locator repair panel, and inline evidence viewer.

## Class: `RunResultsDisplay`

### `render(run_result: RunResult) -> None` (static)

Full run results display:

1. **Command caption**: Shows the pytest command used
2. **Error banner**: If pytest hit collection/import errors
3. **Metrics row**: Total, Passed, Failed, Skipped, Errors (5 columns)
4. **Coverage table**: Criteria-level coverage analysis with pass/fail mapping
5. **Results table**: Per-test results with repair buttons (see `_render_results_table`)
6. **Repair panel**: Shown when user clicks a repair button (see `_render_repair_panel`)
7. **Inline evidence**: Annotated screenshots for just-run tests (see `_render_inline_evidence`)
8. **Pytest output**: Expandable raw output (auto-expanded on errors)
9. **Downloads**: Report download buttons via `RenderDownloads.render()`

**Added 2026-07-20:**
- Self-healing integration: "ðŸ©¹ Self-Heal Failed Tests" button + healing results
- Failed test expanders with error preview, completed steps, full traceback
- Test results table includes Ref column (condition_ref from @pytest.mark.evidence)
- Pytest Output expander opens on any failure (was: only collection errors)

## Functions

### `_render_inline_evidence(run_result) -> None`

Renders inline evidence viewer:
- Loads evidence sidecars from `evidence/` directory
- Filters to only tests that just ran (matches test names from `RunResult`)
- Selectable sidecar with view modes: annotated, heatmap, clean
- Shows step details with pass/fail icons

### `_render_results_table(results) -> None`

Per-test results table with repair buttons:

| Status | Display |
|--------|---------|
| Passed | âœ… icon |
| Failed | âŒ icon + error caption + repair button (if locator failure) |
| Skipped | â­ï¸ icon |

**Repair button logic:**
- `LOCATOR_TIMEOUT` / `STRICT_VIOLATION`: Shows ðŸ”§ Fix locator button â†’ opens repair panel
- `ASSERTION_FAILURE`: Shows info caption (no repair)
- `NAVIGATION_ERROR`: Shows info caption (no repair)

### `_render_repair_panel() -> None`

Dispatcher based on `st.session_state.repair_status`:
- `"waiting"` â†’ `_render_repair_waiting_panel()`
- `"browser_requested"` â†’ `_render_repair_browser_session()`
- `"patched"` / `"error"` â†’ `_render_repair_result_panel()`

### `_render_repair_waiting_panel() -> None`

Shows repair mode UI with failed locator info, test file path, and "Open browser and fix locator" button. Sets `repair_status = "browser_requested"` on click.

### `_render_repair_browser_session() -> None`

Runs a headed browser session via `run_codegen_session()`:
1. Opens browser at the failure URL
2. Waits up to 120s for user to click the correct element
3. Applies the new locator via `LocatorPatch` + `apply_patch_to_file()`
4. Sets `repair_status = "patched"` or `"error"` based on outcome

### `_render_repair_result_panel() -> None`

Shows success/error message with:
- Updated test file viewer (expanded)
- "Run Generated Tests" button (enabled only if patched)
- "Done" button to reset repair state

### `_render_self_healing_results(report: HealingReport) -> None` (added 2026-07-20)

Renders self-healing report after automated repair:
- Metrics: Failures, Fixed, Remaining, Iterations (4 columns)
- Per-patch expanders with diagnosis and diff display
- "ðŸŽ‰ All failures fixed" success or warning for remaining failures
- "ðŸ”„ Re-run Tests" and "ðŸ§¹ Clear Healing Results" buttons

### `_render_failed_tests_repair(results, run_result=None) -> None` (updated 2026-07-20)

Shows expanders for every failed test with:
- Error preview extracted from pytest output or raw output
- **Steps completed before failure** â€” parsed from test source
- Full error output in collapsible sub-expander
- "ðŸ”§ Fix Locator" button for locator-classified failures
- Self-healing button at top of section when failures exist

### `_parse_condition_refs_from_source(source: str) -> dict[str, str]` (added 2026-07-20)

Parses `@pytest.mark.evidence(condition_ref="TC01.05", ...)` decorators to map test function names to their condition references. Used to populate the Ref column in the test results table.

### `_extract_error_from_raw_output(raw_output, test_name) -> str` (added 2026-07-20)

Extracts error details from raw pytest output when `TestResult.error_message` is empty (common for timeouts). Searches the FAILURES block for the test's error.

### `_extract_last_steps_before_failure(source, test_name) -> list[str]` (added 2026-07-20)

Parses test source to find the last completed action steps (Navigate, Click, Fill, Assert) before the failure point. Returns up to 6 steps for context.





# `src/ui/ui_saved_packages.py` â€” Saved Package Loader (AI-026)

## Purpose

Streamlit sidebar and main panel components for loading and re-running saved test packages. Discovers packages in `generated_tests/` via `package_manifest.json`.

## Class: `SavedPackagePanel`

### `render_sidebar() -> None`

Sidebar section:
- Lists all packages with test/run counts
- Selectable dropdown + "Load Package" button
- On load: populates session state with manifest, run results, history, and flaky tests
- Shows loaded summary with metrics and flaky warnings
- "Re-run Saved Suite" button (sets `pipeline_saved_path` and reruns)

### `_render_loaded_summary() -> None`

Sidebar summary of loaded package: name, creation date, story, URL, total runs/passed/failed, flaky test warnings.

### `render_main_panel() -> bool`

Main column detail view (returns `True` if a package is loaded):

**Sections:**
- Package metadata (created, provider, model, URL, file counts)
- User story (expandable)
- Test files (expandable, per-file code viewer)
- Page objects (expandable)
- Additional URLs (expandable)
- Run history table (expandable)
- Flaky tests list (expandable)
- Report paths (expandable)
- Evidence paths (expandable)
- Run buttons: "Run Saved Suite" / "Re-run Failed Only"

### `_render_run_history(runs_data) -> None`

Table with columns: Run ID, Total, Passed, Failed, Skipped, Duration.

### `_render_flaky_tests(flaky) -> None`

Per-test breakdown with pass/fail/skip counts.

### `_handle_rerun_saved_suite(package_root) -> None`

Runs the full saved suite via `PipelineRunService().run_saved_test()`. Stores results and calls `_store_run_report()`.

### `_handle_rerun_failed_only(package_root, previous_run) -> None`

Re-runs only failed tests from the previous run. Passes `rerun_failed_only=True`.

### `_load_previous_run(package_root) -> Any | None`

Loads the most recent run result from the package directory.

### `_store_run_report() -> None`

Delegates to `src.ui.shared.store_run_report()`.





# `src/ui/ui_sidebar.py` â€” Sidebar Configuration Panel

## Purpose

Streamlit sidebar for LLM provider selection and test structure configuration.

## Class: `SidebarConfig`

### `render() -> dict[str, Any]` (static)

Renders the configuration sidebar:

| Widget | Key | Description |
|--------|-----|-------------|
| Selectbox | `provider` | LLM provider (`SUPPORTED_PROVIDERS` with labels from `PROVIDER_LABELS`) |
| Toggle | `pom_mode` | Page Object Model generation (`False` default) |

**Provider options** (from `src.provider_config`):
- Ollama (local)
- LM Studio (local)
- OpenAI-Compatible (local)
- OpenAI (cloud)

**Returns:** `{"provider": str, "pom_mode": bool}`

**POM Mode:** When enabled, generates tests using Page Object Model classes with evidence-aware locators. Stored in `st.session_state.pom_mode`.





# `src/ui/__init__.py` â€” Streamlit UI Module

## Purpose

Package marker for the Streamlit UI rendering modules. Contains no logic â€” signals that `src/ui/` is a Python package.

## Contents

Empty module. Submodules:
- `shared.py` â€” Shared constants and helpers
- `ui_downloads.py` â€” Report download buttons
- `ui_evidence.py` â€” Evidence viewer (screenshots, Gantt, heatmaps, run history)
- `ui_journey.py` â€” Journey builder UI
- `ui_requirements.py` â€” Requirements input panel
- `ui_results.py` â€” Results display panel
- `ui_run_results.py` â€” Run results display
- `ui_saved_packages.py` â€” Saved package management UI
- `ui_sidebar.py` â€” Sidebar configuration





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





# `src/cart_seeding_scraper.py`

## High-Level Purpose

`cart_seeding_scraper.py` provides a specialized journey scraper that ensures the cart has items before scraping cart/checkout pages. Extends `JourneyScraper` to follow a product-selection â†’ add-to-cart â†’ dismiss-modal journey, then navigates to target cart/checkout URLs for scraping.

Added **2026-07-20 (B-022):** Switched from hardcoded selectors to dynamic element discovery via `_discover_selector()`, making it site-agnostic. The cart seeder now works across different e-commerce sites without site-specific CSS selectors.

## Dependencies

- `JourneyScraper` from `src.journey_scraper` â€” base class for stateful journey scraping
- `JourneyStep` from `src.journey_models` â€” step definition for journey actions
- `PRODUCT_SELECTORS`, `ADD_TO_CART_SELECTORS`, `CONTINUE_SHOPPING_SELECTORS` from `src.form_detector` â€” kept for test compatibility, no longer used by `scrape_cart_pages()`

## Classes

### `CartSeedingScraper(JourneyScraper)`

Specialized journey scraper for cart-dependent pages.

**Class-level constants (test compatibility):**
- `PRODUCT_SELECTORS: list[str]`
- `ADD_TO_CART_SELECTORS: list[str]`
- `CONTINUE_SHOPPING_SELECTORS: list[str]`

#### `__init__(self, starting_url: str, products_url: str | None = None, **kwargs: Any) -> None`

Args:
- `starting_url`: Home page URL for session establishment.
- `products_url`: Optional products page URL. Defaults to `urljoin(home_url, "/products")`.

#### `scrape_cart_pages(self, cart_urls: list[str]) -> dict[str, list[dict[str, Any]]]`

Seeds the cart (add item â†’ dismiss confirmation), then scrapes each target URL.

**B-022 change:** Uses dynamic element discovery â€” no hardcoded selectors. Steps:
1. Navigate to products page
2. Click on a product (dynamic discovery via `_discover_selector()`)
3. Click "Add to cart" (dynamic discovery)
4. Capture confirmation popup state
5. Dismiss confirmation modal (dynamic discovery)
6. Wait for modal animation
7. Navigate to and scrape each target cart/checkout URL

Returns `dict[str, list[dict[str, Any]]]` mapping URLs to scraped elements.

#### `_derive_products_url(home_url: str) -> str` (static)

Derives products page URL: `urljoin(home_url, "/products")`

#### `_ensure_full_url(url: str) -> str` (static)

Ensures URL is absolute. Relative URLs are handled by `JourneyScraper._navigate_to()`.





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

## B-021 + B-022 Changes (2026-07-20)

- `_normalize_test_function_names(code)` â€” renames purely descriptive test names to include condition_ref number (e.g., `test_view_cart` â†’ `test_tc01_05_view_cart`). Tests already numbered are left unchanged.
- `replace_token_in_line()` â€” passes through `expect(...)` expressions as-is (URL assertions from B-021) instead of wrapping in `evidence_tracker.*()` calls.





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





# `src/element_matcher.py`

## High-Level Purpose

Multi-pass element matching engine for placeholder resolution. Extracted from `placeholder_orchestrator.py`. Implements a 4-pass resolution pipeline (Pass 0â€“3) for matching placeholder descriptions to scraped DOM elements, plus LLM-based semantic ASSERT resolution (B-020).

## Module Metadata

- **Lines:** ~700
- **Imports:** `re`, `logging`, `typing`, `src.intent_matcher`, `src.locator_builder`, `src.placeholder_resolver`, `src.role_mapper`, `src.semantic_candidate_ranker`, `src.semantic_matcher`
- **Extracted from:** `placeholder_orchestrator.py`

## Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `TEXT_BEARING_ROLES` | `{heading, paragraph, text, status, alert, region, article, listitem, cell, columnheader, rowheader}` | ARIA roles for ASSERT text matching (B-016) |
| `TEXT_BEARING_TAGS` | `{h1-h6, p, span, label, li, td, th}` | HTML tags for ASSERT text matching |
| `MIN_SCORE_FOR_TEXT_FALLBACK` | `5` | Minimum score threshold for text fallback when no LLM selection available (B-020) |

## Class: `ElementMatcher`

### `__init__(self, resolver: PlaceholderResolver, generator: AsyncGeneratorLike | None = None)`
- `resolver`: PlaceholderResolver instance for text matching and ranking
- `generator`: B-020 LLM generator for semantic candidate ranking (nullable)

### Resolution Pipeline

**Pass 0 â€” Exact text match:**
- `pass0_exact_text_match(action, description, pages_data) -> dict | None`
- For ASSERT descriptions wrapped in quotes (`ASSERT:"exact text here"`) â€” strips quotes and does literal string equality against element text
- Bypasses all scoring and LLM calls for the simple "verify text is X" case

**Pass 1 â€” Text match:**
- `pass1_text_match(action, description, pages_data) -> dict | None`
- Fast text match for CLICK/FILL â€” returns first element whose normalised text is contained in the description
- ASSERT tokens for page state fall through to scoring path
- Minimum element text length of 3 characters
- R-001: Key phrase extraction for verbose descriptions (quoted phrases, context boundary words)

**Pass 1b â€” ASSERT text match:**
- `pass1_assert_text_match(action, description, pages_data) -> dict | None`
- ASSERT-specific text matching against elements with `TEXT_BEARING_ROLES` or `TEXT_BEARING_TAGS`
- B-016: Filters to display/text roles only

**Pass 2 â€” Structural match:**
- `pass2_structural_match(action, description, pages_data, excluded_selectors=None) -> dict | None`
- Structural attribute match (id, data-test, aria-label, name, class)
- Falls back to text-bearing elements for ASSERT when no structural match found

**Pass 3 â€” Scoring + LLM:**
- `async find_best_element_for_current_page(action, description, pages_data, *, excluded_selectors=None, current_url="", resolved_context=None, golden_patterns=None) -> tuple[dict | None, float, str]`
- **Main entry point** â€” orchestrates all passes + scoring
- Returns `(element, score, source)` where source identifies which pass resolved the match
- **RAG (2026-07-21):** Accepts optional `golden_patterns` from `RAGRetriever` â€” forwarded to `PlaceholderScorer.compute_element_score()` for bonus
- `_resolve_assert_semantically(action, description, candidates, current_url, resolved_context)` â€” LLM-based semantic ASSERT resolution (B-020)

## Module-Level Functions

### `_is_excluded(element, excluded_selectors) -> bool`
Check if element's selector is in the excluded set.

### `_validate_text_match(element, description) -> bool`
Validate that text match element has at least some text content.

### `_log_resolve_pass(element, action, description, pass_name, score=0)`
Standardised logging for resolution results.

### `select_page_loaded_candidate(candidates) -> dict | None`
Select the best candidate from page-loaded detection results.

## Key Design Decisions

- **4-pass pipeline:** Early passes (0-2) are fast/cheap; Pass 3 (scoring + LLM) is the expensive fallback
- **Pass ordering:** exact text â†’ fast text â†’ structural â†’ scoring/LLM
- **B-020:** LLM semantic ranking for ASSERT resolution when generator is provided
- **B-016:** ASSERT text matching filters to display roles (heading, paragraph, text, etc.)
- **RAG integration:** `golden_patterns` kwarg flows through `find_best_element_for_current_page()` â†’ `PlaceholderScorer.compute_element_score()` â€” zero behaviour change when `None`

## Dependencies

- `src.placeholder_resolver.PlaceholderResolver` â€” text matching and ranking
- `src.semantic_candidate_ranker.SemanticCandidateRanker` â€” LLM-based ranking
- `src.semantic_matcher.SemanticMatcher` â€” semantic text matching
- `src.intent_matcher.SemanticFillStrategy` â€” fill strategy detection
- `src.locator_builder.build_robust_locator` â€” locator construction
- `src.role_mapper` â€” role classification utilities

## Depended On By

- `src/placeholder_orchestrator.py` â€” calls `find_best_element_for_current_page()` with golden_patterns
- `tests/test_element_matcher.py` â€” unit tests





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

## B-021 Changes (2026-07-20)

- `IntentStrategy.match()` return type extended: `bool | str | None` (was `bool | None`)
- `PageStateAssertStrategy.URL_SIGNAL = "url"` â€” returned instead of `False` for page-state descriptions
- `IntentMatcher.match()` and `matches()` return types extended to `bool | str`
- When `"url"` is returned, the orchestrator routes to `resolve_url()` for `expect(page).to_have_url(...)` assertions





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

## B-023 Changes (2026-07-20)

- Added `_dismiss_modals(page)` static method â€” dismisses confirmation modals/popups before click steps
- Tries 8 common modal-dismiss selectors ("Continue Shopping", close buttons, modal footers)
- Non-destructive: if no modal is visible, selectors won't match â†’ no-op
- Called alongside `_dismiss_consent_overlays()` before every click step and after navigation
- Eliminates "intercepts pointer events" errors when cart modals block navigation link clicks





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
- **RAG (2026-07-21):** `_build_rag_retriever()` constructs `RAGRetriever` when `RAG_ENABLED=1` env var is set; passed to `PlaceholderOrchestrator` via `rag_retriever` kwarg

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
- **RAG (2026-07-21):** When `RAG_ENABLED=1`, `_build_rag_retriever()` creates a `RAGRetriever` wired to `MilvusLiteBackend` + `SentenceTransformerEmbedder`; passed to `PlaceholderOrchestrator` for golden-pattern retrieval during resolution

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

### `_build_rag_retriever() -> RAGRetriever | None` (static, 2026-07-21)
- Checks `RAG_ENABLED` env var â€” returns `None` when not set or `"0"`
- Constructs `MilvusLiteBackend` at `get_storage().rag_path()` + `SentenceTransformerEmbedder` + `RAGStore`
- Returns `RAGRetriever(store)` when store is non-empty, `None` otherwise
- Graceful degradation: any import/init error logs a warning and returns `None`

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
- **RAG (2026-07-21):** Controlled by `RAG_ENABLED=1` env var. When enabled, golden-pattern retrieval runs during placeholder resolution, feeding `GOLDEN_PATTERN_BONUS` (+20) to element scoring. RAG store must be pre-built via `python scripts/rag_ingest.py --golden --docs`.





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

### `__init__(starting_url=None, credential_profile=None, pom_mode=False, generator=None, rag_retriever=None)`
- `starting_url`: Base URL for session-aware scraping
- `credential_profile`: Credentials for stateful scraping (authenticated flows)
- `pom_mode`: When True, generate tests using evidence-aware POM classes instead of flat `evidence_tracker` calls
- `generator`: LLM generator for semantic candidate ranking (B-020). When None, ASSERT resolution falls back to mechanical `toBeVisible`
- `rag_retriever`: Optional `RAGRetriever` for golden-pattern scoring (Phase 3 RAG, 2026-07-21). When None, RAG is disabled â€” zero behaviour change.

### Properties
- `pom_mode(self) -> bool`: Whether POM-mode output is enabled
- `rag_retriever` â†’ stored as `self._rag_retriever`; accessed via `_retrieve_golden_patterns()`

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

#### RAG Retrieval (Phase 3, 2026-07-21)
- `_retrieve_golden_patterns(action, description) -> list | None`: Queries `RAGRetriever` for golden patterns matching the placeholder. Returns None when RAG is disabled or no patterns found above confidence threshold. Called before `find_best_element_for_current_page()` â€” results are forwarded as `golden_patterns` kwarg.

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
- **B-021 (2026-07-20):** `_is_page_state_assertion()` + URL assertion routing â†’ `expect(page).to_have_url(...)`
- **B-022 (2026-07-20):** Cart-seeding upgrade now always prefers seeded data for `/view_cart` and `/checkout`; product URL detection from scraped data
- **B-023 (2026-07-20):** Modal dismissal integrated via `JourneyScraper._dismiss_modals()`
- **Phase 3 RAG (2026-07-21):** `rag_retriever` kwarg + `_retrieve_golden_patterns()` â†’ golden patterns flow into `ElementMatcher.find_best_element_for_current_page()` â†’ `PlaceholderScorer.compute_element_score()` for +GOLDEN_PATTERN_BONUS
- Consolidated skip logic reduces noise in generated tests





# `src/placeholder_resolver.py`

## High-Level Purpose
Core placeholder resolution engine that matches `{{TOKEN:description}}` tokens against scraped DOM candidates using semantic matching, confidence scoring, and page-context validation.

## Module Metadata
- **Lines:** ~520
- **Imports:** `re`, `logging`, `dataclasses`, `typing`, `src.semantic_matcher`, `src.placeholder_scorers`, `src.page_context_tracker`
- **RAG update:** 2026-07-21 â€” `golden_patterns` optional kwarg on `rank_candidates()`

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
| `rank_candidates(candidates, description, *, golden_patterns=None)` | Scores and ranks candidates; `golden_patterns` (Phase 3 RAG) adds bonus for golden pattern matches |

## Functions

### `resolve_placeholders(code: str, pages: list[PageData]) -> tuple[str, list[PlaceholderContext]]`
Top-level function â€” returns resolved code and context list.

### `extract_placeholders(code: str) -> list[PlaceholderContext]`
Regex-based extraction of `{{TOKEN:description}}` patterns.

## Key Design Decisions
- Token-only placeholders in skeleton phase (no real selectors)
- Page-context validation prevents cross-page mismatches
- Confidence threshold gate before accepting a match
- **RAG golden_patterns (2026-07-21):** Optional kwarg passed through to `PlaceholderScorer.compute_element_score()` â€” advisory bonus, zero behaviour change when None

## Dependencies
- `src.semantic_matcher`, `src.placeholder_scorers`, `src.page_context_tracker`





# `src/placeholder_scorers.py`

## High-Level Purpose
Composite scoring engine for placeholder resolution â€” provides individual testable scoring functions that evaluate candidate elements against placeholder descriptions.

## Module Metadata
- **Lines:** ~520
- **Imports:** `re`, `math`, `dataclasses`, `typing`, `src.semantic_matcher`
- **RAG updates:** 2026-07-21 â€” `GOLDEN_PATTERN_BONUS` constant, `_golden_pattern_bonus()` method, optional `golden_patterns` parameter on `compute_element_score()`

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

## RAG Integration (2026-07-21)

### `GOLDEN_PATTERN_BONUS` (class constant, `int = 20`)
Module-level constant matching `_vision_enriched_bonus` (+20). Strong enough to break ties between similarly scored candidates; won't override structural/id matches (+80) or visibility penalties (-40).

### `_golden_pattern_bonus(element, golden_patterns) -> int`
Static method. Evaluates whether an element's selector matches any retrieved golden pattern:
- **Direct selector match:** `+GOLDEN_PATTERN_BONUS Ã— pattern.confidence`
- **Tolerance/substring match:** `+GOLDEN_PATTERN_BONUS Ã— 0.5 Ã— pattern.confidence`
- **No match:** `0`

### `compute_element_score()` â€” `golden_patterns` parameter
Optional `list[RetrievedPattern]` kwarg. When non-empty, `_golden_pattern_bonus()` is called and the result added to the element's total score.

## Key Design Decisions
- Composable scoring functions â€” each testable in isolation
- Weighted sum model with configurable weights
- Locator type hierarchy mirrors strict-mode reliability
- Golden pattern bonus is advisory â€” zero behaviour change when patterns list is empty/None

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





# `src/provider_config.py` â€” Shared LLM Provider Configuration

## Purpose

Centralised configuration for LLM provider defaults, labels, and OpenAI API key resolution. Used by both CLI (`src/cli/`) and Streamlit (`src/ui/`) to avoid duplicating provider logic.

## Constants

| Constant | Type | Description |
|----------|------|-------------|
| `CLOUD_OPENAI_PROVIDER` | `str` | `"openai"` |
| `LOCAL_OPENAI_PROVIDER` | `str` | `"openai-local"` |
| `SUPPORTED_PROVIDERS` | `tuple[str, ...]` | `("ollama", "lm-studio", "openai-local", "openai")` |
| `PROVIDER_LABELS` | `dict[str, str]` | Human-readable labels for each provider |

## Functions

### `get_provider_defaults(provider: str) -> tuple[str, str]`

Returns `(base_url, model)` defaults for a given provider.

| Provider | Base URL | Default Model |
|----------|----------|---------------|
| `lm-studio` | `http://localhost:1234` | `lmstudio-community/Qwen2.5-7B-Instruct-GGUF` |
| `openai-local` | `http://localhost:8080` | `llama` |
| `openai` | `https://api.openai.com/v1` | `gpt-4o` |
| `ollama` | `http://localhost:11434` | `qwen3.5:35b` |

### `provider_requires_openai_api_key(provider: str) -> bool`

Returns `True` only for the cloud OpenAI provider (`"openai"`).

### `resolve_openai_api_key(*, provider: str, user_api_key: str | None = None) -> str | None`

Resolves the effective OpenAI API key from:
1. Explicit UI input (`user_api_key`)
2. Environment variable `OPENAI_API_KEY`
3. `None` if neither is set, or if the provider doesn't require a key

### `sync_openai_api_key_to_env(provider: str, api_key: str | None) -> None`

Applies a session-scoped OpenAI API key to `os.environ["OPENAI_API_KEY"]`. Never writes to disk â€” purely in-process.

## Design Patterns

- **Configuration centralisation**: Single source of truth for provider defaults, consumed by both UI and CLI code paths.
- **No side effects for non-OpenAI providers**: `resolve_openai_api_key` returns `None` early for local providers, avoiding unnecessary env lookups.





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





# `src/rag_retriever.py`

## High-Level Purpose

Bridges `RAGStore` into the placeholder resolution pipeline. Provides a resolver-friendly API: takes a placeholder description + action type, queries the vector store, returns `RetrievedPattern` objects. The `scoring_bonus_for()` method evaluates whether a DOM element matches a retrieved golden pattern (by selector overlap), returning the bonus amount to add to the element's score.

When the store is `None` (RAG disabled), every method returns empty/no-op â€” zero overhead.

## Module Metadata

- **Lines:** ~100
- **Imports:** `typing.TYPE_CHECKING`, `src.rag_store.RetrievedPattern`, `src.placeholder_scorers.PlaceholderScorer`
- **Spec:** `docs/specs/FEATURE_SPEC_phase3_rag.md` Â§3b
- **Shipped:** 2026-07-21

## Class: `RAGRetriever`

### `__init__(self, store: RAGStore | None) -> None`
Initialise with an optional `RAGStore`. Pass `None` to disable RAG.

### `enabled` (property) â†’ `bool`
Whether RAG is enabled (store is not `None` and not empty).

### `retrieve(description, *, action_type="", k=5, min_confidence=0.6) -> list[RetrievedPattern]`
Retrieve golden patterns and doc chunks for a placeholder. Returns empty list when RAG is disabled or the store is empty. Prepends `action_type:` to the query for better embedding discrimination.

### `scoring_bonus_for(element: dict[str, str], patterns: list[RetrievedPattern]) -> float`
Compute a scoring bonus for an element based on golden pattern overlap:

| Match type | Bonus |
|---|---|
| **Direct selector match** | `GOLDEN_PATTERN_BONUS (20) Ã— pattern.confidence` |
| **Tolerance/substring match** | `GOLDEN_PATTERN_BONUS (20) Ã— 0.5 Ã— pattern.confidence` |
| **No match / doc-only patterns** | `0.0` |

Only considers patterns with `source == "golden"`. The bonus is designed to tip the scale between similarly-scored candidates (e.g. two elements scoring ~25 each) without overriding strong structural matches (+80) or visibility penalties (-40).

## Key Design Decisions

- **Null-object pattern:** When `store is None`, all methods return empty/no-op â€” the resolver doesn't need to check `enabled` before calling.
- **Selector-based matching:** `scoring_bonus_for()` compares the element's CSS selector against golden pattern selectors (exact and substring). Does not re-embed â€” fast enough for per-candidate evaluation.
- **Bonus magnitude +20:** Mirrors `_vision_enriched_bonus` â€” strong enough to break ties but won't override structural/id matches. Tunable via `PlaceholderScorer.GOLDEN_PATTERN_BONUS`.

## Dependencies

- `src.rag_store.RAGStore`, `src.rag_store.RetrievedPattern` â€” storage and data models
- `src.placeholder_scorers.PlaceholderScorer.GOLDEN_PATTERN_BONUS` â€” bonus constant

## Depended On By

- `src/placeholder_orchestrator.py` â€” calls `retrieve()` + passes patterns to resolver
- `src/orchestrator.py` â€” calls `_build_rag_retriever()` to construct
- `tests/test_rag_retriever.py` â€” 16 unit tests

## Usage

```python
from src.rag_retriever import RAGRetriever
from src.rag_store import RAGStore, MilvusLiteBackend, SentenceTransformerEmbedder
from src.storage import get_storage

embedder = SentenceTransformerEmbedder()
backend = MilvusLiteBackend(str(get_storage().rag_path()), embedder.dimension)
store = RAGStore(backend, embedder)
retriever = RAGRetriever(store)

patterns = retriever.retrieve("Add to cart button", action_type="CLICK")
for elem in candidates:
    bonus = retriever.scoring_bonus_for(elem, patterns)
```





# `src/rag_store.py`

## High-Level Purpose

RAG (Retrieval-Augmented Generation) vector store for placeholder resolution. Indexes verified locator patterns (golden patterns from the eval dataset) and Playwright documentation chunks. At resolution time, the placeholder description is embedded and used to retrieve similar patterns â€” feeding a scoring bonus to `PlaceholderScorer` and augmenting the LLM disambiguation prompt.

All retrieval is **advisory**: an empty or missing store behaves as if disabled â€” the pipeline works identically to pre-RAG.

## Module Metadata

- **Lines:** ~340
- **Imports:** `dataclasses`, `typing.Protocol`, `sentence_transformers`, `pymilvus`
- **Spec:** `docs/specs/FEATURE_SPEC_phase3_rag.md`
- **Shipped:** 2026-07-21

## Architecture

```
RAGStore
  â”œâ”€ EmbeddingProvider (SentenceTransformerEmbedder)
  â””â”€ VectorStoreBackend (MilvusLiteBackend)
```

## Dataclasses

### `GoldenPattern`
A verified placeholder â†’ selector mapping from the eval dataset.

| Field | Type | Description |
|-------|------|-------------|
| `action` | `str` | CLICK, FILL, ASSERT, GOTO, SELECT |
| `description` | `str` | e.g. "Add to cart button" |
| `expected_locator` | `str` | e.g. "button.add-to-cart" |
| `tolerance_selectors` | `list[str]` | Acceptable alternative selectors |
| `expected_page` | `str` | URL fragment the pattern was verified on |
| `query_text` | `property â†’ str` | `"{action}: {description}"` â€” used for embedding |

### `DocChunk`
A chunk of Playwright documentation (or other domain text).

| Field | Type | Description |
|-------|------|-------------|
| `text` | `str` | Chunk content |
| `source` | `str` | Source filename, e.g. "playwright-locators.md" |
| `heading_path` | `str` | Heading hierarchy, e.g. "Locators > Best Practices" |

### `KnowledgeEntry`
Internal entry ready for vector store upsert. Contains `vector`, `text`, `metadata`.

### `SearchHit`
A single search result from the vector store.

| Field/Property | Type | Description |
|----------------|------|-------------|
| `distance` | `float` | Cosine similarity value |
| `metadata` | `dict[str, str]` | Stored entity metadata |
| `confidence` | `property â†’ float` | `distance` clamped to [0.0, 1.0] |

### `RetrievedPattern`
A retrieval result returned to the resolver/retriever.

| Field | Type | Description |
|-------|------|-------------|
| `description` | `str` | Original query or matched text |
| `selector` | `str` | Matched locator (golden patterns) or empty (docs) |
| `action_type` | `str` | Action type from metadata |
| `confidence` | `float` | Similarity score (0.0â€“1.0) |
| `source` | `str` | `"golden"` or `"doc"` |
| `page` | `str` | URL fragment for golden patterns |

## Protocols

### `EmbeddingProvider`
Protocol for text â†’ vector embedding.
- `dimension: int` â€” vector dimension (384 for all-MiniLM-L6-v2)
- `embed(text: str) -> list[float]` â€” single text embedding
- `embed_batch(texts: list[str]) -> list[list[float]]` â€” batch embedding

### `VectorStoreBackend`
Protocol for vector store backends. MilvusLiteBackend is the v1 implementation. The protocol makes swapping to ChromaDB / hosted Milvus a one-file change in Phase 6 (SaaS).

- `dimension: int` â€” vector dimension
- `upsert(entries: list[KnowledgeEntry]) -> int` â€” insert entries, returns count
- `search(query_vector: list[float], k: int) -> list[SearchHit]` â€” top-k similarity search
- `count() -> int` â€” total entries
- `clear() -> None` â€” delete all entries (test/rebuild)

## Classes

### `SentenceTransformerEmbedder`
Embedding provider backed by `sentence-transformers` with `all-MiniLM-L6-v2` (384-dim, ~80 MB, CPU-only). Model is downloaded on first use and cached by Hugging Face.

```python
def __init__(self, model_name: str | None = None) -> None: ...
def embed(self, text: str) -> list[float]: ...
def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
```

### `MilvusLiteBackend`
Vector store backend backed by Milvus Lite (embedded, in-process). Stores data at `db_path` (a `.db` file). Single-writer â€” safe for dev/CLI/single-process Streamlit. For multi-worker SaaS (Phase 6), swap to ChromaDB server or hosted Milvus.

```python
def __init__(self, db_path: str, dimension: int) -> None: ...
def upsert(self, entries: list[KnowledgeEntry]) -> int: ...
def search(self, query_vector: list[float], k: int) -> list[SearchHit]: ...
def count(self) -> int: ...
def clear(self) -> None: ...
```

**Lazy init:** Client and collection are created on first access. Collection uses `IVF_FLAT` index with `COSINE` metric and `nlist=128`. Auto-ID primary key on `INT64`. Dynamic fields enabled for flexible metadata.

**Note:** Explicit `flush()` after insert is deliberately omitted â€” it triggers a known milvus-lite race condition on Windows (`manifest.json.tmp` already exists). Search triggers auto-flush instead.

### `RAGStore`
High-level retrieval store: embeds text and delegates to a vector backend.

```python
def __init__(self, backend: VectorStoreBackend, embedder: EmbeddingProvider) -> None: ...
def add_patterns(self, patterns: list[GoldenPattern]) -> int: ...
def add_docs(self, chunks: list[DocChunk]) -> int: ...
def retrieve(self, query: str, *, action_type: str = "", k: int = 5, min_confidence: float = 0.6) -> list[RetrievedPattern]: ...
```

**`retrieve()`:** Embeds the query, searches the backend, filters by `min_confidence`, and returns `RetrievedPattern` objects sorted by confidence descending. Returns empty list when the store is empty.

## Key Design Decisions

- **Milvus Lite for v1:** Embedded, in-process, no server needed. Protocol abstraction guarantees swap path to ChromaDB/hosted Milvus for Phase 6 SaaS.
- **sentence-transformers for embeddings:** `all-MiniLM-L6-v2` (384-dim, ~80MB, CPU-only) â€” no GPU contention with LM Studio (see AGENTS.md Â§12 VRAM note).
- **COSINE metric:** Used by both Milvus and in-memory test backend for consistency.
- **Advisory retrieval:** Store absence/emptiness is not an error â€” pipeline degrades gracefully to pre-RAG behaviour.
- **Two knowledge sources:** Golden patterns (verified locators) and doc chunks (domain guidance) â€” stored with `entry_type` metadata for downstream filtering.

## Dependencies

- `pymilvus` â€” Milvus Lite client
- `sentence_transformers` â€” embedding model
- `src.storage.get_storage()` â€” workspace-aware `rag_path()`

## Depended On By

- `src/rag_retriever.py` â€” bridge to resolution pipeline
- `scripts/rag_ingest.py` â€” ingestion CLI (build/rebuild store)
- `tests/test_rag_store.py` â€” 35 unit tests

## Usage

```python
from src.rag_store import RAGStore, MilvusLiteBackend, SentenceTransformerEmbedder
from src.storage import get_storage

embedder = SentenceTransformerEmbedder()
backend = MilvusLiteBackend(get_storage().rag_path(), embedder.dimension)
store = RAGStore(backend, embedder)

# Ingestion
store.add_patterns([GoldenPattern(...), ...])
store.add_docs([DocChunk(...), ...])

# Retrieval
results = store.retrieve("Add to cart button", action_type="CLICK", k=5)
```





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





# `src/run_history_chart.py` â€” Plotly Figure Factory for Run History

## Purpose

Pure Plotly figure builder with no Streamlit or CLI dependencies. Consumes `PersistedRunResult` objects from `src.run_result_persistence` and produces stacked bar charts with pass-rate line overlay and flaky-test markers.

Also provides `build_chart_from_db()` for direct SQLite-backed chart building using SQL aggregation queries â€” avoids loading all objects into memory.

## Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `COLOR_PASS` | `"#2ecc71"` | Green |
| `COLOR_FAIL` | `"#e74c3c"` | Red |
| `COLOR_SKIP` | `"#f1c40f"` | Yellow |
| `COLOR_ERROR` | `"#95a5a6"` | Grey |
| `COLOR_LINE` | `"#2c3e50"` | Dark blue (pass-rate line) |

## Private Helpers

### `_parse_run_id(run_id: str) -> datetime`

Best-effort ISO-8601 parse. Falls back to `datetime.min` on failure.

### `_format_timestamp(dt: datetime) -> str`

Formats a datetime as `"YYYY-MM-DD HH:MM"` for x-axis labels.

## Public API

### `build_run_history_chart(runs: list[PersistedRunResult], include_flaky_markers: bool = True) -> go.Figure`

Builds a stacked bar chart from an in-memory list of run results.

**Chart elements:**
- X-axis: run timestamp (chronological, oldest-first)
- Primary Y-axis: stacked bars (pass/fail/skip/error counts)
- Secondary Y-axis: pass rate % line overlay (0â€“100)
- Flaky markers (`â—`): placed above bars for runs containing tests that passed in some runs and failed in others

**Flaky detection logic:** A test is flaky if `"passed" in statuses` AND any status is `"failed"` or `"error"`.

### `build_chart_from_db(date_from: str | None = None, date_to: str | None = None, include_flaky_markers: bool = True) -> go.Figure`

Builds the same chart type but reads directly from SQLite via `_get_db()`, using `get_run_stats_for_chart()` and `get_flaky_tests()` SQL queries. Ideal for large datasets with date-range filtering.

## Architecture

- **Pure function design**: No I/O or side effects â€” returns Plotly `go.Figure` objects consumed by `st.plotly_chart()` or `fig.show()`.
- **Two entry points**: In-memory (`build_run_history_chart`) vs. SQL-backed (`build_chart_from_db`) to handle different data volume scenarios.
- **Empty state handling**: Both functions return a placeholder figure with "No run history available" text when no data exists.





# `src/run_history_cli.py` â€” CLI Run History Formatter

## Purpose

ASCII table formatters for run history data, designed for terminal/CLI display. Complements the Plotly-based chart builder in `run_history_chart.py` for environments without GUI capabilities.

## Constants

| Constant | Value |
|----------|-------|
| `_HEADER` | `"=== Run History ==="` |
| `_FLAKY_HEADER_PREFIX` | `"=== Flaky Tests"` |
| `_COMPARISON_HEADER` | `"=== Last Run Comparison ==="` |

## Functions

### `format_run_history_table(runs: list[PersistedRunResult], max_rows: int = 10) -> str`

Returns an ASCII table of recent test runs (most recent first).

**Columns:** Date, Package, Pass, Fail, Skip, Err, Rate (%)

**Table format:**
```
=== Run History ===
last 10 of 25 runs

Date             Package              Pass   Fail   Skip    Err    Rate
---------------- -------------------- ----- ----- ----- ----- -------
2026-06-11 20:30 saucedemo-login        12     3     0     1   75.0%
...
```

### `format_flaky_tests_table(flaky_tests: list[tuple[str, dict[str, int]]]) -> str`

Returns an ASCII table of flaky tests with pass/fail counts and flakiness percentage.

**Columns:** Test Name, Pass, Fail, Flaky%

### `format_run_comparison(comparison: RunComparison | None) -> str`

Returns an ASCII summary comparing two consecutive runs.

**Sections:**
- Pass rate delta (`old% â†’ new% (Â±Î”%)`)
- Improved tests (âœ“)
- Regressed tests (âœ—)
- New failures (âš )

Returns "insufficient data (need 2+ runs)" when comparison is `None`.

### `format_full_history_summary(directory: str | None = None, max_rows: int = 10) -> str`

Composite function that loads all run results and produces a complete history summary combining:
1. Run history table
2. Flaky tests table (if 2+ runs exist)
3. Last-run comparison (if 2+ runs exist)

### `_format_run_date(run_id: str) -> str`

Converts ISO timestamp to `"YYYY-MM-DD HH:MM"` format.

### `_truncate(text: str, max_width: int) -> str`

Truncates text with ellipsis (`â€¦`) when exceeding `max_width`.

## Design Patterns

- **Formatter pattern**: Pure string-building functions with no I/O â€” returns formatted strings for consumption by any CLI renderer.
- **Composable design**: Individual formatters can be used independently or combined via `format_full_history_summary`.





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





# `src/self_healing.py`

## High-Level Purpose

`self_healing.py` implements Phase 2 of the ML Engineering roadmap â€” automated test repair using an LLM reviewer. When generated Playwright tests fail, this module runs a reflection loop: execute tests â†’ classify failures â†’ feed context to LLM â†’ apply suggested patches â†’ re-run failed tests. Repeats up to a configurable maximum iteration count.

Created **2026-07-20**.

## Dependencies

- `src.failure_classifier` â€” `classify_failure()`, `FailureDetail`
- `src.llm_client` â€” `LLMClient` for reviewer LLM calls
- `src.pytest_output_parser` â€” `parse_pytest_output()`, `RunResult`, `TestResult`
- `json`, `re`, `subprocess` â€” stdlib

## Data Types

### `AppliedPatch`

Records a single code change applied during healing.

Fields:
- `test_name: str` â€” test function name
- `line_number: int` â€” approximate line in test file
- `old_text: str` â€” original code line
- `new_text: str` â€” replacement code line
- `diagnosis: str` â€” LLM's explanation of the failure
- `strategy: str` â€” one of `"replace_locator"`, `"add_navigation"`, `"add_wait"`, `"skip_test"`

### `HealingReport`

Result of a self-healing run.

Fields:
- `total_failures: int` â€” initial failure count
- `fixed: int` â€” how many were fixed
- `remaining: int` â€” still failing after max iterations
- `unfixable: int` â€” classified as not automatically fixable
- `iterations: int` â€” how many loops ran
- `patches: list[AppliedPatch]` â€” all applied patches
- `final_results: list[TestResult]` â€” last test run results
- `all_fixed: bool` (property) â€” True when remaining == 0 and total > 0

### `REVIEWER_SYSTEM_PROMPT: str`

Module-level constant â€” the system prompt sent to the LLM reviewer. Instructs the LLM to analyze failures and return structured JSON with `fixable`, `diagnosis`, `strategy`, `old_line`, `new_line`, and `confidence` fields.

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

- `_run_pytest(test_path, test_names) -> RunResult` â€” runs pytest via subprocess
- `_review_and_suggest(result, detail, test_source) -> AppliedPatch | None` â€” sends context to LLM
- `_extract_test_function(source, test_name) -> str | None` â€” extracts single test from file
- `_format_elements_for_prompt(elements) -> str` â€” formats scraped elements for LLM context
- `_parse_reviewer_response(response, test_name, test_func) -> AppliedPatch | None` â€” parses LLM JSON
- `_apply_patch(test_path, test_source, patch) -> bool` â€” applies patch to file

## Integration Points

- **Streamlit:** `src/ui/ui_run_results.py` â€” "ðŸ©¹ Self-Heal Failed Tests" button, healing results display
- **CLI:** `src/cli/pipeline_runner.py` â€” `self_heal_cli()` with menu-driven fallback to interactive repair

## Tests

`tests/test_self_healing.py` â€” 28 unit tests covering extraction, formatting, parsing, patching, and integration.





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





# `src/sqlite_persistence.py` â€” SQLite Persistence Layer

## Purpose

SQLite-backed persistence for run results, replacing the JSON-based persistence layer. Designed as a drop-in replacement â€” all public API methods mirror signatures in `run_result_persistence.py` so the wrapper layer can delegate transparently.

Uses `sqlite3` from the Python standard library â€” no external server or dependencies required.

## Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `_DEFAULT_DB_DIR` | `Path("evidence")` | Default database directory |
| `_DEFAULT_DB_FILE` | `evidence/run_results.sqlite` | Default database file path |

## Schema

### `runs` table
- `run_id` (TEXT, PRIMARY KEY) â€” ISO-8601 timestamp
- `test_package` (TEXT) â€” test package name
- `total`, `passed`, `failed`, `skipped`, `errors` (INTEGER)
- `duration` (REAL) â€” total run duration in seconds
- `raw_output` (TEXT) â€” full pytest output
- `created_at` (TEXT) â€” ISO-8601 creation timestamp

### `test_results` table
- `id` (INTEGER, AUTOINCREMENT PRIMARY KEY)
- `run_id` (TEXT, FK â†’ runs.run_id, CASCADE DELETE)
- `name` (TEXT) â€” test function name
- `status` (TEXT) â€” "passed", "failed", "skipped", "error"
- `duration` (REAL) â€” individual test duration
- `error_message` (TEXT)
- `file_path` (TEXT)

### Indexes
- `idx_test_results_run_id` on `test_results(run_id)`
- `idx_test_results_name` on `test_results(name)`
- `idx_test_results_status` on `test_results(status)`
- `idx_test_results_name_status` on `test_results(name, status)`

## Class: `SQLitePersistence`

### Constructor

```python
SQLitePersistence(db_path: Path | None = None) -> None
```

Initialises the database connection with WAL journal mode and foreign key enforcement. Creates the schema automatically.

### Property

- `db_path: Path` â€” Path to the SQLite database file.

### Methods

#### `persist_run_result(run_result: RunResult, test_package: str = "") -> str`

Writes a run and its individual test results to the database. Returns the generated `run_id` (ISO-8601 timestamp).

#### `load_run_result(run_id: str) -> PersistedRunResult | None`

Loads a single run by ID, including all child test results. Returns `None` if not found.

#### `list_run_results() -> list[str]`

Returns sorted list of run_ids (oldest first).

#### `load_all_run_results() -> list[PersistedRunResult]`

Loads every persisted run (oldest first).

#### `compute_run_history() -> RunHistory`

Aggregates stats directly from SQL â€” total runs, pass/fail/skip/error counts, and per-test flakiness using `GROUP BY`.

#### `get_flaky_tests(min_runs: int = 2) -> list[tuple[str, dict[str, int]]]`

Detects flaky tests using SQL `GROUP BY` + `HAVING`. A test is flaky when it has both passes and failures/errors across â‰¥ `min_runs` observations. Results sorted by flakiness ratio (descending).

#### `query_test_history(test_name_pattern: str = "%", status: str | None = None, date_from: str | None = None, date_to: str | None = None, include_flaky: bool = False) -> list[dict[str, Any]]`

Rich query interface for ad-hoc queries. Supports LIKE patterns, status filtering, date ranges, and flaky-only mode. Returns structured dicts for Jira/heatmap/Gantt exporters.

#### `get_run_stats_for_chart(date_from: str | None = None, date_to: str | None = None) -> list[dict[str, Any]]`

Chart-optimized aggregation query. Returns one row per run with aggregated stats and computed `pass_rate`.

#### `delete_old_runs(keep: int = 50) -> int`

Deletes oldest runs, keeping the most recent `keep` runs. Uses FK CASCADE to clean up child `test_results`.

#### `close() -> None` / `__enter__()` / `__exit__()`

Connection management and context-manager protocol support.

## Design Patterns

- **WAL journal mode**: Enables concurrent reads while writes happen â€” no table locks during chart rendering.
- **FK CASCADE**: Deleting a `run` automatically removes all child `test_results` rows.
- **Drop-in replacement**: Mirrors `run_result_persistence.py` signatures for transparent delegation.





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





# `src/storage.py`

## High-Level Purpose

Workspace-isolated storage abstraction. Centralises all path construction so no module in the project constructs `Path("generated_tests")` or `Path("evidence")` directly. The default workspace (`"default"`) mirrors the current repo-root layout for backwards compatibility; named workspaces isolate data under a subdirectory.

Enables future cloud storage backends (S3, GCS, Azure Blob) without changing consumer code â€” they just need to satisfy the `StorageBackend` Protocol.

## Module Metadata

- **Lines:** ~145
- **Imports:** `pathlib.Path`, `typing.Protocol`
- **Spec:** `docs/specs/FEATURE_SPEC_AI029_workspace_storage.md`
- **Shipped:** 2026-07-19

## Protocol: `StorageBackend`

```python
class StorageBackend(Protocol):
    @property
    def workspace(self) -> str: ...
    @property
    def root(self) -> Path: ...
    def generated_tests_dir(self) -> Path: ...
    def evidence_dir(self) -> Path: ...
    def db_path(self) -> Path: ...
    def rag_path(self) -> Path: ...
    def ensure_dirs(self) -> None: ...
```

All path methods return `Path` objects â€” no string construction in consumers.

### Path methods

| Method | Returns |
|--------|---------|
| `generated_tests_dir()` | `<root>/<workspace>/generated_tests/` |
| `evidence_dir()` | `<root>/<workspace>/evidence/` |
| `db_path()` | `<root>/<workspace>/evidence/run_results.sqlite` |
| `rag_path()` | `<root>/<workspace>/evidence/rag_store.db` |

## Class: `LocalStorageBackend`

Local filesystem storage with workspace isolation. The only implementation shipped today.

```python
def __init__(self, root: Path | None = None, workspace: str = "default") -> None: ...
```

**Directory layout:**

```
<root>/                       # workspace == "default"
  generated_tests/
  evidence/
    run_results.sqlite
    rag_store.db

<root>/<workspace>/           # workspace != "default"
  generated_tests/
  evidence/
    run_results.sqlite
    rag_store.db
```

`ensure_dirs()` creates the workspace directory structure if it doesn't exist â€” called automatically during `__init__`.

## Singleton Management

### `get_storage() -> StorageBackend`
Return the global storage singleton. Lazily creates a `LocalStorageBackend` with `workspace="default"` on first call â€” safe to call from any module without worrying about startup ordering.

### `init_storage(root=None, workspace="default") -> StorageBackend`
Initialise (or re-initialise) the storage singleton. Call once at application startup:
- **Streamlit:** `init_storage(workspace=os.environ.get("WORKSPACE", "default"))`
- **CLI:** `init_storage(workspace=args.workspace)`

### `reset_storage() -> None`
Reset the singleton â€” used in test teardown for isolation.

## Key Design Decisions

- **Protocol-first:** `StorageBackend` is a `Protocol`, not an ABC â€” structural subtyping means backends don't need to inherit, only satisfy the interface.
- **Default workspace = repo root:** Backwards compatibility â€” all existing code that used `Path("generated_tests")` maps seamlessly.
- **Lazy singleton:** No explicit initialisation required â€” consumers call `get_storage()` and get a functional backend immediately.
- **`rag_path()` added 2026-07-21:** Returns path for the RAG vector store DB (`rag_store.db`), part of Phase 3 RAG integration.

## Dependencies

- `pathlib.Path` â€” stdlib only
- `pyproject.toml` â€” used to auto-detect repo root

## Depended On By

- **~15 consumer files** migrated from hardcoded `Path("generated_tests")` / `Path("evidence")`
- `src/rag_store.py` â€” uses `rag_path()` for vector store location
- `src/orchestrator.py` â€” uses `rag_path()` when building RAG retriever
- CI gate: `rg 'Path\("generated_tests"\)' -- '*.py'` must return zero results

## Notes

- CI gate enforces: zero hardcoded path hits in any `*.py` file under `src/`
- Future: S3/GCS/Azure Blob backends implement `StorageBackend` protocol
- `_find_repo_root()` walks upward from the module file looking for `pyproject.toml`





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





# `src/__init__.py` â€” Structural Summary

## High-Level Purpose

This file serves as the package initializer for the `src` package within the **AI-Playwright-Test-Generator** project. It contains no executable code, imports, or submodule declarations. Its sole content is a module-level docstring that describes the package as the *"Source module for Playwright test generator."*

## File Content (verbatim)

```python
"""Source module for Playwright test generator."""
```

## Classes

**None defined.** The file does not declare or import any classes.

## Functions

**None defined.** The file does not declare or import any functions.

## Module-Level Attributes

| Name | Type | Value | Description |
|------|------|-------|-------------|
| `__doc__` | `str` | `"Source module for Playwright test generator."` | Module docstring, automatically set by the triple-quoted string at the top of the file. |

## Imports

**None.** The file does not contain any `import` or `from ... import` statements.

## Architectural Patterns & Observations

| Aspect | Observation |
|--------|-------------|
| **Package marker** | The file acts as a minimal `__init__.py` that marks the `src/` directory as a Python package. It does not re-export any symbols, meaning consumers must import directly from submodules (e.g., `from src.some_module import X`). |
| **Docstring convention** | A single-line docstring provides a high-level description of the package's purpose. This follows PEP 257 recommendations for package-level documentation. |
| **No `__all__`** | The absence of an `__all__` list means that `from src import *` would export all public names defined in the package (currently none). |
| **Submodule discovery** | Because the `__init__.py` does not explicitly import submodules, they are not automatically loaded when `import src` is executed. Each submodule must be imported individually. |
| **Version / metadata** | No `__version__`, `__author__`, or other metadata attributes are defined. This information, if needed, would typically be added here or sourced from a separate `_version.py` or `pyproject.toml`. |

## Dependencies

**None.** The file has no runtime dependencies beyond the Python standard library (and does not even use the standard library explicitly).

## Related Files (inferred from project structure)

- `src/` â€” sibling modules within the same package (e.g., `src/stateful_scraper.py`, `src/playwright_manager.py`, etc.) are the actual carriers of logic for the Playwright test generator.
- `pyproject.toml` or `setup.py` â€” likely contains the package's metadata (name, version, dependencies) that this `__init__.py` does not duplicate.

## Summary

`src/__init__.py` is a **minimal package initializer** whose only responsibility is to designate the `src/` directory as a Python package. It provides no runtime logic, no public API surface, and no re-exports. All functional code resides in sibling modules within the same directory.





# AI-Playwright-Test-Generator â€” Documentation Index

> Auto-generated documentation sweep â€” 101 source files across `src/`

## Global Architecture

The project generates Playwright Python test scripts from user stories using a local LLM. It has two entry points:

### Streamlit UI (`streamlit_app.py`)

Primary interface. Uses modular UI components from `src/ui/`:

| Module | Role |
|--------|------|
| `src/ui/ui_requirements.py` | Requirements input (paste/upload/baseline) |
| `src/ui/ui_sidebar.py` | LLM provider and POM mode configuration |
| `src/ui/ui_journey.py` | Credential profiles and journey step builder |
| `src/ui/ui_results.py` | Results display and test run buttons |
| `src/ui/ui_run_results.py` | Run results with failure classification and locator repair |
| `src/ui/ui_evidence.py` | Evidence viewer (screenshots, Gantt, heatmaps, run history) |
| `src/ui/ui_downloads.py` | Report download buttons |
| `src/ui/ui_saved_packages.py` | Saved package loader and re-run (AI-026) |
| `src/ui/shared.py` | Session state key whitelisting and report storage helpers |

### CLI (`src/cli/main.py`)

Menu-driven terminal interface with retro CHOICE-style rendering:

| Module | Role |
|--------|------|
| `src/cli/main.py` | Slim orchestrator â€” menu loop and routing |
| `src/cli/session.py` | Session state dataclass with factory |
| `src/cli/menu_renderer.py` | Retro menu rendering and all input prompts |
| `src/cli/retro_ui.py` | CHOICE-style box-drawing and colour primitives |
| `src/cli/color.py` | ANSI colour helpers (standard + phosphor greens) |
| `src/cli/terminal_adapter.py` | Cross-platform TTY/PTY key reading |
| `src/cli/testing_terminal.py` | Queue-based terminal for headless tests |
| `src/cli/pipeline_runner.py` | Pipeline execution, test running, reports |
| `src/cli/input_parser.py` | Multi-format input parsing (Jira, Gherkin, bullets, plain text) |
| `src/cli/evidence_generator.py` | Screenshot capture and evidence collection |
| `src/cli/report_generator.py` | Jira/Confluence/Markdown report generation |
| `src/cli/test_case_orchestrator.py` | Legacy orchestration pipeline |
| `src/cli/run_results_display.py` | Structured ASCII run results for terminals |
| `src/cli/config.py` | Backwards-compatible config re-exports |
| `src/cli/__init__.py` | UTF-8 encoding fix for Windows Git Bash |

### Core Pipeline (`src/`)

| Layer | Modules | Description |
|-------|---------|-------------|
| **Input** | `user_story_parser.py`, `skeleton_parser.py` | Parse user stories into structured requirements |
| **LLM** | `llm_client.py`, `llm_providers/`, `provider_config.py`, `llm_errors.py`, `llm_reasoning_filter.py` | LLM interaction, provider abstraction, error handling |
| **Prompts** | `prompt_utils.py`, `test_generator.py` | Prompt construction and test generation |
| **Scaffolding** | `skeleton_validator.py`, `code_normalizer.py`, `code_postprocessor.py`, `code_validator.py` | Code quality assurance |
| **DOM Scraping** | `scraper.py`, `stateful_scraper.py`, `journey_scraper.py`, `journey_models.py`, `journey_executor.py`, `journey_auth_detector.py`, `page_context_tracker.py` | Page scraping and context capture |
| **Placeholder Resolution** | `placeholder_resolver.py`, `placeholder_orchestrator.py`, `placeholder_scorers.py`, `semantic_matcher.py`, `semantic_candidate_ranker.py`, `intent_matcher.py`, `element_matcher.py`, `element_enricher.py`, `accessibility_enricher.py`, `vision_enricher.py`, `hover_click_utils.py` | Resolving `{{ACTION:description}}` placeholders using scraped DOM |
| **Locators** | `locator_builder.py`, `locator_fallback.py`, `locator_repair.py`, `locator_scorer.py`, `url_resolver.py`, `url_inference.py`, `url_utils.py` | Locator generation, repair, and scoring |
| **Page Objects** | `page_object_builder.py` | POM class generation |
| **Analysis** | `analyzer.py`, `spec_analyzer.py`, `form_detector.py`, `form_login_utils.py` | Test case analysis and pattern detection |
| **Pipeline** | `orchestrator.py`, `pipeline_models.py`, `pipeline_writer.py`, `pipeline_artifact_manager.py`, `pipeline_run_service.py`, `pipeline_report_service.py`, `ui_pipeline.py` | Core pipeline orchestration and artifact management |
| **Execution** | `pytest_output_parser.py`, `run_utils.py`, `screenshot_capture.py`, `evidence_tracker.py`, `evidence_serializer.py`, `evidence_loader.py`, `evidence_report.py`, `state_tracker.py` | Test execution and evidence collection |
| **Failure Handling** | `failure_classifier.py`, `failure_reporter.py` | Failure categorisation and diagnostics |
| **Reports** | `report_builder.py`, `report_formatters.py`, `report_utils.py`, `export_service.py` | Report generation and export |
| **Persistence** | `run_result_persistence.py`, `sqlite_persistence.py`, `run_history_chart.py`, `run_history_cli.py` | SQLite-backed run history and charting |
| **Visualisation** | `gantt_utils.py`, `heatmap_utils.py`, `coverage_utils.py`, `run_history_chart.py` | Gantt charts, heatmaps, coverage analysis |
| **Infrastructure** | `config.py`, `file_utils.py`, `storage.py` | Configuration constants, file utilities, workspace-isolated storage |
| **RAG (Phase 3)** | `rag_store.py`, `rag_retriever.py` | Retrieval-augmented resolution â€” vector store (Milvus Lite) + golden pattern retrieval for scoring bonus |

### Test Plan (`src/test_plan.py`)

Living test plan with sign-off workflow. Conditions derived from acceptance criteria, reviewed by tester, then signed off before generation is unlocked.

### Tests (`tests/`)

Unit tests for all core modules â€” validates the tool itself, not the tests it generates.

### Generated Output (`generated_tests/`)

Test packages produced by the tool. Each package contains:
- `package_manifest.json` â€” Metadata and artifact listing
- `test_xxx.py` â€” Generated Playwright test files
- `evidence/*.evidence.json` â€” Sidecar evidence files with screenshots and step traces

## Documentation Coverage

| Directory | Files | Status |
|-----------|-------|--------|
| `src/` (root) | 61 | âœ… Complete |
| `src/cli/` | 15 | âœ… Complete |
| `src/ui/` | 10 | âœ… Complete |
| `src/llm_providers/` | 1 | âœ… Complete |
| `scripts/` | 1 | âœ… Complete |
| `src/` (all) | **104** | **âœ… Complete** |

## Sweep Progress

See `markdown_docs/.sweep_progress.json` for per-file completion status.

---

*Generated: 2026-07-08*  
*Updated: 2026-07-21 â€” Phase 3 RAG (rag_store, rag_retriever, rag_ingest), storage.py, element_matcher.py*




