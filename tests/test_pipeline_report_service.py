"""Tests for pipeline report artifact generation."""

from __future__ import annotations

from pathlib import Path

from src.pipeline_report_service import PipelineReportService
from src.pytest_output_parser import RunResult, TestResult


def test_build_reports_returns_strings_and_saved_files(tmp_path: Path) -> None:
    service = PipelineReportService()
    run_result = RunResult(
        results=[
            TestResult(
                name="test_01_checkout",
                status="passed",
                duration=1.5,
                error_message="",
                file_path="generated_tests/test_checkout.py",
            )
        ],
        total=1,
        passed=1,
        failed=0,
        duration=1.5,
    )

    bundle = service.build_reports(
        criteria_text="1. checkout works",
        generated_code="def test_01_checkout(page):\n    pass",
        run_result=run_result,
        package_dir=str(tmp_path),
        jira_project_key="payments",
    )

    assert bundle.coverage_rows[0]["status"] == "passed"
    assert "# Test Coverage Report" in bundle.local_report
    assert "Project: PAYMENTS" in bundle.jira_report
    assert "<!DOCTYPE html>" in bundle.html_report
    assert Path(bundle.local_report_path).exists()
    assert Path(bundle.jira_report_path).exists()
    assert Path(bundle.html_report_path).exists()
