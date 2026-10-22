"""t-0847: the page cursor follows a known navigation, and "<noun> loaded"
is a page state.

Two fixes under test:

1. **The cursor.** A GOTO whose URL is not in the human's input is performed
   by the journey as a click on the hyperlink that names the destination (the
   human practice). The trail then records where the browser really landed,
   and the resolver must (a) treat that click as this GOTO's observation,
   (b) emit the proven click instead of typing a URL, and (c) move the
   cursor to the observed landing page so the NEXT step resolves against the
   page the browser is on - not the stale one.

2. **The one-liner.** "accounts dashboard loaded" is a page state, not an
   element. The existing element-keyword guard still wins for a real
   element assertion ("cart summary loaded").
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.journey_models import ObservedStep, ObservedTrail
from src.pipeline_models import PlaceholderUse, TestJourney, TestStep
from src.placeholder_orchestrator import PlaceholderOrchestrator

SEED = "https://www.saucedemo.com"
INVENTORY = "https://www.saucedemo.com/inventory.html"
CART = "https://www.saucedemo.com/cart.html"

CART_LINK = '[data-test="shopping-cart-link"]'
CHECKOUT = "#checkout"


def _el(selector: str, text: str, **extra: Any) -> dict[str, Any]:
    element: dict[str, Any] = {"selector": selector, "text": text, "tag": "a", "role": "link"}
    element.update(extra)
    return element


def _token(action: str, description: str) -> str:
    return "{{" + f"{action}:{description}" + "}}"


def _build(name: str, placeholders: list[tuple[str, str]]) -> tuple[str, TestJourney]:
    lines = [f"def {name}(page) -> None:"]
    steps: list[TestStep] = []
    for i, (action, description) in enumerate(placeholders, start=2):
        token = _token(action, description)
        raw_line = f"    act({token})"
        lines.append(raw_line)
        steps.append(
            TestStep(
                line_number=i,
                raw_line=raw_line,
                placeholders=[
                    PlaceholderUse(
                        token=token, action=action, description=description, line_number=i, raw_line=raw_line
                    )
                ],
            )
        )
    skeleton = "\n".join(lines)
    journey = TestJourney(test_name=name, start_line=1, end_line=len(lines), steps=steps)
    return skeleton, journey


def _resolve(
    skeleton: str,
    journeys: list[TestJourney],
    scraped_data: dict[str, list[dict[str, Any]]],
    observed_trails: dict[str, ObservedTrail] | None = None,
) -> str:
    orch = PlaceholderOrchestrator()
    return asyncio.run(
        orch._replace_placeholders_sequentially(
            skeleton_code=skeleton,
            journeys=journeys,
            page_requirements=[],
            seed_urls=[SEED],
            scraped_data=scraped_data,
            observed_trails=observed_trails,
        )
    )


def _saucedemo_data() -> dict[str, list[dict[str, Any]]]:
    """The two pages the journey really visits: inventory then the cart."""
    return {
        SEED: [_el("#login-button", "Login", tag="button", role="button")],
        INVENTORY: [
            _el(CART_LINK, "Cart", aria_label="Cart, empty", data_test="shopping-cart-link"),
        ],
        CART: [
            _el(CHECKOUT, "Checkout", tag="button", role="button"),
        ],
    }


def _saucedemo_trail() -> ObservedTrail:
    """The journey clicked the cart link and landed on the cart page."""
    return ObservedTrail(
        steps=[
            ObservedStep(
                0, "click", description="Login", from_url=SEED, to_url=INVENTORY, navigated=True, scraped=True
            ),
            ObservedStep(
                1,
                "click",
                description="cart",
                from_url=INVENTORY,
                to_url=CART,
                navigated=True,
                scraped=True,
                selector_used=CART_LINK,
            ),
        ]
    )


# ── the cursor ───────────────────────────────────────────────────────────


def test_goto_maps_to_the_trail_click_that_performed_it() -> None:
    """A GOTO performed as a link click is still THIS placeholder's observation."""
    orch = PlaceholderOrchestrator()
    skeleton, journey = _build("test_cursor", [("GOTO", "cart")])
    mapping = orch._map_trail_to_placeholders(
        journey,
        [
            ObservedStep(0, "click", description="cart", from_url=INVENTORY, to_url=CART, selector_used=CART_LINK),
        ],
    )
    assert mapping, "the GOTO found no observation in the trail"
    assert mapping[_token("GOTO", "cart")].to_url == CART


def test_the_navigation_is_emitted_as_the_proven_click() -> None:
    """The customer clicks the cart link; the test does the same."""
    skeleton, journey = _build("test_cursor_emit", [("GOTO", "cart")])
    code = _resolve(skeleton, [journey], _saucedemo_data(), {"test_cursor_emit": _saucedemo_trail()})
    assert f"click({CART_LINK!r}" in code, f"the proven click was not emitted:\n{code}"
    assert "navigate(" not in code, f"a URL was typed instead of the click:\n{code}"


def test_the_cursor_advances_to_the_observed_landing_page() -> None:
    """After the navigation the NEXT step resolves on the cart page.

    Before the fix the cursor stayed on the inventory page, so 'Checkout'
    resolved to the burger menu there.
    """
    skeleton, journey = _build(
        "test_cursor_next",
        [("GOTO", "cart"), ("CLICK", "Checkout")],
    )
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0,
                "click",
                description="cart",
                from_url=INVENTORY,
                to_url=CART,
                navigated=True,
                scraped=True,
                selector_used=CART_LINK,
            ),
            ObservedStep(
                1,
                "click",
                description="Checkout",
                from_url=CART,
                to_url=CART,
                selector_used=CHECKOUT,
            ),
        ]
    )
    code = _resolve(skeleton, [journey], _saucedemo_data(), {"test_cursor_next": trail})
    assert CHECKOUT in code, f"'Checkout' did not resolve on the cart page:\n{code}"


# ── the one-liner ────────────────────────────────────────────────────────


def test_noun_loaded_is_a_page_state() -> None:
    """'accounts dashboard loaded' means the page arrived."""
    orch = PlaceholderOrchestrator()
    assert orch._is_page_state_assertion("accounts dashboard loaded")
    assert orch._is_page_state_assertion("dashboard loaded")


def test_element_keywords_still_win_over_the_noun_loaded_rule() -> None:
    """A real element assertion is never swallowed by the new shape."""
    orch = PlaceholderOrchestrator()
    for desc in ("cart summary loaded", "product list loaded", "image loaded", "loaded"):
        assert not orch._is_page_state_assertion(desc), f"{desc!r} should stay an element assertion"
