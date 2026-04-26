"""Backwards-compatible re-exports. Import from specific modules in new code."""

from __future__ import annotations

from src.evidence_report import (
    generate_annotated_journey,
    generate_annotated_screenshot,
)
from src.heatmap_utils import generate_suite_heatmap
from src.report_builder import build_report_dicts, escape_html
from src.report_formatters import (
    generate_html_report,
    generate_jira_report,
    generate_local_report,
)

__all__ = [
    "build_report_dicts",
    "escape_html",
    "generate_annotated_journey",
    "generate_annotated_screenshot",
    "generate_html_report",
    "generate_jira_report",
    "generate_local_report",
    "generate_suite_heatmap",
]
