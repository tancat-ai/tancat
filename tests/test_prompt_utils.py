"""Unit tests for prompt utilities."""

from __future__ import annotations

from src.prompt_utils import (
    build_page_context_prompt_block,
    get_skeleton_prompt_template,
    get_streamlit_system_prompt_template,
)


def test_streamlit_prompt_contains_placeholders() -> None:
    """Template should contain expected placeholders."""
    template = get_streamlit_system_prompt_template()
    assert "{user_story}" in template
    assert "{conditions}" in template
    assert "{count}" in template


def test_streamlit_prompt_mentions_pytest_and_sync() -> None:
    """Template should instruct pytest sync Playwright usage."""
    template = get_streamlit_system_prompt_template().lower()
    assert "pytest format" in template
    assert "sync api" in template or "sync" in template
    assert "async/await" in template


def test_streamlit_prompt_mentions_page_context_rules() -> None:
    """Template should include PAGE CONTEXT locator constraints."""
    template = get_streamlit_system_prompt_template()
    assert "PAGE CONTEXT" in template
    assert "constraints" in template.lower()


def test_streamlit_prompt_enforces_test_isolation() -> None:
    """Template must instruct the LLM that each test runs in a fresh browser context."""
    template = get_streamlit_system_prompt_template()
    assert "FRESH browser context" in template
    assert "fresh" in template.lower()


def test_streamlit_prompt_format_resolves_without_error() -> None:
    """Calling .format() with the three expected keys must not raise KeyError."""
    template = get_streamlit_system_prompt_template()
    rendered = template.format(user_story="story", conditions="- do thing", count=3)
    assert "story" in rendered
    assert "do thing" in rendered


def test_skeleton_prompt_format_resolves_without_error() -> None:
    """Skeleton prompt should render cleanly without PAGES_NEEDED (pages discovered by journey scraper)."""
    rendered = get_skeleton_prompt_template()
    assert "PAGES_NEEDED" not in rendered  # Removed per FEATURE_SPEC_remove_pages_needed
    assert "{{GOTO:page keyword}}" in rendered


def test_skeleton_prompt_includes_count_header() -> None:
    """Skeleton prompt should inject EXACTLY N test functions instruction when expected_count is provided."""
    rendered = get_skeleton_prompt_template(expected_count=6)
    assert "EXACTLY 6" in rendered


def test_skeleton_prompt_without_count_has_fallback() -> None:
    """Skeleton prompt should fall back to 'N' when expected_count is not provided."""
    rendered = get_skeleton_prompt_template(expected_count=None).format(
        user_story="Test story",
        conditions="Test conditions",
        known_urls_block="Test URLs",
    )
    assert "EXACTLY N" in rendered


def test_build_page_context_prompt_block_extracts_approved_locators() -> None:
    """Prompt block should include extracted locator allowlist."""
    page_context = """
=== PAGE CONTEXT ===
[input] id="user-name" → page.locator("#user-name")
[a] data-testid="shopping-cart-link" → page.get_by_test_id("shopping-cart-link")
"""
    prompt_block = build_page_context_prompt_block(page_context)
    assert "APPROVED LOCATORS" in prompt_block
    assert 'page.locator("#user-name")' in prompt_block
    assert 'page.get_by_test_id("shopping-cart-link")' in prompt_block


def test_build_page_context_prompt_block_handles_empty_context() -> None:
    """Empty context should produce fallback message."""
    prompt_block = build_page_context_prompt_block("")
    assert "No PAGE CONTEXT is available" in prompt_block


def test_build_page_context_prompt_block_truncates_large_context() -> None:
    """Large page-context payloads should be truncated to keep prompt size bounded."""
    large_context = "X" * 10000
    _prompt_block = build_page_context_prompt_block(large_context)
    # Truncation happens at 15000 chars, so 10000 chars won't trigger it
    # Use larger context to test truncation
    large_context2 = "X" * 20000
    prompt_block2 = build_page_context_prompt_block(large_context2)
    assert "truncated" in prompt_block2


def test_build_page_context_prompt_block_allows_more_than_25_locators() -> None:
    """Large pages should include substantially more than 25 approved locators."""
    locator_lines = [f'[button] visible="Buy {i}" → page.get_by_test_id("buy-{i}")' for i in range(40)]
    prompt_block = build_page_context_prompt_block("\n".join(locator_lines))
    # All locators should be present since we pass through the raw context
    assert prompt_block.count('page.get_by_test_id("buy-') >= 30


def test_prompt_rules_are_site_agnostic() -> None:
    """Prompt templates should not include site-specific brand/domain rules."""
    template = get_streamlit_system_prompt_template().lower()
    prompt_block = build_page_context_prompt_block('=== PAGE CONTEXT ===\n[input] id="x" → page.locator("#x")').lower()
    assert "saucedemo" not in template
    assert "saucedemo" not in prompt_block
