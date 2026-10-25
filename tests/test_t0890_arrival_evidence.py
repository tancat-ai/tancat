"""t-0890: never assert an arrival the browser was not observed to make.

Owner's rule (2026-10-24), from the measurement on eval-002 / eval-006: the
journey's cart click failed, the browser stayed on the shop page, the trail held
only the shop page - and the arrival check was still written, naming the shop
page as if the test had arrived at the cart. That is the same class of claim as
a guessed address: the test checks something the run never established.

The rule: a page-state arrival assertion may only be written when the trail shows
the step AFTER the last interaction on a DIFFERENT page than the one the
interaction ran on. Otherwise the step becomes an honest skip whose reason names
exactly what was missing - including the interaction's own failure, so a broken
click is never hidden behind a quiet skip.

t-0929 (owner's decision, 2026-10-25) refines the second case: when an
observation EXISTS and it is the wrong page, the arrival is a real FAILING
assertion naming both pages, never a skip and never a rewrite of the candidate.
Only "nothing observed at all" keeps the skip.

Three cases are pinned here:

1. the trail evidences the arrival  -> the assertion is written, as before;
2. the trail observes the wrong page -> an honest failure naming both pages;
   a step with NO observation keeps the skip;
3. the click itself failed          -> the failure stays visible in the arrival
                                       record/assertion.
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.journey_models import ObservedStep, ObservedTrail
from src.pipeline_models import PlaceholderUse, TestJourney, TestStep
from src.placeholder_orchestrator import PlaceholderOrchestrator

SHOP = "https://shop.example.com/"
CART = "https://shop.example.com/checkout.html"


def _el(selector: str, text: str, **extra: Any) -> dict[str, Any]:
    element: dict[str, Any] = {"selector": selector, "text": text, "tag": "a", "role": "link"}
    element.update(extra)
    return element


def _scraped() -> dict[str, list[dict[str, Any]]]:
    return {
        SHOP: [
            _el("#submit-order", "Submit order", tag="button", role="button"),
            _el("#cancel", "Cancel", tag="button", role="button"),
        ],
        CART: [_el("h1", "Checkout", tag="h1")],
    }


def _journey() -> tuple[str, TestJourney]:
    """One test: click the cart link, then check the cart page arrived."""
    lines = [
        "def test_go_to_cart(page) -> None:",
        "    act('{{CLICK:Submit order}}')",
        "    act('{{ASSERT:checkout page loaded}}')",
    ]
    steps = [
        TestStep(
            line_number=2,
            raw_line=lines[1],
            placeholders=[
                PlaceholderUse(
                    token="{{CLICK:Submit order}}",
                    action="CLICK",
                    description="Submit order",
                    line_number=2,
                    raw_line=lines[1],
                )
            ],
        ),
        TestStep(
            line_number=3,
            raw_line=lines[2],
            placeholders=[
                PlaceholderUse(
                    token="{{ASSERT:checkout page loaded}}",
                    action="ASSERT",
                    description="checkout page loaded",
                    line_number=3,
                    raw_line=lines[2],
                )
            ],
        ),
    ]
    return "\n".join(lines), TestJourney(test_name="test_go_to_cart", start_line=1, end_line=3, steps=steps)


def _resolve(trail: ObservedTrail) -> str:
    skeleton, journey = _journey()
    orch = PlaceholderOrchestrator(starting_url=SHOP)
    return asyncio.run(
        orch._replace_placeholders_sequentially(  # noqa: SLF001
            skeleton_code=skeleton,
            journeys=[journey],
            page_requirements=[],
            seed_urls=[SHOP],
            scraped_data=_scraped(),
            observed_trails={"test_go_to_cart": trail},
        )
    )


def _trail(*, clicked: bool, navigated: bool, landing: str = CART, error: str | None = None) -> ObservedTrail:
    steps = [
        ObservedStep(
            0,
            "click",
            description="Submit order",
            from_url=SHOP,
            to_url=landing if navigated else SHOP,
            navigated=navigated,
            scraped=True,
            # ObservedStep.selector_used is a str ("" = no proven selector).
            selector_used="#submit-order" if clicked else "",
            error=error,
        ),
        ObservedStep(
            1,
            "scrape",
            description="checkout page loaded",
            from_url=landing if navigated else SHOP,
            to_url=landing if navigated else SHOP,
            navigated=False,
            scraped=True,
        ),
    ]
    return ObservedTrail(steps=steps)


# ── 1. the trail evidences the arrival: assert it, as before ─────────────


def test_observed_landing_is_asserted() -> None:
    """The browser was seen to arrive: the arrival assertion is written."""
    code = _resolve(_trail(clicked=True, navigated=True))
    assert f'to_have_url("{CART}")' in code, f"the observed arrival was not asserted:\n{code}"
    assert "pytest.skip" not in code, f"an evidenced arrival was skipped:\n{code}"


# -- 2. the trail observes the WRONG page: fail honestly (t-0929) ---------


def test_unobserved_landing_is_an_honest_failure() -> None:
    """The click resolved but the browser never left the shop page.

    t-0929 (owner's decision): the candidate must not be rewritten to the
    observation and the step must not be skipped. The emitted assertion names
    the candidate checkout page and fails; the failure message names both the
    expected and the observed page.
    """
    code = _resolve(_trail(clicked=True, navigated=False))
    assert f'to_have_url("{CART}")' in code, f"the candidate was not asserted:\n{code}"
    assert "HONEST FAILURE" in code, code
    assert CART in code and SHOP in code, code
    assert f"observed_url='{SHOP}'" in code, code
    assert "pytest.skip" not in code, f"an observed mismatch was hidden as a skip:\n{code}"
    # The click itself is still emitted as a click (not converted to a typed URL).
    assert "click(" in code, code
    # The evidence record sits immediately before the literal assertion.
    record_at = code.index("record_page_expectation(")
    assert code.index(f'to_have_url("{CART}")', record_at) > record_at, code


def test_a_missing_trail_step_is_a_skip_not_an_assertion() -> None:
    """No trail entry for the step at all is still no evidence."""
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0,
                "click",
                description="Submit order",
                from_url=SHOP,
                to_url=SHOP,
                navigated=False,
                scraped=True,
                selector_used="#submit-order",
            )
        ]
    )
    code = _resolve(trail)
    assert "to_have_url" not in code, code
    assert "no observed landing after 'Submit order'" in code, code


# ── 3. a failed click stays visible ─────────────────────────────────────


def test_a_failed_click_is_named_not_hidden() -> None:
    """The click itself failed: the failure must surface in the honest failure.

    The arrival is a failing assertion (t-0929) and its record NAMES the click
    failure, so a reader of the evidence sees the broken capture rather than a
    quiet "not asserted".
    """
    code = _resolve(_trail(clicked=False, navigated=False, error="locator_not_found_even_relaxed"))
    assert "that step failed: locator_not_found_even_relaxed" in code, f"the click failure was hidden:\n{code}"
    assert f'to_have_url("{CART}")' in code, code
    assert "HONEST FAILURE" in code, code
    # The click step keeps its own visible outcome too - it is not silently
    # upgraded to a passing step.
    assert "evidence_tracker.click(" in code, code


# ── 4. first step, no interaction yet (t-0903, the review's demonstrated hole) ──


def _first_step_journey() -> tuple[str, TestJourney]:
    """A test whose FIRST step is a page-state assertion - nothing interacted."""
    lines = [
        "def test_checkout_page(page) -> None:",
        "    act('{{ASSERT:checkout page loaded}}')",
    ]
    steps = [
        TestStep(
            line_number=2,
            raw_line=lines[1],
            placeholders=[
                PlaceholderUse(
                    token="{{ASSERT:checkout page loaded}}",
                    action="ASSERT",
                    description="checkout page loaded",
                    line_number=2,
                    raw_line=lines[1],
                )
            ],
        )
    ]
    return "\n".join(lines), TestJourney(test_name="test_checkout_page", start_line=1, end_line=2, steps=steps)


def _run_first_step(trail: ObservedTrail) -> str:
    skeleton, journey = _first_step_journey()
    orch = PlaceholderOrchestrator(starting_url=SHOP)
    return asyncio.run(
        orch._replace_placeholders_sequentially(  # noqa: SLF001
            skeleton_code=skeleton,
            journeys=[journey],
            page_requirements=[],
            seed_urls=[SHOP],
            scraped_data=_scraped(),
            observed_trails={"test_checkout_page": trail},
        )
    )


def test_first_step_assertion_with_no_observation_is_a_skip() -> None:
    """The reviewer's demonstrated case.

    A trail exists for the test, nothing has interacted yet, and this assertion
    has NO observation of its own - so nothing established that the browser is on
    the checkout page. Keyword resolution happily names it; before t-0903 that
    was written as `to_have_url("<checkout>")` while the browser sat on the shop
    page. It must be refused.
    """
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0,
                "scrape",
                description="something else entirely",
                from_url=SHOP,
                to_url=SHOP,
                navigated=False,
                scraped=True,
            )
        ]
    )
    code = _run_first_step(trail)
    assert "to_have_url" not in code, f"an arrival was asserted for a page never observed: {code}"
    assert "pytest.skip" in code
    assert "page arrival not asserted" in code
    assert "never recorded" in code or "not the page the browser was observed on" in code, code


def test_first_step_assertion_naming_an_unvisited_page_is_refused() -> None:
    """Observed on the shop page, candidate is the checkout page -> refused."""
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0,
                "scrape",
                description="checkout page loaded",
                from_url=SHOP,
                to_url=SHOP,
                navigated=False,
                scraped=True,
            )
        ]
    )
    orch = PlaceholderOrchestrator(starting_url=SHOP)
    refusal = orch._arrival_refusal(  # noqa: SLF001
        "checkout page loaded", None, trail.steps[0], lambda url: url, CART
    )
    assert refusal is not None
    assert "not the page the browser was observed on" in refusal


def test_first_step_assertion_naming_the_observed_page_is_written() -> None:
    """The same shape, but the assertion names the page the browser was on."""
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0,
                "scrape",
                description="checkout page loaded",
                from_url=CART,
                to_url=CART,
                navigated=False,
                scraped=True,
            )
        ]
    )
    orch = PlaceholderOrchestrator(starting_url=SHOP)
    assert (
        orch._arrival_refusal(  # noqa: SLF001
            "checkout page loaded", None, trail.steps[0], lambda url: url, CART
        )
        is None
    )
    code = _run_first_step(trail)
    assert f'to_have_url("{CART}")' in code, f"the observed page was not asserted: {code}"
    assert "pytest.skip" not in code
