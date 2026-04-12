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
    assert (
        "LOCATORS LISTED IN THE PAGE CONTEXT ABOVE" in template or "NEVER invent, guess, or create locators" in template
    )
    assert "page.goto" in template or "navigation" in template


def test_streamlit_prompt_enforces_test_isolation() -> None:
    """Template must instruct the LLM that each test runs in a fresh browser context.

    This prevents the LLM from generating tests that assume state from previous
    test functions (e.g. assuming a login from test_01 persists into test_02).
    """
    template = get_streamlit_system_prompt_template()
    assert "FRESH browser context" in template
    assert "login" in template.lower()
    assert "fresh" in template.lower()


def test_streamlit_prompt_format_resolves_without_error() -> None:
    """Calling .format() with the three expected keys must not raise KeyError.

    Guards against accidental bare braces introduced into the template constants
    that would cause a runtime crash when the prompt is rendered.
    """
    template = get_streamlit_system_prompt_template()
    rendered = template.format(user_story="story", conditions="- do thing", count=3)
    assert "story" in rendered
    assert "do thing" in rendered


def test_skeleton_prompt_format_resolves_without_error() -> None:
    """Skeleton prompt should render cleanly with escaped placeholder examples."""
    template = get_skeleton_prompt_template()
    rendered = template.format(
        user_story="story",
        conditions="1. Add to cart",
        known_urls_block="- https://example.com/",
    )
    assert "{{CLICK:cart link}}" in rendered
    assert "https://example.com/" in rendered


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
    """Empty context should produce fallback generation instructions."""
    prompt_block = build_page_context_prompt_block("")
    assert "No context available" in prompt_block
    assert "No PAGE CONTEXT is available" in prompt_block


def test_build_page_context_prompt_block_truncates_large_context() -> None:
    """Large page-context payloads should be truncated to keep prompt size bounded."""
    large_context = "X" * 10000
    prompt_block = build_page_context_prompt_block(large_context)
    assert "NOTE: PAGE CONTEXT was truncated" in prompt_block


def test_build_page_context_prompt_block_allows_more_than_25_locators() -> None:
    """Large pages should include substantially more than 25 approved locators."""
    locator_lines = [f'[button] visible="Buy {i}" → page.get_by_test_id("buy-{i}")' for i in range(40)]
    prompt_block = build_page_context_prompt_block("\n".join(locator_lines))
    approved_count = prompt_block.count("- page.get_by_test_id(")
    assert approved_count >= 30


def test_prompt_rules_are_site_agnostic() -> None:
    """Prompt templates should not include site-specific brand/domain rules."""
    template = get_streamlit_system_prompt_template().lower()
    prompt_block = build_page_context_prompt_block('=== PAGE CONTEXT ===\n[input] id="x" → page.locator("#x")').lower()
    assert "saucedemo" not in template
    assert "saucedemo" not in prompt_block
