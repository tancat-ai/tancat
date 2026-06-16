"""Unit tests for src/code_normalizer.py."""

import ast

from src.code_normalizer import (
    ensure_test_navigation,
    fix_indentation,
    normalize_whitespace,
)
from src.code_postprocessor import normalise_generated_code


class TestNormalizeWhitespace:
    def test_tabs_converted_to_spaces(self) -> None:
        code = "\tdef test_foo():\n\t\tpass\n"
        result = normalize_whitespace(code)
        assert "\t" not in result
        assert "    def test_foo():" in result
        assert "        pass" in result

    def test_crlf_normalized_to_lf(self) -> None:
        code = "def test_foo():\r\n    pass\r\n"
        result = normalize_whitespace(code)
        assert "\r" not in result
        assert result == "def test_foo():\n    pass\n"

    def test_cr_normalized_to_lf(self) -> None:
        code = "def test_foo():\r    pass\r"
        result = normalize_whitespace(code)
        assert "\r" not in result
        assert result == "def test_foo():\n    pass\n"

    def test_no_changes_for_clean_code(self) -> None:
        code = "def test_foo():\n    pass\n"
        result = normalize_whitespace(code)
        assert result == code

    def test_mixed_tabs_and_spaces(self) -> None:
        # Tab at column 0, then tab + spaces for nested level
        code = "\tdef test_foo():\n\t    pass\n"
        result = normalize_whitespace(code)
        assert "\t" not in result
        # First tab → 4 spaces, second tab + 4 spaces → 8 spaces
        assert "    def test_foo():" in result
        assert "        pass" in result


class TestNormalizeWhitespaceInPipeline:
    def test_tab_indented_code_becomes_valid_python(self) -> None:
        """Code with tabs should be normalized to valid Python syntax."""
        code = """from playwright.sync_api import Page, expect

def test_homepage(page: Page) -> None:
\tpage.goto("https://example.com")
\texpect(page).to_have_title("Example")
"""
        result = normalise_generated_code(code, consent_mode="none")
        # Should parse without SyntaxError
        ast.parse(result)
        assert "\t" not in result

    def test_tab_indented_code_with_ensure_test_navigation(self) -> None:
        """The original bug: tabs in LLM output + 4-space injection = SyntaxError."""
        code = """from playwright.sync_api import Page, expect

def test_homepage(page: Page, evidence_tracker) -> None:
\tevidence_tracker.click("#button", label="click button")
"""
        result = normalise_generated_code(code, consent_mode="none")
        # Must be valid Python - no "unindent does not match" error
        ast.parse(result)
        assert "\t" not in result


class TestEnsureTestNavigation:
    def test_injects_navigation_when_missing(self) -> None:
        code = """def test_foo(page: Page, evidence_tracker) -> None:
    evidence_tracker.click("#btn", label="click")
"""
        result = ensure_test_navigation(code, target_url="https://example.com")
        assert 'evidence_tracker.navigate("https://example.com")' in result

    def test_does_not_inject_when_navigation_exists(self) -> None:
        code = """def test_foo(page: Page, evidence_tracker) -> None:
    evidence_tracker.navigate("https://example.com")
    evidence_tracker.click("#btn", label="click")
"""
        result = ensure_test_navigation(code, target_url="https://example.com")
        # Should not add a second navigation
        assert result.count("navigate(") == 1

    def test_injects_with_flexible_signature_no_type_hints(self) -> None:
        """Regex must match signatures without type hints."""
        code = """def test_foo(page, evidence_tracker):
    evidence_tracker.click("#btn", label="click")
"""
        result = ensure_test_navigation(code, target_url="https://example.com")
        assert 'evidence_tracker.navigate("https://example.com")' in result

    def test_detects_body_indent_and_matches_it(self) -> None:
        """Injected lines should use the same indentation as the existing body."""
        code = """def test_foo(page: Page, evidence_tracker) -> None:
    evidence_tracker.click("#btn", label="click")
"""
        result = ensure_test_navigation(code, target_url="https://example.com")
        # Both injected lines and existing body should be at 4-space indent
        lines = result.splitlines()
        body_lines = [line for line in lines if line.strip() and not line.strip().startswith("def ")]
        for bl in body_lines:
            assert bl.startswith("    "), f"Expected 4-space indent: {bl!r}"


class TestFixIndentation:
    def test_first_body_line_over_indented_after_def(self) -> None:
        """First body line with extra indent after def must be fixed to func_indent."""
        code = "def test_foo(page: Page) -> None:\n        page.click('#btn')\n    page.click('#other')\n"
        result = fix_indentation(code)
        # Both body lines should be at 4-space indent
        assert "    page.click('#btn')" in result
        assert "    page.click('#other')" in result
        # Must be valid python
        ast.parse(result)

    def test_first_body_line_under_indented_after_def(self) -> None:
        """First body line with less than func_indent must be raised."""
        code = "def test_foo(page: Page) -> None:\n  page.click('#btn')\n"
        result = fix_indentation(code)
        assert "    page.click('#btn')" in result
        ast.parse(result)

    def test_legitimate_nested_block_after_if_preserved(self) -> None:
        """Extra indent after an if-statement must NOT be stripped."""
        code = "def test_foo(page: Page) -> None:\n    if True:\n        page.click('#btn')\n    page.click('#other')\n"
        result = fix_indentation(code)
        assert "        page.click('#btn')" in result  # 8 spaces preserved
        assert "    page.click('#other')" in result
        ast.parse(result)

    def test_mixed_indent_first_line_8_second_line_4(self) -> None:
        """The exact bug pattern: first body line at 8 spaces, second at 4."""
        code = (
            "def test_foo(page: Page, evidence_tracker) -> None:\n"
            "        evidence_tracker.click('#btn', label='click')\n"
            "    evidence_tracker.navigate('https://example.com')\n"
        )
        result = fix_indentation(code)
        # Both should be normalized to 4 spaces
        lines = result.splitlines()
        body_lines = [line for line in lines if line.strip() and not line.strip().startswith("def ")]
        for bl in body_lines:
            assert bl.startswith("    ") and not bl.startswith("        "), f"Unexpected indent: {bl!r}"
        ast.parse(result)


class TestEndToEndIndentationFix:
    def test_full_pipeline_tabs_then_navigation_injection(self) -> None:
        """Reproduce the exact reported error: tab-indented LLM output + navigate injection."""
        code = (
            "from playwright.sync_api import Page, expect\n"
            "\n"
            "def test_checkout(page: Page, evidence_tracker) -> None:\n"
            "\tpage.goto('https://automationexercise.com/')\n"
            "\tpage.locator('#button').click()\n"
        )
        result = normalise_generated_code(
            code, consent_mode="auto-dismiss", target_url="https://automationexercise.com/"
        )
        # Must be valid Python — no "unindent does not match" error
        ast.parse(result)
        assert "\t" not in result

    def test_full_pipeline_no_navigation_body_over_indented(self) -> None:
        """Body has no navigation and uses 8-space indent; injection + fix must produce valid code."""
        code = (
            "from playwright.sync_api import Page, expect\n"
            "\n"
            "def test_checkout(page: Page, evidence_tracker) -> None:\n"
            "        page.locator('#button').click()\n"
        )
        result = normalise_generated_code(
            code, consent_mode="auto-dismiss", target_url="https://automationexercise.com/"
        )
        ast.parse(result)
        assert 'evidence_tracker.navigate("https://automationexercise.com/")' in result
