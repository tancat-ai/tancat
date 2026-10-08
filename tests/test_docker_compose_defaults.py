"""Guard: the Compose provider default matches what the install docs promise (t-0551).

``docker-compose.yml`` is the bundled-Ollama deployment. The app's own ``.env``
is host-oriented (``LLM_PROVIDER=openai-local`` and localhost URLs by default),
so if Compose read it for the container's provider, a user who copied
``.env.example`` would get ``openai-local`` and the bundled Ollama would sit
idle - while ``install.md`` says the app runs against the bundled Ollama. These
tests pin the decoupling so a later edit cannot quietly re-couple them.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPOSE = PROJECT_ROOT / "docker-compose.yml"
INSTALL_DOC = PROJECT_ROOT / "docs" / "user" / "getting-started" / "install.md"

_SUBST = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}")


def _resolve(value: str, env: dict[str, str] | None = None) -> str:
    """Resolve Compose-style ``${VAR:-default}`` substitutions."""
    env = env or {}

    def repl(match: re.Match[str]) -> str:
        return env.get(match.group(1), match.group(2) or "")

    return _SUBST.sub(repl, value)


def _app_environment() -> dict[str, str]:
    doc: Any = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    entries = doc["services"]["test-generator"]["environment"]
    result: dict[str, str] = {}
    for entry in entries:
        key, _, value = str(entry).partition("=")
        result[key] = value
    return result


def test_compose_provider_defaults_to_the_bundled_ollama() -> None:
    env = _app_environment()
    assert _resolve(env["LLM_PROVIDER"]) == "ollama"
    assert _resolve(env["OLLAMA_BASE_URL"]) == "http://ollama:11434"


def test_compose_ignores_the_host_llm_provider() -> None:
    """A copied .env.example (LLM_PROVIDER=openai-local) must not redirect Compose."""
    env = _app_environment()
    # The substitutions must not read the host-oriented keys themselves.
    assert "${LLM_PROVIDER" not in env["LLM_PROVIDER"]
    assert "${OLLAMA_BASE_URL" not in env["OLLAMA_BASE_URL"]
    assert _resolve(env["LLM_PROVIDER"], {"LLM_PROVIDER": "openai-local"}) == "ollama"


def test_install_doc_says_the_bundled_ollama_is_the_default() -> None:
    text = INSTALL_DOC.read_text(encoding="utf-8")
    compose_section = text.split("## Docker Compose", 1)[1].split("## Update", 1)[0]
    assert "bundled Ollama" in compose_section
    assert "COMPOSE_LLM_PROVIDER" in compose_section
