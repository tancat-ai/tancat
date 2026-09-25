"""B-054/B-055 — a multi-step SPA's later-step fields must stay resolvable.

Found by the Session 10 held-out gate re-measure (lv_insurance, 15 of 32 misses).

Two defects, both in the candidate pool:
  1. ``PlaceholderResolver.rank_candidates`` hard-dropped every
     ``is_visible is False`` element for non-ASSERT actions. On a multi-step
     SPA the later steps are ``display:none`` at scrape time, so the real
     target never entered the pool and the resolver fell back to a visible
     step-1 field.
  2. ``IntentMatcher._is_fillable`` omitted the ``date`` / ``time`` /
     ``spinbutton`` roles that ``PlaceholderScorer._is_fillable`` accepts, so
     a date input was filtered out even after (1).
"""

from __future__ import annotations

import asyncio

from src.element_matcher import ElementMatcher
from src.intent_matcher import IntentMatcher
from src.placeholder_resolver import PlaceholderResolver

_URL = "http://localhost:8781/generated_tests/mock_insurance_site.html"


def _el(selector: str, text: str, role: str, *, visible: bool, tag: str = "input") -> dict:
    return {
        "selector": selector,
        "text": text,
        "role": role,
        "tag": tag,
        "is_visible": visible,
        "id": selector.lstrip("#"),
        "name": "",
    }


# Step 1 of the SPA (visible at scrape time).
_VISIBLE_ACCOUNT = [
    _el("#email", "Email Address *", "email", visible=True),
    _el("#lastName", "Last Name *", "text", visible=True),
]

# A later step (display:none at scrape time) — the real target lives here.
_HIDDEN_LATER_STEP = [
    _el("#startDate", "Cover Start Date *", "date", visible=False),
    _el("#scheme", "Select scheme... Standard Premier", "select", visible=False, tag="select"),
]


def test_intent_matcher_fillable_accepts_date_role() -> None:
    """The two _is_fillable implementations must agree on the role set."""
    for role in ("date", "time", "spinbutton"):
        element = _el("#x", "Cover Start Date *", role, visible=True)
        assert IntentMatcher._is_fillable(element) is True, role


def test_rank_candidates_keeps_hidden_later_step_field() -> None:
    """A hidden SPA later-step field is a candidate, not a dropped element."""
    ranked = PlaceholderResolver().rank_candidates("FILL", "start date", _HIDDEN_LATER_STEP)
    selectors = [e.get("selector") for _score, e in ranked]
    assert "#startDate" in selectors


def test_hidden_text_match_beats_visible_unrelated_field() -> None:
    """A hidden element that names the target outranks a visible unrelated one."""
    pool = {_URL: [*_VISIBLE_ACCOUNT, *_HIDDEN_LATER_STEP]}
    matcher = ElementMatcher(PlaceholderResolver(), None)
    result = asyncio.run(matcher.find_best_element_for_current_page("FILL", "start date", _URL, pool))
    assert result is not None
    assert result.get("selector") == "#startDate"
