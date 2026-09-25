"""B-096 — Pass 1 must not resolve same-page similar fields by scrape order.

Residual after the B-054 pool fix (Session 11, lv_insurance): ``driving license
number`` and ``years licensed`` resolved to the ``addDriver*`` twin instead of
the account-holder ``main*`` field, even though the deterministic scorer ranked
``main*`` top.

Root cause found here: the real fields carry a required marker ("Years
Licensed *"), the optional add-driver twins do not ("Years Licensed"). Pass 1's
text rule matched the optional twin exactly and never saw the required field, so
it returned the first — and only — textual hit. Two fixes:

  1. ``normalise_element_text`` drops required-field markers, so the required
     field is a Pass 1 candidate at all.
  2. ``pass1_text_match`` collects every equal-rule match and lets the
     deterministic scorer break the tie, instead of returning the first one in
     scrape order.

Deeper same-page field disambiguation (both fields optional and identically
labelled — a true section-context problem) remains AI-063 Layer 2 territory; it
is not claimed here.
"""

from __future__ import annotations

import pytest

from src.element_matcher import ElementMatcher
from src.placeholder_resolver import PlaceholderResolver
from src.role_mapper import normalise_element_text

_URL = "http://localhost:8781/generated_tests/mock_insurance_site.html"


def _el(selector: str, text: str, *, visible: bool = True, tag: str = "input", accessible_name: str = "") -> dict:
    return {
        "selector": selector,
        "text": text,
        "accessible_name": accessible_name,
        "role": "text",
        "tag": tag,
        "is_visible": visible,
        "id": selector.lstrip("#"),
        "name": selector.lstrip("#"),
    }


def _matcher() -> ElementMatcher:
    return ElementMatcher(PlaceholderResolver(), generator=None)


# ── 1. Required-field marker normalisation ─────────────────────────────────


def test_normalise_element_text_strips_required_marker() -> None:
    assert normalise_element_text({"text": "Years Licensed *"}) == "years licensed"
    assert normalise_element_text({"text": "Driving License Number *"}) == "driving license number"
    assert normalise_element_text({"text": "Number*"}) == "number"
    assert normalise_element_text({"text": "  Required   *  "}) == "required"


def test_required_field_is_not_defeated_by_its_own_marker() -> None:
    """The '*' must not make the real field invisible to Pass 1 text matching."""
    pages = {_URL: [_el("#mainLicenseYears", "Years Licensed *")]}
    result = _matcher().pass1_text_match("FILL", "years licensed", pages)
    assert result is not None
    assert result["id"] == "mainLicenseYears"


# ── 2. Equal-match tie-break uses the scorer, not scrape order ──────────────


def test_pass1_prefers_required_account_holder_over_optional_twin() -> None:
    """lv_insurance: main* (required) must beat addDriver* (optional) for 'years licensed'."""
    pages = {
        _URL: [
            _el("#mainLicenseYears", "Years Licensed *"),
            _el("#addDriverLicenseYears", "Years Licensed"),
        ]
    }
    result = _matcher().pass1_text_match("FILL", "years licensed", pages)
    assert result is not None
    assert result["id"] == "mainLicenseYears"


def test_pass1_tie_is_broken_by_scorer_not_list_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two equal-rule matches: the scorer's ranking decides, not scrape order."""
    matcher = _matcher()
    first = _el("#fieldOne", "Email Address")
    second = _el("#email", "Email Address")
    monkeypatch.setattr(
        matcher._resolver,
        "rank_candidates",
        lambda *args, **kwargs: [(50, second), (50, first)],
    )

    result = matcher.pass1_text_match("FILL", "email address", {_URL: [first, second]})

    assert result is second


# ── 3. No regression: a single unambiguous match is returned unchanged ──────


def test_pass1_single_match_is_unchanged() -> None:
    pages = {_URL: [_el("#email", "Email Address *")]}
    result = _matcher().pass1_text_match("FILL", "email address", pages)
    assert result is not None
    assert result["id"] == "email"


def test_pass1_still_returns_none_when_nothing_matches() -> None:
    pages = {_URL: [_el("#email", "Email Address *")]}
    assert _matcher().pass1_text_match("FILL", "sort by price", pages) is None


# ── 4. Live-pool shapes: garbage accessible_name, word-boundary phrases ──────


def test_marker_only_accessible_name_falls_back_to_text() -> None:
    """The scraper records accessible_name='*' for required fields on lv_insurance.

    That marker must not shadow the real label text — otherwise the required
    account-holder field is invisible to Pass 1 and the optional twin wins.
    """
    element = _el("#mainLicenseYears", "Years Licensed *", accessible_name="*")
    assert normalise_element_text(element) == "years licensed"


def test_live_pool_twins_resolve_to_account_holder() -> None:
    """The exact live-pool shape: hidden fields, '*' accessible names, twins present."""
    pages = {
        _URL: [
            _el("#mainLicenseYears", "Years Licensed *", visible=False, accessible_name="*"),
            _el("#addDriverLicenseYears", "Years Licensed", visible=False),
        ]
    }
    result = _matcher().pass1_text_match("FILL", "years licensed", pages)
    assert result is not None
    assert result["id"] == "mainLicenseYears"


def test_single_word_phrase_needs_a_word_boundary() -> None:
    """'license' must not match 'Years Licensed' on the 'licensed' substring."""
    pages = {_URL: [_el("#mainLicenseYears", "Years Licensed *")]}
    assert _matcher().pass1_text_match("FILL", "license", pages) is None


def test_single_phrase_matches_a_three_word_label() -> None:
    """'license' must still find 'Driving License Number' (ratio == 3 allowed)."""
    pages = {_URL: [_el("#mainLicenseNumber", "Driving License Number *")]}
    result = _matcher().pass1_text_match("FILL", "license", pages)
    assert result is not None
    assert result["id"] == "mainLicenseNumber"
