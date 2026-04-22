"""Backwards-compatible re-exports for CLI.

All enums and defaults are defined in ``src/config.py``.
This module re-exports them so existing CLI code continues to work.
"""

from __future__ import annotations

from src.config import (
    JIRA_PROJECT_KEY,
    AnalysisMode,
    CaptureLevel,
    DetectionMode,
    ReportFormat,
    ScreenshotNaming,
)

__all__ = [
    "AnalysisMode",
    "CaptureLevel",
    "DetectionMode",
    "JIRA_PROJECT_KEY",
    "ReportFormat",
    "ScreenshotNaming",
]
