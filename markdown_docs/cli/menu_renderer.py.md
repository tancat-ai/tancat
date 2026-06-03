# cli/menu_renderer.py

## Purpose

Renders the retro CLI menu system and collects user input for the interactive flow.
Implements CHOICE-inspired UI behavior, model selection, user story entry, URL collection, consent mode, authentication, journey building, and package persistence displays.

## Public API

### Core Menu Functions

- `print_header(title: str, subtitle: str = "") -> None`
- `print_menu(options: list[str], prompt: str = "Choose an option", shortcuts: list[tuple[str, str]] | None = None) -> int`
- `read_non_empty(prompt_text: str) -> str`
- `read_optional(prompt_text: str, default: str = "") -> str`

### Configuration Collectors

- `configure_llm(provider: str, base_url: str, model_name: str) -> tuple[str, str, str]`
- `collect_user_story() -> str`
- `collect_urls() -> tuple[str, str]`
- `collect_consent_mode() -> str`
- `collect_authentication() -> dict[str, str] | None`
- `collect_journey_steps() -> list[dict[str, str]]`

### Package Persistence Rendering (AI-026 — Step 4)

- `render_saved_package_list(packages: list[PackageManifest]) -> None`:
  - Renders a numbered list of discovered saved packages with key metadata.
  - Each entry shows: package name, created date, test file count, and run result count.
  - Used by `load_existing_packages()` in `cli/pipeline_runner.py`.

- `render_package_metadata(manifest: PackageManifest, run_results: list[dict] | None = None) -> None`:
  - Displays a structured metadata table for a loaded package.
  - Shows: package name, created date, source story, starting URL, provider, model, test files, page objects.
  - Optionally includes run history summary (aggregated pass/fail/skip counts) and flakiness report.
  - Used by `_handle_show_package_metadata()` in `cli/main.py`.

- `render_package_run_history(run_results: list[dict]) -> None`:
  - Renders a run-by-run table showing test outcomes across multiple executions.
  - Columns: Run #, Passed, Failed, Skipped, Duration, Timestamp.
  - Highlights flaky tests (tests that alternate between pass/fail across runs).
  - Used alongside `render_package_metadata()` for the "Show Saved Package Metadata" command.

### Utility

- `open_file(path: str) -> None`

## Helper functions

- `_get_available_models(provider_name: str, provider_url: str) -> list[str]`
- `_default_model(provider: str) -> str`
- `_get_baseline_text() -> str`

## Notes

- Supports model provider auto-detection for Ollama, LM Studio, OpenAI local, and OpenAI cloud.
- Handles pasted multi-line input and file uploads for user stories.
- Preserves keyboard shortcuts and menu navigation across different terminal environments.
- Includes a built-in baseline user story for automationexercise.com.
- Package persistence renderers delegate data fetching to `src.pipeline_artifact_manager.py` and `src.run_result_persistence.py` — this module only handles display formatting.