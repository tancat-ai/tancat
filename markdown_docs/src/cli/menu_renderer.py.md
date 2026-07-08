# `src/cli/menu_renderer.py` — CLI Menu Rendering and Input Helpers

## Purpose

Renders a CHOICE-inspired retro terminal UI: green-on-black phosphor aesthetic with box-drawing borders and a `>` selection indicator. Handles all input logic (LLM config, user story, URLs, auth, journey).

## Terminal Input Handling

### Git Bash Detection

#### `_running_in_git_bash() -> bool`

Checks `terminal_adapter.terminal.running_in_git_bash()`. In Git Bash, `msvcrt` functions don't work — must use `select`-based fallback.

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
