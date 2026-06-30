"""Tests for Streamlit provider configuration helpers."""

from __future__ import annotations

from src.provider_config import get_provider_defaults
from src.ui_pipeline import _get_provider_defaults


def test_openai_local_provider_defaults() -> None:
    assert get_provider_defaults("openai-local") == ("http://localhost:8080", "llama")
    assert _get_provider_defaults("openai-local") == ("http://localhost:8080", "llama")


def test_openai_cloud_provider_defaults() -> None:
    assert get_provider_defaults("openai") == ("https://api.openai.com/v1", "gpt-4o")
    assert _get_provider_defaults("openai") == ("https://api.openai.com/v1", "gpt-4o")


def test_ollama_provider_defaults() -> None:
    assert get_provider_defaults("ollama") == ("http://localhost:11434", "qwen3.5:35b")


def test_lm_studio_provider_defaults() -> None:
    assert get_provider_defaults("lm-studio") == (
        "http://localhost:1234",
        "lmstudio-community/Qwen2.5-7B-Instruct-GGUF",
    )
