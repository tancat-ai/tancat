"""A generic element must not win an element ASSERT (t-0542).

The t-0534 held-out run (79.6%, 90/113) had 14 ASSERT misses; the biggest
shape was a generic element winning: ``p:has-text("Blue Top")`` x5,
``#content`` x2, ``.text``, ``p.account_balance``. The gate-2 metric already
rejects a global container (``verification_strength._GLOBAL_CONTAINERS``);
this ports that rule into the ASSERT resolution scoring and demotes a generic
prose run.

Scorer's own numbers (RAG off, ``match_threshold=1``):

| candidate                                      | before | after |
|------------------------------------------------|--------|-------|
| ``#success-title`` (the element named)         | 20     | 20    |
| ``<p>`` whose merged text contains the desc    | 100    | 10    |
| ``#content`` (global container)                | 60     | None  |

Before, the generic won the ranking; after, the named element wins and the
generic stays only as a last resort (honest degrade, not a hard removal).
"""

from __future__ import annotations

from src.placeholder_scorers import PlaceholderScorer


def _element(overrides: dict | None = None) -> dict:
    base: dict = {
        "selector": "#test",
        "text": "",
        "name": "",
        "role": "button",
        "tag": "button",
        "href": "",
        "id": "",
        "data_test": "",
        "classes": "",
        "aria_label": "",
        "placeholder": "",
        "title": "",
        "value": "",
        "icon_classes": "",
        "visual_description": "",
        "parent_text": "",
        "is_visible": True,
        "is_icon": False,
        "is_decorative": False,
    }
    if overrides:
        base.update(overrides)
    return base


_GENERIC_PROSE = _element(
    {
        "tag": "p",
        "selector": 'p:has-text("order success message")',
        "text": "Your order success message will appear here",
        "role": "paragraph",
    }
)
_NAMED_ELEMENT = _element(
    {
        "tag": "h1",
        "id": "success-title",
        "selector": "#success-title",
        "text": "Order Placed Successfully!",
        "role": "heading",
    }
)


def test_generic_prose_run_loses_to_the_named_element() -> None:
    """Before: generic 100 vs named 20. After: named 20 vs generic 10."""
    named = PlaceholderScorer.compute_element_score(
        "ASSERT", "order success message", _NAMED_ELEMENT, "#success-title", match_threshold=1
    )
    generic = PlaceholderScorer.compute_element_score(
        "ASSERT", "order success message", _GENERIC_PROSE, 'p:has-text("order success message")', match_threshold=1
    )
    assert named == 20
    assert generic is not None
    assert generic < named, "the generic prose run still outranks the named element"


def test_global_container_cannot_win_an_element_assert() -> None:
    """Before: ``#content`` scored 60 (fast path 100 - container 40). After: excluded."""
    content = _element(
        {"tag": "div", "id": "content", "selector": "#content", "text": "All elements listing here", "role": "div"}
    )
    score = PlaceholderScorer.compute_element_score(
        "ASSERT", "all elements listing", content, "#content", match_threshold=1
    )
    assert score is None, "a global container must not prove an element ASSERT"


def test_page_level_assert_keeps_its_container_path() -> None:
    """The sanctioned page-level path is untouched (existing AI-064 contract)."""
    content = _element(
        {"tag": "div", "id": "content", "selector": "#content", "text": "Order summary displayed here", "role": "div"}
    )
    score = PlaceholderScorer.compute_element_score(
        "ASSERT", "order summary displayed", content, "#content", match_threshold=1
    )
    assert score is not None and score >= 100


def test_generic_prose_run_stays_a_last_resort() -> None:
    """A generic run that is the only candidate still resolves (not a hard removal)."""
    score = PlaceholderScorer.compute_element_score(
        "ASSERT", "order success message", _GENERIC_PROSE, 'p:has-text("order success message")', match_threshold=1
    )
    assert score is not None and score >= 1


def test_named_element_with_structural_match_is_not_demoted() -> None:
    """A candidate whose class carries the criterion tokens is never penalized."""
    price = _element(
        {"tag": "p", "selector": ".cart_total_price", "text": "Rs. 500", "role": "p", "classes": "cart_total_price"}
    )
    score = PlaceholderScorer.compute_element_score(
        "ASSERT", "product name and price", price, ".cart_total_price", match_threshold=1
    )
    assert score is not None and score >= 15


def test_guard_only_applies_to_assert() -> None:
    """CLICK/FILL scoring is unchanged by the ASSERT guard."""
    assert PlaceholderScorer._assert_generic_winner_penalty("CLICK", "order success message", _GENERIC_PROSE, "p") == 0
    assert PlaceholderScorer._assert_generic_winner_penalty("FILL", "order success message", _GENERIC_PROSE, "p") == 0
