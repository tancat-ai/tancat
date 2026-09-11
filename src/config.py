"""Centralized configuration for AI Playwright Test Generator."""

from __future__ import annotations

import os
from enum import Enum
from typing import Literal


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

    SEQUENTIAL = "sequential"  # test_entry_001.webp
    DESCRIPTIVE = "descriptive"  # login_success_20260303.webp
    HYBRID = "hybrid"  # login_success_001_20260303.webp


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

# Evidence screenshot image format.
#
# Default WebP, encoded *losslessly* by Pillow (see src/evidence_image.py), so
# evidence stays pixel-identical — it is an audit artifact, never trade fidelity
# for size — while halving the footprint. Verified live, same suite + same site
# (17 screenshots): PNG 2501 KB -> WebP 1279 KB (51%, i.e. 49% smaller).
#
# Do NOT capture with Playwright's ``type="webp"``: Chromium's WebP lossless
# encoder emitted files 4.2x LARGER than its own PNG on the real saucedemo login
# page (111.8 KB vs 26.5 KB); the Pillow encode of the same pixels is 10.3 KB.
#
# Set AITEST_EVIDENCE_IMAGE_FORMAT=png to force PNG — escape hatch for a
# downstream consumer that cannot read WebP.
EVIDENCE_IMAGE_FORMAT_DEFAULT: Literal["webp", "png"] = "webp"
_SUPPORTED_EVIDENCE_FORMATS: frozenset[str] = frozenset({"webp", "png"})


def evidence_image_format() -> Literal["webp", "png"]:
    """Return the evidence screenshot format: ``"webp"`` or ``"png"``.

    Honours ``AITEST_EVIDENCE_IMAGE_FORMAT``. An unsupported value falls back
    to the default rather than breaking evidence capture.
    """
    requested = os.environ.get("AITEST_EVIDENCE_IMAGE_FORMAT", "").strip().lower()
    if requested in _SUPPORTED_EVIDENCE_FORMATS and requested != EVIDENCE_IMAGE_FORMAT_DEFAULT:
        return "png"
    return EVIDENCE_IMAGE_FORMAT_DEFAULT


def evidence_image_extension() -> str:
    """Return the evidence screenshot file extension, e.g. ``".webp"``."""
    return "." + evidence_image_format()


# LLM analysis mode (for backward compat with old cli.config)
LLM_ANALYSIS_MODE: AnalysisMode = AnalysisMode.THOROUGH

# Output directories
GENERATED_TESTS_DIR: str = "generated_tests"
