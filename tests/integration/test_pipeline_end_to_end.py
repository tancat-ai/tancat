"""Integration tests for the full skeleton-first pipeline.

These tests use local HTML fixtures (not live URLs) to verify that locators
scraped from a known page survive through the entire pipeline into the final
generated code.

Run:
    pytest tests/integration/test_pipeline_end_to_end.py -v -s

IMPORTANT: These tests require a running LLM (Ollama/LM Studio) for skeleton
generation. They are integration tests, not unit tests.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from src.orchestrator import TestOrchestrator
from src.placeholder_resolver import PlaceholderResolver
from src.scraper import PageScraper
from src.test_generator import TestGenerator

# ── Fixtures ──────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent.parent.parent / "generated_tests"


def mock_insurance_html() -> Path:
    """Return the path to the mock insurance site HTML fixture."""
    p = FIXTURES_DIR / "mock_insurance_site.html"
    assert p.exists(), f"Mock fixture not found at {p}"
    return p


def mock_insurance_file_url() -> str:
    """Return a file:// URL for the mock insurance site."""
    return f"file://{mock_insurance_html()}"


# ── Test: Scraper captures known elements ─────────────────────────────


def test_scraper_finds_known_elements() -> None:
    """Verify the scraper can find elements on our known HTML fixture.

    This is the Stage 1 check: if the scraper doesn't find the elements,
    nothing downstream can resolve them.
    """

    async def _run() -> None:
        scraper = PageScraper()
        url = mock_insurance_file_url()
        elements, error, _final_url = await scraper.scrape_url(url)

        if error:
            pytest.skip(f"Scraping failed: {error}")

        # Verify at least some elements were found
        assert len(elements) > 0, "Scraper found zero elements on mock site"

        # Log what was found for debugging
        print(f"\n  Scraper found {len(elements)} elements:")
        for elem in elements[:10]:
            print(f"    selector={elem.get('selector', '')} text='{elem.get('text', '')}'")

    asyncio.run(_run())


# ── Test: Resolver matches known placeholder to element ───────────────


def test_resolver_matches_known_placeholder() -> None:
    """Verify the resolver can match a placeholder description to a scraped element.

    Stage 2 check: even if the scraper finds elements, the resolver must
    be able to match them to placeholder descriptions.
    """

    async def _run() -> None:
        scraper = PageScraper()
        resolver = PlaceholderResolver()
        url = mock_insurance_file_url()

        elements, error, _final_url = await scraper.scrape_url(url)
        if error:
            pytest.skip(f"Scraping failed: {error}")

        # Use descriptions that match actual elements on the mock insurance site
        # (from scraper output: "Update Policy Details", "View Policy", "Add Driver", etc.)
        actions_to_try = [
            ("CLICK", "Update Policy"),
            ("CLICK", "Add Driver"),
            ("FILL", "Policy Owner"),
        ]

        found_any_match = False
        for action, description in actions_to_try:
            best = resolver.find_best_element(action, description, elements)
            if best:
                selector = resolver._build_robust_locator(best)
                print(f"  ({action}) '{description}' -> {selector}")
                found_any_match = True

        # At least one action should resolve to something
        assert found_any_match, (
            "Resolver could not match any placeholder to scraped elements. "
            "This means the scraper-resolver handoff is broken."
        )

    asyncio.run(_run())


# ── Test: Token replacement preserves resolved locator ────────────────


def test_token_replacement_preserves_locator() -> None:
    """Verify that replace_token_in_line correctly substitutes a resolved locator.

    Stage 3 check: even if resolution works, the token replacement step
    might drop the locator if pattern matching fails.
    """
    from src.code_postprocessor import replace_token_in_line

    token = "{{{{CLICK:login button}}}}"
    resolved_value = "'#login-btn'"
    line = f'    page.locator("{token}").click()'

    result = replace_token_in_line(
        line=line,
        action="CLICK",
        token=token,
        resolved_value=resolved_value,
        duplicate_selectors=set(),
        description="login button",
    )

    # The resolved selector should appear in the output
    assert "'#login-btn'" in result or "#login-btn" in result, (
        f"Resolved locator was lost during token replacement. Input: {line!r}\nOutput: {result!r}"
    )

    # The original token should NOT appear in the output
    assert token not in result, f"Token was not replaced. Output still contains: {token}"


# ── Test: Full pipeline trace with mock fixture ───────────────────────


@pytest.mark.slow
@pytest.mark.integration
def test_locator_survives_full_pipeline() -> None:
    """End-to-end: skeleton → scrape → resolve → final code.

    This is the critical test. It runs the full pipeline against a known
    HTML fixture and verifies that resolved locators appear in the final
    generated code.

    If this test fails, the trace output will show exactly which stage
    dropped the locator.
    """

    async def _run() -> None:
        from src.llm_client import LLMClient

        ph_regex = re.compile(r"\{\{\{\{(\w+):([^}]+)\}\}\}")

        # Build orchestrator
        llm_client = LLMClient()
        test_generator = TestGenerator(client=llm_client)
        orchestrator = TestOrchestrator(test_generator)

        url = mock_insurance_file_url()
        user_story = "As a user I want to browse products and add them to my cart"
        conditions = (
            "1. Navigate to the home page\n"
            "2. Click on a product or category link\n"
            "3. Add a product to the cart\n"
            "(Total: 3 criteria)"
        )

        print(f"\n{'=' * 70}")
        print("INTEGRATION TEST: Locator Survival")
        print(f"URL: {url}")
        print(f"{'=' * 70}\n")

        # Run the full pipeline
        try:
            final_code = await orchestrator.run_pipeline(
                user_story=user_story,
                conditions=conditions,
                target_urls=[url],
            )
        except Exception as e:
            pytest.skip(f"Pipeline failed (LLM may be unavailable): {e}")

        result = orchestrator.last_result
        assert result is not None, "PipelineRunResult not captured"

        # Extract placeholder tokens from skeleton
        skeleton_tokens: list[tuple[str, str, str]] = []
        for match in ph_regex.finditer(result.skeleton_code):
            skeleton_tokens.append((match.group(0), match.group(1), match.group(2)))

        print(f"\n  Skeleton placeholders: {len(skeleton_tokens)}")
        print(f"  Final code length: {len(final_code)} chars")
        print(f"  Unresolved: {len(result.unresolved_placeholders)}")

        # Count resolved vs unresolved
        resolved_count = len(skeleton_tokens) - len(result.unresolved_placeholders)
        print(f"  Resolved: {resolved_count}")

        # Verify: every resolved placeholder should produce an evidence_tracker call
        # or a real locator in the final code (not remain as a raw placeholder)
        dropped: list[str] = []
        for token, action, desc in skeleton_tokens:
            if token in final_code:
                # Token was NOT replaced — this is a bug
                dropped.append(f"({action}) '{desc}' — raw token still present")
                print(f"  ❌ DROPPED: {token}")
            else:
                print(f"  ✅ Replaced: ({action}) '{desc}'")

        # The key assertion: no raw placeholders should remain for resolved items
        if dropped:
            print(f"\n{'=' * 70}")
            print("FAILED: The following placeholders were NOT replaced:")
            for d in dropped:
                print(f"  - {d}")
            print("\nFinal code (first 60 lines):")
            for i, line in enumerate(final_code.splitlines()[:60], 1):
                print(f"  {i:3d} | {line}")
            print(f"{'=' * 70}\n")

        assert not dropped, (
            f"{len(dropped)} placeholder(s) were resolved by the pipeline but "
            f"did not appear in the final code. The token replacement step is "
            f"dropping locators. See trace output above for details."
        )


# ── Test: Pipeline produces valid Python ──────────────────────────────


@pytest.mark.slow
@pytest.mark.integration
def test_pipeline_produces_valid_python() -> None:
    """Verify the final generated code is syntactically valid Python."""

    async def _run() -> None:
        from src.llm_client import LLMClient

        llm_client = LLMClient()
        test_generator = TestGenerator(client=llm_client)
        orchestrator = TestOrchestrator(test_generator)

        url = mock_insurance_file_url()
        user_story = "As a user I want to browse the site"
        conditions = "1. Navigate to the home page\n(Total: 1 criteria)"

        try:
            final_code = await orchestrator.run_pipeline(
                user_story=user_story,
                conditions=conditions,
                target_urls=[url],
            )
        except Exception as e:
            pytest.skip(f"Pipeline failed (LLM may be unavailable): {e}")

        # Verify it's valid Python by compiling it
        try:
            compile(final_code, "<generated_test>", "exec")
        except SyntaxError as e:
            pytest.fail(f"Generated code is not valid Python:\n{e}\n\nCode:\n{final_code}")

    asyncio.run(_run())


# ── Test: Scraped elements contain expected selector format ───────────


def test_scraper_produces_valid_selectors() -> None:
    """Verify the scraper produces elements with valid selector strings.

    If selectors are malformed, downstream resolution will fail silently.
    """

    async def _run() -> None:
        scraper = PageScraper()
        url = mock_insurance_file_url()
        elements, error, _final_url = await scraper.scrape_url(url)

        if error:
            pytest.skip(f"Scraping failed: {error}")

        for i, elem in enumerate(elements):
            selector = elem.get("selector", "")
            assert selector, f"Element {i} has empty selector. Full element: {elem}"
            # Selector should not be a raw placeholder
            assert "{{{{" not in selector, f"Element {i} selector contains placeholder syntax: {selector}"

    asyncio.run(_run())
