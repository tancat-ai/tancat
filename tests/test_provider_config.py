"""Tests for shared LLM provider configuration helpers."""

from __future__ import annotations

import os

import pytest

from src.provider_config import (
    get_provider_defaults,
    provider_requires_openai_api_key,
    resolve_openai_api_key,
    sync_openai_api_key_to_env,
)


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("ollama", ("http://localhost:11434", "qwen3.5:35b")),
        ("lm-studio", ("http://localhost:1234", "lmstudio-community/Qwen2.5-7B-Instruct-GGUF")),
        ("openai-local", ("http://localhost:8080", "llama")),
        ("openai", ("https://api.openai.com/v1", "gpt-4o")),
    ],
)
def test_get_provider_defaults(provider: str, expected: tuple[str, str]) -> None:
    assert get_provider_defaults(provider) == expected


@pytest.mark.parametrize(
    ("provider", "requires_key"),
    [
        ("ollama", False),
        ("lm-studio", False),
        ("openai-local", False),
        ("openai", True),
    ],
)
def test_provider_requires_openai_api_key(provider: str, requires_key: bool) -> None:
    assert provider_requires_openai_api_key(provider) is requires_key


def test_resolve_openai_api_key_prefers_user_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    assert resolve_openai_api_key(provider="openai", user_api_key="user-key") == "user-key"


def test_resolve_openai_api_key_falls_back_to_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    assert resolve_openai_api_key(provider="openai", user_api_key=None) == "env-key"


def test_resolve_openai_api_key_ignored_for_local_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    assert resolve_openai_api_key(provider="openai-local", user_api_key="user-key") is None


def test_sync_openai_api_key_to_env_sets_process_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    sync_openai_api_key_to_env("openai", "session-key")
    assert os.environ["OPENAI_API_KEY"] == "session-key"


def test_sync_openai_api_key_to_env_skips_non_cloud_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    sync_openai_api_key_to_env("ollama", "ignored")
    assert "OPENAI_API_KEY" not in os.environ
