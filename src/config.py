"""Centralized configuration for AI Playwright Test Generator."""

from __future__ import annotations

import os
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


# Jira project configuration - can be overridden via environment variable
JIRA_PROJECT_KEY: str = os.getenv("JIRA_PROJECT_KEY", "TEST")

# Screenshot storage configuration
STORAGE_MODE: str = "filesystem"  # filesystem, s3, base64
NAMING_CONVENTION: ScreenshotNaming = ScreenshotNaming.HYBRID
CAPTURE_LEVEL: CaptureLevel = CaptureLevel.STANDARD
SCREENSHOT_DIR: str = "screenshots"

# LLM analysis mode (for backward compat with old cli.config)
LLM_ANALYSIS_MODE: AnalysisMode = AnalysisMode.THOROUGH

# Output directories
GENERATED_TESTS_DIR: str = "generated_tests"
