"""Tests for CLI report generation format handling."""

from __future__ import annotations

import shutil
from pathlib import Path

from cli.report_generator import JiraReportGenerator
from src.analyzer import AnalyzedTestCase
from src.config import ReportFormat


def test_save_test_cases_supports_all_report_formats() -> None:
    output_dir = Path("generated_tests/test_report_generator_tmp")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    generator = JiraReportGenerator(output_dir=str(output_dir))
    generator.create_test_case(
        AnalyzedTestCase(
            title="Checkout flow",
            description="Generate a checkout test.",
            estimated_complexity="low",
            identified_actions=["navigate", "checkout"],
            expected_outcome="Checkout page is shown.",
        )
    )

    try:
        saved_paths = [generator.save_test_cases(report_format) for report_format in ReportFormat]

        assert len(saved_paths) == len(list(ReportFormat))
        assert all(Path(path).exists() for path in saved_paths)
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)
