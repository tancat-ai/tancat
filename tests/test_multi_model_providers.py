"""Multi-model cloud providers (OpenRouter + generic OpenAI-compatible).

The provider layer implemented these from the start, but every UI/CLI screen
hid them. These tests pin the fixes: they are selectable, they require a key,
the environment route (base URL + model) is honoured, the default model is not
a hard-coded OpenRouter id, and the client sends a browser-like User-Agent.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from src.cli.session import _session_defaults
from src.llm_providers import (
    BROWSER_USER_AGENT,
    ChatMessage,
    OpenAIProvider,
    create_provider_from_env,
    get_provider,
)
from src.provider_config import (
    SUPPORTED_PROVIDERS,
    api_key_env_var,
    get_provider_defaults,
    provider_requires_openai_api_key,
    resolve_openai_api_key,
    sync_openai_api_key_to_env,
)


@pytest.fixture(autouse=True)
def _hermetic_environment() -> Iterator[None]:
    """Snapshot and restore ``os.environ`` around every test in this module.

    ``sync_openai_api_key_to_env`` writes ``os.environ`` directly, which
    ``monkeypatch`` does not track (it only records its own setenv/delenv
    calls). Without this snapshot the key those tests write leaks into later
    tests — and, because an xdist worker runs several files in sequence, into
    later files too. That leak made two j-0095 CI tests order-dependent.
    """
    before = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(before)


class TestSelectable:
    """The registry agrees across the UI list, the factory and the env factory."""

    def test_compatible_providers_are_in_the_supported_list(self) -> None:
        assert "openai-compatible" in SUPPORTED_PROVIDERS
        assert "openrouter" in SUPPORTED_PROVIDERS

    @pytest.mark.parametrize("provider", SUPPORTED_PROVIDERS)
    def test_factory_accepts_every_supported_provider(self, provider: str) -> None:
        # A dummy key is harmless for the local providers (they accept **kwargs).
        instance = get_provider(provider, api_key="test-key", base_url="http://localhost:1/v1")
        assert instance is not None

    @pytest.mark.parametrize("provider", SUPPORTED_PROVIDERS)
    def test_env_factory_accepts_every_supported_provider(self, provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", provider)
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "test-key")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8080")
        monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "https://example.test/v1")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.test.openai.azure.com")
        assert create_provider_from_env() is not None

    def test_key_env_var_maps_to_the_compatible_variable(self) -> None:
        assert api_key_env_var("openai") == "OPENAI_API_KEY"
        assert api_key_env_var("openai-compatible") == "OPENAI_COMPATIBLE_API_KEY"
        assert api_key_env_var("openrouter") == "OPENAI_COMPATIBLE_API_KEY"


class TestKeyRequired:
    @pytest.mark.parametrize("provider", ["openai", "openai-compatible", "openrouter"])
    def test_cloud_providers_require_a_key(self, provider: str) -> None:
        assert provider_requires_openai_api_key(provider) is True

    @pytest.mark.parametrize("provider", ["ollama", "lm-studio", "openai-local"])
    def test_local_providers_do_not_require_a_key(self, provider: str) -> None:
        assert provider_requires_openai_api_key(provider) is False

    def test_compatible_provider_raises_without_a_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
        with pytest.raises(ValueError, match="API key is required"):
            OpenAIProvider(is_openai_compatible=True, base_url="https://example.test/v1")

    def test_resolve_reads_the_compatible_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "env-compat-key")
        assert resolve_openai_api_key(provider="openai-compatible", user_api_key=None) == "env-compat-key"
        assert resolve_openai_api_key(provider="openrouter", user_api_key=None) == "env-compat-key"

    def test_sync_writes_the_compatible_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
        sync_openai_api_key_to_env("openrouter", "session-key")
        assert os.environ["OPENAI_COMPATIBLE_API_KEY"] == "session-key"
        assert os.environ.get("OPENAI_API_KEY") is None

    def test_sync_writes_the_openai_env_var_for_openai(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        sync_openai_api_key_to_env("openai", "session-key")
        assert os.environ["OPENAI_API_KEY"] == "session-key"


class TestEnvironmentRouteHonoured:
    def test_compatible_base_url_and_model_come_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
        monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "https://api.together.xyz/v1")
        monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo")

        defaults = _session_defaults()
        assert defaults["provider"] == "openai-compatible"
        assert defaults["provider_base_url"] == "https://api.together.xyz/v1"
        assert defaults["model_name"] == "meta-llama/Llama-3.3-70B-Instruct-Turbo"

    def test_openrouter_env_model_is_honoured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "openrouter")
        monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "anthropic/claude-sonnet-4")
        monkeypatch.delenv("OPENAI_COMPATIBLE_BASE_URL", raising=False)

        defaults = _session_defaults()
        assert defaults["provider"] == "openrouter"
        assert defaults["provider_base_url"] == "https://openrouter.ai/api/v1"
        assert defaults["model_name"] == "anthropic/claude-sonnet-4"


class TestDefaultModel:
    @pytest.mark.parametrize("provider", ["openai-compatible", "openrouter"])
    def test_default_model_is_not_a_hardcoded_openrouter_id(self, provider: str) -> None:
        _base_url, model = get_provider_defaults(provider)
        assert model not in ("gpt-4o", "openai/gpt-4o")

    def test_llmclient_default_model_is_not_gpt4o(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.llm_client import LLMClient

        monkeypatch.delenv("OPENAI_COMPATIBLE_MODEL", raising=False)
        # No network: the auto-detect list call is stubbed empty.
        monkeypatch.setattr(LLMClient, "list_models", lambda self, timeout=30: [])
        client = LLMClient(provider="openai-compatible", api_key="test-key", base_url="https://example.test/v1")
        assert client.model not in ("gpt-4o", "openai/gpt-4o")

    def test_complete_requires_an_explicit_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_COMPATIBLE_MODEL", raising=False)
        provider = OpenAIProvider(api_key="test-key", base_url="https://example.test/v1", is_openai_compatible=True)
        with pytest.raises(ValueError, match="No model configured"):
            provider.complete([ChatMessage(role="user", content="hi")], model="")


class TestUserAgent:
    def test_compatible_client_sends_a_browser_user_agent(self) -> None:
        provider = OpenAIProvider(api_key="test-key", base_url="https://example.test/v1", is_openai_compatible=True)
        # httpx lower-cases header names.
        assert provider._client.headers.get("user-agent") == BROWSER_USER_AGENT
        assert "Mozilla" in BROWSER_USER_AGENT
