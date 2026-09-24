"""B-086 — document-level (`<head>`) criteria must be checked against the real element.

Measured defect (Session 7, 2026-09-24): the scraper never collects `<meta>`,
`<link>` or `<title>` (`src/scraper.py` collects interactive tags, display tags
and elements with an id), so a criterion about them resolved to the nearest
*visible* element and the emitted assertion was weakened to something that
element could satisfy. The canonical-URL test "passed" by asserting the
visibility of a styled div — a green that checked nothing.

These tests pin the fix: a document-level criterion emits an attribute read
against a deterministic head selector, and never `assert_visible`.
"""

from __future__ import annotations

import pytest

from src.code_postprocessor import (
    DocumentAssertion,
    document_assertion_from_description,
    replace_token_in_line,
)

# Descriptions taken verbatim from the Session 7 run's emitted test file.
SESSION7_CASES = [
    ("meta description non-empty", 'meta[name="description"]', "content"),
    ("canonical URL declared", 'link[rel="canonical"]', "href"),
    ("favicon link resolves", 'link[rel="icon"]', "href"),
    ("Open Graph title declared", 'meta[property="og:title"]', "content"),
    ("Open Graph image declared", 'meta[property="og:image"]', "content"),
    ("twitter card declared", 'meta[name="twitter:card"]', "content"),
    ("viewport meta non-empty", 'meta[name="viewport"]', "content"),
    ("html lang attribute set", "html", "lang"),
]

# Descriptions that must NOT be treated as document-level.
ORDINARY_CASES = [
    "hero headline visible on load",
    "How It Works section heading reads Story to Export",
    "Buy Pro link resolves to a live purchase URL",
    "Watch 3-Min Walkthrough button resolves to a live video URL",
    "no TBD in links",
    "all images have alt",
    "Copy Command button is present",
    "pricing section heading reads Per deployment not per seat",
]


@pytest.mark.parametrize(("description", "selector", "attribute"), SESSION7_CASES)
def test_document_target_mapped(description: str, selector: str, attribute: str) -> None:
    check = document_assertion_from_description(description)
    assert check == DocumentAssertion(selector=selector, attribute=attribute)


@pytest.mark.parametrize("description", ORDINARY_CASES)
def test_ordinary_criterion_is_not_document_level(description: str) -> None:
    assert document_assertion_from_description(description) is None


def test_open_graph_variants_do_not_cross_match() -> None:
    """og:title and og:image are distinct targets, not one 'open graph' bucket."""
    title = document_assertion_from_description("Open Graph title declared")
    image = document_assertion_from_description("Open Graph image declared")
    assert title is not None and title.selector == 'meta[property="og:title"]'
    assert image is not None and image.selector == 'meta[property="og:image"]'


def test_emit_uses_head_selector_not_the_wrong_visible_element() -> None:
    """The Session 7 regression: a visible lookalike was resolved instead.

    The resolver handed the emitter the hero paragraph; the emitted line must
    ignore it and read the real `<meta>` instead.
    """
    desc = "meta description non-empty"
    token = "{{ASSERT:meta description non-empty}}"
    wrong_element = ".leading-relaxed.mt-4.text-slate-400.text-sm"
    out = replace_token_in_line(
        f"    {token}",
        "ASSERT",
        token,
        repr(wrong_element),
        set(),
        desc,
        assertion_type="toHaveAttribute:content",
    )
    assert out.strip() == (
        f"evidence_tracker.assert_attribute('meta[name=\"description\"]', 'content', label={desc!r})"
    )
    assert wrong_element not in out
    assert "assert_visible" not in out


def test_emit_canonical_url_uses_link_rel_canonical() -> None:
    desc = "canonical URL declared"
    token = "{{ASSERT:canonical URL declared}}"
    # Session 7 emitted assert_visible() on this class blob — the false green.
    false_green_selector = ".border-slate-800\\/80.border-t.font-mono.mt-6.pt-4.text-\\[11px\\].text-amber-400\\/90"
    out = replace_token_in_line(f"    {token}", "ASSERT", token, repr(false_green_selector), set(), desc)
    assert out.strip() == (f"evidence_tracker.assert_attribute('link[rel=\"canonical\"]', 'href', label={desc!r})")
    assert "assert_visible" not in out


def test_emit_beats_an_unverified_skip() -> None:
    """A document target CAN be checked, so it must not be skipped.

    Resolution may classify the criterion as unverified (no scraped candidate).
    The document intercept runs first, so a real check wins over the skip.
    """
    desc = "favicon link resolves"
    token = "{{ASSERT:favicon link resolves}}"
    skip_value = f"pytest.skip(\"Assertion for '{desc}' could not be verified on this page\")"
    out = replace_token_in_line(f"    {token}", "ASSERT", token, skip_value, set(), desc)
    assert "pytest.skip" not in out
    assert "evidence_tracker.assert_attribute('link[rel=\"icon\"]', 'href'" in out


def test_emitted_line_compiles_for_every_document_target() -> None:
    """The emitted line must be valid Python — a syntax error kills the suite."""
    for description, _selector, _attribute in SESSION7_CASES:
        token = f"{{{{ASSERT:{description}}}}}"
        out = replace_token_in_line(f"    {token}", "ASSERT", token, "'.some-class'", set(), description)
        # The emitter returns an indented statement for a function body, so
        # compile it inside one rather than as a bare module-level line.
        compile(f"def _emitted() -> None:\n{out}\n", "<emitted>", "exec")


def test_click_action_is_unaffected() -> None:
    """Only ASSERT is intercepted — a CLICK is never rewritten to an attribute read."""
    desc = "canonical URL declared"
    token = "{{CLICK:canonical URL declared}}"
    out = replace_token_in_line(f"    {token}", "CLICK", token, "'a.link'", set(), desc)
    assert "assert_attribute" not in out
    assert "evidence_tracker.click(" in out
