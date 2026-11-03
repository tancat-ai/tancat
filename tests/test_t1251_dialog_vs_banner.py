"""t-1251: a dialog the click opened is content; a banner is an obstacle.

j-0269 marked every element inside ``#cartModal``, ``.modal`` and ``[role='dialog']``
the same as one inside a cookie banner, and the ASSERT path demoted both. The
t-1241 review proved the cost with two headings of identical text: with the marker
the page heading won, without it the dialog heading won - so a genuine confirmation
inside the dialog the click had just opened lost to page content that merely looked
like it.

This module pins the three fixes:

1. the dialog and the banner are told apart by what the click did - a container the
   page already had before the click is an obstacle, one only the post-click look
   has was opened by the click and is content (the trail says the look IS the
   landing; the DOM says which container is new; the class list is the fallback);
2. membership asks for real containers, so a layout wrapper called ``cookie-policy``
   no longer flags its whole subtree;
3. a Playwright-only selector (``:has-text``, ``:visible``) is resolved through
   Playwright, and when that fails the answer is "could not be evaluated" (None),
   never a silent "not in an overlay".

The CLICK path stays as it was, and a test here pins it.
"""

from __future__ import annotations

from typing import Any

from src.browser_utils import (
    OVERLAY_BANNER_SELECTOR,
    OVERLAY_CONTAINER_SELECTOR,
    OVERLAY_DIALOG_SELECTOR,
    OVERLAY_MEMBERSHIP_SELECTOR,
)
from src.journey_enrichment import capture_element_visibility_sync
from src.placeholder_orchestrator import PlaceholderOrchestrator
from src.placeholder_resolver import PlaceholderResolver

PAGE = "https://shop.example.com/"

CONFIRM_TEXT = "Order confirmed"


def _heading(selector: str, text: str = CONFIRM_TEXT, **extra: Any) -> dict[str, Any]:
    element: dict[str, Any] = {"selector": selector, "text": text, "tag": "h2", "role": "heading"}
    element.update(extra)
    return element


def _in_dialog(selector: str, container: str = "#cartModal") -> dict[str, Any]:
    return _heading(selector, in_overlay=True, overlay_kind="dialog", overlay_container=container)


def _in_banner(selector: str, container: str = ".cookie-banner") -> dict[str, Any]:
    return _heading(selector, in_overlay=True, overlay_kind="banner", overlay_container=container)


def _rank(elements: list[dict[str, Any]], description: str = CONFIRM_TEXT) -> list[str]:
    ranked = PlaceholderResolver().rank_candidates("ASSERT", description, elements)
    return [str(element.get("selector", "")) for _score, element in ranked]


# ---------------------------------------------------------------------------
# The dialog the click opened is content
# ---------------------------------------------------------------------------


def test_a_dialog_the_click_opened_wins_over_page_content() -> None:
    """The reviewer's case, both directions: the marker alone lost the dialog."""
    pool = [
        _heading("#page-confirm"),
        _in_dialog("#cart-modal-confirm"),
    ]
    before_click = [_heading("#page-confirm"), _heading("#shop-grid")]  # no dialog on the page yet

    assert _rank(pool)[0] == "#page-confirm", "without the decision the dialog is demoted (j-0269)"

    marked = PlaceholderOrchestrator._mark_landing_overlays([dict(e) for e in pool], before_click)

    assert _rank(marked)[0] == "#cart-modal-confirm", "the dialog the click opened stayed demoted"
    assert marked[1]["in_overlay"] is False
    assert marked[1]["overlay_opened_by_click"] is True


def test_a_cookie_banner_in_the_same_pool_stays_demoted() -> None:
    pool = [
        _heading("#page-confirm"),
        _in_banner("#banner-confirm"),
    ]
    before_click = [_heading("#page-confirm")]  # the banner is new too

    marked = PlaceholderOrchestrator._mark_landing_overlays([dict(e) for e in pool], before_click)

    assert marked[1]["in_overlay"] is True, "a banner was promoted to content"
    assert _rank(marked)[0] == "#page-confirm"


def test_an_overlay_that_was_there_before_the_click_still_demotes() -> None:
    """The reverse: the same dialog was already on the page - it is an obstacle."""
    pool = [
        _heading("#page-confirm"),
        _in_dialog("#cart-modal-confirm"),
    ]
    before_click = [_heading("#page-confirm"), _in_dialog("#cart-modal-old")]

    marked = PlaceholderOrchestrator._mark_landing_overlays([dict(e) for e in pool], before_click)

    assert marked[1]["in_overlay"] is True
    assert _rank(marked)[0] == "#page-confirm", "an overlay that pre-dated the click was promoted"


def test_no_before_click_dom_leaves_the_class_list_answer_standing() -> None:
    pool = [_heading("#page-confirm"), _in_dialog("#cart-modal-confirm")]

    marked = PlaceholderOrchestrator._mark_landing_overlays([dict(e) for e in pool], [])

    assert marked[1]["in_overlay"] is True, "with no evidence the dialog must stay conservative"
    assert _rank(marked)[0] == "#page-confirm"


# ---------------------------------------------------------------------------
# Fix 2: membership asks for containers, not for words in a class name
# ---------------------------------------------------------------------------


def test_a_layout_wrapper_named_after_cookies_is_not_a_container() -> None:
    """``cookie-policy`` is page content; the old membership selector flagged it."""
    assert "[class*='cookie']" not in OVERLAY_MEMBERSHIP_SELECTOR
    assert "[class*='consent']" not in OVERLAY_MEMBERSHIP_SELECTOR
    assert "[class*='cookie-banner']" in OVERLAY_MEMBERSHIP_SELECTOR
    # The reveal guard keeps its wider list: it must never reveal a dismissed overlay.
    assert "[class*='cookie']" in OVERLAY_CONTAINER_SELECTOR
    # Every dialog shape survives the narrowing.
    assert "#cartModal" in OVERLAY_DIALOG_SELECTOR
    assert "[role='dialog']" in OVERLAY_DIALOG_SELECTOR
    assert ".modal" in OVERLAY_MEMBERSHIP_SELECTOR
    assert OVERLAY_BANNER_SELECTOR


# ---------------------------------------------------------------------------
# Fix 3: a selector the browser-side probe cannot read is not silently "no"
# ---------------------------------------------------------------------------


class _FakeLocator:
    def __init__(self, answer: Any) -> None:
        self._answer = answer

    @property
    def first(self) -> _FakeLocator:
        return self

    def count(self) -> int:
        return 1

    def is_visible(self) -> bool:
        return True

    def evaluate(self, _script: str, _arg: Any) -> Any:
        if isinstance(self._answer, Exception):
            raise self._answer
        return self._answer


class _FakePage:
    """A page whose browser-side evaluate answers "no container" for everything."""

    def __init__(self, answer: Any = None) -> None:
        self._answer = answer

    def evaluate(self, _script: str, args: Any) -> Any:
        selectors = args[0] if args else []
        return [{"key": None, "kind": None} for _ in selectors]

    def locator(self, _selector: str) -> _FakeLocator:
        return _FakeLocator(self._answer)


def test_a_playwright_only_selector_is_resolved_not_missed() -> None:
    page = _FakePage(answer={"key": "#cartModal", "kind": "dialog"})
    elements = [_heading("h2:has-text('Order confirmed')")]

    marked = capture_element_visibility_sync(page, elements)

    assert marked[0]["in_overlay"] is True, "a :has-text selector silently read as out of the overlay"
    assert marked[0]["overlay_container"] == "#cartModal"
    assert marked[0]["overlay_kind"] == "dialog"


def test_an_unevaluable_selector_says_so_instead_of_no() -> None:
    page = _FakePage(answer=RuntimeError("selector not supported"))
    elements = [_heading("h2:visible")]

    marked = capture_element_visibility_sync(page, elements)

    assert marked[0]["in_overlay"] is None, "an unevaluable selector was reported as 'not in an overlay'"


def test_the_click_path_is_unchanged() -> None:
    """The marker never demotes a CLICK - it is an assert rule (t-1238, pinned here)."""
    elements = [
        _heading("#cookie-accept", "Accept cookies", in_overlay=True, overlay_kind="banner"),
        _heading("#other", "Something else"),
    ]

    ranked = PlaceholderResolver().rank_candidates("CLICK", "accept cookies", elements)

    assert str(ranked[0][1].get("selector")) == "#cookie-accept"
