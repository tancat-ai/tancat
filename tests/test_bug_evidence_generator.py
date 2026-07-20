"""Tests for BugEvidenceGenerator — offline, no browser or LLM needed."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

from src.cli.evidence_generator import BugEvidenceGenerator
from src.pytest_output_parser import RunResult, TestResult


def _make_test_result(
    name: str = "test_login",
    status: str = "failed",
    error_message: str = "TimeoutError: element not found",
    file_path: str = "generated_tests/test_login.py",
    duration: float = 2.5,
) -> TestResult:
    return TestResult(
        name=name,
        status=status,
        duration=duration,
        error_message=error_message,
        file_path=file_path,
    )


# ── add_test_failure ──────────────────────────────────────────────────────


def test_add_test_failure_creates_evidence_dict() -> None:
    gen = BugEvidenceGenerator()
    result = _make_test_result()
    evidence = gen.add_test_failure(result)

    assert evidence["description"] == result.name
    assert evidence["error_message"] == result.error_message
    assert evidence["file_path"] == result.file_path
    assert evidence["screenshot"] is None
    assert evidence["console_logs"] == []
    assert evidence["network_errors"] == []
    assert "timestamp" in evidence
    # Classification fields
    assert "failure_category" in evidence
    assert "raw_locator" in evidence
    assert "repair_suggestion" in evidence


def test_add_test_failure_appends_to_internal_list() -> None:
    gen = BugEvidenceGenerator()
    result1 = _make_test_result(name="test_a")
    result2 = _make_test_result(name="test_b")
    gen.add_test_failure(result1)
    gen.add_test_failure(result2)

    assert len(gen.bug_evidence) == 2
    assert gen.bug_evidence[0]["description"] == "test_a"
    assert gen.bug_evidence[1]["description"] == "test_b"


def test_add_test_failure_custom_page_url() -> None:
    gen = BugEvidenceGenerator()
    result = _make_test_result()
    evidence = gen.add_test_failure(result, page_url="https://example.com/login")

    assert evidence["url"] == "https://example.com/login"


# ── process_run_result ───────────────────────────────────────────────────


def test_process_run_result_filters_only_failures() -> None:
    run = RunResult(
        results=[
            _make_test_result(name="test_pass", status="passed", error_message=""),
            _make_test_result(name="test_fail", status="failed"),
            _make_test_result(name="test_error", status="error"),
        ],
        total=3,
        passed=1,
        failed=1,
        errors=1,
    )

    gen = BugEvidenceGenerator()
    new_evidence = gen.process_run_result(run)

    assert len(new_evidence) == 2
    assert new_evidence[0]["description"] == "test_fail"
    assert new_evidence[1]["description"] == "test_error"


def test_process_run_result_empty_when_all_passed() -> None:
    run = RunResult(
        results=[
            _make_test_result(name="test_a", status="passed", error_message=""),
            _make_test_result(name="test_b", status="passed", error_message=""),
        ],
        total=2,
        passed=2,
    )

    gen = BugEvidenceGenerator()
    new_evidence = gen.process_run_result(run)

    assert len(new_evidence) == 0


def test_process_run_result_returns_new_evidence_list() -> None:
    run = RunResult(
        results=[_make_test_result(name="test_fail", status="failed")],
        total=1,
        failed=1,
    )

    gen = BugEvidenceGenerator()
    result = gen.process_run_result(run)

    assert len(result) == 1
    assert result[0]["description"] == "test_fail"
    assert len(gen.bug_evidence) == 1


# ── generate_bug_report ──────────────────────────────────────────────────


def test_generate_bug_report_creates_file(tmp_path: Path) -> None:
    output = str(tmp_path / "bug_report.txt")
    gen = BugEvidenceGenerator()
    gen.add_test_failure(_make_test_result(name="test_login", error_message="TimeoutError: element not found"))

    path = gen.generate_bug_report(output)

    assert Path(path).exists()
    content = Path(path).read_text()
    assert "BUG REPORT" in content
    assert "test_login" in content
    assert "TimeoutError: element not found" in content


def test_generate_bug_report_includes_file_path(tmp_path: Path) -> None:
    output = str(tmp_path / "bug_report_test.txt")
    try:
        gen = BugEvidenceGenerator()
        gen.add_test_failure(_make_test_result(name="test_checkout", file_path="generated_tests/test_checkout.py"))
        gen.generate_bug_report(output)

        content = Path(output).read_text()
        assert "generated_tests/test_checkout.py" in content
    finally:
        if os.path.exists(output):
            os.remove(output)


def test_generate_bug_report_truncates_long_errors(tmp_path: Path) -> None:
    output = str(tmp_path / "bug_report_truncate.txt")
    try:
        gen = BugEvidenceGenerator()
        long_error = "X" * 600
        gen.add_test_failure(_make_test_result(error_message=long_error))
        gen.generate_bug_report(output)

        content = Path(output).read_text()
        # Should be truncated to 497 + "..." = 500 chars in the report
        assert "..." in content
        assert content.count("X") < 600
    finally:
        if os.path.exists(output):
            os.remove(output)


def test_generate_bug_report_empty_evidence(tmp_path: Path) -> None:
    output = str(tmp_path / "bug_report_empty.txt")
    try:
        gen = BugEvidenceGenerator()
        gen.generate_bug_report(output)

        content = Path(output).read_text()
        assert "BUG REPORT" in content
        assert "--- Bug #" not in content
    finally:
        if os.path.exists(output):
            os.remove(output)


# ── capture_bug_evidence (with mock) ─────────────────────────────────────


def test_capture_bug_evidence_with_mock_page() -> None:
    gen = BugEvidenceGenerator()
    gen.capturer = MagicMock()

    page = MagicMock()
    page.url = "https://example.com/checkout"

    evidence = gen.capture_bug_evidence(page, "Checkout button missing")

    assert evidence["description"] == "Checkout button missing"
    assert evidence["url"] == "https://example.com/checkout"
    assert len(gen.bug_evidence) == 1


# ── Classification-aware tests ───────────────────────────────────────────


def test_locator_timeout_includes_repair_suggestion() -> None:
    gen = BugEvidenceGenerator()
    result = _make_test_result(error_message='TimeoutError: waiting for locator("#submit-btn")')
    evidence = gen.add_test_failure(result)

    assert evidence["failure_category"] == "LOCATOR_TIMEOUT"
    assert "locator repair" in evidence["repair_suggestion"].lower()


def test_strict_violation_includes_repair_suggestion() -> None:
    gen = BugEvidenceGenerator()
    result = _make_test_result(error_message="strict mode violation: resolved to 2 elements")
    evidence = gen.add_test_failure(result)

    assert evidence["failure_category"] == "STRICT_VIOLATION"
    assert "locator repair" in evidence["repair_suggestion"].lower()


def test_assertion_failure_has_review_suggestion() -> None:
    gen = BugEvidenceGenerator()
    result = _make_test_result(error_message="AssertionError: Expected 'Login' but got 'Sign In'")
    evidence = gen.add_test_failure(result)

    assert evidence["failure_category"] == "ASSERTION_FAILURE"
    assert "content" in evidence["repair_suggestion"].lower()


def test_navigation_error_has_url_suggestion() -> None:
    gen = BugEvidenceGenerator()
    result = _make_test_result(error_message="Error: net::ERR_CONNECTION_REFUSED")
    evidence = gen.add_test_failure(result)

    assert evidence["failure_category"] == "NAVIGATION_ERROR"
    assert "url" in evidence["repair_suggestion"].lower()


def test_unknown_error_classified_as_other() -> None:
    gen = BugEvidenceGenerator()
    result = _make_test_result(error_message="NameError: name 'foo' is not defined")
    evidence = gen.add_test_failure(result)

    assert evidence["failure_category"] == "OTHER"
    assert evidence["repair_suggestion"] == ""


def test_bug_report_includes_category_tags(tmp_path: Path) -> None:
    output = str(tmp_path / "report.txt")
    gen = BugEvidenceGenerator()
    gen.add_test_failure(_make_test_result(error_message='TimeoutError: waiting for locator("#old-btn")'))
    gen.add_test_failure(_make_test_result(error_message="AssertionError: assert False"))
    gen.generate_bug_report(output)

    content = Path(output).read_text()
    assert "[LOCATOR_TIMEOUT]" in content
    assert "[ASSERTION_FAILURE]" in content
    assert "Suggestion:" in content


def test_bug_report_includes_failed_locator(tmp_path: Path) -> None:
    output = str(tmp_path / "report.txt")
    gen = BugEvidenceGenerator()
    gen.add_test_failure(_make_test_result(error_message='TimeoutError: waiting for locator("#submit-btn")'))
    gen.generate_bug_report(output)

    content = Path(output).read_text()
    assert "#submit-btn" in content
