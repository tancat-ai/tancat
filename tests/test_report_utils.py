"""Unit tests for report generation utilities."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from src.coverage_utils import RequirementCoverage
from src.pytest_output_parser import RunResult, TestResult
from src.report_utils import (
    build_report_dicts,
    generate_annotated_journey,
    generate_html_report,
    generate_jira_report,
    generate_local_report,
    generate_suite_heatmap,
)


@pytest.fixture
def sample_coverage() -> list[dict[str, Any]]:
    """Sample test coverage data for testing."""
    return [
        {
            "test_name": "test_login_success",
            "status": "passed",
            "duration": 2.5,
            "screenshots": [{"path": "screenshots/screenshot1.png", "description": "Login page"}],
            "error_message": "",
        },
        {
            "test_name": "test_login_failure",
            "status": "failed",
            "duration": 1.3,
            "screenshots": [{"path": "screenshots/screenshot2.png", "description": "Error state"}],
            "error_message": "AssertionError: Expected failure message",
        },
    ]


@pytest.fixture
def coverage_with_empty_screenshots_dir() -> list[dict[str, Any]]:
    """Coverage data for testing with empty screenshot directory."""
    return [
        {
            "test_name": "test_example",
            "status": "passed",
            "duration": 1.0,
            "screenshots": [],
            "error_message": "",
        }
    ]


def test_generate_local_report_empty_coverage() -> None:
    """Empty coverage list returns valid markdown."""
    result = generate_local_report([])

    assert "# Test Coverage Report" in result
    assert "## Summary" in result
    assert "**Total Tests:** 0" in result
    assert "Generated:" in result


def test_generate_jira_report_format() -> None:
    """Output contains Jira thumbnail syntax."""
    sample_data = [
        {
            "test_name": "test_example",
            "status": "passed",
            "duration": 1.0,
            "screenshots": [{"path": "screenshot.png", "description": "Test screenshot"}],
            "error_message": "",
        }
    ]

    result = generate_jira_report(sample_data)

    assert "!screenshot.png|thumbnail!" in result
    assert "test_example" in result
    # Status can be 'passed' (lowercase) - case insensitive check
    assert any(status in result.lower() for status in ["passed", "✅"])


def test_generate_html_report_no_screenshots() -> None:
    """Returns valid HTML without crashing."""
    result = generate_html_report([])

    assert "<!DOCTYPE html>" in result
    assert "<html lang='en'>" in result
    assert "</html>" in result
    assert "Test Coverage Report" in result
    # Check for stat-value and stat-label pattern with single quotes
    assert "class='stat-value'>0</div><div class='stat-label'>Total Tests</div>" in result


def test_generate_local_report_with_coverage(sample_coverage: list[dict[str, Any]]) -> None:
    """Local report includes all test details."""
    result = generate_local_report(sample_coverage)

    assert "test_login_success" in result
    assert "test_login_failure" in result
    assert "Passed:** 1" in result
    assert "**Failed:** 1" in result
    # Duration format is X.XXs (two decimal places)
    assert "**Duration:** 2.50s" in result
    assert "AssertionError" in result


def test_generate_jira_report_with_coverage(sample_coverage: list[dict[str, Any]]) -> None:
    """Jira report format is correct."""
    result = generate_jira_report(sample_coverage)

    assert "# Test Coverage Report" in result
    assert "test_login_success ✅" in result
    assert "test_login_failure ❌" in result
    assert "Total Tests: 2 | Passed: 1 | Failed: 1 | Pending: 0 | Unknown: 0" in result


def test_generate_html_report_with_coverage(sample_coverage: list[dict[str, Any]]) -> None:
    """HTML report renders properly."""
    result = generate_html_report(sample_coverage)

    assert "<div class='test-item'>" in result
    assert "test_login_success ✅" in result
    # HTML uses single quotes for class attributes
    assert "class='status-badge status-passed'" in result or 'class="status-badge status-passed"' in result
    # Duration format is X.XXs (two decimal places)
    assert "2.50s</span></div>" in result


def test_generate_html_report_missing_screenshot_dir() -> None:
    """HTML report handles missing screenshot directory gracefully."""
    sample_data = [
        {
            "test_name": "test_no_images",
            "status": "passed",
            "duration": 0.5,
            "screenshots": [{"path": "nonexistent.png", "description": "Missing"}],
            "error_message": "",
        }
    ]

    # Pass None explicitly
    result = generate_html_report(sample_data, screenshots_dir=None)
    assert "Test Coverage Report" in result

    # Pass non-existent directory
    with TemporaryDirectory() as tmpdir:
        fake_dir = Path(tmpdir) / "nonexistent"
        result = generate_html_report(sample_data, screenshots_dir=fake_dir)
        assert "Test Coverage Report" in result
        assert "File not found" in result or "Screenshot unavailable" in result


def test_generate_html_report_with_screenshots_in_dir() -> None:
    """HTML report embeds actual screenshots when directory provided."""
    sample_data = [
        {
            "test_name": "test_with_image",
            "status": "passed",
            "duration": 1.0,
            "screenshots": [{"path": "test_img.png", "description": "Test"}],
            "error_message": "",
        }
    ]

    with TemporaryDirectory() as tmpdir:
        screenshot_dir = Path(tmpdir) / "screenshots"
        screenshot_dir.mkdir()

        # Create a minimal PNG (1x1 pixel)
        test_img = screenshot_dir / "test_img.png"
        test_img.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x1dIEND\xaeB`\x82"
        )

        result = generate_html_report(sample_data, screenshots_dir=screenshot_dir)

        assert "Test Coverage Report" in result
        # Should have embedded image with base64 data URI
        assert "data:image/png;base64" in result


def test_coverage_with_unknown_status() -> None:
    """Handles unknown status correctly."""
    sample_data = [
        {
            "test_name": "test_peeky",
            "status": "unknown",
            "duration": 0.1,
            "screenshots": [],
            "error_message": "",
        }
    ]

    local_result = generate_local_report(sample_data)
    assert "unknown" in local_result.lower()

    jira_result = generate_jira_report(sample_data)
    assert "test_peeky" in jira_result


def test_build_report_dicts_uses_pending_before_run() -> None:
    """Requirements with generated tests should be pending before pytest run."""
    coverage = {
        "requirements": [
            RequirementCoverage(
                id="TC-001",
                description="Login works",
                status="covered",
                linked_tests=["test_01_login"],
            )
        ]
    }
    rows = build_report_dicts(coverage_analysis=coverage, run_result=None)
    assert rows[0]["status"] == "pending"


def test_build_report_dicts_uses_unknown_for_uncovered_without_run() -> None:
    """Uncovered requirements should remain unknown, not failed, pre-run."""
    coverage = {
        "requirements": [
            RequirementCoverage(
                id="TC-001",
                description="Login works",
                status="not_covered",
                linked_tests=[],
            )
        ]
    }
    rows = build_report_dicts(coverage_analysis=coverage, run_result=None)
    assert rows[0]["status"] == "unknown"


def test_reports_do_not_count_pending_as_failed() -> None:
    """Summary should only count true failed items in failed total."""
    coverage_rows = [
        {"test_name": "TC-001", "status": "passed", "duration": 1.0, "screenshots": [], "error_message": ""},
        {"test_name": "TC-002", "status": "pending", "duration": 0.0, "screenshots": [], "error_message": ""},
    ]
    local_report = generate_local_report(coverage_rows)
    assert "**Failed:** 0" in local_report
    assert "**Pending:** 1" in local_report


def test_build_report_dicts_maps_run_statuses() -> None:
    """Linked tests should inherit status from run results when available."""
    coverage = {
        "requirements": [
            RequirementCoverage(
                id="TC-001",
                description="Login works",
                status="covered",
                linked_tests=["test_01_login"],
            )
        ]
    }
    run_result = RunResult(
        results=[
            TestResult(
                name="test_01_login",
                status="failed",
                duration=1.2,
                error_message="assert false",
                file_path="generated_tests/test_demo.py",
            )
        ],
        total=1,
        passed=0,
        failed=1,
        errors=0,
        duration=1.2,
        raw_output="",
    )
    rows = build_report_dicts(coverage_analysis=coverage, run_result=run_result)
    assert rows[0]["status"] == "failed"


def test_build_report_dicts_maps_parameterized_run_statuses() -> None:
    """Linked tests should match run names with pytest parameter suffixes."""
    coverage = {
        "requirements": [
            RequirementCoverage(
                id="TC-001",
                description="Login works",
                status="covered",
                linked_tests=["test_01_login"],
            )
        ]
    }
    run_result = RunResult(
        results=[
            TestResult(
                name="test_01_login[chromium]",
                status="passed",
                duration=5.4,
                error_message="",
                file_path="generated_tests/test_demo.py",
            )
        ],
        total=1,
        passed=1,
        failed=0,
        errors=0,
        duration=5.4,
        raw_output="",
    )
    rows = build_report_dicts(coverage_analysis=coverage, run_result=run_result)
    assert rows[0]["status"] == "passed"
    assert rows[0]["duration"] == 5.4


def test_generate_annotated_journey_cleans_placeholder_labels(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    screenshot = evidence_dir / "shot.png"
    screenshot.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x1dIEND\xaeB`\x82"
    )
    sidecar = evidence_dir / "test.evidence.json"
    sidecar.write_text(
        """{
  "schema_version": "1.0",
  "test": {"name": "test_example", "condition_ref": "TC01.01", "story_ref": "S1", "status": "passed", "duration_s": 1.0},
  "page": {"url": "https://example.com/"},
  "run_history": {"total_runs": 1, "passed_runs": 1, "failed_runs": 0},
  "steps": [
    {"step": 1, "type": "navigate", "label": "Navigate to https://example.com/", "value": "https://example.com/", "screenshot": "evidence/shot.png", "element": {}, "result": {"status": "passed", "run_count": 1}},
    {"step": 2, "type": "click", "label": "{{CLICK:view cart link}}", "locator": "#cart", "screenshot": null, "element": {"viewport_pct": {"x": 40, "y": 20}}, "result": {"status": "passed", "run_count": 1}}
  ]
}""",
        encoding="utf-8",
    )

    html = generate_annotated_journey(sidecar_path=sidecar, view_mode="annotated", title="demo")
    assert "Click: view cart link" in html
    assert "{{CLICK:view cart link}}" not in html


def test_generate_suite_heatmap_counts_navigation_arrivals_as_page_evidence(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    screenshot = evidence_dir / "shot.png"
    screenshot.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x1dIEND\xaeB`\x82"
    )
    sidecar = evidence_dir / "test.evidence.json"
    sidecar.write_text(
        """{
  "schema_version": "1.0",
  "test": {"name": "test_example", "condition_ref": "TC01.02", "story_ref": "S1", "status": "passed", "duration_s": 1.0},
  "page": {"url": "https://example.com/view_cart"},
  "run_history": {"total_runs": 1, "passed_runs": 1, "failed_runs": 0},
  "steps": [
    {"step": 1, "type": "navigate", "label": "Navigate to https://example.com/", "value": "https://example.com/", "screenshot": "evidence/shot.png", "element": {}, "result": {"status": "passed", "run_count": 1}},
    {"step": 2, "type": "click", "label": "Click: view cart link", "locator": "#cart", "screenshot": null, "element": {"viewport_pct": {"x": 54, "y": 5}}, "result": {"status": "passed", "run_count": 1}},
    {"step": 3, "type": "navigate", "label": "Navigate to https://example.com/view_cart", "value": "https://example.com/view_cart", "screenshot": "evidence/shot.png", "element": {}, "result": {"status": "passed", "run_count": 1}}
  ]
}""",
        encoding="utf-8",
    )

    html = generate_suite_heatmap(evidence_dir=evidence_dir, page_url="https://example.com/view_cart")
    assert "No evidence points found" not in html
    assert "Points" in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
