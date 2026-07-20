"""Tests for B-016 ASSERT role filtering in PlaceholderOrchestrator.

B-016: ASSERT placeholders resolve to wrong interactive elements (buttons, links)
instead of display elements. Fixed by adding role filtering to Pass 1 ASSERT,
Pass 2 structural, and Pass 3 scoring.
"""

from src.placeholder_orchestrator import PlaceholderOrchestrator
from src.role_mapper import DISPLAY_ROLES, ROLE_FALLBACK_GAP, get_effective_role, is_display_role

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestDisplayRoles:
    """Verify DISPLAY_ROLES contains expected roles."""

    def test_contains_heading(self) -> None:
        assert "heading" in DISPLAY_ROLES

    def test_contains_paragraph(self) -> None:
        assert "paragraph" in DISPLAY_ROLES

    def test_contains_text(self) -> None:
        assert "text" in DISPLAY_ROLES

    def test_contains_status(self) -> None:
        assert "status" in DISPLAY_ROLES

    def test_contains_image(self) -> None:
        assert "image" in DISPLAY_ROLES

    def test_excludes_button(self) -> None:
        assert "button" not in DISPLAY_ROLES

    def test_excludes_link(self) -> None:
        assert "link" not in DISPLAY_ROLES

    def test_excludes_textbox(self) -> None:
        assert "textbox" not in DISPLAY_ROLES

    def test_excludes_checkbox(self) -> None:
        assert "checkbox" not in DISPLAY_ROLES

    def test_role_fallback_gap_is_positive(self) -> None:
        assert ROLE_FALLBACK_GAP > 0


# ---------------------------------------------------------------------------
# _get_effective_role
# ---------------------------------------------------------------------------


class TestGetEffectiveRole:
    """Verify role resolution prefers computed_role over raw role."""

    def _make_orchestrator(self) -> PlaceholderOrchestrator:
        return PlaceholderOrchestrator()

    def test_prefers_computed_role(self) -> None:
        element = {"computed_role": "heading", "role": "h1"}
        assert get_effective_role(element) == "heading"

    def test_falls_back_to_raw_role(self) -> None:
        element = {"role": "button"}
        assert get_effective_role(element) == "button"

    def test_empty_when_missing(self) -> None:
        element: dict[str, str] = {}
        assert get_effective_role(element) == ""

    def test_handles_whitespace(self) -> None:
        element = {"computed_role": "  STATUS  "}
        assert get_effective_role(element) == "status"

    def test_computed_role_overrides_tag_fallback(self) -> None:
        """computed_role='text' should win over role='div' (tag-name fallback)."""
        element = {"computed_role": "text", "role": "div"}
        assert get_effective_role(element) == "text"


# ---------------------------------------------------------------------------
# _is_display_role
# ---------------------------------------------------------------------------


class TestIsDisplayRole:
    """Verify display role detection via computed_role and tag fallback."""

    def _make_orchestrator(self) -> PlaceholderOrchestrator:
        return PlaceholderOrchestrator()

    # -- computed_role path --

    def test_computed_heading_is_display(self) -> None:
        assert is_display_role({"computed_role": "heading"})

    def test_computed_paragraph_is_display(self) -> None:
        assert is_display_role({"computed_role": "paragraph"})

    def test_computed_text_is_display(self) -> None:
        assert is_display_role({"computed_role": "text"})

    def test_computed_status_is_display(self) -> None:
        assert is_display_role({"computed_role": "status"})

    def test_computed_alert_is_display(self) -> None:
        assert is_display_role({"computed_role": "alert"})

    def test_computed_listitem_is_display(self) -> None:
        assert is_display_role({"computed_role": "listitem"})

    def test_computed_cell_is_display(self) -> None:
        assert is_display_role({"computed_role": "cell"})

    def test_computed_image_is_display(self) -> None:
        assert is_display_role({"computed_role": "image"})

    def test_computed_caption_is_display(self) -> None:
        assert is_display_role({"computed_role": "caption"})

    def test_computed_button_is_not_display(self) -> None:
        assert not is_display_role({"computed_role": "button"})

    def test_computed_link_is_not_display(self) -> None:
        assert not is_display_role({"computed_role": "link"})

    def test_computed_textbox_is_not_display(self) -> None:
        assert not is_display_role({"computed_role": "textbox"})

    def test_computed_checkbox_is_not_display(self) -> None:
        assert not is_display_role({"computed_role": "checkbox"})

    def test_computed_combo_is_not_display(self) -> None:
        assert not is_display_role({"computed_role": "combobox"})

    def test_computed_menuitem_is_not_display(self) -> None:
        assert not is_display_role({"computed_role": "menuitem"})

    # -- tag fallback path (no computed_role) --

    def test_tag_h1_is_display(self) -> None:
        assert is_display_role({"tag": "h1"})

    def test_tag_h2_is_display(self) -> None:
        assert is_display_role({"tag": "h2"})

    def test_tag_p_is_display(self) -> None:
        assert is_display_role({"tag": "p"})

    def test_tag_span_is_display(self) -> None:
        assert is_display_role({"tag": "span"})

    def test_tag_li_is_display(self) -> None:
        assert is_display_role({"tag": "li"})

    def test_tag_td_is_display(self) -> None:
        assert is_display_role({"tag": "td"})

    def test_tag_th_is_display(self) -> None:
        assert is_display_role({"tag": "th"})

    def test_tag_label_is_display(self) -> None:
        assert is_display_role({"tag": "label"})

    def test_tag_button_is_not_display(self) -> None:
        assert not is_display_role({"tag": "button"})

    def test_tag_a_is_not_display(self) -> None:
        """<a> without computed_role='link' is not a display role via tag."""
        assert not is_display_role({"tag": "a"})

    def test_tag_input_is_not_display(self) -> None:
        assert not is_display_role({"tag": "input"})

    def test_tag_div_without_role_is_display_as_generic(self) -> None:
        """Plain <div> without computed_role maps to 'generic' which is in DISPLAY_ROLES."""
        assert is_display_role({"tag": "div"})

    def test_empty_element_is_not_display(self) -> None:
        assert not is_display_role({})

    # -- computed_role overrides tag fallback --

    def test_computed_role_overrides_div_tag(self) -> None:
        """A <div> with computed_role='text' is a display element."""
        assert is_display_role(
            {
                "computed_role": "text",
                "tag": "div",
            }
        )

    def test_computed_role_overrides_span_tag(self) -> None:
        """A <span> with computed_role='button' is NOT a display element
        even though span->generic is in DISPLAY_ROLES."""
        assert not is_display_role(
            {
                "computed_role": "button",
                "tag": "span",
            }
        )

    def test_span_via_generic_is_display(self) -> None:
        """Plain <span> (no computed_role) maps to generic, which is display."""
        assert is_display_role({"tag": "span"})

    def test_div_via_generic_is_display(self) -> None:
        """Plain <div> (no computed_role) maps to generic, which is display."""
        assert is_display_role({"tag": "div"})
        assert is_display_role({"role": "div"})


# ---------------------------------------------------------------------------
# _pass2_structural_match with role filtering
# ---------------------------------------------------------------------------


class TestPass2StructuralRoleFiltering:
    """Pass 2 structural match should skip interactive elements for ASSERT."""

    def _make_orchestrator(self) -> PlaceholderOrchestrator:
        return PlaceholderOrchestrator()

    def test_assert_skips_button_for_cart_badge(self) -> None:
        """ASSERT 'cart badge' should not match a button with 'cart' in data-test."""
        orchestrator = self._make_orchestrator()
        pages_data = {
            "http://example.com": [
                {
                    "selector": "button#cart-btn",
                    "data_test": "cart-button",
                    "id": "cart-btn",
                    "role": "button",
                    "computed_role": "button",
                    "text": "Cart",
                    "tag": "button",
                },
                {
                    "selector": "span#cart-badge",
                    "data_test": "cart-badge",
                    "id": "cart-badge",
                    "role": "status",
                    "computed_role": "status",
                    "text": "1",
                    "tag": "span",
                },
            ],
        }
        result = orchestrator._pass2_structural_match("ASSERT", "cart badge", pages_data)
        assert result is not None
        assert result["id"] == "cart-badge"

    def test_assert_skips_link_for_cart_badge(self) -> None:
        """ASSERT 'cart badge' should not match a link with 'cart' in data-test."""
        orchestrator = self._make_orchestrator()
        pages_data = {
            "http://example.com": [
                {
                    "selector": "a#cart-link",
                    "data_test": "shopping-cart-link",
                    "id": "cart-link",
                    "role": "link",
                    "computed_role": "link",
                    "text": "Cart",
                    "tag": "a",
                },
                {
                    "selector": "div#cart-summary",
                    "data_test": "cart-summary",
                    "id": "cart-summary",
                    "role": "region",
                    "computed_role": "region",
                    "text": "Your cart has items",
                    "tag": "div",
                },
            ],
        }
        result = orchestrator._pass2_structural_match("ASSERT", "cart badge", pages_data)
        # Both link and region are non-display, so pass 2 returns None
        # (region is a container role, not in DISPLAY_ROLES)
        assert result is None

    def test_click_allows_all_roles(self) -> None:
        """CLICK should not apply role filtering — any element is fair game."""
        orchestrator = self._make_orchestrator()
        pages_data = {
            "http://example.com": [
                {
                    "selector": "button#submit",
                    "data_test": "submit-button",
                    "id": "submit",
                    "role": "button",
                    "computed_role": "button",
                    "text": "Submit",
                    "tag": "button",
                },
            ],
        }
        result = orchestrator._pass2_structural_match("CLICK", "submit button", pages_data)
        assert result is not None
        assert result["id"] == "submit"

    def test_fill_allows_all_roles(self) -> None:
        """FILL should not apply role filtering."""
        orchestrator = self._make_orchestrator()
        pages_data = {
            "http://example.com": [
                {
                    "selector": "input#username",
                    "data_test": "username-input",
                    "id": "username",
                    "role": "textbox",
                    "computed_role": "textbox",
                    "text": "",
                    "tag": "input",
                },
            ],
        }
        result = orchestrator._pass2_structural_match("FILL", "username input", pages_data)
        assert result is not None
        assert result["id"] == "username"

    def test_assert_with_tag_fallback(self) -> None:
        """ASSERT should match <h1> via tag fallback when no computed_role."""
        orchestrator = self._make_orchestrator()
        pages_data = {
            "http://example.com": [
                {
                    "selector": "button#checkout",
                    "data_test": "checkout-button",
                    "id": "checkout",
                    "role": "button",
                    "text": "Checkout",
                    "tag": "button",
                },
                {
                    "selector": "h1#page-title",
                    "data_test": "page-title",
                    "id": "page-title",
                    "role": "h1",
                    "text": "Checkout",
                    "tag": "h1",
                },
            ],
        }
        result = orchestrator._pass2_structural_match("ASSERT", "checkout page title", pages_data)
        assert result is not None
        assert result["id"] == "page-title"


# ---------------------------------------------------------------------------
# _pass1_assert_text_match with computed_role
# ---------------------------------------------------------------------------


class TestPass1AssertTextComputedRole:
    """Pass 1 ASSERT text match should use computed_role."""

    def _make_orchestrator(self) -> PlaceholderOrchestrator:
        return PlaceholderOrchestrator()

    def test_computed_role_text_matches(self) -> None:
        """Element with computed_role='text' and matching text should be found."""
        orchestrator = self._make_orchestrator()
        pages_data = {
            "http://example.com": [
                {
                    "selector": "div#msg",
                    "data_test": "message",
                    "computed_role": "text",
                    "role": "div",
                    "text": "order confirmation message",
                    "tag": "div",
                },
            ],
        }
        result = orchestrator._pass1_assert_text_match("ASSERT", "order confirmation message visible", pages_data)
        assert result is not None
        assert result["selector"] == "div#msg"

    def test_computed_role_button_excluded(self) -> None:
        """Element with computed_role='button' should be excluded from ASSERT text match."""
        orchestrator = self._make_orchestrator()
        pages_data = {
            "http://example.com": [
                {
                    "selector": "button#login",
                    "computed_role": "button",
                    "role": "button",
                    "text": "order confirmation",
                    "tag": "button",
                },
            ],
        }
        result = orchestrator._pass1_assert_text_match("ASSERT", "order confirmation", pages_data)
        assert result is None

    def test_raw_role_fallback_still_works(self) -> None:
        """Element with raw role='heading' (no computed_role) should still match."""
        orchestrator = self._make_orchestrator()
        pages_data = {
            "http://example.com": [
                {
                    "selector": "h1#title",
                    "role": "heading",
                    "text": "Welcome message",
                    "tag": "h1",
                },
            ],
        }
        result = orchestrator._pass1_assert_text_match("ASSERT", "welcome message visible", pages_data)
        assert result is not None
