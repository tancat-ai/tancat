"""Shared LLM provider configuration for CLI and Streamlit."""

from __future__ import annotations

import os

CLOUD_OPENAI_PROVIDER = "openai"
LOCAL_OPENAI_PROVIDER = "openai-local"

SUPPORTED_PROVIDERS: tuple[str, ...] = (
    "ollama",
    "lm-studio",
    LOCAL_OPENAI_PROVIDER,
    CLOUD_OPENAI_PROVIDER,
)

PROVIDER_LABELS: dict[str, str] = {
    "ollama": "Ollama (local)",
    "lm-studio": "LM Studio (local)",
    LOCAL_OPENAI_PROVIDER: "OpenAI-Compatible (local)",
    CLOUD_OPENAI_PROVIDER: "OpenAI (cloud)",
}


def get_provider_defaults(provider: str) -> tuple[str, str]:
    """Return (base_url, model) defaults for the given provider."""
    if provider == "lm-studio":
        return "http://localhost:1234", "lmstudio-community/Qwen2.5-7B-Instruct-GGUF"
    if provider == LOCAL_OPENAI_PROVIDER:
        return "http://localhost:8080", "llama"
    if provider == CLOUD_OPENAI_PROVIDER:
        return "https://api.openai.com/v1", "gpt-4o"
    return "http://localhost:11434", "qwen3.5:35b"


def provider_requires_openai_api_key(provider: str) -> bool:
    """Return True when the provider needs a cloud OpenAI API key."""
    return provider == CLOUD_OPENAI_PROVIDER


def resolve_openai_api_key(*, provider: str, user_api_key: str | None = None) -> str | None:
    """Resolve the effective OpenAI API key from UI input or process environment."""
    if not provider_requires_openai_api_key(provider):
        return None
    if user_api_key and user_api_key.strip():
        return user_api_key.strip()
    env_key = os.environ.get("OPENAI_API_KEY", "").strip()
    return env_key or None


def sync_openai_api_key_to_env(provider: str, api_key: str | None) -> None:
    """Apply a session-scoped OpenAI API key to the process environment.

    Never writes to disk. Platform injectors (Azure App Service, AWS, etc.)
    can still pre-populate OPENAI_API_KEY before the app starts.
    """
    if provider_requires_openai_api_key(provider) and api_key:
        os.environ["OPENAI_API_KEY"] = api_key
