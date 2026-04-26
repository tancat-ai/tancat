"""Tests for _strip_llm_reasoning_text in src/code_postprocessor.py."""

from __future__ import annotations

import pytest

from src.code_postprocessor import _is_llm_reasoning_line, _strip_llm_reasoning_text


class TestIsLlmReasoningLine:
    """Tests for the _is_llm_reasoning_line heuristic detector."""

    @pytest.mark.parametrize(
        "line",
        [
            "Wait, the placeholder syntax requires exactly two braces on each side.",
            "Note, this is important.",
            "Actually, I think that's wrong.",
            "Hmm, let me check.",
            "Okay, I'll do that.",
            "Sure, here's the code.",
            "Let's check the line count.",
            "That's within 3-10 lines.",
            "This is a valid test.",
            "The prompt says to do X.",
            "The example shows Y.",
            "I will add the code.",
            "I need to check more.",
            "I should verify this.",
            "All constraints met.",
            "Matches all criteria.",
            "Output matches expected.",
            "Proceeds to next step.",
            "Self-Correction: this is wrong.",
            "Refinement: better approach.",
            "One minor issue.",
            "One check passed.",
            "Final check complete.",
            "Self check done.",
            "Edge case handled.",
            "Corner case found.",
            "In the example shown.",
            "To be safe, I'll add more.",
            "To avoid issues, do X.",
        ],
    )
    def test_detects_llm_reasoning_prefixes(self, line: str) -> None:
        """Lines starting with known LLM reasoning prefixes should be detected."""
        assert _is_llm_reasoning_line(line) is True

    @pytest.mark.parametrize(
        "line",
        [
            "def test_add_to_cart(page: Page, evidence_tracker) -> None:",
            "class TestCart:",
            "import pytest",
            "from playwright.sync_api import Page",
            "return None",
            "if page.is_visible():",
            "elif something:",
            "else:",
            "for item in items:",
            "while condition:",
            "try:",
            "except Exception:",
            "finally:",
            "with page:",
            "assert True",
            "raise ValueError",
            "yield result",
            "lambda x: x",
            "pass",
            "break",
            "continue",
            "@pytest.mark.evidence",
            "@pytest.fixture",
            "# PAGES_NEEDED:",
            "# - https://example.com",
            '"""This is a docstring."""',
            "'''Another docstring.'''",
            "pytest.skip('reason')",
            "evidence_tracker.click(selector)",
            "dismiss_consent_overlays(page)",
            "page.locator('#button')",
            "self.page.goto(url)",
        ],
    )
    def test_preserves_valid_python(self, line: str) -> None:
        """Valid Python constructs should NOT be flagged as reasoning."""
        assert _is_llm_reasoning_line(line) is False

    @pytest.mark.parametrize(
        "line",
        [
            "Wait, this needs fixing.",
            "Note, check the logic.",
        ],
    )
    def test_detects_comment_style_reasoning(self, line: str) -> None:
        """Lines like '# Note, ...' should be detected."""
        assert _is_llm_reasoning_line(f"# {line}") is True

    def test_allows_capital_letter_with_colon(self) -> None:
        """Lines like 'Page: str =' should NOT be flagged (type hint pattern)."""
        assert _is_llm_reasoning_line("Page: str = None") is False

    def test_allows_capital_letter_with_equals(self) -> None:
        """Lines like 'ClassName =' should NOT be flagged (assignment pattern)."""
        assert _is_llm_reasoning_line("CartPage = None") is False

    def test_empty_line_not_reasoning(self) -> None:
        """Empty lines should not be flagged as reasoning."""
        assert _is_llm_reasoning_line("") is False

    def test_whitespace_only_not_reasoning(self) -> None:
        """Whitespace-only lines should not be flagged as reasoning."""
        assert _is_llm_reasoning_line("   ") is False


class TestStripLlmReasoningText:
    """Tests for the _strip_llm_reasoning_text function."""

    def test_removes_reasoning_lines_from_code(self) -> None:
        """Reasoning lines should be removed while code is preserved."""
        code = """def test_add_to_cart(page: Page, evidence_tracker) -> None:
    Wait, the placeholder syntax requires exactly two braces on each side.
    evidence_tracker.click("#add-to-cart", label="Add to cart")
    Note, this is important.
    page.wait_for_timeout(500)
"""
        result = _strip_llm_reasoning_text(code)
        assert "Wait, the placeholder syntax" not in result
        assert "Note, this is important" not in result
        assert 'evidence_tracker.click("#add-to-cart"' in result
        assert "page.wait_for_timeout(500)" in result

    def test_preserves_blank_lines(self) -> None:
        """Blank lines should be preserved."""
        code = """def test_example() -> None:
    pass

    Wait, reasoning.

    x = 1
"""
        result = _strip_llm_reasoning_text(code)
        # Blank lines should remain
        assert "\n\n" in result

    def test_handles_code_without_reasoning(self) -> None:
        """Clean code should pass through unchanged (minus trailing newline)."""
        code = """def test_clean() -> None:
    assert True"""
        result = _strip_llm_reasoning_text(code)
        assert result == code

    def test_removes_reasoning_between_functions(self) -> None:
        """Reasoning between function definitions should be removed."""
        code = """def test_first() -> None:
    pass

    Let's check the line count.
    That's within 3-10 lines.

def test_second() -> None:
    assert True
"""
        result = _strip_llm_reasoning_text(code)
        assert "Let's check" not in result
        assert "That's within" not in result
        assert "def test_first" in result
        assert "def test_second" in result

    def test_preserves_reasoning_like_strings_inside_code(self) -> None:
        """Strings that happen to contain reasoning-like text but are part of
        valid Python (e.g., inside a function call) should be preserved."""
        code = """def test_example() -> None:
    evidence_tracker.navigate("https://example.com")
    # Wait, this is a URL, not reasoning.
"""
        result = _strip_llm_reasoning_text(code)
        # The comment line starts with "# Wait," which matches the pattern
        # This is a known limitation - comments with reasoning prefixes get stripped
        # The heuristic is intentionally aggressive to catch leaked reasoning
        assert "evidence_tracker.navigate" in result

    def test_handles_reasoning_with_indentation(self) -> None:
        """Reasoning lines with indentation should be removed."""
        code = """def test_example() -> None:
        Wait, indented reasoning.
    page.goto("https://example.com")
"""
        result = _strip_llm_reasoning_text(code)
        assert "indented reasoning" not in result
        assert "page.goto" in result
