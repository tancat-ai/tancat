"""t-1239/t-1240: a check the tool cannot verify has three outcomes, not one.

The owner's rule (agreed 2026-11-03):

- something on the page interfered (a banner covering the target, an overlay, a
  pop-up that would not close) -> FAIL, and name it;
- the tool has no evidence at all (no observation, a landing never captured) ->
  SKIP, and the skip is counted out loud;
- the check ran and the page is not what the story expects -> ordinary FAIL.

Page arrivals already split this way (t-0929). This module pins the same split
for element asserts, and pins that the eval report carries the skip count.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from src.placeholder_orchestrator import PlaceholderOrchestrator

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "eval"))

CHECKOUT = "http://localhost:8781/checkout.html"
SUCCESS = "http://localhost:8781/checkout_success.html"
PLACE_ORDER = "#place-order"


class _Placeholder:
    line_number = 10
    token = "{{ASSERT:order success message}}"


class _Matcher:
    """Rule-based stand-in: returns the first pool element with the given selector."""

    def __init__(self, selector: str | None, *, stubborn: bool = False) -> None:
        self.selector = selector
        self.stubborn = stubborn
        self.pools: list[dict[str, list[dict[str, str]]]] = []

    async def find_best_elements_batch(
        self,
        requests: list[dict[str, Any]],
        current_url: str | None,
        pages_data: dict[str, list[dict[str, str]]],
        excluded_selectors: set[str] | None = None,
    ) -> list[dict[str, str] | None]:
        self.pools.append(dict(pages_data))
        if self.selector is None:
            return [None]
        pools = list(_scraped().values()) if self.stubborn else list(pages_data.values())
        for elements in pools:
            for element in elements:
                if element.get("selector") == self.selector:
                    return [dict(element)]
        return [None]

    async def find_best_element_for_current_page(
        self,
        action: str,
        description: str,
        current_url: str | None,
        pages_data: dict[str, list[dict[str, str]]],
        excluded_selectors: set[str] | None = None,
        resolved_steps: list[str] | None = None,
        golden_patterns: Any = None,
        site_hash: str | None = None,
    ) -> dict[str, str] | None:
        """Same stub for the single-placeholder path (the CLICK step uses it)."""
        results = await self.find_best_elements_batch(
            [{"action": action, "description": description}],
            current_url,
            pages_data,
            excluded_selectors,
        )
        return results[0]


def _scraped() -> dict[str, list[dict[str, str]]]:
    return {
        CHECKOUT: [
            {
                "selector": PLACE_ORDER,
                "role": "button",
                "tag": "button",
                "text": "Place Order",
                "assertion_type": "toBeVisible",
            }
        ],
        SUCCESS: [
            {
                "selector": "#success-title",
                "role": "heading",
                "tag": "h1",
                "text": "Order Placed Successfully!",
                "assertion_type": "toBeVisible",
            }
        ],
    }


def _deferred(**overrides: Any) -> dict[str, Any]:
    da: dict[str, Any] = {
        "placeholder": _Placeholder(),
        "action": "ASSERT",
        "description": "order success message",
        "fill_value": "",
        "current_url": CHECKOUT,
        "previous_selector": PLACE_ORDER,
        "previous_description": "Place Order",
        "previous_interaction": True,
        "previous_landing": None,
        "previous_landing_url": None,
        "previous_landing_dom": None,
        "previous_stayed_put": False,
        "previous_click_error": None,
        "previous_landing_available": True,
    }
    da.update(overrides)
    return da


async def _resolve(da: dict[str, Any], selector: str | None, *, stubborn: bool = False) -> str:
    orchestrator = PlaceholderOrchestrator()
    orchestrator._element_matcher = _Matcher(selector, stubborn=stubborn)  # type: ignore[assignment]  # noqa: SLF001
    resolutions: dict[int, list[tuple[str, str, str, str, str, str | None, str | None]]] = {}
    await orchestrator._batch_resolve_deferred_asserts(  # noqa: SLF001 - the unit under test
        deferred_asserts=[da],
        scraped_data=_scraped(),
        scraped_errors={},
        fallback_url=None,
        line_resolutions=resolutions,
        journey_unresolved={},
        journey_unresolved_keys={},
        journey_name="eval-006",
        strict_scope=True,
    )
    (entry,) = resolutions[10]
    return str(entry[2])


# ─── 1. No evidence -> SKIP ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_evidence_is_a_skip() -> None:
    """The walk never recorded a page after the click: nothing to check against."""
    value = await _resolve(_deferred(previous_stayed_put=False), PLACE_ORDER)

    assert value.startswith('pytest.skip("check not run: '), value
    assert "the walk never recorded a page after 'Place Order'" in value


@pytest.mark.asyncio
async def test_landing_named_but_never_captured_is_a_skip() -> None:
    value = await _resolve(
        _deferred(previous_landing_url="http://localhost:8781/checkout_success.html?session=9"),
        PLACE_ORDER,
    )

    assert value.startswith('pytest.skip("check not run: '), value
    assert "never recorded" in value


@pytest.mark.asyncio
async def test_empty_same_page_look_is_a_skip() -> None:
    value = await _resolve(
        _deferred(previous_landing_dom=[], previous_landing_url=CHECKOUT),
        PLACE_ORDER,
    )

    assert value.startswith('pytest.skip("check not run: '), value
    assert "looked at the page after 'Place Order' and found nothing" in value


# ─── 2. Interference -> FAIL, naming it ─────────────────────────────────────


@pytest.mark.asyncio
async def test_interference_is_a_failure_that_names_it() -> None:
    """A click blocked by an overlay is interference, not a missing check."""
    value = await _resolve(
        _deferred(
            previous_click_error="Locator.click: Timeout 5000ms exceeded. <div id='ad'> intercepts pointer events",
            previous_stayed_put=True,
        ),
        PLACE_ORDER,
    )

    assert value.startswith('pytest.fail("check failed: '), value
    assert "covering the target when 'Place Order' ran" in value


# ─── 3. Wrong answer -> FAIL ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_click_that_stayed_put_with_no_landing_is_a_failure() -> None:
    """The false green: the pool is still the DOM from BEFORE the click."""
    value = await _resolve(_deferred(previous_stayed_put=True), PLACE_ORDER)

    assert value.startswith('pytest.fail("check failed: '), value
    assert "never left the page and the walk recorded nothing after it" in value


@pytest.mark.asyncio
async def test_nearest_match_on_another_page_is_a_failure() -> None:
    """The expected page WAS captured and the target is not on it: wrong answer."""
    value = await _resolve(
        _deferred(previous_landing=SUCCESS, previous_landing_url=SUCCESS),
        PLACE_ORDER,
        stubborn=True,
    )

    assert value.startswith('pytest.fail("check failed: '), value
    assert "the nearest element for 'order success message'" in value
    assert CHECKOUT in value and SUCCESS in value


# ─── The report carries the skip count (item 5) ─────────────────────────────


def test_report_counts_skips_and_says_so() -> None:
    from eval_metrics import HarnessReport, StoryResult

    report = HarnessReport(
        stories=[
            StoryResult(
                story_id="eval-006",
                site="ecommerce_mock",
                total_criteria=8,
                criteria_with_skeletons=8,
                tests_executed=10,
                tests_passed=9,
                tests_skipped=5,
            )
        ]
    )

    assert report.total_skipped == 5
    text = report.to_summary()
    assert "Checks skipped (no evidence): 5" in text
    assert "skipped=5" in text, "the per-story line must carry the skip count"
    pass_rate_line = next(line for line in text.splitlines() if "Test pass rate:" in line)
    assert "not run for want of evidence" in pass_rate_line, "a pass rate must not print alone when checks were skipped"


def test_report_says_zero_skips_plainly() -> None:
    from eval_metrics import HarnessReport, StoryResult

    report = HarnessReport(
        stories=[
            StoryResult(
                story_id="eval-001",
                site="saucedemo",
                total_criteria=6,
                criteria_with_skeletons=6,
                tests_executed=6,
                tests_passed=6,
            )
        ]
    )

    text = report.to_summary()
    assert "Checks skipped (no evidence): 0" in text
    assert "skipped=0" in text


# ─── t-1243: each shape, through the EMITTER, verbatim ──────────────────────


def _emit(resolved_value: str) -> str:
    """Render the line the generated test carries for a resolved value."""
    from src.code_postprocessor import replace_token_in_line

    line = "    {{ASSERT:order success message}}"
    return replace_token_in_line(
        line,
        "ASSERT",
        "{{ASSERT:order success message}}",
        resolved_value,
        set(),
        description="order success message",
    ).strip()


@pytest.mark.asyncio
async def test_emitted_no_evidence_line_is_a_skip_with_its_reason() -> None:
    value = await _resolve(_deferred(), PLACE_ORDER)
    assert _emit(value) == (
        "pytest.skip(\"check not run: the walk never recorded a page after 'Place Order', "
        'so there was nothing to check against")'
    )


@pytest.mark.asyncio
async def test_emitted_interference_line_is_a_fail_with_its_reason() -> None:
    value = await _resolve(
        _deferred(previous_click_error="waiting for element to be visible, enabled and stable"),
        PLACE_ORDER,
    )
    assert _emit(value) == (
        "pytest.fail(\"check failed: something on the page was covering the target when 'Place Order' ran\")"
    )


@pytest.mark.asyncio
async def test_emitted_wrong_page_line_is_a_fail() -> None:
    value = await _resolve(
        _deferred(previous_landing=SUCCESS, previous_landing_url=SUCCESS), PLACE_ORDER, stubborn=True
    )
    emitted = _emit(value)
    assert emitted.startswith("pytest.fail(\"check failed: the nearest element for 'order success message' is on ")
    assert CHECKOUT in emitted and SUCCESS in emitted


@pytest.mark.asyncio
async def test_emitted_stayed_put_line_is_a_fail() -> None:
    value = await _resolve(_deferred(previous_stayed_put=True), PLACE_ORDER)
    assert _emit(value) == (
        "pytest.fail(\"check failed: the click on 'Place Order' never left the page and the walk "
        'recorded nothing after it, so the check would sit on the page from before the click")'
    )


@pytest.mark.asyncio
async def test_emitted_same_address_landing_line_is_a_normal_assert() -> None:
    value = await _resolve(
        _deferred(previous_landing_dom=[{"selector": ".text-center", "text": "added"}], previous_landing_url=CHECKOUT),
        ".text-center",
    )
    emitted = _emit(value)
    assert emitted.startswith("evidence_tracker.assert_visible(")
    assert ".text-center" in emitted


@pytest.mark.asyncio
async def test_stayed_put_false_green_is_closed_on_the_real_path() -> None:
    """d-0107: driven through _replace_placeholders_sequentially, not by hand.

    A click the trail saw stay put, with no post-click landing recorded: the
    assert must FAIL. The old order returned "resolved" first because the
    stayed-put click's to_url canonises to the page it was already on.
    """
    from src.journey_models import ObservedStep, ObservedTrail
    from src.pipeline_models import PageRequirement, PlaceholderUse, TestJourney, TestStep
    from src.placeholder_orchestrator import PlaceholderOrchestrator

    def ph(action: str, desc: str, line: int, token: str) -> PlaceholderUse:
        return PlaceholderUse(token=token, action=action, description=desc, line_number=line, raw_line=token)

    journey = TestJourney(
        test_name="test_place_order",
        start_line=1,
        end_line=3,
        steps=[
            TestStep(
                line_number=2,
                raw_line="page.click('{{CLICK:Place Order}}')",
                placeholders=[ph("CLICK", "Place Order", 2, "{{CLICK:Place Order}}")],
            ),
            TestStep(
                line_number=3,
                raw_line="assert '{{ASSERT:order success message}}'",
                placeholders=[ph("ASSERT", "order success message", 3, "{{ASSERT:order success message}}")],
            ),
        ],
    )
    trail = ObservedTrail(
        steps=[
            ObservedStep(0, "click", description="Place Order", from_url=CHECKOUT, to_url=CHECKOUT, navigated=False),
            ObservedStep(1, "scrape", description="order success message", from_url=CHECKOUT, to_url=CHECKOUT),
        ]
    )
    orchestrator = PlaceholderOrchestrator(starting_url=CHECKOUT)

    emitted = await orchestrator._replace_placeholders_sequentially(  # noqa: SLF001 - the unit under test
        skeleton_code="def test_place_order(page):\n    page.click('{{CLICK:Place Order}}')\n    assert '{{ASSERT:order success message}}'\n",
        journeys=[journey],
        page_requirements=[PageRequirement(keyword="checkout")],
        seed_urls=[CHECKOUT],
        scraped_data=_scraped(),
        scraped_errors={},
        observed_trails={"test_place_order": trail},
    )

    assert "pytest.fail(\"check failed: the click on 'Place Order' never left the page" in emitted, emitted
    assert "assert_visible('#place-order'" not in emitted, "the false green must be gone"


# ─── t-1246: no "looks unchanged" evidence; positive signals only ────────────


def _same_capture() -> list[dict[str, str]]:
    return [
        {"selector": "#aggree", "role": "radio", "classes": "form-check", "text": "", "is_visible": "True"},
        {"selector": "#other", "role": "text", "classes": "", "text": "Type here", "is_visible": "True"},
    ]


@pytest.mark.asyncio
async def test_a_radio_tick_is_not_interference() -> None:
    """A ticked radio (checked is not captured) leaves the look identical - not a blocker."""
    value = await _resolve(
        _deferred(previous_landing_dom=_same_capture(), previous_landing_url=CHECKOUT),
        "#aggree",
    )
    assert not value.startswith("pytest.fail("), value


@pytest.mark.asyncio
async def test_a_scroll_is_not_interference() -> None:
    """A scroll (position is not captured) leaves the look identical - not a blocker."""
    value = await _resolve(
        _deferred(previous_landing_dom=_same_capture(), previous_landing_url=CHECKOUT),
        "#other",
    )
    assert not value.startswith("pytest.fail("), value


@pytest.mark.asyncio
async def test_target_present_but_unreachable_is_interference_naming_the_click() -> None:
    """The positive signal: the check's target is on the page but not reachable."""
    landing = [{"selector": "#total", "role": "text", "text": "0", "is_visible": "False"}]
    values = await _resolve_lines(
        _deferred(previous_landing_dom=landing, previous_landing_url=CHECKOUT),
        "#total",
    )
    assert values.startswith('pytest.fail("check failed: '), values
    assert "could not be reached after the click on 'Place Order'" in values
    assert "order success message" in values


@pytest.mark.asyncio
async def test_journey_mode_with_no_look_is_a_skip() -> None:
    """The user-provided journey executor records no look: that is no evidence."""
    value = await _resolve(
        _deferred(previous_landing_available=False, previous_stayed_put=True),
        PLACE_ORDER,
    )
    assert value.startswith('pytest.skip("check not run: '), value
    assert "does not look at the page after a click" in value


async def _resolve_lines(da: dict[str, Any], selector: str | None) -> str:
    """Resolve, then render the emitted line through the real emitter."""
    return _emit(await _resolve(da, selector))


def test_interference_message_names_the_click_on_the_real_path() -> None:
    """Drive the real path: the fail must name the click, never the assert."""
    import asyncio

    from src.journey_models import ObservedStep, ObservedTrail
    from src.pipeline_models import PageRequirement, PlaceholderUse, TestJourney, TestStep

    def ph(action: str, desc: str, line: int) -> PlaceholderUse:
        token = f"{{{{{action}:{desc}}}}}"
        return PlaceholderUse(token=token, action=action, description=desc, line_number=line, raw_line=token)

    journey = TestJourney(
        test_name="test_place_order",
        start_line=1,
        end_line=3,
        steps=[
            TestStep(
                line_number=2,
                raw_line="page.click('{{CLICK:Place Order}}')",
                placeholders=[ph("CLICK", "Place Order", 2)],
            ),
            TestStep(
                line_number=3,
                raw_line="assert '{{ASSERT:order success message}}'",
                placeholders=[ph("ASSERT", "order success message", 3)],
            ),
        ],
    )
    hidden_target = [{"selector": PLACE_ORDER, "role": "button", "text": "Place Order", "is_visible": "False"}]
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0,
                "click",
                description="Place Order",
                from_url=CHECKOUT,
                to_url=CHECKOUT,
                navigated=False,
                landing_checked=True,
                landing_dom=hidden_target,
            ),
            ObservedStep(1, "scrape", description="order success message", from_url=CHECKOUT, to_url=CHECKOUT),
        ]
    )
    scraped = {
        CHECKOUT: [{"selector": PLACE_ORDER, "role": "button", "text": "Place Order", "assertion_type": "toBeVisible"}]
    }
    orchestrator = PlaceholderOrchestrator(starting_url=CHECKOUT)
    # A stub ranker returns the pool element (the LLM would pick it at run time);
    # everything around it - the trail, the classifier, the emitter - is real.
    orchestrator._element_matcher = _Matcher(PLACE_ORDER)  # type: ignore[assignment]  # noqa: SLF001

    emitted = asyncio.run(
        orchestrator._replace_placeholders_sequentially(  # noqa: SLF001 - the unit under test
            skeleton_code=(
                "def test_place_order(page):\n"
                "    page.click('{{CLICK:Place Order}}')\n"
                "    assert '{{ASSERT:order success message}}'\n"
            ),
            journeys=[journey],
            page_requirements=[PageRequirement(keyword="checkout")],
            seed_urls=[CHECKOUT],
            scraped_data=scraped,
            scraped_errors={},
            observed_trails={"test_place_order": trail},
        )
    )

    assert "could not be reached after the click on 'Place Order'" in emitted, emitted
    assert "the click on 'order success message'" not in emitted


# ─── t-1248: an absence check is not interference ───────────────────────────


def test_absence_after_a_click_emits_assert_hidden_on_the_real_path() -> None:
    """A closed banner is recorded hidden - that is the PASS, not a blocker."""
    import asyncio

    from src.journey_models import ObservedStep, ObservedTrail
    from src.pipeline_models import PageRequirement, PlaceholderUse, TestJourney, TestStep

    def ph(action: str, desc: str, line: int) -> PlaceholderUse:
        token = f"{{{{{action}:{desc}}}}}"
        return PlaceholderUse(token=token, action=action, description=desc, line_number=line, raw_line=token)

    journey = TestJourney(
        test_name="test_close_banner",
        start_line=1,
        end_line=3,
        steps=[
            TestStep(
                line_number=2,
                raw_line="page.click('{{CLICK:Close the promo banner}}')",
                placeholders=[ph("CLICK", "Close the promo banner", 2)],
            ),
            TestStep(
                line_number=3,
                raw_line="assert '{{ASSERT:promo banner closed}}'",
                placeholders=[ph("ASSERT", "promo banner closed", 3)],
            ),
        ],
    )
    banner_hidden = [{"selector": "#promo", "role": "banner", "text": "50% off", "is_visible": "False"}]
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0,
                "click",
                description="Close the promo banner",
                from_url=CHECKOUT,
                to_url=CHECKOUT,
                navigated=False,
                landing_checked=True,
                landing_dom=banner_hidden,
            ),
            ObservedStep(1, "scrape", description="promo banner closed", from_url=CHECKOUT, to_url=CHECKOUT),
        ]
    )
    scraped = {
        CHECKOUT: [
            {"selector": "#promo", "role": "banner", "text": "50% off", "assertion_type": "toBeVisible"},
            {
                "selector": PLACE_ORDER,
                "role": "button",
                "text": "Place Order",
                "assertion_type": "toBeVisible",
            },
        ]
    }
    orchestrator = PlaceholderOrchestrator(starting_url=CHECKOUT)
    orchestrator._element_matcher = _Matcher("#promo")  # type: ignore[assignment]  # noqa: SLF001

    emitted = asyncio.run(
        orchestrator._replace_placeholders_sequentially(  # noqa: SLF001 - the unit under test
            skeleton_code=(
                "def test_close_banner(page):\n"
                "    page.click('{{CLICK:Close the promo banner}}')\n"
                "    {{ASSERT:promo banner closed}}\n"
            ),
            journeys=[journey],
            page_requirements=[PageRequirement(keyword="checkout")],
            seed_urls=[CHECKOUT],
            scraped_data=scraped,
            scraped_errors={},
            observed_trails={"test_close_banner": trail},
        )
    )

    assert "evidence_tracker.assert_hidden(" in emitted, emitted
    assert "pytest.fail(" not in emitted, "an absence check must not be blamed on the page"
