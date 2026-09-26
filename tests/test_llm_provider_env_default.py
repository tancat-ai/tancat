"""The env fallback for create_provider_from_env must default to openai-local.

AGENTS.md §5 pins the default LLM provider to ``openai-local`` (llama.cpp :8080)
and forbids hardcoding ``ollama``. Before this, an unset ``LLM_PROVIDER``
silently targeted the Ollama port and only failed at the first LLM call.
"""

from __future__ import annotations

import pytest

from src.llm_providers import OllamaProvider, OpenAIProvider, create_provider_from_env


class TestCreateProviderFromEnvDefault:
    def test_unset_provider_defaults_to_openai_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        # Pin the base URL so construction does not probe localhost ports.
        monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8080")

        provider = create_provider_from_env()

        assert isinstance(provider, OpenAIProvider)
        assert provider.provider_name == "openai-local"
        assert provider.base_url == "http://localhost:8080"

    def test_explicit_ollama_still_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

        provider = create_provider_from_env()

        assert isinstance(provider, OllamaProvider)

    def test_explicit_openai_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "openai-local")
        monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8080")

        provider = create_provider_from_env()

        assert isinstance(provider, OpenAIProvider)
        assert provider.provider_name == "openai-local"
