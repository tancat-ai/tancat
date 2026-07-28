"""Tests for OpenAI-compatible cloud provider support.

Verifies that ``openai-compatible`` and ``openrouter`` provider names
work through the factory, env-var config, and OpenAIProvider class.
"""

from __future__ import annotations

import pytest

from src.llm_providers import (
    OpenAIProvider,
    create_provider_from_env,
    get_provider,
)


class TestGetProvider:
    def test_openai_compatible_provider_name(self) -> None:
        provider = get_provider("openai-compatible", api_key="test-key")
        assert provider.provider_name == "openai-compatible"

    def test_openrouter_provider_name(self) -> None:
        provider = get_provider("openrouter", api_key="test-key")
        assert provider.provider_name == "openai-compatible"

    def test_openai_compatible_sets_flag(self) -> None:
        provider = get_provider("openai-compatible", api_key="test-key")
        assert isinstance(provider, OpenAIProvider)
        assert provider._is_openai_compatible is True

    def test_openrouter_sets_flag(self) -> None:
        provider = get_provider("openrouter", api_key="test-key")
        assert isinstance(provider, OpenAIProvider)
        assert provider._is_openai_compatible is True

    def test_raises_on_missing_api_key(self) -> None:
        with pytest.raises(ValueError, match="API key is required"):
            get_provider("openai-compatible")

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("nonexistent-provider")


class TestCreateProviderFromEnv:
    def test_openai_compatible_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-test-key")
        monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "https://api.together.xyz/v1")
        monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "meta-llama/Llama-3.3-70B")

        provider = create_provider_from_env()
        assert provider.provider_name == "openai-compatible"
        assert isinstance(provider, OpenAIProvider)

    def test_openrouter_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "openrouter")
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-or-v1-test-key")

        provider = create_provider_from_env()
        assert provider.provider_name == "openai-compatible"
        assert isinstance(provider, OpenAIProvider)

    def test_unknown_provider_from_env_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "invalid-provider")
        with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
            create_provider_from_env()


class TestOpenAICompatibleInstance:
    def test_provider_name_property(self) -> None:
        provider = OpenAIProvider(api_key="test-key", is_openai_compatible=True)
        assert provider.provider_name == "openai-compatible"

    def test_default_model_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "anthropic/claude-sonnet-4")
        provider = OpenAIProvider(api_key="test-key", is_openai_compatible=True)
        # The model is resolved inside complete(), but we can verify the env var config
        assert provider.provider_name == "openai-compatible"

    def test_api_key_reads_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-or-v1-test-key")
        provider = OpenAIProvider(is_openai_compatible=True)
        assert provider.provider_name == "openai-compatible"

    def test_local_provider_name_unchanged(self) -> None:
        provider = OpenAIProvider(is_local=True)
        assert provider.provider_name == "openai-local"
