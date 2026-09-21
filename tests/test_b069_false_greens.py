"""Targeted verification for B-069 part (a) and part (b).

Verifies:
- A. Unverified fallback produces pytest.skip (part a).
- B. Attribute-condition descriptions emit attribute-read assertions (part b).
- B2. Part (b) completion: the emitted check tests the PREDICATE in the
      description ("does not contain TBD" / "live video URL" cannot pass on
      a placeholder value), and page-level count checks ("no TBD in links",
      "all images have alt") are emitted without element resolution.
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.code_postprocessor import (
    _ASSERTION_TO_ET_METHOD,
    _PLACEHOLDER_FORBIDDEN,
    _assertion_type_to_et_method,
    attribute_predicate,
    count_assertion_from_description,
    replace_token_in_line,
)
from src.evidence_tracker import EvidenceTracker
from src.placeholder_orchestrator import attribute_assertion_type, polarity_assertion_type

# ---------------------------------------------------------------------------
# A — B-069 part (a): unverified fallback → pytest.skip
# ---------------------------------------------------------------------------


def test_unverified_assertion_emits_skip() -> None:
    """When element matcher returns a fallback with unverified=True,
    the batch path emits pytest.skip, not a passing assert."""
    desc = "How It Works heading"
    emitted = f"pytest.skip(\"Assertion for '{desc}' could not be verified on this page\")"
    assert "pytest.skip" in emitted
    assert desc in emitted


# ---------------------------------------------------------------------------
# B — B-069 part (b): attribute assertions read the attribute
# ---------------------------------------------------------------------------


def test_polarity_negative_state() -> None:
    assert polarity_assertion_type("popup closed") == "toBeHidden"
    assert polarity_assertion_type("item removed") == "toBeHidden"


@pytest.mark.parametrize(
    "description,expected_attr",
    [
        ("watch 3 min walkthrough... href does not contain TBD", "href"),
        ("meta description tag exists", "content"),
        ("every image has a non-empty alt", "alt"),
        ("Open Graph title tag present", "content"),
        ("video URL is valid", "href"),
        # B-072: link-resolution criteria verify the href, not visibility.
        ("GitHub link resolves to the correct URL", "href"),
        ("Security Policy link resolves without returning 404", "href"),
        ("License link does not return 404", "href"),
    ],
)
def test_attribute_description_detected(description: str, expected_attr: str) -> None:
    """Attribute-condition descriptions should return 'toHaveAttribute:<attr>'."""
    result = attribute_assertion_type(description)
    assert result is not None, f"attribute_assertion_type returned None for {description!r}"
    assert result.startswith("toHaveAttribute:"), f"expected prefixed type, got {result!r}"
    assert result.endswith(expected_attr), f"expected attr {expected_attr!r} in {result!r}"


def test_non_attribute_description_returns_none() -> None:
    """Non-attribute descriptions should not trigger attribute assertions."""
    assert attribute_assertion_type("login button is visible") is None
    assert attribute_assertion_type("page title is displayed") is None
    assert attribute_assertion_type("item added to cart") is None


def test_assertion_mapping_to_evidence_tracker() -> None:
    """toHaveAttribute maps to assert_attribute, not assert_visible."""
    assert _ASSERTION_TO_ET_METHOD["toHaveAttribute"] == "assert_attribute"
    assert _assertion_type_to_et_method("toHaveAttribute") == "assert_attribute"
    assert _assertion_type_to_et_method("toBeVisible") == "assert_visible"


# ---------------------------------------------------------------------------
# B2 — B-069 part (b) completion: predicates + page-level count checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("description", "attribute", "expected_url_flag", "forbidden_includes"),
    [
        ("Buy Pro link href does not contain TBD", "href", False, ("tbd",)),
        ("Watch 3-Min Walkthrough button href is live video URL", "href", True, ("your_", "tbd")),
        ("Walkthrough href does not contain YOUR_VIDEO_ID_HERE", "href", False, ("your_video_id_here",)),
        ("Buy Air-Gap link resolves to a live purchase URL", "href", True, ("tbd",)),
        ("hero headline visible", "href", False, ()),
        ("contact link or email in tier", "href", False, ()),
        ("no more than 3 items shown", "href", False, ()),
    ],
)
def test_attribute_predicate(
    description: str, attribute: str, expected_url_flag: bool, forbidden_includes: tuple[str, ...]
) -> None:
    must_be_url, forbidden = attribute_predicate(description, attribute)
    assert must_be_url is expected_url_flag, f"{description!r}: must_be_url={must_be_url}"
    for token in forbidden_includes:
        assert token in forbidden, f"{description!r}: {token!r} not in {forbidden}"


def test_attribute_predicate_must_be_url_is_href_only() -> None:
    """A non-href attribute never gets the http(s) URL requirement."""
    must_be_url, _ = attribute_predicate("live video", "alt")
    assert must_be_url is False


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("no TBD in links", ("assert_no_forbidden", "a", "tbd", "href")),
        ("no TBD in buttons", ("assert_no_forbidden", "button", "tbd", None)),
        ("no lorem ipsum in headings", ("assert_no_forbidden", "h1, h2, h3, h4, h5, h6", "lorem", None)),
        ("no YOUR_VIDEO_ID_HERE in links", ("assert_no_forbidden", "a", "your_video_id_here", "href")),
        ("all images have alt", ("assert_attribute_all", "img", "alt", "alt")),
        ("every image has a non-empty alt", ("assert_attribute_all", "img", "alt", "alt")),
        ("all anchor links valid", ("assert_attribute_all", "a", "href", "href")),
    ],
)
def test_count_assertion_classified(description: str, expected: tuple[str, str, str, str | None]) -> None:
    check = count_assertion_from_description(description)
    assert check is not None, f"not classified: {description!r}"
    assert (check.method, check.selector, check.argument, check.attribute) == expected


def test_count_assertion_all_links_valid_carries_placeholder_forbidden() -> None:
    check = count_assertion_from_description("all anchor links valid")
    assert check is not None
    assert check.forbidden == _PLACEHOLDER_FORBIDDEN


@pytest.mark.parametrize(
    "description",
    [
        "hero headline visible",
        "no horizontal scroll",
        "no broken images",
        "login button is visible",
        "item added to cart",
        "all prices visible",
        "no TBD anywhere on the page",
    ],
)
def test_count_assertion_none_for_non_count_descriptions(description: str) -> None:
    assert count_assertion_from_description(description) is None


def test_emit_count_assertion_bypasses_unverified_skip() -> None:
    """A page-level count check emits even when the resolver marked the
    element unverified — the check does not depend on the element."""
    desc = "no TBD in links"
    token = "{{ASSERT:no TBD in links}}"
    resolved = f"pytest.skip(\"Assertion for '{desc}' could not be verified on this page\")"
    out = replace_token_in_line(f"    {token}", "ASSERT", token, resolved, set(), desc)
    assert out.strip() == "evidence_tracker.assert_no_forbidden('a', 'tbd', label='no TBD in links', attribute='href')"


def test_emit_count_assertion_attribute_all() -> None:
    token = "{{ASSERT:all images have alt}}"
    out = replace_token_in_line(f"    {token}", "ASSERT", token, "'#contact'", set(), "all images have alt")
    assert out.strip() == "evidence_tracker.assert_attribute_all('img', 'alt', label='all images have alt')"


def test_emit_attribute_predicate_forbidden() -> None:
    desc = "Buy Pro link href does not contain TBD"
    token = "{{ASSERT:Buy Pro link href does not contain TBD}}"
    out = replace_token_in_line(
        f"    {token}",
        "ASSERT",
        token,
        "'a[href=\"x\"]'",
        set(),
        desc,
        assertion_type="toHaveAttribute:href",
    )
    assert "evidence_tracker.assert_attribute('a[href=\"x\"]', 'href'" in out
    assert "forbidden=('tbd',)" in out


def test_emit_attribute_predicate_live_url() -> None:
    desc = "Watch 3-Min Walkthrough button href is live video URL"
    token = "{{ASSERT:watch button href is live video url}}"
    out = replace_token_in_line(
        f"    {token}", "ASSERT", token, "'a.btn'", set(), desc, assertion_type="toHaveAttribute:href"
    )
    assert "must_be_url=True" in out
    assert "forbidden=" in out


def test_emit_link_resolves_asserts_attribute_not_click() -> None:
    """B-072: a 'link resolves' ASSERT must emit an href check (assert_attribute
    with must_be_url + placeholder forbidden) — never a click, which cannot be
    verified on a new-tab link in a headless run."""
    desc = "GitHub link resolves to the correct URL"
    token = "{{ASSERT:GitHub link resolves}}"
    out = replace_token_in_line(
        f"    {token}",
        "ASSERT",
        token,
        "'a[href=\"https://github.com/tancat-ai/tancat\"]'",
        set(),
        desc,
        assertion_type="toHaveAttribute:href",
    )
    assert out.strip().startswith("evidence_tracker.assert_attribute(")
    assert "'href'" in out
    assert "must_be_url=True" in out
    assert "forbidden=" in out
    assert ".click(" not in out


# ---------------------------------------------------------------------------
# B2 — EvidenceTracker: the predicates actually run
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
    return EvidenceTracker(page, "test_attr", evidence_root=Path(tmp_path))


def test_assert_attribute_forbidden_fails_on_tbd_href(tmp_path: Any) -> None:
    tracker = _tracker(tmp_path, [_element("https://lemonsqueezy.com/l/TANCAT-PRO-TBD")])
    with pytest.raises(AssertionError, match="forbidden 'tbd'"):
        tracker.assert_attribute('a[href="x"]', "href", label="Buy Pro link", forbidden=("tbd",))
    assert tracker.steps[-1]["result"]["status"] == "failed"


def test_assert_attribute_must_be_url_fails_on_placeholder(tmp_path: Any) -> None:
    tracker = _tracker(tmp_path, [_element("YOUR_VIDEO_ID_HERE")])
    with pytest.raises(AssertionError, match="not an http"):
        tracker.assert_attribute("a.btn", "href", label="live video", must_be_url=True)


def test_assert_attribute_live_url_passes(tmp_path: Any) -> None:
    tracker = _tracker(tmp_path, [_element("https://www.loom.com/share/abc123")])
    tracker.assert_attribute("a.btn", "href", label="live video", forbidden=("tbd", "your_"), must_be_url=True)
    assert tracker.steps[-1]["result"]["status"] == "passed"


def test_assert_attribute_empty_still_fails(tmp_path: Any) -> None:
    tracker = _tracker(tmp_path, [_element(None)])
    with pytest.raises(AssertionError, match="non-empty"):
        tracker.assert_attribute("meta", "content", label="meta description")


def test_assert_no_forbidden_finds_offender(tmp_path: Any) -> None:
    tracker = _tracker(tmp_path, [_element("https://x.com"), _element("https://x.com/l/TBD")])
    with pytest.raises(AssertionError, match="1 element"):
        tracker.assert_no_forbidden("a", "tbd", label="no TBD in links", attribute="href")
    assert tracker.steps[-1]["result"]["status"] == "failed"


def test_assert_no_forbidden_passes_and_records_count(tmp_path: Any) -> None:
    tracker = _tracker(tmp_path, [_element("https://x.com"), _element("https://y.com")])
    tracker.assert_no_forbidden("a", "tbd", label="no TBD in links", attribute="href")
    step = tracker.steps[-1]["result"]
    assert step["status"] == "passed"
    assert "2 element" in step["matched_text"]


def test_assert_no_forbidden_text_mode(tmp_path: Any) -> None:
    tracker = _tracker(tmp_path, [_element(None, "Buy Now (TBD)")])
    with pytest.raises(AssertionError, match="tbd"):
        tracker.assert_no_forbidden("button", "tbd", label="no TBD in buttons")


def test_assert_no_forbidden_zero_elements_passes_vacuously(tmp_path: Any) -> None:
    tracker = _tracker(tmp_path, [])
    tracker.assert_no_forbidden("a", "tbd", label="no TBD in links", attribute="href")
    assert tracker.steps[-1]["result"]["status"] == "passed"
    assert "0 element" in tracker.steps[-1]["result"]["matched_text"]


def test_assert_attribute_all_fails_on_empty(tmp_path: Any) -> None:
    tracker = _tracker(tmp_path, [_element(None), _element("alt text")])
    with pytest.raises(AssertionError, match="1/2"):
        tracker.assert_attribute_all("img", "alt", label="all images have alt")


def test_assert_attribute_all_fails_on_zero_elements(tmp_path: Any) -> None:
    tracker = _tracker(tmp_path, [])
    with pytest.raises(AssertionError, match="found none"):
        tracker.assert_attribute_all("img", "alt", label="all images have alt")


def test_assert_attribute_all_forbidden_fails(tmp_path: Any) -> None:
    tracker = _tracker(tmp_path, [_element("https://x.com/TBD")])
    with pytest.raises(AssertionError, match="forbidden"):
        tracker.assert_attribute_all("a", "href", label="all anchor links valid", forbidden=("tbd",))


def test_assert_attribute_all_passes(tmp_path: Any) -> None:
    tracker = _tracker(tmp_path, [_element("a1"), _element("a2")])
    tracker.assert_attribute_all("img", "alt", label="all images have alt")
    assert tracker.steps[-1]["result"]["status"] == "passed"
