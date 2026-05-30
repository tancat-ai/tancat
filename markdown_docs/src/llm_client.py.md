---
purpose: >
  Unified LLM client that supports multiple providers (Ollama, LM Studio, OpenAI cloud/local).
  Auto-detects models and handles provider-specific timeouts and errors.
lines: ~400
created: "2026-05-30"
---

# `src/llm_client.py`

## High-Level Purpose

Provider-agnostic LLM client. Wraps Ollama, LM Studio, and OpenAI APIs behind a single `generate()` interface. Supports auto-detection of loaded models for LM Studio.

## Providers

| Provider | Selection | Key Details |
|----------|-----------|-------------|
| Ollama | `ollama` | Uses `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT=300` |
| LM Studio | `lm-studio` | Probes `/api/v0/models` for loaded model, auto-detects if no `LM_STUDIO_MODEL` |
| OpenAI (cloud) | `openai` | Requires `OPENAI_API_KEY`, uses `gpt-4o` default |
| OpenAI (local) | `openai-compatible` | No API key needed. Probes ports 8080/8000/5000. Auto-detects models |

## Key Methods

| Method | Description |
|--------|-------------|
| `generate(prompt: str) -> str` | Send prompt, return LLM response text |
| `set_session_provider(provider_name)` | Switch provider mid-session (for UAT scripts) |
| `detect_loaded_model() -> str` | LM Studio: find model currently loaded in VRAM |

## Environment Variables

- `OLLAMA_BASE_URL` — default `http://localhost:11434`
- `OLLAMA_MODEL` — default `qwen3.5:35b`
- `OLLAMA_TIMEOUT` — must be 300 (default 60s causes timeouts)
- `LM_STUDIO_BASE_URL` — default `http://localhost:1234`
- `LM_STUDIO_MODEL` — optional, auto-detects if omitted
- `OPENAI_API_KEY` — required for cloud provider only
- `OPENAI_BASE_URL` — for custom OpenAI-compatible endpoints

## Dependencies

- `openai` package — for OpenAI-compatible API calls
- `requests` — for LM Studio auto-detection, port probing
- `dotenv` — for `.env` loading

## Depended On By

- `src/test_generator.py` — generates skeleton code
- `src/orchestrator.py` — pipeline orchestration
- UAT scripts via `set_session_provider()`