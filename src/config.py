"""Centralized configuration for AI Playwright Test Generator."""

from __future__ import annotations

from enum import Enum


class AnalysisMode(Enum):
    """How to analyze user stories."""

    FAST = "fast"  # Regex-based, no LLM
    THOROUGH = "thorough"  # LLM-powered
    AUTO = "auto"  # Fast first, thorough if complex


class ReportFormat(Enum):
    """Report output format."""

    CONFLUENCE = "confluence"  # HTML for Confluence/Cloud
    JIRA_XML = "jira_xml"  # XML for Jira import
    JSON = "json"  # JSON data format
    MARKDOWN = "markdown"  # Markdown documentation
    LOCAL = "local"  # Relative paths, for local viewing
    JIRA = "jira"  # Absolute paths, for Jira uploads
    SHAREABLE = "shareable"  # Clean, for team documentation


class DetectionMode(Enum):
    """How to detect input format."""

    AUTO = "auto"  # Regex-first, LLM fallback
    EXPLICIT = "explicit"  # User specifies format
    FAST = "fast"  # Pure regex, no LLM
    THOROUGH = "thorough"  # LLM-based detection


class CaptureLevel(Enum):
    """Level of screenshot capture."""

    BASIC = "basic"  # Entry and outcome only
    STANDARD = "standard"  # Entry, steps, outcome
    THOROUGH = "thorough"  # Every major action


class ScreenshotNaming(Enum):
    """Screenshot naming convention."""

    SEQUENTIAL = "sequential"  # test_entry_001.png
    DESCRIPTIVE = "descriptive"  # login_success_20260303.png
    HYBRID = "hybrid"  # login_success_001_20260303.png


class Environment(Enum):
    """Deployment environment for target URLs."""

    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"
    CUSTOM = "custom"

    @classmethod
    def get_default_url(cls, env: Environment) -> str | None:
        """Return default URL for an environment (placeholder)."""
        defaults = {
            cls.LOCAL: "http://localhost:3000",
            cls.STAGING: "https://staging.example.com",
            cls.PRODUCTION: "https://example.com",
            cls.CUSTOM: None,
        }
        return defaults.get(env)


# Jira project configuration (B-036 Phase 4): the value is now a plain
# default — consumers set it at export time (Streamlit export panel / CLI
# menu / SettingsStore "jira_project_key"). The env-var read was removed;
# the constant stays for backwards compatibility (src/cli/config.py re-exports
# it and src/cli/report_generator.py uses it as its default).
JIRA_PROJECT_KEY: str = "TEST"

# Screenshot storage configuration
STORAGE_MODE: str = "filesystem"  # filesystem, s3, base64
NAMING_CONVENTION: ScreenshotNaming = ScreenshotNaming.HYBRID
CAPTURE_LEVEL: CaptureLevel = CaptureLevel.STANDARD
SCREENSHOT_DIR: str = "screenshots"

# LLM analysis mode (for backward compat with old cli.config)
LLM_ANALYSIS_MODE: AnalysisMode = AnalysisMode.THOROUGH

# Output directories
GENERATED_TESTS_DIR: str = "generated_tests"
