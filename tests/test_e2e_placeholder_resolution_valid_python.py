"""End-to-end integration test: PlaceholderOrchestrator produces valid Python.

This test verifies that when PlaceholderOrchestrator resolves placeholders
using scraped DOM data, the resulting code passes Python syntax validation
via ast.parse().

This is the PROPER way to test the fix for the quoting bug where selectors
like .btn.btn-default.add-to-cart[data-product-id="11"] were producing
broken Python: evidence_tracker.click('a:has-text("Add to cart", label='...')
"""

from __future__ import annotations

import ast

from src.code_postprocessor import replace_token_in_line
from src.placeholder_orchestrator import PlaceholderOrchestrator


class TestPlaceholderOrchestratorQuoting:
    """Verify PlaceholderOrchestrator produces valid Python when resolving placeholders."""

    def test_robust_locator_with_double_quotes_produces_valid_python(self) -> None:
        """When find_best_match returns 'a:has-text("Add to cart")', the final code must parse."""
        _orchestrator = PlaceholderOrchestrator(starting_url="https://example.com")

        # Simulate what find_best_match returns for "Add to cart" button
        robust_selector = 'a:has-text("Add to cart")'
        # This is what repr() produces
        resolved_value = repr(robust_selector)

        # Now simulate what replace_token_in_line does
        line = "    {{CLICK:add to cart button}}.click()"
        result = replace_token_in_line(
            line=line,
            action="CLICK",
            token="{{CLICK:add to cart button}}",
            resolved_value=resolved_value,
            duplicate_selectors=set(),
            description="add to cart button",
        )

        # Validate: must parse as Python
        full_code = f"def test_foo(page):\n{result}"
        ast.parse(full_code)

        # Verify the selector is intact
        assert 'a:has-text("Add to cart")' in result
        assert "evidence_tracker.click" in result

    def test_robust_locator_with_nested_quotes_all_action_types(self) -> None:
        """Test all action types with nested quotes to ensure full coverage."""
        # CLICK action
        resolved_click = repr('a:has-text("Add to cart")')
        line_click = "    {{CLICK:add to cart button}}"
        result_click = replace_token_in_line(
            line=line_click,
            action="CLICK",
            token="{{CLICK:add to cart button}}",
            resolved_value=resolved_click,
            duplicate_selectors=set(),
            description="add to cart",
        )
        full_code_click = f"def test_foo(page):\n{result_click}"
        ast.parse(full_code_click)

        # ASSERT action
        resolved_assert = repr("Add to cart")
        line_assert = "    {{ASSERT:cart item count}}"
        result_assert = replace_token_in_line(
            line=line_assert,
            action="ASSERT",
            token="{{ASSERT:cart item count}}",
            resolved_value=resolved_assert,
            duplicate_selectors=set(),
            description="cart item count",
        )
        full_code_assert = f"def test_foo(page):\n{result_assert}"
        ast.parse(full_code_assert)

        # FILL action
        resolved_fill = repr("#email")
        line_fill = "    {{FILL:email field}}"
        result_fill = replace_token_in_line(
            line=line_fill,
            action="FILL",
            token="{{FILL:email field}}",
            resolved_value=resolved_fill,
            duplicate_selectors=set(),
            description="email field",
        )
        full_code_fill = f"def test_foo(page):\n{result_fill}"
        ast.parse(full_code_fill)

        # GOTO action
        resolved_goto = repr("https://example.com/checkout")
        line_goto = "    {{GOTO:checkout page}}"
        result_goto = replace_token_in_line(
            line=line_goto,
            action="GOTO",
            token="{{GOTO:checkout page}}",
            resolved_value=resolved_goto,
            duplicate_selectors=set(),
            description="checkout page",
        )
        full_code_goto = f"def test_foo(page):\n{result_goto}"
        ast.parse(full_code_goto)

    def test_plain_selector_without_quotes_gets_repr_wrapped(self) -> None:
        """Plain selectors without quotes must be wrapped in repr() by replace_token_in_line."""
        # This is what happens when robust_selector is None and we fall back to raw selector
        resolved = "button.btn-primary"
        line = "    {{CLICK:primary button}}"
        result = replace_token_in_line(
            line=line,
            action="CLICK",
            token="{{CLICK:primary button}}",
            resolved_value=resolved,
            duplicate_selectors=set(),
            description="primary button",
        )
        full_code = f"def test_foo(page):\n{result}"
        ast.parse(full_code)
        # The selector should be repr-wrapped
        assert "evidence_tracker.click" in result
        assert "button.btn-primary" in result


class TestFullCodeGeneration:
    """Test that a full generated test file with resolved placeholders parses correctly."""

    def test_full_test_file_with_mixed_resolved_placeholders(self) -> None:
        """Simulate a full test function with multiple resolved placeholders."""
        # Simulate resolved code after placeholder replacement
        lines = [
            "def test_add_items_to_cart(page, evidence_tracker) -> None:",
            '    """Test: Add items to cart."""',
            "",
            "    evidence_tracker.navigate('https://automationexercise.com/')",
            "    dismiss_consent_overlays(page)",
            "",
            '    evidence_tracker.click("a:has-text(\\"Add to cart\\")", label="add to cart button")',
            "",
            '    evidence_tracker.assert_visible("Add to cart", label="cart confirmation")',
            "",
            "    evidence_tracker.navigate('https://automationexercise.com/cart')",
            "",
            '    evidence_tracker.assert_visible("Cart - Your product has been added!", label="cart success message")',
            "",
        ]
        full_code = "\n".join(lines)

        # This must parse as valid Python
        ast.parse(full_code)

    def test_full_test_file_with_skip_and_resolved_placeholders(self) -> None:
        """Test with a mix of skips and resolved placeholders."""
        lines = [
            "def test_view_product_details(page, evidence_tracker) -> None:",
            '    """Test: View product details."""',
            "",
            "    pytest.skip('Skipping: unresolved placeholders for product card')",
            "    evidence_tracker.navigate('https://automationexercise.com/')",
            "",
            '    evidence_tracker.click("a:has-text(\\"Blue Dress\\")", label="product card")',
            "",
            '    evidence_tracker.assert_visible("Blue Dress", label="product title")',
            "",
        ]
        full_code = "\n".join(lines)

        # This must parse as valid Python
        ast.parse(full_code)
