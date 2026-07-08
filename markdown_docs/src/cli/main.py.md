# `src/cli/main.py` — CLI Interactive Entry Point

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

Legacy parameter-based command. Parses input → runs analysis → generates tests → evidence → reports.

### `main() -> int`

Entry point with `argparse`:
- No arguments → `interactive_session()` (default)
- `generate` subcommand → legacy parameter-based generation
- `test` subcommand → placeholder for test suite

## Legacy Functions

| Function | Description |
|----------|-------------|
| `run_analysis(parsed)` | Runs `KeywordAnalyzer.analyze_parsed()` |
| `run_generation(parsed, output_dir, url)` | Orchestrates test generation via `TestCaseOrchestrator` |
| `run_evidence_generation(output_dir)` | Generates evidence via `EvidenceGenerator` |
| `generate_reports_legacy(parsed, analysis_result, output_dir)` | Generates Jira reports |

## Architecture

- **Slim orchestrator**: Main loop is purely routing — all logic lives in `menu_renderer` and `pipeline_runner`.
- **UTF-8 handling**: Dual encoding fix (module-level + `__init__` import) for Windows Git Bash.
- **Context-sensitive menu**: Items appear/disappear based on `Session` state flags.
