"""t-1238: the landing pool must not hand an assert an element the walk cannot stand behind.

Two defects the t-1234 review found in the same-page landing work (j-0267, on main):

- d-0111: the post-click look records ``is_visible`` per element, and the landing
  pool now holds the page as it was, but the ASSERT path never read it. A hidden
  heading whose text matched won, and the emitted line was
  ``assert_visible('#hidden-confirm')`` - a failure only the run could find.
- d-0112: the look is taken BEFORE the consent/pop-up dismissal (deliberately, so a
  confirmation modal is not recorded as closed), so a banner or promo control lands
  in the pool. Elements inside ``OVERLAY_CONTAINER_SELECTOR`` are now marked, and the
  ASSERT path prefers page content over them.

Both are pinned here against the real matcher, and one join test starts from a
recorded trail step and ends at the emitted line, so the orchestrator half
(``_assert_landing``) is covered rather than only the reviewer's own run.
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.journey_models import ObservedStep, ObservedTrail
from src.pipeline_models import PlaceholderUse, TestJourney, TestStep
from src.placeholder_orchestrator import PlaceholderOrchestrator
from src.placeholder_resolver import PlaceholderResolver

SHOP = "https://shop.example.com/"
CONFIRM = "https://shop.example.com/confirm"


def _heading(selector: str, text: str, **extra: Any) -> dict[str, Any]:
    element: dict[str, Any] = {"selector": selector, "text": text, "tag": "h2", "role": "heading"}
    element.update(extra)
    return element


def _rank(description: str, elements: list[dict[str, Any]]) -> list[str]:
    ranked = PlaceholderResolver().rank_candidates("ASSERT", description, elements)
    return [str(element.get("selector", "")) for _score, element in ranked]


# ---------------------------------------------------------------------------
# d-0111 - a hidden element must not win a visibility assert
# ---------------------------------------------------------------------------


def test_a_hidden_heading_does_not_win_over_the_visible_one() -> None:
    """The reviewer's case: the hidden element matches the words and used to win."""
    elements = [
        _heading("#hidden-confirm", "Order confirmed", is_visible=False),
        _heading("#confirm-title", "Order confirmed", is_visible=True),
    ]

    ranked = _rank("order confirmed", elements)

    assert ranked, "the assert found no candidate at all"
    assert ranked[0] == "#confirm-title", f"a hidden element was chosen for a visibility assert: {ranked}"
    assert "#hidden-confirm" in ranked, "the hidden element was dropped; the case must stay reachable"


def test_a_hidden_only_pool_still_resolves_and_is_marked_last() -> None:
    """Today the hidden-only case still resolves - q-0364 will make it fail loudly.

    The demotion keeps the element (so behaviour today is unchanged) and puts it
    after every candidate the walk could stand behind, so the later rule has one
    place to change.
    """
    hidden = _heading("#hidden-confirm", "Order confirmed", is_visible=False)

    ranked = _rank("order confirmed", [hidden])

    assert ranked == ["#hidden-confirm"], f"a hidden-only pool no longer resolves at all: {ranked}"
    assert PlaceholderResolver._assert_stand_behind("ASSERT", "order confirmed", hidden) == 1


def test_a_closed_criterion_still_accepts_a_hidden_element() -> None:
    """An ABSENCE assert asks for the element to be gone - hidden is the answer.

    Pinned at the decision point rather than through the score, because "popup
    closed" also carries the polarity floor and the score is not what this rule
    changes.
    """
    hidden = _heading("#banner", "Promo banner", is_visible=False)

    assert PlaceholderResolver._assert_stand_behind("ASSERT", "promo banner closed", hidden) == 0
    assert PlaceholderResolver._assert_stand_behind("ASSERT", "promo banner visible", hidden) == 1


# ---------------------------------------------------------------------------
# d-0112 - an element inside an overlay is deprioritised (assert-only)
# ---------------------------------------------------------------------------


def test_an_overlay_element_is_deprioritised_for_an_assert() -> None:
    elements = [
        _heading("#cookie-accept", "Order confirmed", is_visible=True, in_overlay=True),
        _heading("#confirm-title", "Order confirmed", is_visible=True, in_overlay=False),
    ]

    ranked = _rank("order confirmed", elements)

    assert ranked[0] == "#confirm-title", f"an overlay control was chosen for the assert: {ranked}"
    assert "#cookie-accept" in ranked, "the overlay element was dropped instead of demoted"


def test_the_overlay_marker_does_not_move_a_click() -> None:
    """The marker is assert-only: a CLICK rule of its own was not asked for."""
    elements = [
        _heading("#cookie-accept", "Accept cookies", is_visible=True, in_overlay=True),
        _heading("#other", "Something else", is_visible=True),
    ]

    ranked = PlaceholderResolver().rank_candidates("CLICK", "accept cookies", elements)

    assert ranked, "the click found no candidate"
    assert str(ranked[0][1].get("selector")) == "#cookie-accept", (
        f"the overlay marker changed CLICK ranking: {[e.get('selector') for _s, e in ranked]}"
    )


# ---------------------------------------------------------------------------
# d-0107 - the join: a recorded step, through the orchestrator, to the emitted line
# ---------------------------------------------------------------------------


def _journey() -> tuple[str, TestJourney]:
    click_token = "{{CLICK:Place order}}"
    assert_token = "{{ASSERT:order confirmed}}"
    lines = [
        "def test_checkout(page) -> None:",
        f"    page.click('{click_token}')",
        f"    evidence_tracker.assert_visible('{assert_token}')",
    ]
    steps = [
        TestStep(
            line_number=2,
            raw_line=lines[1],
            placeholders=[
                PlaceholderUse(
                    token=click_token, action="CLICK", description="Place order", line_number=2, raw_line=lines[1]
                )
            ],
        ),
        TestStep(
            line_number=3,
            raw_line=lines[2],
            placeholders=[
                PlaceholderUse(
                    token=assert_token,
                    action="ASSERT",
                    description="order confirmed",
                    line_number=3,
                    raw_line=lines[2],
                )
            ],
        ),
    ]
    return "\n".join(lines), TestJourney(test_name="test_checkout", start_line=1, end_line=3, steps=steps)


def test_a_recorded_landing_reaches_the_emitted_line_without_the_hidden_element() -> None:
    """One test from the recorded step to the emitted assertion (d-0107).

    The click stayed on the address (same-page landing), the look recorded a
    hidden heading and a visible one, and the emitted line must name the visible
    one - which means the trail reached ``_assert_landing``, the landing DOM became
    the pool, and the matcher read the recorded visibility through the orchestrator.
    """
    skeleton, journey = _journey()
    landing = [
        _heading("#hidden-confirm", "Order confirmed", is_visible=False),
        _heading("#confirm-title", "Order confirmed", is_visible=True),
        {"selector": "#place-order", "text": "Place order", "tag": "button", "role": "button", "is_visible": True},
    ]
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0,
                "click",
                description="Place order",
                selector_used="#place-order",
                from_url=SHOP,
                to_url=SHOP,
                navigated=False,
                landing_checked=True,
                landing_dom=landing,
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
            scraped_data={
                SHOP: [
                    {"selector": "#place-order", "text": "Place order", "tag": "button", "role": "button"},
                ]
            },
            observed_trails={"test_checkout": trail},
        )
    )

    emitted_asserts = [line for line in code.splitlines() if "assert_" in line]
    assert emitted_asserts, f"no assertion was emitted:\n{code}"
    assert "#confirm-title" in emitted_asserts[0], f"the visible heading was not chosen:\n{code}"
    assert "#hidden-confirm" not in code, f"the hidden heading reached the emitted test:\n{code}"
