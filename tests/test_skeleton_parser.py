"""Tests for skeleton parsing helpers."""

from src.pipeline_models import PageRequirement
from src.skeleton_parser import SkeletonParser


def test_parse_placeholders_extracts_all_supported_tags() -> None:
    parser = SkeletonParser()
    code = """
page.click({{CLICK:login_button}})
page.fill({{FILL:email_input}}, "a")
expect(page).to_have_url({{URL:dashboard}})
"""
    assert parser.parse_placeholders(code) == [
        ("CLICK", "login_button"),
        ("FILL", "email_input"),
        ("URL", "dashboard"),
    ]


def test_parse_pages_needed_extracts_urls_and_descriptions() -> None:
    parser = SkeletonParser()
    code = """
# PAGES_NEEDED:
# - https://example.com/ (home)
# - https://example.com/cart (cart page)
"""
    assert parser.parse_pages_needed(code) == [
        ("https://example.com/", "home"),
        ("https://example.com/cart", "cart page"),
    ]


def test_parse_page_requirements_returns_typed_records() -> None:
    parser = SkeletonParser()
    code = """
# PAGES_NEEDED:
# - https://example.com/ (home)
# - https://example.com/cart (cart page)
"""

    assert parser.parse_page_requirements(code) == [
        PageRequirement(url="https://example.com/", description="home"),
        PageRequirement(url="https://example.com/cart", description="cart page"),
    ]


def test_parse_placeholder_uses_tracks_lines_and_tokens() -> None:
    parser = SkeletonParser()
    code = """
def test_checkout(page):
    {{GOTO:home page}}
    {{CLICK:cart link}}
"""

    placeholder_uses = parser.parse_placeholder_uses(code)

    assert [placeholder.action for placeholder in placeholder_uses] == ["GOTO", "CLICK"]
    assert placeholder_uses[0].line_number == 3
    assert placeholder_uses[1].token == "{{CLICK:cart link}}"


def test_parse_test_journeys_extracts_tests_steps_and_page_objects() -> None:
    parser = SkeletonParser()
    code = """
from playwright.sync_api import Page

class ProductPage:
    pass

class CartPage:
    pass

def test_add_to_cart(page: Page):
    product_page = ProductPage(page)
    {{GOTO:home page}}
    {{CLICK:add to cart button}}
    cart_page = CartPage(page)
    {{ASSERT:cart summary}}

def test_checkout(page: Page):
    cart_page = CartPage(page)
    {{CLICK:checkout button}}
    {{URL:checkout page}}
"""

    journeys = parser.parse_test_journeys(code)

    assert [journey.test_name for journey in journeys] == ["test_add_to_cart", "test_checkout"]
    assert journeys[0].page_object_names == ["ProductPage", "CartPage"]
    assert [step.raw_line.strip() for step in journeys[0].steps[:4]] == [
        "product_page = ProductPage(page)",
        "{{GOTO:home page}}",
        "{{CLICK:add to cart button}}",
        "cart_page = CartPage(page)",
    ]
    assert [placeholder.action for placeholder in journeys[0].placeholders] == ["GOTO", "CLICK", "ASSERT"]
    assert journeys[1].steps[-1].placeholders[0].description == "checkout page"


def test_validate_skeleton_rejects_single_brace_placeholders() -> None:
    parser = SkeletonParser()
    code = """
def test_checkout(page):
    {GOTO:Product Page URL}
"""
    error = parser.validate_skeleton(code)
    assert error is not None
    assert "single-brace placeholders" in error


def test_single_to_double_brace_converts_single_to_double() -> None:
    # Single-brace placeholders should be converted to double-brace.
    code = 'page.click({CLICK:login_button})\npage.fill({FILL:email}, "a")'
    result = SkeletonParser._single_to_double_brace(code)
    assert result == 'page.click({{CLICK:login_button}})\npage.fill({{FILL:email}}, "a")'


def test_single_to_double_brace_ignores_already_double_braced() -> None:
    # Double-brace placeholders should not be modified.
    code = "page.click({{CLICK:login_button}})"
    result = SkeletonParser._single_to_double_brace(code)
    assert result == "page.click({{CLICK:login_button}})"


def test_single_to_double_brace_ignores_non_placeholder_braces() -> None:
    # Regular single braces that are not placeholders should not be modified.
    code = 'x = {key: "value"}'
    result = SkeletonParser._single_to_double_brace(code)
    assert result == 'x = {key: "value"}'


def test_normalise_placeholder_actions_handles_single_brace_input() -> None:
    # When the LLM emits single-brace placeholders, normalise_placeholder_actions
    # should convert them to double-brace before rewriting action synonyms.
    code = "page.click({ADD:login_button})\npage.click({CLICK:login_button})"
    result = SkeletonParser.normalise_placeholder_actions(code)
    # Both should become double-brace CLICK placeholders.
    assert "{{CLICK:login_button}}" in result
    assert "{{CLICK:login_button}}" in result  # Both lines produce CLICK


def test_validate_skeleton_rejects_non_url_pages_needed_entries() -> None:
    parser = SkeletonParser()
    code = """
# PAGES_NEEDED:
# - {URL:Product Page}
"""
    error = parser.validate_skeleton(code)
    assert error is not None
    assert "single-brace placeholders" in error or "invalid page entries" in error
