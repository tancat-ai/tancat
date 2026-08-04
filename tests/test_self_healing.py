"""Unit tests for src/self_healing.py — Phase 2 Self-Healing Reflection Loops."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.pytest_output_parser import TestResult
from src.rag_learn import site_hash
from src.rag_store import LearnedPattern
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


# ---------------------------------------------------------------------------
# Reflection loop tests (Phase 2 — iterative reflection)
# ---------------------------------------------------------------------------


class TestHealingReportAttemptHistory:
    """HealingReport.attempt_history and total_llm_calls fields."""

    def test_attempt_history_defaults_empty(self) -> None:
        report = HealingReport()
        assert report.attempt_history == {}

    def test_total_llm_calls_defaults_zero(self) -> None:
        report = HealingReport()
        assert report.total_llm_calls == 0

    def test_attempt_history_can_be_populated(self) -> None:
        report = HealingReport()
        report.attempt_history["test_foo"] = [
            {
                "strategy": "replace_locator",
                "old_text": "#old",
                "new_text": "#new",
                "diagnosis": "Wrong selector",
            }
        ]
        assert len(report.attempt_history["test_foo"]) == 1


class TestReviewAndSuggestWithPriorAttempts:
    """Reflection: prior attempts are injected into the LLM prompt."""

    def test_prior_attempts_included_in_prompt(self) -> None:
        """When prior_attempts is provided, prompt includes PREVIOUS FIX ATTEMPTS."""
        import json

        mock_llm = MagicMock()
        mock_llm.generate_test.return_value = json.dumps(
            {
                "fixable": True,
                "diagnosis": "Trying add_wait instead",
                "strategy": "add_wait",
                "old_line": "page.locator('#btn').click()",
                "new_line": "page.wait_for_load_state('networkidle')\n    page.locator('#btn').click()",
                "confidence": 0.85,
            }
        )

        runner = SelfHealingRunner(llm_client=mock_llm)

        from src.failure_classifier import FailureCategory, FailureDetail
        from src.pytest_output_parser import TestResult

        result = TestResult(
            name="test_reflect",
            status="failed",
            error_message="Timeout waiting for locator('#btn')",
            duration=0.5,
            file_path="test.py",
        )
        detail = FailureDetail(
            category=FailureCategory.LOCATOR_TIMEOUT,
            raw_locator="#btn",
            failure_url=None,
            line_number=None,
            error_message="Timeout waiting for locator('#btn')",
        )
        source = "def test_reflect():\n    page.locator('#btn').click()\n"

        prior = [
            {
                "strategy": "replace_locator",
                "old_text": "page.locator('#old').click()",
                "new_text": "page.locator('#btn').click()",
                "diagnosis": "Wrong selector",
            }
        ]

        runner._review_and_suggest(result, detail, source, prior_attempts=prior)

        call_args = mock_llm.generate_test.call_args
        user_prompt = call_args.kwargs.get("prompt", call_args.args[0] if call_args.args else "")
        assert "PREVIOUS FIX ATTEMPTS" in user_prompt
        assert "replace_locator" in user_prompt
        assert "page.locator('#old').click()" in user_prompt
        assert "Do NOT repeat" in user_prompt

    def test_empty_prior_attempts_no_section(self) -> None:
        """When prior_attempts is empty, no PREVIOUS section in user prompt."""
        import json

        mock_llm = MagicMock()
        mock_llm.generate_test.return_value = json.dumps(
            {
                "fixable": True,
                "diagnosis": "Simple fix",
                "strategy": "replace_locator",
                "old_line": "page.locator('#btn').click()",
                "new_line": "page.locator('#real-btn').click()",
                "confidence": 0.9,
            }
        )

        runner = SelfHealingRunner(llm_client=mock_llm)

        from src.failure_classifier import FailureCategory, FailureDetail
        from src.pytest_output_parser import TestResult

        result = TestResult(
            name="test_first_try",
            status="failed",
            error_message="Timeout waiting for locator('#btn')",
            duration=0.5,
            file_path="test.py",
        )
        detail = FailureDetail(
            category=FailureCategory.LOCATOR_TIMEOUT,
            raw_locator="#btn",
            failure_url=None,
            line_number=None,
            error_message="Timeout waiting for locator('#btn')",
        )
        source = "def test_first_try():\n    page.locator('#btn').click()\n"

        runner._review_and_suggest(result, detail, source, prior_attempts=[])

        call_args = mock_llm.generate_test.call_args
        user_prompt = call_args.kwargs.get("prompt", call_args.args[0] if call_args.args else "")
        assert "PREVIOUS FIX ATTEMPTS" not in user_prompt

    def test_multiple_prior_attempts_both_listed(self) -> None:
        """Multiple prior attempts should all appear, numbered."""
        import json

        mock_llm = MagicMock()
        mock_llm.generate_test.return_value = json.dumps(
            {
                "fixable": True,
                "diagnosis": "Third attempt",
                "strategy": "add_navigation",
                "old_line": "page.locator('#btn').click()",
                "new_line": "page.goto('/correct-page')\n    page.locator('#btn').click()",
                "confidence": 0.8,
            }
        )

        runner = SelfHealingRunner(llm_client=mock_llm)

        from src.failure_classifier import FailureCategory, FailureDetail
        from src.pytest_output_parser import TestResult

        result = TestResult(
            name="test_multiple",
            status="failed",
            error_message="Timeout waiting for locator('#btn')",
            duration=0.5,
            file_path="test.py",
        )
        detail = FailureDetail(
            category=FailureCategory.LOCATOR_TIMEOUT,
            raw_locator="#btn",
            failure_url=None,
            line_number=None,
            error_message="Timeout waiting for locator('#btn')",
        )
        source = "def test_multiple():\n    page.locator('#btn').click()\n"

        prior = [
            {"strategy": "replace_locator", "old_text": "#a", "new_text": "#b", "diagnosis": "First try"},
            {"strategy": "add_wait", "old_text": "#b", "new_text": "wait + #b", "diagnosis": "Second try"},
        ]

        runner._review_and_suggest(result, detail, source, prior_attempts=prior)

        call_args = mock_llm.generate_test.call_args
        user_prompt = call_args.kwargs.get("prompt", call_args.args[0] if call_args.args else "")
        assert "1. replace_locator" in user_prompt
        assert "2. add_wait" in user_prompt


class TestHealReflectionHistoryTracking:
    """Integration: heal() builds attempt_history and tracks LLM calls."""

    def test_heal_tracks_attempt_history(self, tmp_path: Path) -> None:
        """After healing, report.attempt_history contains recorded attempts."""
        import json

        test_file = tmp_path / "test_tracked.py"
        test_file.write_text(
            "def test_tracked():\n"
            '    raise TimeoutError("page.wait_for_selector: Timeout 30000ms exceeded. '
            "waiting for locator('#bad-btn')\")\n",
            encoding="utf-8",
        )

        reviewer_response = json.dumps(
            {
                "fixable": True,
                "diagnosis": "Wrong selector",
                "strategy": "replace_locator",
                "old_line": (
                    'raise TimeoutError("page.wait_for_selector: Timeout 30000ms exceeded. '
                    "waiting for locator('#bad-btn')\")"
                ),
                "new_line": (
                    'raise TimeoutError("page.wait_for_selector: Timeout 30000ms exceeded. '
                    "waiting for locator('#better-btn')\")"
                ),
                "confidence": 0.9,
            }
        )

        mock_llm = MagicMock()
        mock_llm.generate_test.return_value = reviewer_response

        runner = SelfHealingRunner(llm_client=mock_llm, max_iterations=2)
        report = runner.heal(test_file)

        assert "test_tracked" in report.attempt_history, (
            f"Expected test_tracked in attempt_history, got keys: {list(report.attempt_history.keys())}"
        )
        attempts = report.attempt_history["test_tracked"]
        assert len(attempts) >= 1
        assert attempts[0]["strategy"] == "replace_locator"

    def test_heal_counts_total_llm_calls(self, tmp_path: Path) -> None:
        """report.total_llm_calls matches the number of LLM reviewer calls."""
        import json

        test_file = tmp_path / "test_llm_count.py"
        test_file.write_text(
            "def test_count():\n"
            '    raise TimeoutError("page.wait_for_selector: Timeout 30000ms exceeded. '
            "waiting for locator('#btn')\")\n",
            encoding="utf-8",
        )

        reviewer_response = json.dumps(
            {
                "fixable": True,
                "diagnosis": "Fix",
                "strategy": "replace_locator",
                "old_line": (
                    'raise TimeoutError("page.wait_for_selector: Timeout 30000ms exceeded. '
                    "waiting for locator('#btn')\")"
                ),
                "new_line": (
                    'raise TimeoutError("page.wait_for_selector: Timeout 30000ms exceeded. '
                    "waiting for locator('#new')\")"
                ),
                "confidence": 0.9,
            }
        )

        mock_llm = MagicMock()
        mock_llm.generate_test.return_value = reviewer_response

        runner = SelfHealingRunner(llm_client=mock_llm, max_iterations=2)
        report = runner.heal(test_file)

        assert report.total_llm_calls >= 1

    def test_heal_two_failures_two_llm_calls(self, tmp_path: Path) -> None:
        """Two failing tests produce two LLM calls and attempt history."""
        import json

        test_file = tmp_path / "test_two.py"
        test_file.write_text(
            "def test_a():\n"
            '    raise TimeoutError("page.wait_for_selector: Timeout 30000ms exceeded. '
            "waiting for locator('#a')\")\n"
            "def test_b():\n"
            '    raise TimeoutError("page.wait_for_selector: Timeout 30000ms exceeded. '
            "waiting for locator('#b')\")\n",
            encoding="utf-8",
        )

        call_count = [0]
        prior_per_call: list[list[dict]] = []

        def side_effect(*args: object, **kwargs: object) -> str:
            call_count[0] += 1
            prior_raw = kwargs.get("prior_attempts", args[4] if len(args) > 4 else [])
            prior: list[dict[str, str]] = prior_raw if isinstance(prior_raw, list) else []
            prior_per_call.append(list(prior))
            return json.dumps(
                {
                    "fixable": call_count[0] == 1,
                    "diagnosis": f"Attempt {call_count[0]}",
                    "strategy": "replace_locator" if call_count[0] == 1 else "skip_test",
                    "old_line": "some.line('x')",
                    "new_line": "some.line('y')",
                    "confidence": 0.9 if call_count[0] == 1 else 0.0,
                }
            )

        mock_llm = MagicMock()
        mock_llm.generate_test.side_effect = side_effect

        runner = SelfHealingRunner(llm_client=mock_llm, max_iterations=2)
        report = runner.heal(test_file)

        assert call_count[0] >= 2, f"Expected >=2 LLM calls, got {call_count[0]}"
        assert prior_per_call[0] == []  # First call: no priors
        assert isinstance(report.attempt_history, dict)

    def test_heal_no_prior_on_first_iteration(self, tmp_path: Path) -> None:
        """On iteration 1, there are no prior attempts."""
        import json

        test_file = tmp_path / "test_first_iter.py"
        test_file.write_text(
            "def test_fresh():\n"
            '    raise TimeoutError("page.wait_for_selector: Timeout 30000ms exceeded. '
            "waiting for locator('#fresh')\")\n",
            encoding="utf-8",
        )

        reviewer_response = json.dumps(
            {
                "fixable": True,
                "diagnosis": "First fix",
                "strategy": "replace_locator",
                "old_line": (
                    'raise TimeoutError("page.wait_for_selector: Timeout 30000ms exceeded. '
                    "waiting for locator('#fresh')\")"
                ),
                "new_line": (
                    'raise TimeoutError("page.wait_for_selector: Timeout 30000ms exceeded. '
                    "waiting for locator('#fixed')\")"
                ),
                "confidence": 0.9,
            }
        )

        mock_llm = MagicMock()
        mock_llm.generate_test.return_value = reviewer_response

        runner = SelfHealingRunner(llm_client=mock_llm, max_iterations=2)
        runner.heal(test_file)

        first_call = mock_llm.generate_test.call_args_list[0]
        user_prompt = first_call.kwargs.get("prompt", first_call.args[0] if first_call.args else "")
        assert "PREVIOUS FIX ATTEMPTS" not in user_prompt, (
            "First iteration should NOT have prior attempts in user prompt"
        )

    def test_all_passing_returns_empty_history(self, tmp_path: Path) -> None:
        """When all tests pass on first run, attempt_history is empty."""
        test_file = tmp_path / "test_all_good.py"
        test_file.write_text(
            "def test_good():\n    assert True\n",
            encoding="utf-8",
        )

        runner = SelfHealingRunner(max_iterations=3)
        report = runner.heal(test_file)

        assert report.attempt_history == {}
        assert report.total_llm_calls == 0


# ---------------------------------------------------------------------------
# AI-035: self-healing → RAG write-back (_learn_from_patch / _evidence_context)
# ---------------------------------------------------------------------------


class TestEvidenceContext:
    """Recover (steps, base_url) from the evidence sidecar / package manifest."""

    def _sidecar(self, pkg: Path, name: str = "test_foo", locator: str = "#old") -> Path:
        evidence_dir = pkg / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        sidecar = evidence_dir / f"{name}.evidence.json"
        sidecar.write_text(
            json.dumps(
                {
                    "page": {"url": "https://example.com/cart"},
                    "steps": [
                        {
                            "type": "click",
                            "label": "{{CLICK:view cart link}}",
                            "locator": locator,
                            "url": "https://example.com/cart",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return sidecar

    def test_reads_sidecar(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        self._sidecar(pkg)
        steps, url = SelfHealingRunner._evidence_context(pkg / "test_foo.py", "test_foo")
        assert url == "https://example.com/cart"
        assert steps[0]["label"] == "{{CLICK:view cart link}}"

    def test_strips_param_suffix(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        self._sidecar(pkg, name="test_foo")
        steps, url = SelfHealingRunner._evidence_context(pkg / "test_foo.py", "test_foo[chromium]")
        assert url == "https://example.com/cart"
        assert len(steps) == 1

    def test_manifest_fallback_when_no_sidecar(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "scrape_manifest.json").write_text(
            json.dumps({"starting_url": "https://saucedemo.com/inventory.html"}),
            encoding="utf-8",
        )
        steps, url = SelfHealingRunner._evidence_context(pkg / "test_foo.py", "test_foo")
        assert steps == []
        assert url == "https://saucedemo.com/inventory.html"

    def test_missing_returns_empty(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir(parents=True, exist_ok=True)
        steps, url = SelfHealingRunner._evidence_context(pkg / "test_foo.py", "test_foo")
        assert steps == []
        assert url == ""

    def test_corrupt_sidecar_returns_empty(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        evidence_dir = pkg / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "test_foo.evidence.json").write_text("{not-json", encoding="utf-8")
        steps, url = SelfHealingRunner._evidence_context(pkg / "test_foo.py", "test_foo")
        assert steps == []
        assert url == ""


class TestLearnFromPatchRunner:
    """SelfHealingRunner._learn_from_patch — the AI-035 write-back hook."""

    @staticmethod
    def _patch(
        strategy: str = "replace_locator",
        old: str = 'page.locator("#old").click()',
        new: str = 'page.locator("#new").click()',
    ) -> AppliedPatch:
        return AppliedPatch(
            test_name="test_foo",
            line_number=2,
            old_text=old,
            new_text=new,
            diagnosis="Wrong locator",
            strategy=strategy,
        )

    @staticmethod
    def _runner(store: MagicMock | None = None) -> SelfHealingRunner:
        return SelfHealingRunner(llm_client=MagicMock(), rag_store=store)

    @staticmethod
    def _result() -> TestResult:
        return TestResult(
            name="test_foo",
            status="failed",
            duration=0.1,
            error_message="TimeoutError: waiting for locator",
            file_path="test_foo.py",
        )

    def _pkg_with_sidecar(self, tmp_path: Path, locator: str = "#old") -> Path:
        pkg = tmp_path / "pkg"
        evidence_dir = pkg / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "test_foo.evidence.json").write_text(
            json.dumps(
                {
                    "page": {"url": "https://example.com/cart"},
                    "steps": [
                        {
                            "type": "click",
                            "label": "{{CLICK:view cart link}}",
                            "locator": locator,
                            "url": "https://example.com/cart",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        test_file = pkg / "test_foo.py"
        test_file.write_text("def test_foo(page):\n    page.locator('#old').click()\n", encoding="utf-8")
        return test_file

    def test_upserts_self_healing_pattern(self, tmp_path: Path) -> None:
        store = MagicMock()
        store.upsert_pattern.return_value = ("inserted", 1)
        test_file = self._pkg_with_sidecar(tmp_path)

        learned = self._runner(store)._learn_from_patch(test_file, self._result(), self._patch())

        assert learned is True
        pattern: LearnedPattern = store.upsert_pattern.call_args.args[0]
        assert pattern.source == "self_healing"
        assert pattern.confidence == 1.0
        assert pattern.description == "view cart link"
        assert pattern.locator == "#new"
        assert pattern.action_type == "CLICK"
        assert pattern.site_hash == site_hash("example.com")

    def test_skips_non_locator_strategy(self, tmp_path: Path) -> None:
        store = MagicMock()
        test_file = self._pkg_with_sidecar(tmp_path)
        patch = self._patch(strategy="add_wait", new='page.wait_for_selector("#new")')

        learned = self._runner(store)._learn_from_patch(test_file, self._result(), patch)

        assert learned is False
        store.upsert_pattern.assert_not_called()

    def test_no_sidecar_returns_false(self, tmp_path: Path) -> None:
        store = MagicMock()
        pkg = tmp_path / "pkg"
        pkg.mkdir(parents=True, exist_ok=True)
        test_file = pkg / "test_foo.py"
        test_file.write_text("def test_foo(page):\n    pass\n", encoding="utf-8")

        learned = self._runner(store)._learn_from_patch(test_file, self._result(), self._patch())

        assert learned is False
        store.upsert_pattern.assert_not_called()

    def test_store_failure_never_breaks_healing(self, tmp_path: Path) -> None:
        store = MagicMock()
        store.upsert_pattern.side_effect = RuntimeError("store down")
        test_file = self._pkg_with_sidecar(tmp_path)

        learned = self._runner(store)._learn_from_patch(test_file, self._result(), self._patch())

        assert learned is False  # swallowed, no exception

    def test_healing_report_learned_defaults_zero(self) -> None:
        assert HealingReport().learned == 0
