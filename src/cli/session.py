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
from src.provider_config import get_provider_defaults
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


def _session_defaults() -> dict[str, str]:
    """Compute Session defaults from environment variables or provider fallbacks."""
    provider = _env_or_default("LLM_PROVIDER", "ollama")
    base_url, model = get_provider_defaults(provider)

    url_env_keys: dict[str, str] = {
        "ollama": "OLLAMA_BASE_URL",
        "lm-studio": "LM_STUDIO_BASE_URL",
        "openai": "OPENAI_BASE_URL",
        "openai-local": "OPENAI_BASE_URL",
    }
    model_env_keys: dict[str, str] = {
        "ollama": "OLLAMA_MODEL",
        "lm-studio": "LM_STUDIO_MODEL",
        "openai": "OPENAI_MODEL",
        "openai-local": "OPENAI_MODEL",
    }

    return {
        "provider": provider,
        "provider_base_url": _env_or_default(url_env_keys.get(provider, ""), base_url),
        "model_name": _env_or_default(model_env_keys.get(provider, ""), model),
    }


def create_session() -> Session:
    """Factory: create a Session populated with persisted + environment defaults.

    B-036 Phase 4: persisted SettingsStore values win over env defaults for
    provider/base-url/model, consent mode, POM mode and the Jira project key,
    so CLI choices survive across sessions (matching the Streamlit sidebar).
    """
    defaults = _session_defaults()
    provider = str(load_setting("provider", "") or defaults["provider"])
    consent_mode = str(load_setting("consent_mode", "") or "auto-dismiss")
    return Session(
        provider=provider,
        provider_base_url=str(load_setting("provider_base_url", "") or defaults["provider_base_url"]),
        model_name=str(load_setting("model_name", "") or defaults["model_name"]),
        consent_mode=consent_mode,
        pom_mode=bool(load_setting("pom_mode", False)),
        jira_project_key=str(load_setting("jira_project_key", "") or "TEST"),
    )
