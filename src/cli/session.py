"""CLI session state management.

Holds all mutable state across interactive prompts so that the main
menu loop and pipeline handlers share a single, well-typed context.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.file_utils import slugify
from src.journey_scraper import CredentialProfile, JourneyStep
from src.pipeline_artifact_manager import PackageManifest
from src.provider_config import DEFAULT_PROVIDER, get_provider_defaults, resolve_provider, validate_provider
from src.pytest_output_parser import RunResult
from src.run_result_persistence import PersistedRunResult
from src.settings_store import load_setting
from src.spec_analyzer import TestCondition
from src.test_plan import TestPlan
from src.test_table import TestTable


@dataclass
class Session:
    """Holds mutable state across interactive prompts."""

    # Pipeline artifacts
    pipeline_results: str | None = None
    pipeline_skeleton: str = ""
    pipeline_saved_path: str | Path = ""
    pipeline_manifest_path: str = ""
    pipeline_error: str = ""
    pipeline_unresolved: list[str] = field(default_factory=list)
    pipeline_scraped_pages: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    pipeline_urls: list[str] = field(default_factory=list)
    pipeline_criteria: str = ""
    pipeline_conditions: list[TestCondition] = field(default_factory=list)
    pipeline_run_result: RunResult | None = None
    pipeline_run_output: str = ""
    pipeline_run_command: str = ""
    pipeline_run_return_code: int | None = None

    # Reports
    pipeline_local_report: str = ""
    pipeline_jira_report: str = ""
    pipeline_html_report: str = ""
    pipeline_local_report_path: str = ""
    pipeline_jira_report_path: str = ""
    pipeline_html_report_path: str = ""
    # j-0286: the JSON report the service already writes, and the three evidence
    # exports (csv/ndjson/junit) the menu now offers alongside it. Keyed by
    # format name so the viewer lists whatever was actually produced.
    pipeline_local_json_path: str = ""
    pipeline_export_paths: dict[str, str] = field(default_factory=dict)

    # Bug report
    pipeline_bug_report: str = ""
    pipeline_bug_report_path: str = ""

    # Test plan
    test_plan: TestPlan | None = None
    plan_confirmed: bool = False

    # Test table (AI-034) — expanded rows per condition
    test_table: TestTable | None = None
    test_table_confirmed: bool = False

    # LLM configuration
    provider: str = ""
    provider_base_url: str = ""
    model_name: str = ""

    # Target site
    starting_url: str = ""
    additional_urls: str = ""

    # Pipeline settings
    consent_mode: str = "auto-dismiss"
    pom_mode: bool = False

    # Export-time Jira project key (B-036 Phase 4) — feeds Jira test-case
    # IDs and the Jira report header.
    jira_project_key: str = "TEST"

    # Requirements
    raw_requirements: str = ""

    @property
    def story_slug(self) -> str:
        """Slug of the pasted story, used to name exported output directories.

        Mirrors the pipeline writer's package naming (slugify of the first 50
        chars of the story). Previously referenced as ``session.story_slug``
        without ever being defined — the CLI export flow raised AttributeError.
        """
        story_text = (self.raw_requirements or "").strip()
        return slugify(story_text[:50]) if story_text else ""

    # Authentication / Journey (AI-009 Phase B)
    credential_profile: CredentialProfile | None = None
    journey_steps: list[JourneyStep] = field(default_factory=list)

    # Persisted package state (AI-026)
    loaded_package_manifest: PackageManifest | None = None
    loaded_package_run_results: list[PersistedRunResult] | None = None
    loaded_package_flaky_tests: list[tuple[str, dict[str, int]]] = field(default_factory=list)


def _env_or_default(key: str, default: str) -> str:
    """Return env var value or *default* when empty/missing."""
    return os.environ.get(key, "").strip() or default


def _session_defaults(provider: str | None = None) -> dict[str, str]:
    """Compute Session defaults for *provider* from environment variables.

    When *provider* is None the name comes from ``$LLM_PROVIDER`` (default
    openai-local). d-0132: an unknown name raises ``ValueError`` here, and the
    CLI boundary turns that into one clear line - it never becomes a traceback.
    """
    # AGENTS.md §5 / README: the documented default provider is openai-local
    # (llama.cpp :8080). This used to default to "ollama", contradicting both
    # the settings store and create_provider_from_env.
    provider = provider or _env_or_default("LLM_PROVIDER", DEFAULT_PROVIDER)
    validate_provider(provider)
    base_url, model = get_provider_defaults(provider)

    url_env_keys: dict[str, str] = {
        "ollama": "OLLAMA_BASE_URL",
        "lm-studio": "LM_STUDIO_BASE_URL",
        "openai": "OPENAI_BASE_URL",
        "openai-local": "OPENAI_BASE_URL",
        "azure-openai": "AZURE_OPENAI_ENDPOINT",
        "openai-compatible": "OPENAI_COMPATIBLE_BASE_URL",
        "openrouter": "OPENAI_COMPATIBLE_BASE_URL",
    }
    model_env_keys: dict[str, str] = {
        "ollama": "OLLAMA_MODEL",
        "lm-studio": "LM_STUDIO_MODEL",
        "openai": "OPENAI_MODEL",
        "openai-local": "OPENAI_MODEL",
        "azure-openai": "AZURE_OPENAI_DEPLOYMENT",
        "openai-compatible": "OPENAI_COMPATIBLE_MODEL",
        "openrouter": "OPENAI_COMPATIBLE_MODEL",
    }

    return {
        "provider": provider,
        "provider_base_url": _env_or_default(url_env_keys.get(provider, ""), base_url),
        "model_name": _env_or_default(model_env_keys.get(provider, ""), model),
    }


def resolve_session_provider(flag: str = "") -> str:
    """Resolve and validate the provider the CLI will use, before a Session exists.

    d-0132: one precedence for the session layer - the ``--provider`` flag,
    then the persisted setting, then ``$LLM_PROVIDER``, then openai-local. A
    valid flag outranks a stale environment variable, a saved choice outranks
    one too (B-036), and an unknown name from ANY of the three sources is
    refused instead of reaching the menu, the probe or the pipeline.

    Raises:
        ValueError: when the winning name is not a supported provider.
    """
    return resolve_provider(
        flag=flag,
        persisted=str(load_setting("provider", "") or ""),
        env=os.environ.get("LLM_PROVIDER", ""),
    )


def create_session(provider: str | None = None) -> Session:
    """Factory: create a Session populated with persisted + environment defaults.

    B-036 Phase 4: persisted SettingsStore values seed base-url/model, consent
    mode, POM mode and the Jira project key, so CLI choices survive across
    sessions (matching the Streamlit sidebar). d-0132: the PROVIDER is the
    exception, because it must be validated before anything else is read - see
    resolve_session_provider() for its precedence.

    *provider* is the caller's own choice (normally a ``--provider`` flag) and
    it outranks both the environment and the persisted setting. The
    winning name is validated before anything is built, so an unknown provider
    from a flag, the environment or the settings store raises ``ValueError``
    here - at the session boundary - and never as a traceback from a later
    menu or probe call.
    """
    chosen = resolve_session_provider(provider or "")
    defaults = _session_defaults(chosen)
    consent_mode = str(load_setting("consent_mode", "") or "auto-dismiss")
    return Session(
        provider=chosen,
        provider_base_url=str(load_setting("provider_base_url", "") or defaults["provider_base_url"]),
        model_name=str(load_setting("model_name", "") or defaults["model_name"]),
        consent_mode=consent_mode,
        pom_mode=bool(load_setting("pom_mode", False)),
        jira_project_key=str(load_setting("jira_project_key", "") or "TEST"),
    )
