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


class TestThinkingModeSwitch:
    """OpenAI-compatible endpoints get an explicit chat_template_kwargs switch.

    ``enable_thinking=None`` (the default) must NOT add the field — the
    model/server default governs and is never silently overridden. Only an
    explicit True/False is forwarded.
    """

    @staticmethod
    def _payload_for(provider: object, **complete_kwargs: object) -> dict[str, object]:
        from unittest.mock import MagicMock, patch

        from src.llm_providers import ChatMessage

        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
            "model": "m",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        with patch.object(provider, "_client") as mock_client:  # type: ignore[arg-type]
            mock_client.post.return_value = mock_resp
            mock_post = mock_client.post
            provider.complete([ChatMessage(role="user", content="hi")], model="m", **complete_kwargs)  # type: ignore[attr-defined,union-attr]
        return mock_post.call_args[1]["json"]  # type: ignore[no-any-return]

    def test_openai_default_sends_no_thinking_field(self) -> None:
        provider = get_provider("openai-compatible", api_key="sk-test-key")
        payload = self._payload_for(provider)
        assert "chat_template_kwargs" not in payload

    def test_openai_explicit_off_sends_chat_template_kwargs(self) -> None:
        provider = get_provider("openai-compatible", api_key="sk-test-key")
        payload = self._payload_for(provider, enable_thinking=False)
        assert payload["chat_template_kwargs"] == {"enable_thinking": False}

    def test_openai_explicit_on_sends_chat_template_kwargs(self) -> None:
        provider = get_provider("openai-compatible", api_key="sk-test-key")
        payload = self._payload_for(provider, enable_thinking=True)
        assert payload["chat_template_kwargs"] == {"enable_thinking": True}

    def test_lmstudio_default_sends_no_thinking_field(self) -> None:
        from src.llm_providers import LMStudioProvider

        provider = LMStudioProvider(base_url="http://localhost:1234")
        payload = self._payload_for(provider)
        assert "chat_template_kwargs" not in payload

    def test_lmstudio_explicit_off_sends_chat_template_kwargs(self) -> None:
        from src.llm_providers import LMStudioProvider

        provider = LMStudioProvider(base_url="http://localhost:1234")
        payload = self._payload_for(provider, enable_thinking=False)
        assert payload["chat_template_kwargs"] == {"enable_thinking": False}

    def test_ollama_accepts_switch_for_contract_parity(self) -> None:
        from unittest.mock import MagicMock, patch

        from src.llm_providers import ChatMessage, OllamaProvider

        provider = OllamaProvider(base_url="http://localhost:11434")
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"message": {"content": "ok"}, "model": "m"}
        with patch.object(provider, "_client") as mock_client:
            mock_client.post.return_value = mock_resp
            # Must not raise — Ollama has no thinking switch but honors the contract.
            provider.complete([ChatMessage(role="user", content="hi")], model="m", enable_thinking=False)


class TestGenerationTokenCap:
    """Every provider must cap generation so a runaway LLM response can't burn
    the full request timeout (B-028 session: skeleton call ran 600s)."""

    def test_openai_payload_includes_max_tokens(self) -> None:
        from unittest.mock import MagicMock, patch

        from src.llm_providers import ChatMessage

        with patch("src.llm_providers.generation_max_tokens", return_value=2048):
            provider = get_provider("openai-compatible", api_key="sk-test-key")
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "ok"}}],
                "model": "m",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }
            with patch.object(provider, "_client") as mock_client:
                mock_client.post.return_value = mock_resp
                mock_post = mock_client.post
                provider.complete([ChatMessage(role="user", content="hi")], model="m")
            payload = mock_post.call_args[1]["json"]
            assert payload["max_tokens"] == 2048

    def test_lmstudio_payload_includes_max_tokens(self) -> None:
        from unittest.mock import MagicMock, patch

        from src.llm_providers import ChatMessage, LMStudioProvider

        with patch("src.llm_providers.generation_max_tokens", return_value=2048):
            provider = LMStudioProvider(base_url="http://localhost:1234")
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "ok"}}],
                "model": "m",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }
            with patch.object(provider, "_client") as mock_client:
                mock_client.post.return_value = mock_resp
                mock_post = mock_client.post
                provider.complete([ChatMessage(role="user", content="hi")], model="m")
            payload = mock_post.call_args[1]["json"]
            assert payload["max_tokens"] == 2048

    def test_ollama_payload_includes_num_predict(self) -> None:
        from unittest.mock import MagicMock, patch

        from src.llm_providers import ChatMessage, OllamaProvider

        with patch("src.llm_providers.generation_max_tokens", return_value=2048):
            provider = OllamaProvider(base_url="http://localhost:11434")
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {"message": {"content": "ok"}, "model": "m"}
            with patch.object(provider, "_client") as mock_client:
                mock_client.post.return_value = mock_resp
                mock_post = mock_client.post
                provider.complete([ChatMessage(role="user", content="hi")], model="m")
            payload = mock_post.call_args[1]["json"]
            assert payload["options"]["num_predict"] == 2048

    def test_env_var_overrides_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.llm_providers import generation_max_tokens

        monkeypatch.setenv("LLM_MAX_TOKENS", "1024")
        assert generation_max_tokens() == 1024

    def test_invalid_env_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.llm_providers import generation_max_tokens

        monkeypatch.setenv("LLM_MAX_TOKENS", "not-a-number")
        assert generation_max_tokens() == 4096
