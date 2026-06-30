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
| `generate(prompt, timeout=600, system_prompt=None) -> str` | Async generation — used by intelligent pipeline |
| `generate_test(prompt, timeout=300, system_prompt=None) -> str` | Sync generation — retained for tests/utilities |
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

- `OLLAMA_MODEL` — override default Ollama model
- `LM_STUDIO_MODEL` — override default LM Studio model
- `OPENAI_MODEL` — override default OpenAI model
- `OPENAI_API_KEY` — required for cloud OpenAI provider
- `PIPELINE_DEBUG=1` — enable debug logging

## Dependencies

- `src.llm_providers` — provider implementations (Ollama, LM Studio, OpenAI)
- `asyncio` — async generation support
- `re` — code extraction from LLM responses

## Depended On By

- `src/orchestrator.py` — pipeline orchestration
- `src/test_generator.py` — skeleton generation
- `src/placeholder_orchestrator.py` — placeholder resolution
- CLI/Streamlit UI — provider selection and session management

## Notes

- Uses `httpx` (via `llm_providers`) instead of `requests`
- No longer uses `dotenv` — environment loading handled elsewhere
- Session provider state is class-level, shared across all instances
- Vision completion uses base64-encoded PNG images
- Code extraction handles markdown fences, `<channel|>` tags, and