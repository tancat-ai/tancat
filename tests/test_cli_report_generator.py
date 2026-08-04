"""Tests for CLI report generation format handling."""

from __future__ import annotations

import shutil
from pathlib import Path

from src.analyzer import AnalyzedTestCase
from src.cli.report_generator import JiraReportGenerator
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


def test_jira_project_key_prefixes_test_case_ids(tmp_path: Path) -> None:
    """B-036 Phase 4: export-time project key feeds test-case IDs."""
    output_dir = tmp_path / "jira_out"
    generator = JiraReportGenerator(output_dir=str(output_dir), project_key="payments")

    test_case = generator.create_test_case(
        AnalyzedTestCase(
            title="Payment flow",
            description="A payment test.",
            estimated_complexity="low",
            identified_actions=["navigate", "pay"],
            expected_outcome="Payment succeeds.",
        )
    )

    assert test_case.key == "PAYMENTS-TC-0001"


def test_jira_project_key_defaults_to_test(tmp_path: Path) -> None:
    """Without an explicit key the module default (TEST) applies."""
    output_dir = tmp_path / "jira_out_default"
    generator = JiraReportGenerator(output_dir=str(output_dir))

    test_case = generator.create_test_case(
        AnalyzedTestCase(
            title="Default flow",
            description="Default key test.",
            estimated_complexity="low",
            identified_actions=["navigate"],
            expected_outcome="Nothing breaks.",
        )
    )

    assert test_case.key == "TEST-TC-0001"
