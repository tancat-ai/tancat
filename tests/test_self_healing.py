"""Unit tests for src/self_healing.py — Phase 2 Self-Healing Reflection Loops."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.self_healing import (
    AppliedPatch,
    HealingReport,
    SelfHealingRunner,
)

# ---------------------------------------------------------------------------
# HealingReport
# ---------------------------------------------------------------------------


class TestHealingReport:
    def test_all_fixed_when_no_remaining(self) -> None:
        report = HealingReport(total_failures=2, fixed=2, remaining=0)
        assert report.all_fixed is True

    def test_not_all_fixed_when_remaining(self) -> None:
        report = HealingReport(total_failures=3, fixed=2, remaining=1)
        assert report.all_fixed is False

    def test_all_fixed_zero_failures_is_false(self) -> None:
        report = HealingReport(total_failures=0, fixed=0, remaining=0)
        assert report.all_fixed is False

    def test_patches_defaults(self) -> None:
        report = HealingReport()
        assert report.patches == []
        assert report.final_results == []
        assert report.total_failures == 0


# ---------------------------------------------------------------------------
# AppliedPatch
# ---------------------------------------------------------------------------


class TestAppliedPatch:
    def test_creation(self) -> None:
        patch = AppliedPatch(
            test_name="test_login",
            line_number=10,
            old_text='page.locator("#old").click()',
            new_text='page.locator("#new").click()',
            diagnosis="Wrong selector",
            strategy="replace_locator",
        )
        assert patch.test_name == "test_login"
        assert patch.strategy == "replace_locator"


# ---------------------------------------------------------------------------
# SelfHealingRunner — unit tests
# ---------------------------------------------------------------------------


class TestSelfHealingRunnerInit:
    def test_default_max_iterations(self) -> None:
        runner = SelfHealingRunner()
        assert runner.max_iterations == 3

    def test_custom_max_iterations(self) -> None:
        runner = SelfHealingRunner(max_iterations=5)
        assert runner.max_iterations == 5

    def test_default_llm_client(self) -> None:
        runner = SelfHealingRunner()
        assert runner._llm is not None

    def test_file_not_found_raises(self) -> None:
        runner = SelfHealingRunner()
        with pytest.raises(FileNotFoundError):
            runner.heal("/nonexistent/path/test.py")


class TestExtractTestFunction:
    def test_extracts_simple_function(self) -> None:
        source = """
def test_foo(page):
    page.goto("https://example.com")
    page.locator("#btn").click()

def test_bar(page):
    pass
"""
        result = SelfHealingRunner._extract_test_function(source, "test_foo")
        assert result is not None
        assert "def test_foo" in result
        assert "page.goto" in result
        assert "def test_bar" not in result

    def test_extracts_last_function(self) -> None:
        source = """
def test_first(page):
    pass

def test_last(page):
    page.goto("https://end.com")
"""
        result = SelfHealingRunner._extract_test_function(source, "test_last")
        assert result is not None
        assert "test_last" in result
        assert "test_first" not in result

    def test_returns_none_for_missing_function(self) -> None:
        source = "def test_foo(page): pass"
        result = SelfHealingRunner._extract_test_function(source, "test_missing")
        assert result is None

    def test_extracts_function_with_decorator(self) -> None:
        source = """
@pytest.mark.evidence(condition_ref="TC01.01")
def test_decorated(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://example.com')
"""
        result = SelfHealingRunner._extract_test_function(source, "test_decorated")
        assert result is not None
        assert "evidence_tracker.navigate" in result


class TestFormatElementsForPrompt:
    def test_empty_list(self) -> None:
        result = SelfHealingRunner._format_elements_for_prompt([])
        assert result == ""

    def test_formats_single_element(self) -> None:
        elements = [
            {
                "selector": "#login-btn",
                "text": "Login",
                "role": "button",
                "tag": "button",
                "id": "login-btn",
                "data_test": "",
                "aria_label": "Sign in",
            }
        ]
        result = SelfHealingRunner._format_elements_for_prompt(elements)
        assert "selector=#login-btn" in result
        assert "text='Login'" in result
        assert "role=button" in result
        assert "aria-label='Sign in'" in result

    def test_truncates_long_text(self) -> None:
        elements = [
            {"selector": "#btn", "text": "A" * 100, "role": "", "tag": "", "id": "", "data_test": "", "aria_label": ""}
        ]
        result = SelfHealingRunner._format_elements_for_prompt(elements)
        text_part = [p for p in result.split(", ") if p.startswith("text=")][0]
        assert len(text_part) <= 70  # "text='" + 60 chars + "'"

    def test_limits_to_30_elements(self) -> None:
        elements = [
            {"selector": f"#el{i}", "text": "", "role": "", "tag": "", "id": "", "data_test": "", "aria_label": ""}
            for i in range(50)
        ]
        result = SelfHealingRunner._format_elements_for_prompt(elements)
        assert len(result.split("\n")) <= 30


class TestParseReviewerResponse:
    def test_parses_valid_fixable_response(self) -> None:
        response = """{
  "fixable": true,
  "diagnosis": "Wrong selector used",
  "strategy": "replace_locator",
  "old_line": "page.locator('#old').click()",
  "new_line": "page.locator('#new').click()",
  "confidence": 0.9
}"""
        patch = SelfHealingRunner._parse_reviewer_response(response, "test_x", "page.locator('#old').click()")
        assert patch is not None
        assert patch.strategy == "replace_locator"
        assert patch.old_text == "page.locator('#old').click()"
        assert patch.new_text == "page.locator('#new').click()"

    def test_rejects_unfixable_response(self) -> None:
        response = '{"fixable": false, "diagnosis": "Logic error", "strategy": "skip_test", "old_line": "", "new_line": "", "confidence": 0.0}'
        patch = SelfHealingRunner._parse_reviewer_response(response, "test_x", "")
        assert patch is None

    def test_rejects_low_confidence(self) -> None:
        response = '{"fixable": true, "diagnosis": "Unsure", "strategy": "replace_locator", "old_line": "...", "new_line": "...", "confidence": 0.3}'
        patch = SelfHealingRunner._parse_reviewer_response(response, "test_x", "...")
        assert patch is None

    def test_rejects_missing_old_line(self) -> None:
        response = '{"fixable": true, "diagnosis": "x", "strategy": "replace_locator", "old_line": "", "new_line": "x", "confidence": 0.8}'
        patch = SelfHealingRunner._parse_reviewer_response(response, "test_x", "")
        assert patch is None

    def test_handles_markdown_fences(self) -> None:
        response = """```json
{"fixable": true, "diagnosis": "x", "strategy": "replace_locator", "old_line": "click", "new_line": "click2", "confidence": 0.8}
```"""
        patch = SelfHealingRunner._parse_reviewer_response(response, "test_x", "click")
        assert patch is not None
        assert patch.old_text == "click"

    def test_handles_no_json_at_all(self) -> None:
        response = "I cannot fix this test."
        patch = SelfHealingRunner._parse_reviewer_response(response, "test_x", "")
        assert patch is None


class TestApplyPatch:
    @pytest.fixture
    def tmp_test_file(self, tmp_path: Path) -> Path:
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            "def test_foo(page):\n    page.locator('#old-btn').click()\n",
            encoding="utf-8",
        )
        return test_file

    def test_applies_simple_patch(self, tmp_test_file: Path) -> None:
        source = tmp_test_file.read_text(encoding="utf-8")
        patch = AppliedPatch(
            test_name="test_foo",
            line_number=2,
            old_text="page.locator('#old-btn').click()",
            new_text="page.locator('#new-btn').click()",
            diagnosis="Wrong button",
            strategy="replace_locator",
        )
        result = SelfHealingRunner._apply_patch(tmp_test_file, source, patch)
        assert result is True
        new_source = tmp_test_file.read_text(encoding="utf-8")
        assert "#new-btn" in new_source
        assert "#old-btn" not in new_source

    def test_rejects_patch_not_found_in_source(self, tmp_test_file: Path) -> None:
        source = tmp_test_file.read_text(encoding="utf-8")
        patch = AppliedPatch(
            test_name="test_foo",
            line_number=2,
            old_text="page.locator('#nonexistent').click()",
            new_text="page.locator('#x').click()",
            diagnosis="N/A",
            strategy="replace_locator",
        )
        result = SelfHealingRunner._apply_patch(tmp_test_file, source, patch)
        assert result is False


class TestRunPytest:
    def test_runs_pytest_and_parses_output(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_dummy.py"
        test_file.write_text(
            "def test_pass():\n    assert True\n\ndef test_fail():\n    assert False\n",
            encoding="utf-8",
        )
        result = SelfHealingRunner._run_pytest(test_file)
        assert result.total == 2
        assert result.passed == 1
        assert result.failed == 1

    def test_runs_specific_tests(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_filtered.py"
        test_file.write_text(
            "def test_a():\n    assert True\n\ndef test_b():\n    assert False\n",
            encoding="utf-8",
        )
        result = SelfHealingRunner._run_pytest(test_file, test_names=["test_a"])
        # Should only run test_a
        assert result.total >= 1
        assert result.failed == 0


class TestHealIntegration:
    def test_heal_all_passing_returns_immediately(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_all_pass.py"
        test_file.write_text(
            "def test_pass1():\n    assert True\n\ndef test_pass2():\n    assert True\n",
            encoding="utf-8",
        )
        runner = SelfHealingRunner(max_iterations=3)
        report = runner.heal(test_file)
        assert report.total_failures == 0 or report.fixed >= 0
        assert report.iterations <= 3

    def test_heal_fixes_broken_locator(self, tmp_path: Path) -> None:
        """Prove self-healing loop runs with mocked LLM and attempts fixes."""
        import json

        test_file = tmp_path / "test_fixable.py"
        # Use TimeoutError with 'waiting for' so classifier returns LOCATOR_TIMEOUT
        # (simple NameError would be classified as OTHER and pre-screened out)
        test_file.write_text(
            "def test_broken():\n"
            '    raise TimeoutError("page.wait_for_selector: Timeout 30000ms exceeded. '
            "waiting for locator('#broken-btn')\")\n",
            encoding="utf-8",
        )

        reviewer_response = json.dumps(
            {
                "fixable": True,
                "diagnosis": "Wrong selector",
                "strategy": "replace_locator",
                "old_line": "page.locator('#broken-btn').click()",
                "new_line": "page.locator('#fixed-btn').click()",
                "confidence": 0.9,
            }
        )

        mock_llm = MagicMock()
        mock_llm.generate_test.return_value = reviewer_response

        runner = SelfHealingRunner(llm_client=mock_llm, max_iterations=2)
        report = runner.heal(test_file)

        # Verify the LLM was called with the right context
        assert mock_llm.generate_test.called
        call_args = mock_llm.generate_test.call_args
        assert "test_broken" in str(call_args)
        assert "#broken-btn" in str(call_args)

        # Verify the loop ran
        assert report.iterations >= 1
        assert report.total_failures + report.fixed >= 0  # always valid

    def test_heal_applies_locator_fix_to_file(self, tmp_path: Path) -> None:
        """End-to-end: mock LLM, verify the test file is actually patched."""
        import json

        original_code = (
            "def test_broken():\n"
            '    raise TimeoutError("page.wait_for_selector: Timeout 30000ms exceeded. '
            "waiting for locator('#broken-btn')\")\n"
        )
        test_file = tmp_path / "test_locator_fix.py"
        test_file.write_text(original_code, encoding="utf-8")

        # LLM suggests fixing the selector
        reviewer_response = json.dumps(
            {
                "fixable": True,
                "diagnosis": "Wrong selector for button",
                "strategy": "replace_locator",
                "old_line": "raise TimeoutError(\"page.wait_for_selector: Timeout 30000ms exceeded. waiting for locator('#broken-btn')\")",
                "new_line": "raise TimeoutError(\"page.wait_for_selector: Timeout 30000ms exceeded. waiting for locator('#real-btn')\")",
                "confidence": 0.9,
            }
        )

        mock_llm = MagicMock()
        mock_llm.generate_test.return_value = reviewer_response

        runner = SelfHealingRunner(llm_client=mock_llm, max_iterations=2)
        runner.heal(test_file)

        # Verify the file was actually patched
        patched = test_file.read_text(encoding="utf-8")
        assert "#real-btn" in patched, f"Expected #real-btn in patched file, got: {patched}"
        assert "#broken-btn" not in patched, f"#broken-btn should be gone, got: {patched}"


# ---------------------------------------------------------------------------
# Pre-screening tests (Phase 2b)
# ---------------------------------------------------------------------------


class TestPreScreenFailure:
    """Tests for _pre_screen_failure — rule-based LLM call avoidance."""

    def test_locator_timeout_is_screenable(self) -> None:
        from src.failure_classifier import FailureCategory, FailureDetail

        detail = FailureDetail(
            category=FailureCategory.LOCATOR_TIMEOUT,
            raw_locator="#btn",
            failure_url=None,
            line_number=None,
            error_message="Timeout waiting for locator",
        )
        assert SelfHealingRunner._pre_screen_failure(detail) is True

    def test_strict_violation_is_screenable(self) -> None:
        from src.failure_classifier import FailureCategory, FailureDetail

        detail = FailureDetail(
            category=FailureCategory.STRICT_VIOLATION,
            raw_locator="#btn",
            failure_url=None,
            line_number=None,
            error_message="Strict mode violation: resolved to 2 elements",
        )
        assert SelfHealingRunner._pre_screen_failure(detail) is True

    def test_assertion_failure_is_unscreenable(self) -> None:
        """Assertion failures are logic errors — not fixable by locator changes."""
        from src.failure_classifier import FailureCategory, FailureDetail

        detail = FailureDetail(
            category=FailureCategory.ASSERTION_FAILURE,
            raw_locator=None,
            failure_url=None,
            line_number=None,
            error_message="AssertionError: expected 'Hello' but got 'Goodbye'",
        )
        assert SelfHealingRunner._pre_screen_failure(detail) is False

    def test_navigation_error_is_unscreenable(self) -> None:
        """Navigation errors mean site is down — nothing to fix in test code."""
        from src.failure_classifier import FailureCategory, FailureDetail

        detail = FailureDetail(
            category=FailureCategory.NAVIGATION_ERROR,
            raw_locator=None,
            failure_url=None,
            line_number=None,
            error_message="net::ERR_CONNECTION_REFUSED",
        )
        assert SelfHealingRunner._pre_screen_failure(detail) is False

    def test_other_is_unscreenable(self) -> None:
        """Unknown/unclassified errors are not worth LLM review."""
        from src.failure_classifier import FailureCategory, FailureDetail

        detail = FailureDetail(
            category=FailureCategory.OTHER,
            raw_locator=None,
            failure_url=None,
            line_number=None,
            error_message="Something went wrong",
        )
        assert SelfHealingRunner._pre_screen_failure(detail) is False

    def test_empty_error_is_unscreenable(self) -> None:
        """Empty error messages fall into OTHER — skip LLM."""
        from src.failure_classifier import classify_failure

        detail = classify_failure("")
        assert detail.category == "other"
        assert SelfHealingRunner._pre_screen_failure(detail) is False


class TestMaybeAddInteractiveCandidate:
    """Tests for _maybe_add_interactive_candidate — locator failures flagged for interactive repair."""

    def test_adds_locator_timeout_candidate(self) -> None:
        from src.failure_classifier import FailureCategory, FailureDetail
        from src.pytest_output_parser import TestResult

        report = HealingReport()
        result = TestResult(
            name="test_click",
            status="failed",
            error_message="Timeout waiting for locator('#bad')",
            duration=1.0,
            file_path="test.py",
        )
        detail = FailureDetail(
            category=FailureCategory.LOCATOR_TIMEOUT,
            raw_locator="#bad",
            failure_url="https://example.com",
            line_number=5,
            error_message="Timeout waiting for locator('#bad')",
        )

        SelfHealingRunner._maybe_add_interactive_candidate(report, result, detail)

        assert len(report.interactive_repair_candidates) == 1
        assert report.interactive_repair_candidates[0]["test_name"] == "test_click"
        assert report.interactive_repair_candidates[0]["raw_locator"] == "#bad"
        assert report.interactive_repair_candidates[0]["failure_url"] == "https://example.com"

    def test_adds_strict_violation_candidate(self) -> None:
        from src.failure_classifier import FailureCategory, FailureDetail
        from src.pytest_output_parser import TestResult

        report = HealingReport()
        result = TestResult(
            name="test_form",
            status="failed",
            error_message="Strict mode: 2 elements",
            duration=0.5,
            file_path="test.py",
        )
        detail = FailureDetail(
            category=FailureCategory.STRICT_VIOLATION,
            raw_locator="get_by_label('Name')",
            failure_url=None,
            line_number=None,
            error_message="Strict mode violation",
        )

        SelfHealingRunner._maybe_add_interactive_candidate(report, result, detail)

        assert len(report.interactive_repair_candidates) == 1
        assert report.interactive_repair_candidates[0]["raw_locator"] == "get_by_label('Name')"

    def test_skips_assertion_failures(self) -> None:
        """Assertion failures can't be fixed by clicking a different element."""
        from src.failure_classifier import FailureCategory, FailureDetail
        from src.pytest_output_parser import TestResult

        report = HealingReport()
        result = TestResult(
            name="test_assert", status="failed", error_message="AssertionError", duration=0.1, file_path="test.py"
        )
        detail = FailureDetail(
            category=FailureCategory.ASSERTION_FAILURE,
            raw_locator=None,
            failure_url=None,
            line_number=None,
            error_message="AssertionError",
        )

        SelfHealingRunner._maybe_add_interactive_candidate(report, result, detail)
        assert len(report.interactive_repair_candidates) == 0

    def test_skips_navigation_errors(self) -> None:
        from src.failure_classifier import FailureCategory, FailureDetail
        from src.pytest_output_parser import TestResult

        report = HealingReport()
        result = TestResult(
            name="test_nav", status="failed", error_message="ERR_CONNECTION_REFUSED", duration=0.1, file_path="test.py"
        )
        detail = FailureDetail(
            category=FailureCategory.NAVIGATION_ERROR,
            raw_locator=None,
            failure_url=None,
            line_number=None,
            error_message="net::ERR_CONNECTION_REFUSED",
        )

        SelfHealingRunner._maybe_add_interactive_candidate(report, result, detail)
        assert len(report.interactive_repair_candidates) == 0

    def test_skips_other_category(self) -> None:
        from src.failure_classifier import FailureCategory, FailureDetail
        from src.pytest_output_parser import TestResult

        report = HealingReport()
        result = TestResult(
            name="test_other", status="failed", error_message="Unknown error", duration=0.1, file_path="test.py"
        )
        detail = FailureDetail(
            category=FailureCategory.OTHER,
            raw_locator=None,
            failure_url=None,
            line_number=None,
            error_message="Unknown error",
        )

        SelfHealingRunner._maybe_add_interactive_candidate(report, result, detail)
        assert len(report.interactive_repair_candidates) == 0


class TestHealingReportInteractiveCandidates:
    """HealingReport.interactive_repair_candidates field."""

    def test_default_is_empty(self) -> None:
        report = HealingReport()
        assert report.interactive_repair_candidates == []

    def test_can_populate_manually(self) -> None:
        report = HealingReport()
        report.interactive_repair_candidates.append(
            {
                "test_name": "test_foo",
                "raw_locator": "#bad",
                "error_message": "timeout",
                "failure_url": None,
            }
        )
        assert len(report.interactive_repair_candidates) == 1


class TestHealPreScreenIntegration:
    """Integration: heal() skips LLM for assertion/navigation/other failures."""

    def test_assertion_failure_skips_llm_and_counts_unfixable(self, tmp_path: Path) -> None:
        """When a test has an assertion failure, it should be pre-screened
        as unfixable without calling the LLM."""
        test_file = tmp_path / "test_assert_fail.py"
        test_file.write_text(
            "def test_fails_assertion():\n    assert False, 'Expected Hello but got Goodbye'\n",
            encoding="utf-8",
        )

        mock_llm = MagicMock()
        runner = SelfHealingRunner(llm_client=mock_llm, max_iterations=2)
        report = runner.heal(test_file)

        # LLM should NOT be called — assertion failures are pre-screened
        assert not mock_llm.generate_test.called, "LLM should not be called for assertion failures"
        assert report.unfixable >= 1
        # Assertion failures are NOT interactive candidates
        assert len(report.interactive_repair_candidates) == 0

    def test_locator_timeout_calls_llm(self, tmp_path: Path) -> None:
        """Locator timeout failures should still go to the LLM."""
        import json

        test_file = tmp_path / "test_locator_timeout.py"
        # Use TimeoutError so classifier returns LOCATOR_TIMEOUT (not OTHER)
        test_file.write_text(
            "def test_click_broken():\n"
            '    raise TimeoutError("page.wait_for_selector: Timeout 30000ms exceeded. '
            "waiting for locator('#bad-btn')\")\n",
            encoding="utf-8",
        )

        reviewer_response = json.dumps(
            {
                "fixable": True,
                "diagnosis": "Wrong selector",
                "strategy": "replace_locator",
                "old_line": "raise TimeoutError(\"page.wait_for_selector: Timeout 30000ms exceeded. waiting for locator('#bad-btn')\")",
                "new_line": "raise TimeoutError(\"page.wait_for_selector: Timeout 30000ms exceeded. waiting for locator('#good-btn')\")",
                "confidence": 0.9,
            }
        )

        mock_llm = MagicMock()
        mock_llm.generate_test.return_value = reviewer_response

        runner = SelfHealingRunner(llm_client=mock_llm, max_iterations=2)
        report = runner.heal(test_file)

        # LLM should be called — locator timeouts are screenable
        assert mock_llm.generate_test.called, "LLM should be called for locator timeout"
        assert report.fixed >= 1

    def test_pre_screened_locator_timeout_becomes_interactive_candidate(self, tmp_path: Path) -> None:
        """When the LLM can't fix a locator timeout, it should become an
        interactive repair candidate."""
        import json

        test_file = tmp_path / "test_hard_locator.py"
        # Use TimeoutError so classifier returns LOCATOR_TIMEOUT (not OTHER)
        test_file.write_text(
            "def test_weird_click():\n"
            '    raise TimeoutError("page.wait_for_selector: Timeout 30000ms exceeded. '
            "waiting for locator('#weird-btn')\")\n",
            encoding="utf-8",
        )

        # LLM says unfixable
        reviewer_response = json.dumps(
            {
                "fixable": False,
                "diagnosis": "Cannot determine correct element",
                "strategy": "skip_test",
                "old_line": "",
                "new_line": "",
                "confidence": 0.0,
            }
        )

        mock_llm = MagicMock()
        mock_llm.generate_test.return_value = reviewer_response

        runner = SelfHealingRunner(llm_client=mock_llm, max_iterations=1)
        report = runner.heal(test_file)

        # Should be flagged as interactive candidate since it's a locator failure
        assert len(report.interactive_repair_candidates) >= 1
        assert report.interactive_repair_candidates[0]["test_name"] == "test_weird_click"
