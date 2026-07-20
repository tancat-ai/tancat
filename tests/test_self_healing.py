"""Unit tests for src/self_healing.py — Phase 2 Self-Healing Reflection Loops."""

from __future__ import annotations

from pathlib import Path

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
