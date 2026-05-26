"""Unit tests for the UI pipeline module."""

from __future__ import annotations

from src.ui_pipeline import _get_provider_defaults


class TestGetProviderDefaults:
    """Tests for the _get_provider_defaults function."""

    def test_ollama_defaults(self) -> None:
        """Verify Ollama default URL and model."""
        base_url, model = _get_provider_defaults("ollama")
        assert base_url == "http://localhost:11434"
        assert model == "qwen3.5:35b"

    def test_lm_studio_defaults(self) -> None:
        """Verify LM Studio default URL and model."""
        base_url, model = _get_provider_defaults("lm-studio")
        assert base_url == "http://localhost:1234"
        assert model == "lmstudio-community/Qwen2.5-7B-Instruct-GGUF"

    def test_openai_local_defaults(self) -> None:
        """Verify OpenAI-compatible local default URL and model."""
        base_url, model = _get_provider_defaults("openai-local")
        assert base_url == "http://localhost:8080/v1"
        assert model == "llama"

    def test_openai_cloud_defaults(self) -> None:
        """Verify cloud OpenAI default URL and model."""
        base_url, model = _get_provider_defaults("openai")
        assert base_url == "https://api.openai.com/v1"
        assert model == "gpt-4o"

    def test_fallback_defaults(self) -> None:
        """Verify fallback defaults for an unknown provider."""
        base_url, model = _get_provider_defaults("unknown-provider")
        assert base_url == "http://localhost:11434"
        assert model == "qwen3.5:35b"
