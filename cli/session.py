"""CLI session state management.

Holds all mutable state across interactive prompts so that the main
menu loop and pipeline handlers share a single, well-typed context.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from src.journey_scraper import CredentialProfile, JourneyStep
from src.pytest_output_parser import RunResult
from src.spec_analyzer import TestCondition
from src.test_plan import TestPlan


@dataclass
class Session:
    """Holds mutable state across interactive prompts."""

    # Pipeline artifacts
    pipeline_results: str | None = None
    pipeline_skeleton: str = ""
    pipeline_saved_path: str = ""
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

    # Test plan
    test_plan: TestPlan | None = None
    plan_confirmed: bool = False

    # LLM configuration
    provider: str = ""
    provider_base_url: str = ""
    model_name: str = ""

    # Target site
    starting_url: str = ""
    additional_urls: str = ""

    # Pipeline settings
    consent_mode: str = "auto-dismiss"

    # Requirements
    raw_requirements: str = ""

    # Authentication / Journey (AI-009 Phase B)
    credential_profile: CredentialProfile | None = None
    journey_steps: list[JourneyStep] = field(default_factory=list)


def _env_or_default(key: str, default: str) -> str:
    """Return env var value or *default* when empty/missing."""
    return os.environ.get(key, "").strip() or default


def _session_defaults() -> dict[str, str]:
    """Compute Session defaults from .env (already loaded) or hardcoded fallbacks."""
    provider = _env_or_default("LLM_PROVIDER", "ollama")

    if provider == "lm-studio":
        return {
            "provider": "lm-studio",
            "provider_base_url": _env_or_default("LM_STUDIO_BASE_URL", "http://localhost:1234"),
            "model_name": _env_or_default("LM_STUDIO_MODEL", "lmstudio-community/Qwen2.5-7B-Instruct-GGUF"),
        }
    # Default (ollama or openai)
    return {
        "provider": "ollama",
        "provider_base_url": _env_or_default("OLLAMA_BASE_URL", "http://localhost:11434"),
        "model_name": _env_or_default("OLLAMA_MODEL", "qwen3.5:35b"),
    }


def create_session() -> Session:
    """Factory: create a Session populated with environment-based defaults."""
    defaults = _session_defaults()
    return Session(
        provider=defaults["provider"],
        provider_base_url=defaults["provider_base_url"],
        model_name=defaults["model_name"],
    )
