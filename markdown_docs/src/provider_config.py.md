# `src/provider_config.py` — Shared LLM Provider Configuration

## Purpose

Centralised configuration for LLM provider defaults, labels, and OpenAI API key resolution. Used by both CLI (`src/cli/`) and Streamlit (`src/ui/`) to avoid duplicating provider logic.

## Constants

| Constant | Type | Description |
|----------|------|-------------|
| `CLOUD_OPENAI_PROVIDER` | `str` | `"openai"` |
| `LOCAL_OPENAI_PROVIDER` | `str` | `"openai-local"` |
| `AZURE_OPENAI_PROVIDER` | `str` | `"azure-openai"` |
| `SUPPORTED_PROVIDERS` | `tuple[str, ...]` | `("ollama", "lm-studio", "openai-local", "openai", "azure-openai", "openai-compatible", "openrouter")` |
| `PROVIDER_LABELS` | `dict[str, str]` | Human-readable labels for each provider |

## Functions

### `get_provider_defaults(provider: str) -> tuple[str, str]`

Returns `(base_url, model)` defaults for a given provider.

| Provider | Base URL | Default Model |
|----------|----------|---------------|
| `lm-studio` | `http://localhost:1234` | `lmstudio-community/Qwen2.5-7B-Instruct-GGUF` |
| `openai-local` | `http://localhost:8080` | `llama` |
| `openai` | `https://api.openai.com/v1` | `gpt-4o` |
| `azure-openai` | *(none)* | *(none - the deployment name is the model)* |
| `openai-compatible` | `https://openrouter.ai/api/v1` | *(none - name the model)* |
| `openrouter` | `https://openrouter.ai/api/v1` | *(none - name the model)* |
| `ollama` | `http://localhost:11434` | `qwen3.5:35b` |

### `api_key_env_var(provider: str) -> str`

Returns the environment variable that carries the provider's API key
(`OPENAI_API_KEY`, `AZURE_OPENAI_API_KEY`, or `OPENAI_COMPATIBLE_API_KEY`).

### `provider_requires_openai_api_key(provider: str) -> bool`

Returns `True` for `openai`, `azure-openai`, `openai-compatible` and
`openrouter`; `False` for the local providers.

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

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `OPENAI_COMPATIBLE_PROVIDER` (constant): `OPENAI_COMPATIBLE_PROVIDER = 'openai-compatible'`
- `OPENROUTER_PROVIDER` (constant): `OPENROUTER_PROVIDER = 'openrouter'`
