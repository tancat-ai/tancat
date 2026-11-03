"""t-1222: an element ASSERT after a click resolves against the LANDED page.

The defect: the tool resolved an element check from the DOM captured before the
click that creates the target. When the target was not there it kept the nearest
element and the story's label, so a test could go green on a step that never
happened - eval-006 c7 checked the Place Order button instead of the order
success title.

The fact that makes the fix cheap: the observed trail names the page the click
produced (``ObservedStep.to_url``), and the scraper already captured that page's
DOM when the URL changed. This module tests the batch resolver against stubs -
no browser, no model, no run.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.placeholder_orchestrator import PlaceholderOrchestrator

CHECKOUT = "http://localhost:8781/checkout.html"
SUCCESS = "http://localhost:8781/checkout_success.html"

#: What the trail recorded for the "Place Order" click in eval-006: the mock's
#: own submit handler sends the browser to checkout_success.html.
PLACE_ORDER = "#place-order"
SUCCESS_TITLE = "#success-title"


class _Placeholder:
    """The little the batch resolver needs from a placeholder."""

    def __init__(self, line_number: int = 10, token: str = "{{ASSERT:order success message}}") -> None:
        self.line_number = line_number
        self.token = token


class _PoolMatcher:
    """Stand-in for ElementMatcher: returns a fixed selector from the pool it is given.

    It records the pool so a test can prove WHICH pages the resolver searched. With
    ``stubborn=True`` it hands the selector back even when the pool does not hold it
    - that is the "nearest element wins" substitution this slice removes.
    """

    def __init__(self, selector: str, *, stubborn: bool = False) -> None:
        self.selector = selector
        self.stubborn = stubborn
        self.pools: list[dict[str, list[dict[str, str]]]] = []
        self._all = _scraped()

    async def find_best_elements_batch(
        self,
        requests: list[dict[str, Any]],
        current_url: str | None,
        pages_data: dict[str, list[dict[str, str]]],
        excluded_selectors: set[str] | None = None,
    ) -> list[dict[str, str] | None]:
        self.pools.append(dict(pages_data))
        pools = list(pages_data.values())
        if self.stubborn:
            pools = list(self._all.values())
        for elements in pools:
            for element in elements:
                if element.get("selector") == self.selector:
                    return [dict(element)]
        return [None]


def _scraped() -> dict[str, list[dict[str, str]]]:
    return {
        CHECKOUT: [
            {
                "selector": PLACE_ORDER,
                "role": "button",
                "tag": "button",
                "text": "Place Order",
                "assertion_type": "toBeVisible",
            },
            {"selector": "#name", "role": "text", "tag": "input", "assertion_type": "toBeVisible"},
        ],
        SUCCESS: [
            {
                "selector": SUCCESS_TITLE,
                "role": "heading",
                "tag": "h1",
                "text": "Order Placed Successfully!",
                "assertion_type": "toBeVisible",
            },
        ],
    }


def _deferred(
    *,
    previous_interaction: bool = True,
    previous_landing: str | None = SUCCESS,
    previous_landing_url: str | None = SUCCESS,
) -> dict[str, Any]:
    return {
        "placeholder": _Placeholder(),
        "action": "ASSERT",
        "description": "order success message",
        "fill_value": "",
        "current_url": CHECKOUT,
        "previous_selector": PLACE_ORDER,
        "previous_description": "Place Order",
        "previous_interaction": previous_interaction,
        "previous_landing": previous_landing,
        "previous_landing_url": previous_landing_url,
    }


async def _resolve(
    deferred: dict[str, Any],
    selector: str,
    *,
    stubborn: bool = False,
) -> tuple[dict[int, list[tuple[str, str, str, str, str, str | None, str | None]]], _PoolMatcher]:
    orchestrator = PlaceholderOrchestrator()
    matcher = _PoolMatcher(selector, stubborn=stubborn)
    orchestrator._element_matcher = matcher  # type: ignore[assignment]  # noqa: SLF001 - the seam under test
    resolutions: dict[int, list[tuple[str, str, str, str, str, str | None, str | None]]] = {}
    await orchestrator._batch_resolve_deferred_asserts(  # noqa: SLF001 - the unit under test
        deferred_asserts=[deferred],
        scraped_data=_scraped(),
        scraped_errors={},
        fallback_url=None,
        line_resolutions=resolutions,
        journey_unresolved={},
        journey_unresolved_keys={},
        journey_name="eval-006",
        strict_scope=True,
    )
    return resolutions, matcher


@pytest.mark.asyncio
async def test_assert_resolves_against_the_landed_page() -> None:
    """A (regression pin, not the fix): a known landing page supplies the element.

    The parent commit already did this; this test exists so the t-1225 narrowing
    cannot lose it.
    """
    resolutions, matcher = await _resolve(_deferred(), SUCCESS_TITLE)

    assert list(matcher.pools[0]) == [SUCCESS], "the resolver must search the landed page only"
    (entry,) = resolutions[10]
    _token, _action, resolved_value, _description, _fill, expected_page, assertion_type = entry
    assert resolved_value == repr(SUCCESS_TITLE)
    assert expected_page == SUCCESS
    assert assertion_type is not None


@pytest.mark.asyncio
async def test_click_with_no_trail_entry_refuses() -> None:
    """B: a click the trail never recorded -> a skip, never the pre-click DOM.

    This is the shape that kills the false green (eval-006 c7): the order step ran,
    nothing was observed after it, and the old code asserted on the Place Order
    button of the page before it.
    """
    resolutions, _matcher = await _resolve(
        _deferred(previous_landing=None, previous_landing_url=None),
        PLACE_ORDER,
    )

    (entry,) = resolutions[10]
    resolved_value = entry[2]
    assert resolved_value.startswith('pytest.skip("assertion target not verified: ')
    assert "no landing page was recorded for 'Place Order'" in resolved_value
    assert PLACE_ORDER not in resolved_value


@pytest.mark.asyncio
async def test_landing_named_but_not_scraped_refuses() -> None:
    """A landing the trail named but the scraper never captured -> a skip."""
    unscraped = "http://localhost:8781/checkout_success.html?session=9"
    resolutions, _matcher = await _resolve(
        _deferred(previous_landing=None, previous_landing_url=unscraped),
        PLACE_ORDER,
    )

    (entry,) = resolutions[10]
    resolved_value = entry[2]
    assert resolved_value.startswith('pytest.skip("assertion target not verified: ')
    assert "was not scraped" in resolved_value
    assert unscraped in resolved_value


@pytest.mark.asyncio
async def test_match_on_another_page_after_a_click_refuses() -> None:
    """A nearest element on a page the click did not produce is the defect itself."""
    # The matcher insists on the Place Order button - an element of the PREVIOUS page.
    resolutions, _matcher = await _resolve(_deferred(), PLACE_ORDER, stubborn=True)

    (entry,) = resolutions[10]
    resolved_value = entry[2]
    assert resolved_value.startswith('pytest.skip("assertion target not verified: ')
    assert "nearest match for 'order success message'" in resolved_value
    assert CHECKOUT in resolved_value
    assert SUCCESS in resolved_value


@pytest.mark.asyncio
async def test_target_absent_from_the_landed_page_is_not_asserted() -> None:
    """When the landed page has no target, no assert is emitted against the old page."""
    resolutions, matcher = await _resolve(_deferred(), SUCCESS_TITLE.replace("success", "missing"))

    assert list(matcher.pools[0]) == [SUCCESS]
    assert resolutions.get(10, []) == [] or "assert_visible" not in str(resolutions[10])


@pytest.mark.asyncio
@pytest.mark.parametrize("selector", [PLACE_ORDER, SUCCESS_TITLE])
async def test_no_preceding_click_is_unchanged_same_and_cross_page(selector: str) -> None:
    """D: no click before the assert -> the parent's behaviour, cross-page included.

    Same-page: the cursor page supplies the element. Cross-page: the match is still
    emitted (the parent emitted it) - a click-less assert is not a landing claim.
    """
    resolutions, matcher = await _resolve(
        _deferred(previous_interaction=False, previous_landing=None, previous_landing_url=None),
        selector,
        stubborn=True,
    )

    assert list(matcher.pools[0]) == [CHECKOUT]
    (entry,) = resolutions[10]
    assert entry[2] == repr(selector), "the parent emitted this match; it must not become a skip"
    assert entry[5] == CHECKOUT


@pytest.mark.asyncio
async def test_fill_before_the_assert_is_unchanged() -> None:
    """E: a fill is not a landing claim - no refusal even when the fill is unrecorded."""
    resolutions, matcher = await _resolve(
        _deferred(previous_interaction=False, previous_landing=None, previous_landing_url=None),
        PLACE_ORDER,
    )

    assert list(matcher.pools[0]) == [CHECKOUT]
    (entry,) = resolutions[10]
    assert entry[2] == repr(PLACE_ORDER)
    assert not str(entry[2]).startswith("pytest.skip")
