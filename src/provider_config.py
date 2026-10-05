"""Shared LLM provider configuration for CLI and Streamlit."""

from __future__ import annotations

import os

CLOUD_OPENAI_PROVIDER = "openai"
LOCAL_OPENAI_PROVIDER = "openai-local"
OPENAI_COMPATIBLE_PROVIDER = "openai-compatible"
OPENROUTER_PROVIDER = "openrouter"

SUPPORTED_PROVIDERS: tuple[str, ...] = (
    "ollama",
    "lm-studio",
    LOCAL_OPENAI_PROVIDER,
    CLOUD_OPENAI_PROVIDER,
    OPENAI_COMPATIBLE_PROVIDER,
    OPENROUTER_PROVIDER,
)

# The environment variable that carries each provider's API key. Keep this the
# single source of truth so the UI field, the CLI prompt and the provider
# factory all read and write the same variable.
_PROVIDER_KEY_ENV: dict[str, str] = {
    CLOUD_OPENAI_PROVIDER: "OPENAI_API_KEY",
    OPENAI_COMPATIBLE_PROVIDER: "OPENAI_COMPATIBLE_API_KEY",
    OPENROUTER_PROVIDER: "OPENAI_COMPATIBLE_API_KEY",
}

PROVIDER_LABELS: dict[str, str] = {
    "ollama": "Ollama (local)",
    "lm-studio": "LM Studio (local)",
    LOCAL_OPENAI_PROVIDER: "OpenAI-Compatible (local)",
    CLOUD_OPENAI_PROVIDER: "OpenAI (cloud)",
    OPENAI_COMPATIBLE_PROVIDER: "OpenAI-Compatible (cloud)",
    OPENROUTER_PROVIDER: "OpenRouter (cloud)",
}


def get_provider_defaults(provider: str) -> tuple[str, str]:
    """Return (base_url, model) defaults for the given provider.

    The compatible cloud providers deliberately have no default *model*: the
    model catalogue differs per endpoint (OpenRouter IDs are not Together, Groq
    or OpenCode IDs), so a hardcoded ``openai/gpt-4o`` was wrong for most of
    them. The user names the model, or sets ``OPENAI_COMPATIBLE_MODEL``; the
    endpoint can also be queried. The base URL defaults to OpenRouter's for both
    compatible keys (the long-standing behaviour) and is overridden by
    ``OPENAI_COMPATIBLE_BASE_URL`` when set.
    """
    if provider == "lm-studio":
        return "http://localhost:1234", "lmstudio-community/Qwen2.5-7B-Instruct-GGUF"
    if provider == LOCAL_OPENAI_PROVIDER:
        return "http://localhost:8080", "llama"
    if provider == CLOUD_OPENAI_PROVIDER:
        return "https://api.openai.com/v1", "gpt-4o"
    if provider == OPENAI_COMPATIBLE_PROVIDER:
        return "https://openrouter.ai/api/v1", ""
    if provider == OPENROUTER_PROVIDER:
        # OpenRouter has a fixed endpoint but a huge catalogue — name the model.
        return "https://openrouter.ai/api/v1", ""
    return "http://localhost:11434", "qwen3.5:35b"


def api_key_env_var(provider: str) -> str:
    """Return the environment variable that carries *provider*'s API key."""
    return _PROVIDER_KEY_ENV.get(provider, "OPENAI_API_KEY")


def provider_requires_openai_api_key(provider: str) -> bool:
    """Return True when the provider needs a cloud API key.

    Covers OpenAI cloud and the OpenAI-compatible cloud providers (OpenRouter
    and any generic compatible endpoint); the local providers need no key.
    """
    return provider in _PROVIDER_KEY_ENV


def resolve_openai_api_key(*, provider: str, user_api_key: str | None = None) -> str | None:
    """Resolve the effective API key from UI input or the provider's env var."""
    if not provider_requires_openai_api_key(provider):
        return None
    if user_api_key and user_api_key.strip():
        return user_api_key.strip()
    env_key = os.environ.get(api_key_env_var(provider), "").strip()
    return env_key or None


def sync_openai_api_key_to_env(provider: str, api_key: str | None) -> None:
    """Apply a session-scoped API key to the provider's environment variable.

    Never writes to disk. Platform injectors (Azure App Service, AWS, etc.) can
    still pre-populate the variable before the app starts. Writing to the
    provider's own variable (``OPENAI_API_KEY`` for OpenAI,
    ``OPENAI_COMPATIBLE_API_KEY`` for the compatible providers) is what lets
    fallback ``LLMClient()`` instances, built from env alone, pick the key up.
    """
    if provider_requires_openai_api_key(provider) and api_key:
        os.environ[api_key_env_var(provider)] = api_key
