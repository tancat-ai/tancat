"""Tests for Streamlit provider configuration helpers."""

from __future__ import annotations

from src.ui_pipeline import _get_provider_defaults


def test_openai_local_provider_defaults() -> None:
    assert _get_provider_defaults("openai-local") == ("http://localhost:8080", "llama")


def test_openai_cloud_provider_defaults() -> None:
    assert _get_provider_defaults("openai") == ("https://api.openai.com/v1", "gpt-4o")
