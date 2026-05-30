# cli/main.py

## Purpose

Interactive CLI entry point for the AI Playwright Test Generator.
Provides a classic menu-driven flow as well as legacy command-line compatibility.

## Key functions

- `interactive_session() -> None`:
  - Drives the main menu loop.
  - Builds available menu options based on session state.
  - Routes user actions to configuration, story input, URL input, authentication, journey builder, plan review, pipeline execution, report viewing, and test execution.

- `_configure_llm_inline(session: Session) -> None`
- `_collect_user_story_inline(session: Session) -> None`
- `_collect_urls_inline(session: Session) -> None`
- `_collect_authentication_inline(session: Session) -> None`
- `_collect_journey_inline(session: Session) -> None`

- `cmd_generate(args: Any, parser: Any) -> int`
  - Legacy parameter-based generation path.
  - Parses input from CLI arguments or files, runs analysis, generates tests, captures evidence, and creates reports.

- `run_analysis(parsed: Any) -> Any`
- `run_generation(parsed: Any, output_dir: str, url: str | None = None) -> None`
- `run_evidence_generation(output_dir: str) -> None`
- `generate_reports_legacy(parsed: Any, analysis_result: Any, output_dir: str) -> None`

- `main() -> int`
  - Argument parser entry point.
  - Supports interactive mode by default.
  - Provides legacy `generate`, `test`, and `help` subcommands.

## Implementation details

- Forces UTF-8 output on Windows and Git Bash for box-drawing characters.
- Loads `.env` if available via `python-dotenv`.
- Reuses `cli.menu_renderer` for UI prompts and `cli.pipeline_runner` for pipeline execution.
- Keeps backward compatibility while exposing the newer interactive flow.
