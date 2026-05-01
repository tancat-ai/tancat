"""End-to-end test that verifies placeholder resolution produces valid Python."""

from __future__ import annotations

import ast

from src.code_postprocessor import replace_token_in_line


class TestReplaceTokenInLine:
    """Verify replace_token_in_line produces valid Python for all action types."""

    def test_click_with_double_quotes_in_selector(self) -> None:
        """Selector contains double quotes — must not break Python syntax."""
        # This simulates what find_best_match returns for "Add to cart" button:
        # 'a:has-text("Add to cart")' — a 27-char string with single-quote wrapping
        resolved = 'a:has-text("Add to cart")'
        line = "    {{CLICK:add to cart button}}.click()"
        result = replace_token_in_line(
            line=line,
            action="CLICK",
            token="{{CLICK:add to cart button}}",
            resolved_value=resolved,
            duplicate_selectors=set(),
            description="add to cart button",
        )
        # Validate it parses as Python
        full_code = f"def test_foo(page):\n{result}"
        ast.parse(full_code)
        # The result should use evidence_tracker.click, not .click()
        assert "evidence_tracker.click" in result
        assert 'a:has-text("Add to cart")' in result

    def test_click_with_single_quotes_in_selector(self) -> None:
        """Selector contains single quotes — must not break Python syntax."""
        resolved = "button:has-text('Submit')"
        line = "    {{CLICK:submit button}}"
        result = replace_token_in_line(
            line=line,
            action="CLICK",
            token="{{CLICK:submit button}}",
            resolved_value=resolved,
            duplicate_selectors=set(),
            description="submit button",
        )
        full_code = f"def test_foo(page):\n{result}"
        ast.parse(full_code)
        assert "evidence_tracker.click" in result

    def test_click_with_no_quotes_in_selector(self) -> None:
        """Plain selector — must be wrapped in repr()."""
        resolved = "a:has-text(Add to cart)"
        line = "    {{CLICK:add to cart button}}"
        result = replace_token_in_line(
            line=line,
            action="CLICK",
            token="{{CLICK:add to cart button}}",
            resolved_value=resolved,
            duplicate_selectors=set(),
            description="add to cart button",
        )
        full_code = f"def test_foo(page):\n{result}"
        ast.parse(full_code)
        assert "evidence_tracker.click" in result

    def test_assert_with_double_quotes(self) -> None:
        """Assert action with double quotes in resolved value."""
        resolved = "Add to cart"
        line = "    {{ASSERT:add to cart}}"
        result = replace_token_in_line(
            line=line,
            action="ASSERT",
            token="{{ASSERT:add to cart}}",
            resolved_value=resolved,
            duplicate_selectors=set(),
            description="add to cart",
        )
        full_code = f"def test_foo(page):\n{result}"
        ast.parse(full_code)
        assert "evidence_tracker.assert_visible" in result

    def test_fill_with_double_quotes(self) -> None:
        """Fill action with double quotes in resolved value."""
        resolved = "'#email'"
        line = "    {{FILL:email}}"
        result = replace_token_in_line(
            line=line,
            action="FILL",
            token="{{FILL:email}}",
            resolved_value=resolved,
            duplicate_selectors=set(),
            description="email field",
        )
        full_code = f"def test_foo(page):\n{result}"
        ast.parse(full_code)
        assert "evidence_tracker.fill" in result

    def test_goto_with_url(self) -> None:
        """GOTO action with URL."""
        resolved = "'https://example.com/checkout'"
        line = "    {{GOTO:checkout page}}"
        result = replace_token_in_line(
            line=line,
            action="GOTO",
            token="{{GOTO:checkout page}}",
            resolved_value=resolved,
            duplicate_selectors=set(),
            description="checkout page",
        )
        full_code = f"def test_foo(page):\n{result}"
        ast.parse(full_code)
        assert "evidence_tracker.navigate" in result

    def test_skip_resolution(self) -> None:
        """When resolution is pytest.skip, whole line must be replaced."""
        resolved = "pytest.skip('Unresolved: product card')"
        line = "    {{CLICK:product card}}"
        result = replace_token_in_line(
            line=line,
            action="CLICK",
            token="{{CLICK:product card}}",
            resolved_value=resolved,
            duplicate_selectors=set(),
            description="product card",
        )
        full_code = f"def test_foo(page):\n{result}"
        ast.parse(full_code)
        assert "pytest.skip" in result
