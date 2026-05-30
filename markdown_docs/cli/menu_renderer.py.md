# cli/menu_renderer.py

## Purpose

Renders the retro CLI menu system and collects user input for the interactive flow.
Implements CHOICE-inspired UI behavior, model selection, user story entry, URL collection, consent mode, authentication, and journey building.

## Public API

- `print_header(title: str, subtitle: str = "") -> None`
- `print_menu(options: list[str], prompt: str = "Choose an option", shortcuts: list[tuple[str, str]] | None = None) -> int`
- `read_non_empty(prompt_text: str) -> str`
- `read_optional(prompt_text: str, default: str = "") -> str`
- `configure_llm(provider: str, base_url: str, model_name: str) -> tuple[str, str, str]`
- `collect_user_story() -> str`
- `collect_urls() -> tuple[str, str]`
- `collect_consent_mode() -> str`
- `collect_authentication() -> dict[str, str] | None`
- `collect_journey_steps() -> list[dict[str, str]]`
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
