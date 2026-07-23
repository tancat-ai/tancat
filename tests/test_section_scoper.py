"""Unit tests for src/section_scoper.py — section detection and element scoping."""

from __future__ import annotations

from typing import Any

from src.section_scoper import (
    Section,
    _extract_section_hint,
    _match_section_hint,
    _normalise_name,
    build_element_to_section_map,
    detect_sections,
    scope_elements,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_element(
    text: str,
    role: str,
    idx: int,
    visible: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build a minimal element dict."""
    return {
        "text": text,
        "role": role,
        "_element_box_index": idx,
        "is_visible": visible,
        "selector": f"#el-{idx}",
        **kwargs,
    }


# ---------------------------------------------------------------------------
# _normalise_name
# ---------------------------------------------------------------------------


class TestNormaliseName:
    def test_plain(self) -> None:
        assert _normalise_name("Hello World") == "hello world"

    def test_strips_emoji(self) -> None:
        assert _normalise_name("🚗 Car Insurance") == "car insurance"

    def test_collapses_whitespace(self) -> None:
        assert _normalise_name("  Hello   World  ") == "hello world"

    def test_empty(self) -> None:
        assert _normalise_name("") == ""


# ---------------------------------------------------------------------------
# _extract_section_hint
# ---------------------------------------------------------------------------


class TestExtractSectionHint:
    def test_on_page(self) -> None:
        hint = _extract_section_hint("Next button on account page")
        assert hint == "account"

    def test_in_section(self) -> None:
        hint = _extract_section_hint("Select dropdown in drivers section")
        assert hint == "drivers"

    def test_under_section(self) -> None:
        hint = _extract_section_hint("Input field under vehicles section")
        assert hint == "vehicles"

    def test_in_the_section(self) -> None:
        hint = _extract_section_hint("Button in the quote section")
        assert hint == "quote"

    def test_on_the_page(self) -> None:
        hint = _extract_section_hint("Link on the home page")
        assert hint == "home"

    def test_no_hint(self) -> None:
        hint = _extract_section_hint("Submit button")
        assert hint is None

    def test_multi_word_hint(self) -> None:
        hint = _extract_section_hint("Field on policy details page")
        assert hint == "policy details"


# ---------------------------------------------------------------------------
# _match_section_hint
# ---------------------------------------------------------------------------


class TestMatchSectionHint:
    def test_exact_match(self) -> None:
        sections = [Section(name="Account", heading_role="h2", heading_index=0, element_indices=[1])]
        assert _match_section_hint("account", sections) == "Account"

    def test_substring_match(self) -> None:
        sections = [Section(name="Create Your Account", heading_role="h2", heading_index=0, element_indices=[1])]
        assert _match_section_hint("account", sections) == "Create Your Account"

    def test_no_match(self) -> None:
        sections = [Section(name="Drivers", heading_role="h2", heading_index=0, element_indices=[1])]
        assert _match_section_hint("account", sections) is None

    def test_emoji_stripped(self) -> None:
        sections = [Section(name="🚗 Car Insurance", heading_role="h4", heading_index=0, element_indices=[1])]
        assert _match_section_hint("car insurance", sections) == "🚗 Car Insurance"

    def test_word_overlap(self) -> None:
        sections = [Section(name="Policy Details", heading_role="h2", heading_index=0, element_indices=[1])]
        assert _match_section_hint("policy", sections) == "Policy Details"

    def test_empty_hint(self) -> None:
        assert _match_section_hint("", []) is None


# ---------------------------------------------------------------------------
# detect_sections
# ---------------------------------------------------------------------------


class TestDetectSections:
    def test_basic(self) -> None:
        elements = [
            _make_element("Nav link", "link", 1),
            _make_element("Main Title", "h1", 10),
            _make_element("Input 1", "textbox", 11),
            _make_element("Input 2", "textbox", 12),
            _make_element("Section B", "h2", 20),
            _make_element("Button 1", "button", 21),
        ]
        sections = detect_sections(elements)
        assert len(sections) == 2
        # Nav link (idx=1) is before first heading but assigned to it
        assert sections[0].name == "Main Title"
        assert sections[0].heading_role == "h1"
        assert 1 in sections[0].element_indices  # pre-heading nav
        assert 11 in sections[0].element_indices
        assert 12 in sections[0].element_indices
        assert sections[1].name == "Section B"
        assert sections[1].heading_role == "h2"
        assert 21 in sections[1].element_indices

    def test_pre_heading_elements_assigned_to_first_heading(self) -> None:
        # Elements before the first heading go to that heading
        # (not a synthetic section) — SPA forms often have inputs before headings.
        elements = [
            _make_element("Nav", "link", 1),
            _make_element("Logo", "img", 2),
            _make_element("Title", "h1", 10),
            _make_element("Content", "paragraph", 11),
        ]
        sections = detect_sections(elements)
        assert len(sections) == 1
        assert sections[0].name == "Title"
        # Nav and Logo (indices 1, 2) are before the heading but assigned to it
        assert 1 in sections[0].element_indices
        assert 2 in sections[0].element_indices
        assert 11 in sections[0].element_indices

    def test_h4_not_boundary(self) -> None:
        elements = [
            _make_element("Main", "h1", 10),
            _make_element("Sub", "h4", 11),
            _make_element("Content", "paragraph", 12),
        ]
        sections = detect_sections(elements)
        # h4 is not a boundary — elements go under h1
        assert len(sections) == 1
        assert sections[0].name == "Main"

    def test_no_headings(self) -> None:
        elements = [
            _make_element("A", "button", 1),
            _make_element("B", "button", 2),
        ]
        assert detect_sections(elements) == []

    def test_empty(self) -> None:
        assert detect_sections([]) == []

    def test_element_assignment(self) -> None:
        elements = [
            _make_element("Title", "h1", 10),
            _make_element("A", "button", 11),
            _make_element("B", "textbox", 12),
            _make_element("Section 2", "h2", 20),
            _make_element("C", "button", 21),
        ]
        sections = detect_sections(elements)
        # Find sections by name
        by_name = {s.name: s for s in sections}
        assert 11 in by_name["Title"].element_indices
        assert 12 in by_name["Title"].element_indices
        assert 21 in by_name["Section 2"].element_indices

    def test_heading_not_in_children(self) -> None:
        elements = [
            _make_element("Title", "h1", 10),
            _make_element("Content", "p", 11),
        ]
        sections = detect_sections(elements)
        assert 10 not in sections[0].element_indices  # heading itself is not a child


# ---------------------------------------------------------------------------
# scope_elements
# ---------------------------------------------------------------------------


class TestScopeElements:
    def test_scopes_to_section(self) -> None:
        elements = [
            _make_element("Title A", "h2", 10),
            _make_element("Button A", "button", 11),
            _make_element("Button A2", "button", 12),
            _make_element("Title B", "h2", 20),
            _make_element("Button B", "button", 21),
        ]
        scoped, section_name = scope_elements("Next button on title a page", elements)
        assert section_name == "Title A"
        # Should have heading + 2 buttons from section A
        assert len(scoped) == 3
        assert all(e["_element_box_index"] in {10, 11, 12} for e in scoped)

    def test_no_hint_returns_all(self) -> None:
        elements = [
            _make_element("A", "h2", 10),
            _make_element("B", "button", 11),
        ]
        scoped, section_name = scope_elements("Submit button", elements)
        assert section_name is None
        assert len(scoped) == len(elements)

    def test_no_headings_returns_all(self) -> None:
        elements = [
            _make_element("A", "button", 1),
            _make_element("B", "button", 2),
        ]
        scoped, section_name = scope_elements("Button on account page", elements)
        assert section_name is None
        assert len(scoped) == len(elements)

    def test_hint_no_match_returns_all(self) -> None:
        elements = [
            _make_element("Drivers", "h2", 10),
            _make_element("A", "button", 11),
        ]
        scoped, section_name = scope_elements("Button on checkout page", elements)
        assert section_name is None
        assert len(scoped) == len(elements)

    def test_in_section_pattern(self) -> None:
        elements = [
            _make_element("Drivers", "h2", 10),
            _make_element("Input", "textbox", 11),
            _make_element("Vehicles", "h2", 20),
            _make_element("Input 2", "textbox", 21),
        ]
        scoped, section_name = scope_elements("Field in drivers section", elements)
        assert section_name == "Drivers"
        assert len(scoped) == 2

    def test_empty_elements(self) -> None:
        scoped, section_name = scope_elements("Button on page", [])
        assert scoped == []
        assert section_name is None


# ---------------------------------------------------------------------------
# build_element_to_section_map
# ---------------------------------------------------------------------------


class TestBuildElementToSectionMap:
    def test_basic(self) -> None:
        elements = [
            _make_element("Account", "h2", 10),
            _make_element("A", "button", 11),
            _make_element("Drivers", "h2", 20),
            _make_element("B", "button", 21),
        ]
        mapping = build_element_to_section_map(elements)
        assert mapping[10] == "Account"
        assert mapping[11] == "Account"
        assert mapping[20] == "Drivers"
        assert mapping[21] == "Drivers"

    def test_no_sections(self) -> None:
        elements = [
            _make_element("A", "button", 1),
        ]
        assert build_element_to_section_map(elements) == {}


# ---------------------------------------------------------------------------
# Integration: LV Insurance-style data
# ---------------------------------------------------------------------------


class TestLVInsuranceStyle:
    def _build_lv_elements(self) -> list[dict[str, Any]]:
        """Build a minimal LV-style element set with sections.

        Indices follow heading-then-children ordering: heading at N, children at N+1.."""
        return [
            _make_element("Create Your Account", "h2", 10, visible=True, selector="h2-account"),
            _make_element("Email", "textbox", 11, visible=True, selector="#email"),
            _make_element("Password", "textbox", 12, visible=True, selector="#password"),
            _make_element("Next →", "button", 13, visible=True, selector="#accountNext"),
            _make_element("Error", "text", 14, visible=False, selector="#accountError"),
            _make_element("Select a Product", "h2", 20, visible=True, selector="h2-product"),
            _make_element("← Back", "button", 21, visible=False, selector="#productBack"),
            _make_element("Next →", "button", 22, visible=False, selector="#productNext"),
            _make_element("Policy Details", "h2", 30, visible=True, selector="h2-policy"),
            _make_element("← Back", "button", 31, visible=False, selector="#policyBack"),
            _make_element("Next →", "button", 32, visible=False, selector="#policyNext"),
            _make_element("Drivers", "h2", 40, visible=True, selector="h2-drivers"),
            _make_element("← Back", "button", 41, visible=False, selector="#driversBack"),
            _make_element("Next →", "button", 42, visible=False, selector="#driversNext"),
            _make_element("Vehicles", "h2", 50, visible=True, selector="h2-vehicles"),
            _make_element("← Back", "button", 51, visible=False, selector="#vehiclesBack"),
            _make_element("Next →", "button", 52, visible=False, selector="#vehiclesNext"),
        ]

    def test_detects_sections(self) -> None:
        elements = self._build_lv_elements()
        sections = detect_sections(elements)
        names = [s.name for s in sections]
        assert "Create Your Account" in names
        assert "Drivers" in names
        assert "Vehicles" in names

    def test_scopes_next_button_on_account_page(self) -> None:
        elements = self._build_lv_elements()
        scoped, section_name = scope_elements(
            "Next button on account page",
            elements,
        )
        # Should find the account section
        assert section_name is not None
        # All scoped elements should be from the account section
        selectors = {e["selector"] for e in scoped}
        assert "#accountNext" in selectors
        # Should NOT contain buttons from other sections
        assert "#productNext" not in selectors
        assert "#driversNext" not in selectors

    def test_scopes_back_button_on_drivers_section(self) -> None:
        elements = self._build_lv_elements()
        scoped, section_name = scope_elements(
            "Back button in drivers section",
            elements,
        )
        assert section_name == "Drivers"
        selectors = {e["selector"] for e in scoped}
        assert "#driversBack" in selectors
        assert "#productBack" not in selectors

    def test_no_section_hint_returns_all_elements(self) -> None:
        elements = self._build_lv_elements()
        scoped, section_name = scope_elements("Submit button", elements)
        assert section_name is None
        assert len(scoped) == len(elements)
