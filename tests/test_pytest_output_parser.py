"""
Tests for pytest_output_parser module.

Uses real pytest output strings as fixtures to verify parsing accuracy.
"""

import pytest

from src.pytest_output_parser import (
    RunResult,
    TestResult,
    format_pytest_output_for_display,
    parse_pytest_output,
)


@pytest.fixture
def all_passed_output() -> str:
    """Real pytest output: 3 tests all passed."""
    return """============================= test session starts =============================
collected 3 items

generated_tests/test_generated_playwright.py::test_01_login_page_displayed PASSED [ 33%]
generated_tests/test_generated_playwright.py::test_02_inventory_displayed PASSED [ 66%]
generated_tests/test_generated_playwright.py::test_03_add_to_cart PASSED [100%]

============================== 3 passed in 4.52s ============================="""


@pytest.fixture
def mixed_pass_fail_output() -> str:
    """Real pytest output: mix of passed and failed tests."""
    return """============================= test session starts =============================
collected 3 items

generated_tests/test_generated_playwright.py::test_01_login_page_displayed PASSED [ 33%]
generated_tests/test_generated_playwright.py::test_02_inventory_displayed PASSED [ 66%]
generated_tests/test_generated_playwright.py::test_03_add_to_cart FAILED [100%]

=================================== FAILURES ===================================
___________________________ test_03_add_to_cart ____________________________
generated_tests/test_generated_playwright.py:47: in test_03_add_to_cart
    await page.locator("text=Add to cart").first.wait_for(timeout=5000)
AssertionError: Timeout 5000ms exceeded.

=========================== 1 failed, 2 passed in 6.12s ==========================="""


@pytest.fixture
def simple_duration_output() -> str:
    """Pytest output with 'X passed in Ys' format (no failed count)."""
    return """============================= test session starts =============================
collected 5 items

tests/test_example.py::test_one PASSED [ 20%]
tests/test_example.py::test_two PASSED [ 40%]
tests/test_example.py::test_three PASSED [ 60%]
tests/test_example.py::test_four PASSED [ 80%]
tests/test_example.py::test_five PASSED [100%]

============================== 5 passed in 2.34s ============================="""


@pytest.fixture
def empty_output() -> str:
    """Minimal pytest output with no tests collected."""
    return """============================= test session starts =============================
collected 0 items

============================ no tests ran in 0.01s ============================="""


@pytest.fixture
def collection_error_output() -> str:
    """Pytest output with collection errors (no tests run)."""
    return """============================= test session starts =============================
collected 0 items / 1 error

==================================== ERRORS ====================================
_______________ ERROR collecting generated_tests/test_nonexistent.py ________________
ImportError while importing test module 'generated_tests/test_nonexistent.py'.
Hint: make sure your test packages/packages have valid Python names.
Traceback:
generated_tests/test_nonexistent.py:3: in <module>
    import nonexistent_module
=========================== short test summary info ===========================
ERROR generated_tests/test_nonexistent.py
============================== 1 error in 0.12s ============================="""


@pytest.fixture
def failed_with_inline_error() -> str:
    """Failed test with inline assertion error."""
    return """============================= test session starts =============================
collected 2 items

generated_tests/test_generated_playwright.py::test_01_login PASSED [ 50%]
generated_tests/test_generated_playwright.py::test_02_password_field FAILED [100%]

=================================== FAILURES ===================================
__________________________ test_02_password_field ___________________________
generated_tests/test_generated_playwright.py:18: in test_02_password_field
    assert page.locator("text=Submit").is_visible() == True
AssertionError: assert False == True
=========================== 1 failed, 1 passed in 1.85s ==========================="""


class TestParsePytestOutput:
    """Test suite for parse_pytest_output function."""

    def test_parses_all_passed(self, all_passed_output: str) -> None:
        """Test parsing when all tests pass."""
        result = parse_pytest_output(all_passed_output)

        assert isinstance(result, RunResult)
        assert result.total == 3
        assert result.passed == 3
        assert result.failed == 0
        assert result.errors == 0
        assert result.duration > 0

    def test_parses_mixed_pass_fail(self, mixed_pass_fail_output: str) -> None:
        """Test parsing when some tests pass and some fail."""
        result = parse_pytest_output(mixed_pass_fail_output)

        assert isinstance(result, RunResult)
        assert result.total == 3
        assert result.passed == 2
        assert result.failed == 1
        assert result.errors == 0
        assert result.duration > 0

    def test_extracts_test_names(self, all_passed_output: str) -> None:
        """Test that test names are correctly extracted."""
        result = parse_pytest_output(all_passed_output)

        test_names = [r.name for r in result.results]
        assert "test_01_login_page_displayed" in test_names
        assert "test_02_inventory_displayed" in test_names
        assert "test_03_add_to_cart" in test_names

    def test_extracts_duration(self, all_passed_output: str) -> None:
        """Test that run duration is correctly extracted."""
        result = parse_pytest_output(all_passed_output)

        # Duration should be a float > 0 and reasonable (between 1-10 seconds)
        assert isinstance(result.duration, float)
        assert result.duration > 0
        assert result.duration < 10.0

    def test_failed_count_correct(self, mixed_pass_fail_output: str) -> None:
        """Test that failed count is correct."""
        result = parse_pytest_output(mixed_pass_fail_output)

        assert result.failed == 1

    def test_passed_count_correct(self, all_passed_output: str) -> None:
        """Test that passed count matches total when all pass."""
        result = parse_pytest_output(all_passed_output)

        assert result.passed == result.total

    def test_error_message_extracted(self, failed_with_inline_error: str) -> None:
        """Test that error messages are extracted from failed tests."""
        result = parse_pytest_output(failed_with_inline_error)

        # Find the failed test
        failed_tests = [r for r in result.results if r.status == "failed"]
        assert len(failed_tests) == 1

        error = failed_tests[0].error_message
        # Error message should contain just the assertion content, not "AssertionError:" prefix
        assert "assert False == True" in error

    def test_handles_empty_output(self, empty_output: str) -> None:
        """Test handling of minimal pytest output with no tests."""
        result = parse_pytest_output(empty_output)

        assert isinstance(result, RunResult)
        assert result.total == 0
        assert result.passed == 0
        assert result.failed == 0

    def test_handles_collection_error(self, collection_error_output: str) -> None:
        """Test handling of pytest output with collection errors."""
        result = parse_pytest_output(collection_error_output)

        assert isinstance(result, RunResult)
        assert result.total == 0
        assert result.errors == 1
        assert result.duration == pytest.approx(0.12, abs=0.01)

    def test_preserves_raw_output(self, all_passed_output: str) -> None:
        """Test that raw output is preserved in result."""
        result = parse_pytest_output(all_passed_output)

        assert result.raw_output == all_passed_output


class TestTestDataclass:
    """Tests for TestResult dataclass structure."""

    def test_testresult_structure(self) -> None:
        """Test TestResult has all required fields."""
        test_result = TestResult(
            name="test_example", status="passed", duration=1.5, error_message="", file_path="tests/test_example.py"
        )

        assert test_result.name == "test_example"
        assert test_result.status in ("passed", "failed", "error")
        assert isinstance(test_result.duration, float)
        assert test_result.error_message == ""
        assert test_result.file_path.endswith(".py")


class TestStatusCounts:
    """Tests for passed/failed/error counts logic."""

    def test_only_passed_in_results(self) -> None:
        """Test count when all results are passed."""
        run_result = RunResult(
            results=[
                TestResult(name="test_1", status="passed", duration=0.5, error_message="", file_path="t.py"),
                TestResult(name="test_2", status="passed", duration=0.3, error_message="", file_path="t.py"),
            ],
            total=2,
            passed=2,
            failed=0,
            errors=0,
            duration=0.8,
            raw_output="test output",
        )

        assert run_result.passed == 2
        assert run_result.failed == 0

    def test_status_from_results_when_no_counts(self) -> None:
        """Test that status counts are derived from results when not explicitly set."""
        result = parse_pytest_output("""============================= test session starts =============================
collected 2 items

t.py::test_a PASSED [ 50%]
t.py::test_b FAILED [100%]

=========================== 1 passed, 1 failed in 1.0s ===========================""")

        assert result.passed == 1
        assert result.failed == 1


class TestB006BannerRegression:
    """B-006: Parser must report correct totals from the FINAL summary line.

    The bug was that an intermediate '1 passed' match would overwrite the
    real totals from the final summary line.
    """

    def test_b006_mixed_pass_fail_banner_correct(self) -> None:
        """Ensure parser uses final summary when intermediate lines could match."""
        raw = """============================= test session starts =============================
collected 4 items

generated_tests/test_flow.py::test_01_login PASSED [ 25%]
generated_tests/test_flow.py::test_02_dashboard FAILED [ 50%]
generated_tests/test_flow.py::test_03_settings FAILED [ 75%]
generated_tests/test_flow.py::test_04_logout FAILED [100%]

=================================== FAILURES ===================================
____________________________ test_02_dashboard _____________________________
generated_tests/test_flow.py:12: in test_02_dashboard
    assert page.locator("#dash").is_visible()
AssertionError: assert False == True
____________________________ test_03_settings ______________________________
generated_tests/test_flow.py:20: in test_03_settings
    assert page.locator("#settings-panel").is_visible()
AssertionError: assert False == True
____________________________ test_04_logout ________________________________
generated_tests/test_flow.py:28: in test_04_logout
    assert page.locator("#logout-btn").is_visible()
AssertionError: assert False == True
=========================== short test summary info ===========================
FAILED generated_tests/test_flow.py::test_02_dashboard - AssertionError: assert False == True
FAILED generated_tests/test_flow.py::test_03_settings - AssertionError: assert False == True
FAILED generated_tests/test_flow.py::test_04_logout - AssertionError: assert False == True
========================= 1 passed, 3 failed in 5.23s ========================="""

        result = parse_pytest_output(raw)

        # B-006: these must match the FINAL summary line, not an intermediate match
        assert result.passed == 1, f"Expected 1 passed, got {result.passed}"
        assert result.failed == 3, f"Expected 3 failed, got {result.failed}"
        assert result.total == 4
        assert result.duration == pytest.approx(5.23, abs=0.01)

    def test_b006_all_fail_banner(self) -> None:
        """Ensure parser works when ALL tests fail (no 'passed' in summary)."""
        raw = """============================= test session starts =============================
collected 2 items

t.py::test_a FAILED [ 50%]
t.py::test_b FAILED [100%]

=========================== 2 failed in 2.10s ==========================="""

        result = parse_pytest_output(raw)

        assert result.passed == 0
        assert result.failed == 2
        assert result.duration == pytest.approx(2.10, abs=0.01)


class TestFormatPytestOutputForDisplay:
    """Tests for filtered pytest output formatter."""

    def test_filters_low_signal_lines(self) -> None:
        """Formatter should remove environment and coverage boilerplate."""
        raw = """platform win32 -- Python 3.13.0, pytest-8.0.0
plugins: cov-4.1.0
generated_tests/test_sample.py::test_01_login PASSED [100%]
---------- coverage: platform win32, python 3.13.0-final-0 -----------
Name    Stmts   Miss
================================= 1 passed in 1.20s ================================="""
        filtered = format_pytest_output_for_display(raw)
        assert "platform win32" not in filtered
        assert "coverage:" not in filtered
        assert "test_01_login PASSED" in filtered
        assert "1 passed in 1.20s" in filtered

    def test_fallback_keeps_recent_lines_when_no_matches(self) -> None:
        """Formatter should still return readable output when patterns do not match."""
        raw = "line1\nline2\nline3\n"
        filtered = format_pytest_output_for_display(raw, max_lines=2)
        assert filtered == "line2\nline3"

    def test_keeps_collection_error_lines(self) -> None:
        """Formatter should preserve collection/import error details."""
        raw = """==================================== ERRORS ====================================
_______________ ERROR collecting generated_tests/test_bad.py ________________
generated_tests/test_bad.py:10: in <module>
    class CheckoutPage:
generated_tests/test_bad.py:11: in CheckoutPage
    def __init__(self, page: Payable):
NameError: name 'Payable' is not defined
=========================== short test summary info ===========================
ERROR generated_tests/test_bad.py
============================== 1 error in 0.13s ============================="""
        filtered = format_pytest_output_for_display(raw)

        assert "ERROR collecting generated_tests/test_bad.py" in filtered
        assert "NameError: name 'Payable' is not defined" in filtered
        assert "1 error in 0.13s" in filtered


class TestTotalConsistency:
    """Total must always equal Passed + Failed + Skipped.

    Guards the regression where run.total was set to len(run.results) (per-test
    regex count) independently of run.passed / run.failed / run.skipped (summary
    line counts), which could produce a Total that did not add up in the UI.
    """

    def test_total_equals_passed_plus_failed_plus_skipped_all_pass(self) -> None:
        raw = """============================= test session starts =============================
collected 3 items

t.py::test_a PASSED [ 33%]
t.py::test_b PASSED [ 66%]
t.py::test_c PASSED [100%]

============================== 3 passed in 1.0s =============================="""
        result = parse_pytest_output(raw)
        assert result.total == result.passed + result.failed + result.skipped
        assert result.total == 3

    def test_total_equals_passed_plus_failed_plus_skipped_mixed(self) -> None:
        raw = """============================= test session starts =============================
collected 3 items

t.py::test_a PASSED [ 33%]
t.py::test_b FAILED [ 66%]
t.py::test_c PASSED [100%]

========================= 2 passed, 1 failed in 2.0s =========================="""
        result = parse_pytest_output(raw)
        assert result.total == result.passed + result.failed + result.skipped
        assert result.total == 3
        assert result.passed == 2
        assert result.failed == 1

    def test_total_equals_passed_when_no_per_test_lines_matched(self) -> None:
        """Edge case: summary line parses fine but per-test lines were missed.

        Previously this would give Total=0 but Passed=2, which is confusing in the UI.
        With the fix, Total is always derived from the summary counts.
        """
        # Deliberately malformed PASSED lines that the regex cannot match,
        # but the summary line is clean.
        raw = """============================= test session starts =============================
collected 2 items

[CUSTOM_RUNNER] test_a ... ok
[CUSTOM_RUNNER] test_b ... ok

============================== 2 passed in 0.5s =============================="""
        result = parse_pytest_output(raw)
        assert result.passed == 2
        assert result.total == result.passed + result.failed + result.skipped
        assert result.total == 2
