"""j-0259: arm the "did not reach the next page" stop for clicks the trail proved moved.

The carry-on rules (j-0240) stop a journey when a step whose job is to change
page does not change it. That stop is armed by ``click(must_move=True)``, which
existed and was tested (``tests/test_t1095_stop_rules.py``) - but no emitter
passed it, so a page that silently ignores clicks yielded passing steps and
nothing stopped the test.

The walk already knows the fact: the scrape trail records, per click, whether
the browser's URL changed (``ObservedStep.navigated``). This file pins the
carry of that one fact into the emitted call, in both shapes:

- a click the trail marks as navigated emits ``must_move=True`` (flat and POM);
- a click the trail leaves as non-navigating emits without it;
- a click with no trail entry emits without it - "no fact" is never "it moved";
- nothing but a click ever carries it.

What the flag does at run time is the tracker's business, still pinned by
t-1095 (a dead ``must_move`` click stops with ``no_arrival``). Here the last
test only checks that the keyword the emitters write is the one the tracker
accepts, so the two halves cannot drift apart.

The trail records a page change only: a click that opens a NEW TAB leaves the
page URL alone, so the trail holds no fact for it and the flag stays off.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from src.code_postprocessor import replace_token_in_line, strip_evidence_from_test_code
from src.evidence_tracker import EvidenceTracker
from src.journey_models import ObservedStep, ObservedTrail
from src.pipeline_models import (
    GeneratedPageObject,
    PlaceholderUse,
    ScrapedPage,
    TestJourney,
    TestStep,
)
from src.placeholder_orchestrator import PlaceholderOrchestrator
from src.pom_helpers import build_page_object_artifacts, get_pom_method_call

SHOP = "https://shop.example.com/"
CART = "https://shop.example.com/cart.html"


# ---------------------------------------------------------------------------
# The flat emitter (replace_token_in_line)
# ---------------------------------------------------------------------------


def _emit_click(*, must_move: bool, expected_page: str = "") -> str:
    return replace_token_in_line(
        line='    evidence_tracker.click("{{CLICK:Submit order}}")',
        action="CLICK",
        token="{{CLICK:Submit order}}",
        resolved_value="'#submit-order'",
        duplicate_selectors=set(),
        description="Submit order",
        expected_page=expected_page,
        must_move=must_move,
    )


def test_a_trail_proven_click_emits_must_move() -> None:
    emitted = _emit_click(must_move=True)

    assert emitted.strip() == "evidence_tracker.click('#submit-order', label='Submit order', must_move=True)"


def test_a_click_with_no_trail_fact_emits_without_it() -> None:
    emitted = _emit_click(must_move=False)

    assert "must_move" not in emitted
    assert emitted.strip() == "evidence_tracker.click('#submit-order', label='Submit order')"


def test_the_flag_sits_beside_the_page_the_step_expects() -> None:
    """Both facts travel together: where the step should be, and that it must move."""
    emitted = _emit_click(must_move=True, expected_page=SHOP)

    assert "expected_page='https://shop.example.com/'" in emitted
    assert emitted.rstrip().endswith(", must_move=True)")
    compile(emitted.strip(), "<emitted>", "exec")


def test_only_a_click_carries_the_flag() -> None:
    """A goto cannot arm a click stop, so the flag must never leak onto one."""
    emitted = replace_token_in_line(
        line='    evidence_tracker.navigate("{{GOTO:cart}}")',
        action="GOTO",
        token="{{GOTO:cart}}",
        resolved_value=f"'{CART}'",
        duplicate_selectors=set(),
        description="cart",
        must_move=True,
    )

    assert "must_move" not in emitted
    assert "evidence_tracker.navigate(" in emitted


def test_the_export_strip_removes_the_flag() -> None:
    """An exported test has no tracker, so the keyword must not survive."""
    stripped = strip_evidence_from_test_code(
        'evidence_tracker.click("#submit-order", label="Submit order", must_move=True)'
    )

    assert 'page.locator("#submit-order").click()' in stripped
    assert "must_move" not in stripped


# ---------------------------------------------------------------------------
# The POM emitter (get_pom_method_call, and the page object it calls)
# ---------------------------------------------------------------------------


def test_a_trail_proven_click_emits_must_move_in_pom_mode() -> None:
    call = get_pom_method_call(
        action="CLICK",
        description="Submit order",
        resolved_selector="'#submit-order'",
        pom_instance_name="shop_page",
        must_move=True,
    )

    assert call == "shop_page.click('Submit order', selector='#submit-order', must_move=True)"


def test_a_click_with_no_trail_fact_emits_without_it_in_pom_mode() -> None:
    call = get_pom_method_call(
        action="CLICK",
        description="Submit order",
        resolved_selector="'#submit-order'",
        pom_instance_name="shop_page",
        must_move=False,
    )

    assert call == "shop_page.click('Submit order', selector='#submit-order')"


def test_a_proven_click_with_no_named_target_still_carries_the_flag() -> None:
    """The stop asks whether the browser moved, not whether we named the target."""
    call = get_pom_method_call(
        action="CLICK",
        description="Submit order",
        resolved_selector='pytest.skip("nope")',
        pom_instance_name="shop_page",
        must_move=True,
    )

    assert call == "shop_page.click('Submit order', must_move=True)"


def _page_object(tracker: Any) -> Any:
    """Build a real evidence-aware page object instance bound to *tracker*."""
    scraped = [
        ScrapedPage(
            url=SHOP,
            element_count=1,
            elements=[{"tag": "button", "text": "Submit order", "selector": "#submit-order", "role": "button"}],
        )
    ]
    objects = build_page_object_artifacts(scraped, pom_mode=True)
    assert len(objects) == 1
    namespace: dict[str, Any] = {}
    exec(objects[0].module_source, namespace)  # noqa: S102 - generated source is what is under test
    return namespace[objects[0].class_name](None, tracker)


def test_the_page_object_forwards_the_flag_to_the_tracker() -> None:
    """A generated page object must not swallow the flag as a TypeError or drop it."""
    recorded: list[dict[str, Any]] = []

    class _Recorder:
        def click(self, locator: str, label: str = "", must_move: bool = False) -> None:
            recorded.append({"locator": locator, "label": label, "must_move": must_move})

    page = _page_object(_Recorder())
    page.click("Submit order", selector="#submit-order", must_move=True)
    page.click("Submit order", selector="#submit-order")

    assert recorded == [
        {"locator": "#submit-order", "label": "Submit order", "must_move": True},
        {"locator": "#submit-order", "label": "Submit order", "must_move": False},
    ]


def test_the_emitted_keyword_is_the_one_the_tracker_accepts() -> None:
    """t-1095 keeps the stop; this keeps the emitters speaking its language."""
    parameter = inspect.signature(EvidenceTracker.click).parameters.get("must_move")

    assert parameter is not None
    assert parameter.default is False


# ---------------------------------------------------------------------------
# The orchestrator: the walked trail decides, per emitted click
# ---------------------------------------------------------------------------


def _scraped() -> dict[str, list[dict[str, Any]]]:
    return {
        SHOP: [
            {"selector": "#submit-order", "text": "Submit order", "tag": "button", "role": "button"},
            {"selector": "#add-to-cart", "text": "Add to cart", "tag": "button", "role": "button"},
        ],
        CART: [{"selector": "h1", "text": "Cart", "tag": "h1", "role": "heading"}],
    }


def _skeleton_and_journey() -> tuple[str, TestJourney]:
    token = "{{CLICK:Submit order}}"
    line = f"    page.click('{token}')"
    skeleton = "\n".join(["def test_checkout(page) -> None:", line, ""])
    journey = TestJourney(
        test_name="test_checkout",
        start_line=1,
        end_line=2,
        steps=[
            TestStep(
                line_number=2,
                raw_line=line,
                placeholders=[
                    PlaceholderUse(
                        token=token,
                        action="CLICK",
                        description="Submit order",
                        line_number=2,
                        raw_line=line,
                    )
                ],
            )
        ],
    )
    return skeleton, journey


def _trail(*, navigated: bool) -> ObservedTrail:
    return ObservedTrail(
        steps=[
            ObservedStep(
                0,
                "click",
                description="Submit order",
                selector_used="#submit-order",
                from_url=SHOP,
                to_url=CART if navigated else SHOP,
                navigated=navigated,
            )
        ]
    )


def _resolve(trail: ObservedTrail | None, *, pom_mode: bool = False) -> str:
    skeleton, journey = _skeleton_and_journey()
    orch = PlaceholderOrchestrator(starting_url=SHOP, pom_mode=pom_mode)
    if pom_mode:
        orch._generated_page_objects = [  # noqa: SLF001
            GeneratedPageObject(
                url=SHOP,
                class_name="ShopPage",
                module_name="shop_page",
                file_path="pages/shop_page.py",
            )
        ]
    return asyncio.run(
        orch._replace_placeholders_sequentially(  # noqa: SLF001
            skeleton_code=skeleton,
            journeys=[journey],
            page_requirements=[],
            seed_urls=[SHOP],
            scraped_data=_scraped(),
            observed_trails={"test_checkout": trail} if trail is not None else {},
        )
    )


def test_a_walked_click_that_changed_the_page_emits_must_move() -> None:
    code = _resolve(_trail(navigated=True))

    assert "evidence_tracker.click(" in code
    assert "must_move=True" in code
    compile(code, "<generated>", "exec")


def test_a_walked_click_that_stayed_put_emits_without_the_flag() -> None:
    """The trail observed this click NOT moving the page: no stop is armed for it."""
    code = _resolve(_trail(navigated=False))

    assert "evidence_tracker.click(" in code
    assert "must_move" not in code


def test_a_click_with_no_trail_entry_emits_without_the_flag() -> None:
    assert "must_move" not in _resolve(None)


def test_a_walked_click_that_changed_the_page_emits_must_move_in_pom_mode() -> None:
    code = _resolve(_trail(navigated=True), pom_mode=True)

    assert "shop_page.click('Submit order'" in code
    assert "must_move=True" in code
    compile(code, "<generated>", "exec")


def test_a_walked_click_that_stayed_put_emits_without_the_flag_in_pom_mode() -> None:
    code = _resolve(_trail(navigated=False), pom_mode=True)

    assert "shop_page.click(" in code
    assert "must_move" not in code


def test_a_walked_goto_replayed_as_a_click_still_carries_the_flag() -> None:
    """A "go to the page" step the walk performed by clicking stays a click.

    That emitted click is the one the trail measured, so it arms the stop like
    any other proved click - the flag follows the fact, not the placeholder name.
    """
    token = "{{GOTO:Cart page}}"
    line = f"    page.goto('{token}')"
    skeleton = "\n".join(["def test_checkout(page) -> None:", line, ""])
    journey = TestJourney(
        test_name="test_checkout",
        start_line=1,
        end_line=2,
        steps=[
            TestStep(
                line_number=2,
                raw_line=line,
                placeholders=[
                    PlaceholderUse(
                        token=token,
                        action="GOTO",
                        description="Cart page",
                        line_number=2,
                        raw_line=line,
                    )
                ],
            )
        ],
    )
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0,
                "click",
                description="Cart page",
                selector_used="#cart-link",
                from_url=SHOP,
                to_url=CART,
                navigated=True,
            )
        ]
    )
    orch = PlaceholderOrchestrator(starting_url=SHOP)

    code = asyncio.run(
        orch._replace_placeholders_sequentially(  # noqa: SLF001
            skeleton_code=skeleton,
            journeys=[journey],
            page_requirements=[],
            seed_urls=[SHOP],
            scraped_data=_scraped(),
            observed_trails={"test_checkout": trail},
        )
    )

    assert "evidence_tracker.click(" in code
    assert "must_move=True" in code
    compile(code, "<generated>", "exec")
