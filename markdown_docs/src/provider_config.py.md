# `src/provider_config.py` — Shared LLM Provider Configuration

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

Applies a session-scoped OpenAI API key to `os.environ["OPENAI_API_KEY"]`. Never writes to disk — purely in-process.

## Design Patterns

- **Configuration centralisation**: Single source of truth for provider defaults, consumed by both UI and CLI code paths.
- **No side effects for non-OpenAI providers**: `resolve_openai_api_key` returns `None` early for local providers, avoiding unnecessary env lookups.
