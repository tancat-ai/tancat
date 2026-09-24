"""B-088 — page-level and section-scoped criteria must check the real thing.

Session 7 (2026-09-24) left four reds on the 35-criterion landing-page story,
all a different root cause from B-086's `<head>` class:

- **24** "no link, button or heading anywhere contains placeholder text" — the
  skeleton decomposed it into "no TBD in hrefs" / "no TBD in visible copy" and
  the resolver mapped each to a *hero paragraph*, emitting ``assert_attribute``
  on an element with no href. Fixed by extending the page-level count
  classifier and the ``assert_no_forbidden`` tracker (multi-token + text).
- **22** "Security Policy link resolves" — the fast text pass returned a
  ``<span>`` that names the link, not the anchor. A link criterion must only
  resolve to an anchor.
- **16** "Watch 3-Min Walkthrough link resolves" — the named link no longer
  exists, so the resolver fell back to the nav-logo anchor. A named link that
  matches no anchor must skip honestly, not check a lookalike.
- **27** "the Air-Gap tier ... a contact link appears inside that tier" — the
  skeleton split it into two ``assert_visible`` heading checks. A
  section-containment criterion emits a scoped check instead.

B-087 is the mirror false red: "the hello@tancat.dev link is a mailto link"
emitted ``must_be_url=True`` and failed a correct page.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.code_postprocessor import (
    attribute_predicate,
    attribute_scheme,
    count_assertion_from_description,
    replace_token_in_line,
    section_contains_from_description,
)
from src.element_matcher import ElementMatcher
from src.evidence_tracker import EvidenceTracker
from src.link_scoping import (
    is_anchor,
    is_link_criterion,
    link_name_matches,
    link_name_tokens,
    scope_pages_to_links,
)
from src.placeholder_resolver import PlaceholderResolver

# ---------------------------------------------------------------------------
# Criterion 24 — page-level scans
# ---------------------------------------------------------------------------

# Descriptions taken verbatim from the Session 7 skeleton (package manifest).
SESSION7_SCANS = [
    ("no TBD in hrefs", "[href]", "tbd", "href"),
    ("no YOUR_VIDEO_ID_HERE in hrefs", "[href]", "your_video_id_here", "href"),
    ("no lorem ipsum in hrefs", "[href]", "lorem", "href"),
    ("no TBD in visible copy", "body", "tbd", None),
    ("no YOUR_VIDEO_ID_HERE in visible copy", "body", "your_video_id_here", None),
    ("no lorem ipsum in visible copy", "body", "lorem", None),
]

COMBINED = (
    "No link, button or heading anywhere on the page contains placeholder text — the strings "
    '"TBD", "YOUR_VIDEO_ID_HERE" and "lorem ipsum" appear in no href and in no visible copy'
)


@pytest.mark.parametrize(("description", "selector", "argument", "attribute"), SESSION7_SCANS)
def test_criterion_24_scan_classified(description: str, selector: str, argument: str, attribute: str | None) -> None:
    check = count_assertion_from_description(description)
    assert check is not None, f"not classified: {description!r}"
    assert (check.method, check.selector, check.argument, check.attribute) == (
        "assert_no_forbidden",
        selector,
        argument,
        attribute,
    )


def test_criterion_24_scan_emits_page_level_call() -> None:
    desc = "no TBD in hrefs"
    token = f"{{{{ASSERT:{desc}}}}}"
    out = replace_token_in_line(f"    {token}", "ASSERT", token, "p.hero", set(), desc)
    assert (
        out.strip()
        == "evidence_tracker.assert_no_forbidden('[href]', 'tbd', label='no TBD in hrefs', attribute='href')"
    )


def test_criterion_24_visible_copy_is_a_body_scan() -> None:
    desc = "no lorem ipsum in visible copy"
    token = f"{{{{ASSERT:{desc}}}}}"
    out = replace_token_in_line(f"    {token}", "ASSERT", token, "p.hero", set(), desc)
    assert (
        out.strip() == "evidence_tracker.assert_no_forbidden('body', 'lorem', label='no lorem ipsum in visible copy')"
    )


def test_criterion_24_combined_shape_carries_every_token_and_checks_text() -> None:
    check = count_assertion_from_description(COMBINED)
    assert check is not None
    assert check.selector == "a, button, h1, h2, h3, h4, h5, h6"
    assert check.tokens == ("TBD", "YOUR_VIDEO_ID_HERE", "lorem ipsum")
    assert check.attribute == "href"
    assert check.also_text is True
    token = f"{{{{ASSERT:{COMBINED}}}}}"
    out = replace_token_in_line(f"    {token}", "ASSERT", token, "p.hero", set(), COMBINED)
    assert "assert_no_forbidden(" in out
    assert "('TBD', 'YOUR_VIDEO_ID_HERE', 'lorem ipsum')" in out
    assert "also_text=True" in out
    assert "assert_visible" not in out


@pytest.mark.parametrize(
    "description",
    ["hero headline visible", "no horizontal scroll", "login button is visible", "no broken images"],
)
def test_non_scan_descriptions_are_untouched(description: str) -> None:
    assert count_assertion_from_description(description) is None


# ---------------------------------------------------------------------------
# EvidenceTracker — multi-token / text scan
# ---------------------------------------------------------------------------


def _element(attr_value: str | None = None, text: str | None = None) -> MagicMock:
    el = MagicMock()
    el.get_attribute.return_value = attr_value
    el.text_content.return_value = text
    return el


def _tracker(tmp_path: Any, elements: list[MagicMock]) -> EvidenceTracker:
    page = MagicMock()
    loc = MagicMock()
    loc.count.return_value = len(elements)
    loc.nth.side_effect = lambda i: elements[i]
    loc.first = elements[0] if elements else MagicMock()
    page.locator.return_value = loc
    page.url = "https://example.com"
    return EvidenceTracker(page, "test_b088", evidence_root=Path(tmp_path))


def test_multi_token_scan_finds_any_offender(tmp_path: Any) -> None:
    tracker = _tracker(tmp_path, [_element("https://x.com"), _element("https://x.com/l/YOUR_VIDEO_ID_HERE")])
    with pytest.raises(AssertionError, match="one of"):
        tracker.assert_no_forbidden("[href]", ("tbd", "your_video_id_here"), label="no placeholders", attribute="href")


def test_multi_token_scan_passes_when_clean(tmp_path: Any) -> None:
    tracker = _tracker(tmp_path, [_element("https://x.com"), _element("https://y.com")])
    tracker.assert_no_forbidden("[href]", ("tbd", "your_video_id_here"), label="no placeholders", attribute="href")
    assert tracker.steps[-1]["result"]["status"] == "passed"


def test_also_text_scans_visible_copy_too(tmp_path: Any) -> None:
    """A link whose href is clean but whose text says TBD is still an offender."""
    tracker = _tracker(tmp_path, [_element("https://x.com", "Buy now (TBD)")])
    with pytest.raises(AssertionError, match="tbd"):
        tracker.assert_no_forbidden("a", ("tbd",), label="no placeholder text", attribute="href", also_text=True)


# ---------------------------------------------------------------------------
# B-087 — scheme-naming criteria (mailto/tel)
# ---------------------------------------------------------------------------


def test_attribute_scheme_detects_mailto() -> None:
    assert attribute_scheme("hello@tancat.dev mailto link") == "mailto:"
    assert attribute_scheme("telephone link") == "tel:"
    assert attribute_scheme("Buy Pro link resolves") is None


def test_mailto_criterion_is_not_an_http_url_check() -> None:
    must_be_url, _forbidden = attribute_predicate("hello@tancat.dev mailto link", "href")
    assert must_be_url is False


def test_mailto_emit_uses_required_scheme() -> None:
    desc = "hello@tancat.dev mailto link"
    token = f"{{{{ASSERT:{desc}}}}}"
    out = replace_token_in_line(
        f"    {token}",
        "ASSERT",
        token,
        "'a[href^=\"mailto:\"]'",
        set(),
        desc,
        assertion_type="toHaveAttribute:href",
    )
    assert "required_scheme='mailto:'" in out
    assert "must_be_url=True" not in out


def test_assert_attribute_required_scheme_passes_for_mailto(tmp_path: Any) -> None:
    tracker = _tracker(tmp_path, [_element("mailto:hello@tancat.dev")])
    tracker.assert_attribute('a[href^="mailto:"]', "href", label="mailto link", required_scheme="mailto:")
    assert tracker.steps[-1]["result"]["status"] == "passed"


def test_assert_attribute_required_scheme_fails_for_http(tmp_path: Any) -> None:
    tracker = _tracker(tmp_path, [_element("https://github.com/tancat-ai/tancat")])
    with pytest.raises(AssertionError, match="does not start with 'mailto:'"):
        tracker.assert_attribute('a[href^="mailto:"]', "href", label="mailto link", required_scheme="mailto:")


# ---------------------------------------------------------------------------
# Link-criterion scoping
# ---------------------------------------------------------------------------


def test_is_link_criterion_for_resolution_shapes() -> None:
    assert is_link_criterion("Security Policy link resolves")
    assert is_link_criterion("Watch 3-Min Walkthrough link resolves")
    assert is_link_criterion("Watch 3-Min Walkthrough live video URL")
    assert is_link_criterion("GitHub link resolves to the correct URL")
    assert not is_link_criterion("no TBD in hrefs")
    assert not is_link_criterion("all anchor links valid")
    assert not is_link_criterion("hero headline visible")
    assert not is_link_criterion("Every header navigation link scrolls to a section")


def test_link_name_tokens_keep_the_link_name_only() -> None:
    assert link_name_tokens("Watch 3-Min Walkthrough link resolves") == ("watch", "3-min", "walkthrough")
    assert link_name_tokens("GitHub link resolves") == ("github",)


def test_is_anchor_accepts_links_and_rejects_lookalikes() -> None:
    assert is_anchor({"tag": "a", "text": "x"})
    assert is_anchor({"tag": "span", "role": "link"})
    assert is_anchor({"tag": "div", "selector": 'a[href="#"]'})
    assert not is_anchor({"tag": "span", "role": "span", "text": "Security Policy"})


def test_link_name_matches_requires_a_named_token() -> None:
    span = {"tag": "span", "text": "Security Policy", "selector": "div > span"}
    assert not link_name_matches("Watch 3-Min Walkthrough link resolves", span)
    anchor = {"tag": "a", "text": "Security Policy", "href": "https://x/SECURITY.md"}
    assert link_name_matches("Security Policy link resolves", anchor)


def test_scope_pages_to_links_drops_non_anchors() -> None:
    span = {"tag": "span", "role": "span", "text": "Security Policy"}
    anchor = {"tag": "a", "role": "a", "text": "Security Policy", "href": "https://x"}
    pages = {"https://x": [span, anchor]}
    scoped = scope_pages_to_links("ASSERT", "Security Policy link resolves", pages)
    assert scoped == {"https://x": [anchor]}
    # Non-link criteria are untouched.
    assert scope_pages_to_links("ASSERT", "hero headline visible", pages) == pages


# ---------------------------------------------------------------------------
# ElementMatcher integration — the Session 7 cases
# ---------------------------------------------------------------------------


def _matcher() -> ElementMatcher:
    return ElementMatcher(PlaceholderResolver())


def _resolve(matcher: ElementMatcher, description: str, pages: dict[str, list[dict[str, Any]]]) -> Any:
    return asyncio.run(
        matcher.find_best_element_for_current_page(
            action="ASSERT", description=description, current_url="https://x.test/", pages_data=pages
        )
    )


def test_security_policy_link_resolves_to_the_anchor_not_the_span() -> None:
    """Session 7: the span won the fast text pass and had no href."""
    span = {"selector": "div > span", "text": "Security Policy", "tag": "span", "role": "span"}
    anchor = {
        "selector": 'a[href="https://github.com/tancat-ai/tancat/blob/main/SECURITY.md"]',
        "text": "Security Policy",
        "tag": "a",
        "role": "a",
        "href": "https://github.com/tancat-ai/tancat/blob/main/SECURITY.md",
    }
    matched = _resolve(_matcher(), "Security Policy link resolves", {"https://x.test/": [span, anchor]})
    assert matched is not None
    assert matched.get("tag") == "a"


def test_missing_named_link_skips_instead_of_resolving_the_logo() -> None:
    """Session 7: the nav logo (href="#") was used for a link that no longer exists."""
    logo = {"selector": 'a[href="#"]', "text": "TanCat tancat-0.1.0", "tag": "a", "role": "a", "raw_href": "#"}
    matched = _resolve(_matcher(), "Watch 3-Min Walkthrough link resolves", {"https://x.test/": [logo]})
    assert matched is None


def test_skeleton_url_description_also_skips_when_the_named_link_is_absent() -> None:
    """The prompt rule renders it "... live video URL" and the skeleton drops
    the word "link"; it must still stay out of a non-anchor lookalike."""
    div = {"selector": "#view-product-ui", "text": "", "tag": "div", "role": "div"}
    logo = {"selector": 'a[href="#"]', "text": "TanCat tancat-0.1.0", "tag": "a", "role": "a", "raw_href": "#"}
    matched = _resolve(_matcher(), "Watch 3-Min Walkthrough live video URL", {"https://x.test/": [div, logo]})
    assert matched is None


def test_non_link_criterion_still_resolves_an_ordinary_element() -> None:
    heading = {"selector": "h3", "text": "Air-Gap / Defense", "tag": "h3", "role": "h3"}
    matched = _resolve(_matcher(), "Air-Gap / Defense tier", {"https://x.test/": [heading]})
    assert matched is not None


# ---------------------------------------------------------------------------
# Criterion 27 — section containment
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("description", "section"),
    [
        ("contact link inside Air-Gap tier", "air-gap"),
        ("contact link inside the Air-Gap / Defense card", "air-gap / defense"),
        ("Air-Gap / Defense tier contains a contact link", "air-gap / defense"),
        ("email address inside the pricing section", "pricing"),
    ],
)
def test_section_contains_classified(description: str, section: str) -> None:
    check = section_contains_from_description(description)
    assert check is not None, f"not classified: {description!r}"
    assert check.section == section
    assert "contact" in check.child or "mailto" in check.child


@pytest.mark.parametrize(
    "description",
    ["Air-Gap / Defense tier", "Contact us", "email address inside that tier", "hero headline visible"],
)
def test_section_contains_ignored_when_unspecified(description: str) -> None:
    assert section_contains_from_description(description) is None


def test_section_contains_emits_scoped_call() -> None:
    desc = "contact link inside Air-Gap tier"
    token = f"{{{{ASSERT:{desc}}}}}"
    out = replace_token_in_line(f"    {token}", "ASSERT", token, "h3.x", set(), desc)
    assert out.strip() == (
        "evidence_tracker.assert_contains('air-gap', 'a[href^=\"mailto:\"], a[href*=\"contact\"]', "
        "label='contact link inside Air-Gap tier')"
    )
    assert "assert_visible" not in out


def _contains_tracker(tmp_path: Any, container_count: int) -> EvidenceTracker:
    page = MagicMock()
    page.url = "https://example.com"
    heading = MagicMock()
    container = MagicMock()
    container.count.return_value = container_count
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.last = container
    page.locator.side_effect = lambda sel: heading if ":has-text(" in sel else chain
    return EvidenceTracker(page, "test_b088_contains", evidence_root=Path(tmp_path))


def test_assert_contains_passes_when_child_is_inside(tmp_path: Any) -> None:
    tracker = _contains_tracker(tmp_path, container_count=1)
    tracker.assert_contains("air-gap", 'a[href^="mailto:"]', label="contact inside tier")
    assert tracker.steps[-1]["result"]["status"] == "passed"


def test_assert_contains_fails_when_child_is_elsewhere(tmp_path: Any) -> None:
    tracker = _contains_tracker(tmp_path, container_count=0)
    with pytest.raises(AssertionError, match="also contains"):
        tracker.assert_contains("air-gap", 'a[href^="mailto:"]', label="contact inside tier")


def test_page_level_asserts_never_trigger_the_journey_skip() -> None:
    """B-088: the emitter owns these checks, so an unresolved resolver result
    must not add a journey-level skip (the whole test would skip)."""
    from src.placeholder_orchestrator import _is_page_level_assert

    assert _is_page_level_assert("ASSERT", "no TBD in hrefs")
    assert _is_page_level_assert("ASSERT", "no lorem ipsum in visible copy")
    assert _is_page_level_assert("ASSERT", "meta description non-empty")
    assert _is_page_level_assert("ASSERT", "canonical URL declared")
    assert _is_page_level_assert("ASSERT", "contact link inside Air-Gap tier")
    assert not _is_page_level_assert("ASSERT", "hero headline visible")
    assert not _is_page_level_assert("ASSERT", "Security Policy link resolves")
    # A CLICK with a page-level-looking description has no page-level emitter.
    assert not _is_page_level_assert("CLICK", "contact link inside Air-Gap tier")


def test_emitted_section_and_mailto_lines_compile() -> None:
    for description in [
        "contact link inside Air-Gap tier",
        "hello@tancat.dev mailto link",
        "no TBD in hrefs",
        "no lorem ipsum in visible copy",
    ]:
        token = f"{{{{ASSERT:{description}}}}}"
        assertion_type = "toHaveAttribute:href" if "mailto" in description else "toBeVisible"
        out = replace_token_in_line(
            f"    {token}", "ASSERT", token, "'a.x'", set(), description, assertion_type=assertion_type
        )
        compile("def _emitted() -> None:\n" + out, "<emitted>", "exec")
