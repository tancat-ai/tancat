"""Tests for CLI LLM configuration parity."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.cli import menu_renderer


def test_configure_llm_prompts_for_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with (
        patch.object(menu_renderer, "print_menu", return_value=3),
        patch.object(menu_renderer, "read_optional", side_effect=["https://api.openai.com/v1", "1"]),
        patch.object(menu_renderer, "_get_available_models", return_value=["gpt-4o"]),
        patch.object(menu_renderer, "_prompt_openai_api_key", return_value="sk-test-key") as mock_prompt,
    ):
        provider, base_url, model = menu_renderer.configure_llm("ollama", "http://localhost:11434", "qwen3.5:35b")

    mock_prompt.assert_called_once()
    assert provider == "openai"
    assert base_url == "https://api.openai.com/v1"
    assert model == "gpt-4o"
    assert os.environ["OPENAI_API_KEY"] == "sk-test-key"


def test_configure_llm_skips_api_key_prompt_for_openai_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with (
        patch.object(menu_renderer, "print_menu", return_value=2),
        patch.object(menu_renderer, "read_optional", side_effect=["http://localhost:8080", "llama"]),
        patch.object(menu_renderer, "_get_available_models", return_value=[]),
        patch.object(menu_renderer, "_prompt_openai_api_key") as mock_prompt,
    ):
        provider, base_url, model = menu_renderer.configure_llm("ollama", "http://localhost:11434", "qwen3.5:35b")

    mock_prompt.assert_not_called()
    assert provider == "openai-local"
    assert base_url == "http://localhost:8080"
    assert model == "llama"
    assert "OPENAI_API_KEY" not in os.environ
