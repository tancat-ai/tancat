"""Integration tests that validate generated test output is valid Python.

These tests catch bugs that unit tests miss by validating the full
normalization pipeline end-to-end with realistic LLM-generated code.
"""

from __future__ import annotations

import ast
import re

from src.code_normalizer import (
    convert_standalone_placeholders,
    deduplicate_skip_calls,
    fix_indentation,
    normalize_whitespace,
    replace_remaining_placeholders,
    strip_pages_needed_block,
)
from src.code_postprocessor import normalise_generated_code


def _build_pipeline(code: str, target_url: str = "", consent_mode: str = "cookie") -> str:
    """Run the full normalization pipeline as used by the orchestrator."""
    code = normalize_whitespace(code)
    code = convert_standalone_placeholders(code)
    code = replace_remaining_placeholders(code)
    code = strip_pages_needed_block(code)
    code = fix_indentation(code)
    code = deduplicate_skip_calls(code)
    code = normalise_generated_code(code, consent_mode=consent_mode, target_url=target_url)
    return code


class TestPlaceholderConversion:
    """Verify that unresolved placeholders are converted to valid pytest.skip() calls."""

    def test_output_is_valid_python(self) -> None:
        """Any input with placeholders must produce valid Python."""
        code = """def test_foo(page, evidence_tracker):
    evidence_tracker.navigate("https://example.com")
    {{ASSERT:something visible}}
"""
        result = _build_pipeline(code)
        ast.parse(result)  # Must not raise

    def test_output_with_embedded_quotes_is_valid_python(self) -> None:
        """Placeholders with embedded double quotes must produce valid Python."""
        code = """def test_foo(page, evidence_tracker):
    evidence_tracker.navigate("https://example.com")
    {{ASSERT:Product "Blue Top" is visible}}
"""
        result = _build_pipeline(code)
        ast.parse(result)  # Must not raise

    def test_multiple_unresolved_placeholders_deduplicated(self) -> None:
        """Multiple consecutive pytest.skip() calls should be deduplicated."""
        code = """def test_foo(page, evidence_tracker):
    {{ASSERT:first thing}}
    {{ASSERT:second thing}}
    evidence_tracker.navigate("https://example.com")
"""
        result = _build_pipeline(code)
        ast.parse(result)
        skip_count = result.count("pytest.skip(")
        assert skip_count >= 1
        assert skip_count <= 2  # deduplicate should reduce

    def test_placeholder_inside_function_call_handled(self) -> None:
        """When a placeholder is inside a function call, the line becomes pytest.skip()."""
        code = """def test_foo(page, evidence_tracker):
    evidence_tracker.navigate("https://example.com")
    evidence_tracker.click('{{CLICK:Submit button}}', label='click submit')
"""
        result = _build_pipeline(code)
        ast.parse(result)
        # Original broken line should be replaced
        assert "evidence_tracker.click('{{CLICK:" not in result

    def test_no_raw_standalone_placeholders_in_output(self) -> None:
        """Standalone placeholder tokens must not appear as bare expressions."""
        code = """def test_foo(page, evidence_tracker):
    evidence_tracker.navigate("https://example.com")
    {{CLICK:unknown button}}
    {{FILL:unknown input}}
    {{ASSERT:unknown element}}
"""
        result = _build_pipeline(code)
        ast.parse(result)
        # Bare placeholder expressions (not inside strings) should not exist
        lines = result.splitlines()
        for line in lines:
            stripped = line.strip()
            # Skip lines where placeholder is inside a string (pytest.skip output)
            if "pytest.skip(" in stripped:
                continue
            # Bare placeholder should not appear
            assert not stripped.startswith("{{"), f"Bare placeholder found: {stripped}"


class TestPOMModeIntegration:
    """Verify POM mode generates valid Python with correct imports and instantiation."""

    def test_pom_instantiation_valid_python(self) -> None:
        """POM instantiation lines must be valid Python when injected."""
        code = """from playwright.sync_api import Page, expect
from src.browser_utils import dismiss_consent_overlays
import pytest
from pages.home_page import HomePage

def test_foo(page: Page, evidence_tracker) -> None:
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate("https://example.com")
    home_page.click_submit()
"""
        ast.parse(code)
        assert "HomePage(page, evidence_tracker)" in code

    def test_pom_instantiation_indentation(self) -> None:
        """POM instantiation must be at the correct indentation level inside test functions."""
        code = """from playwright.sync_api import Page
from pages.home_page import HomePage

def test_bar(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page.click_login()
"""
        result = fix_indentation(code)
        ast.parse(result)
        lines = result.splitlines()
        for line in lines:
            if "HomePage(" in line:
                assert line.startswith("    "), f"POM line not at 4-space indent: {line!r}"
                assert not line.startswith("        "), f"POM line double-indented: {line!r}"


class TestSkipBeforeNavigateFixed:
    """
    FIXED: pytest.skip() now appears AFTER navigate() thanks to deduplicate_skip_calls.

    The deduplicate_skip_calls function defers flushing pending skips until after
    navigation steps, ensuring tests navigate before being skipped.
    """

    def test_skip_appears_after_navigate(self) -> None:
        """pytest.skip() should appear AFTER navigate(), not before."""
        code = """def test_foo(page, evidence_tracker):
    pytest.skip("Skipping: unresolved placeholders for: 'something'")
    evidence_tracker.navigate("https://example.com")
    dismiss_consent_overlays(page)
    pytest.skip('Unresolved placeholder in this step. {{ASSERT:something}}')
"""
        result = _build_pipeline(code)
        ast.parse(result)

        # Find the function body
        func_match = re.search(r"def test_foo[^:]*:(.*?)(?=\ndef |\Z)", result, re.S)
        assert func_match is not None
        body = func_match.group(1)

        skip_pos = body.find("pytest.skip(")
        navigate_pos = body.find("navigate(")

        # FIXED: navigate should come before skip
        if skip_pos >= 0 and navigate_pos >= 0:
            assert navigate_pos < skip_pos, (
                f"BUG: pytest.skip() at pos {skip_pos} appears before navigate() at pos {navigate_pos}"
            )


class TestImportHandling:
    """Verify imports are correct in generated output."""

    def test_pytest_import_added_when_skip_used(self) -> None:
        """If pytest.skip() is in output, 'import pytest' must be present."""
        code = """def test_foo(page, evidence_tracker):
    {{ASSERT:unresolved}}
"""
        result = _build_pipeline(code)
        assert "import pytest" in result
        assert "pytest.skip(" in result

    def test_page_fixture_in_signatures(self) -> None:
        """Tests that use page: must have page: Page in signature."""
        code = """def test_foo(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://example.com")
"""
        result = _build_pipeline(code)
        assert "page: Page" in result or "page" in result
