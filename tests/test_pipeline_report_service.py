"""Tests for pipeline report artifact generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.pipeline_report_service import PipelineReportBundle, PipelineReportService
from src.pytest_output_parser import RunResult, TestResult
from tests.test_usage_meter import _meter, _paid_license


def test_build_reports_returns_strings_and_saved_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Jira is the gated format: licence the deployment so the report is produced
    # regardless of this machine's free-tier export ledger (the gate is real).
    _paid_license(monkeypatch, tier="self-serve")
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


def _build(tmp_path: Path, **kwargs: object) -> PipelineReportBundle:
    """Build reports for one passing test into tmp_path/pkg."""
    run_result = RunResult(
        results=[
            TestResult(
                name="test_01_checkout",
                status="passed",
                duration=1.0,
                error_message="",
                file_path="generated_tests/test_checkout.py",
            )
        ],
        total=1,
        passed=1,
        failed=0,
        duration=1.0,
    )
    return PipelineReportService().build_reports(
        criteria_text="1. checkout works",
        generated_code="def test_01_checkout(page):\n    pass",
        run_result=run_result,
        package_dir=str(tmp_path / "pkg"),
        **kwargs,  # type: ignore[arg-type]
    )


def test_free_deployment_is_refused_the_jira_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The Jira export is Pro-only: a free deployment is refused at once.

    No free allowance - the free reports must still be produced, and only
    report_jira.md is withheld.
    """
    monkeypatch.delenv("AITEST_LICENSE_KEY", raising=False)
    monkeypatch.delenv("AITEST_LICENSE_FILE", raising=False)
    meter = _meter(tmp_path)
    monkeypatch.setattr("src.usage_meter.UsageMeter", lambda: meter)

    bundle = _build(tmp_path)

    assert bundle.jira_blocked
    assert bundle.jira_report == ""
    assert not (tmp_path / "pkg" / "report_jira.md").exists()
    # The free formats are unaffected.
    assert (tmp_path / "pkg" / "report_local.md").exists()
    assert (tmp_path / "pkg" / "report.html").exists()


def test_licensed_deployment_can_write_the_jira_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A licence that grants jira_export is never capped for the Jira report."""
    _paid_license(monkeypatch, tier="self-serve")
    meter = _meter(tmp_path)
    monkeypatch.setattr("src.usage_meter.UsageMeter", lambda: meter)

    bundle = _build(tmp_path)

    assert bundle.jira_blocked == ""
    assert (tmp_path / "pkg" / "report_jira.md").exists()
