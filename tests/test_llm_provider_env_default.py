"""The env fallback for create_provider_from_env must default to openai-local.

AGENTS.md §5 pins the default LLM provider to ``openai-local`` (llama.cpp :8080)
and forbids hardcoding ``ollama``. Before this, an unset ``LLM_PROVIDER``
silently targeted the Ollama port and only failed at the first LLM call.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.llm_providers import OllamaProvider, OpenAIProvider, create_provider_from_env

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"


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


def _active_env_values(path: Path) -> dict[str, str]:
    """Return the uncommented KEY=VALUE lines from an env template."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


class TestEnvExampleDefaultProvider:
    """Copying .env.example must not land a new user on the wrong provider.

    The template used to set ``LLM_PROVIDER=ollama`` while the code default and
    the docs said ``openai-local``, so the first configuration step pointed at
    :11434 and only failed at the first LLM call.
    """

    def test_env_example_selects_the_code_default_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8080")
        code_default = create_provider_from_env().provider_name

        assert _active_env_values(ENV_EXAMPLE)["LLM_PROVIDER"] == code_default

    def test_env_example_default_is_not_ollama(self) -> None:
        assert _active_env_values(ENV_EXAMPLE)["LLM_PROVIDER"] != "ollama"

    def test_env_example_cannot_point_the_default_at_the_cloud(self) -> None:
        """The active OPENAI_* values must stay local for the openai-local default."""
        active = _active_env_values(ENV_EXAMPLE)
        assert active["LLM_PROVIDER"] == "openai-local"
        assert "api.openai.com" not in active.get("OPENAI_BASE_URL", "")
