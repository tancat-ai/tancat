"""AI-052 Session 5: ARIA role-aware candidate collection (penalty-first).

The fast passes (0/D/1/2) return their first match outright — historically a
heading or text field sharing words with the description could win a CLICK
before the role-aware scoring pass ever ran. The S5 gate defers such
role-contradicted matches so deeper passes compete; if NOTHING else resolves,
the deferred candidate is still used (penalty-first, never a hard filter).
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.element_matcher import ElementMatcher
from src.placeholder_resolver import PlaceholderResolver


def _el(selector: str, text: str, **extra: Any) -> dict[str, Any]:
    element: dict[str, Any] = {"selector": selector, "text": text, "tag": "div", "role": "generic"}
    element.update(extra)
    return element


def _matcher() -> ElementMatcher:
    """ElementMatcher with a real offline resolver; LLM ranker gets no generator."""
    return ElementMatcher(PlaceholderResolver())


def _resolve_click(
    matcher: ElementMatcher, description: str, pages: dict[str, list[dict[str, Any]]]
) -> dict[str, Any] | None:
    return asyncio.run(
        matcher.find_best_element_for_current_page(
            action="CLICK",
            description=description,
            current_url="https://x.test/page",
            pages_data=pages,
        )
    )


def test_role_contradicts_click_detects_headings_and_fillables() -> None:
    assert ElementMatcher.role_contradicts_click(_el("#h", "Cart", computed_role="heading"))
    assert ElementMatcher.role_contradicts_click(_el("#h", "Cart", role="h2"))
    # Fillable input (structurally detected even without an explicit role):
    assert ElementMatcher.role_contradicts_click(_el("#cart-name", "cart name", tag="input", role="textbox"))
    # Plain containers / buttons are fine:
    assert not ElementMatcher.role_contradicts_click(_el("#btn", "Add to cart", tag="button", role="button"))
    assert not ElementMatcher.role_contradicts_click(_el("#container", "", tag="div"))  # B-025 containers stay eligible
    assert not ElementMatcher.role_contradicts_click(_el("#link", "Cart", tag="a", href="/cart"))


def test_heading_text_match_defers_in_favour_of_button() -> None:
    """A heading whose text matches the description must NOT win a CLICK when
    a same-named button exists — the gate defers it and Pass 3 picks the
    button (its interactive-role bonus makes it the top scorer)."""
    pages = {
        "https://x.test/page": [
            _el("h2.item-name", "Sauce Labs Backpack", computed_role="heading"),
            _el("#add-to-cart-sauce-labs-backpack", "Sauce Labs Backpack", tag="button", role="button"),
        ]
    }
    matched = _resolve_click(_matcher(), "Sauce Labs Backpack", pages)
    assert matched is not None
    assert matched.get("selector") == "#add-to-cart-sauce-labs-backpack"


def test_fillable_input_defers_for_click() -> None:
    """B-045 shape at the fast-pass layer: a 'Payment Date' input must not win
    'submit payment' on shared words when a submit button exists."""
    pages = {
        "https://x.test/page": [
            _el("#payment-date", "payment date", tag="input", role="textbox"),
            _el("#submit-payment", "submit payment", tag="button", role="button"),
        ]
    }
    matched = _resolve_click(_matcher(), "payment", pages)
    assert matched is not None
    assert matched.get("selector") == "#submit-payment"


def test_penalty_first_contradicted_candidate_still_used_as_last_resort() -> None:
    """When the ONLY text-matching candidate is role-contradicted, it is still
    returned (deferred, not dropped) once every pass is exhausted."""
    pages = {
        "https://x.test/page": [
            _el("h2.cart-title", "Shopping Cart", computed_role="heading"),
        ]
    }
    matched = _resolve_click(_matcher(), "shopping cart", pages)
    assert matched is not None
    assert matched.get("selector") == "h2.cart-title"


def test_computed_role_takes_precedence_over_raw_role() -> None:
    """The enricher's computed_role is authoritative: raw role may say
    'generic' while the AX tree says textbox."""
    assert ElementMatcher.role_contradicts_click(_el("#f", "search cart", computed_role="textbox", tag="input"))


def test_fill_resolution_unaffected() -> None:
    """FILL steps bypass the click gate entirely."""
    matcher = _matcher()
    pages = {
        "https://x.test/page": [
            _el("#username", "username", tag="input", role="textbox"),
        ]
    }
    matched = asyncio.run(
        matcher.find_best_element_for_current_page(
            action="FILL",
            description="username",
            current_url="https://x.test/page",
            pages_data=pages,
        )
    )
    assert matched is not None
    assert matched.get("selector") == "#username"


def test_assert_resolution_unaffected_by_click_gate() -> None:
    """ASSERT keeps its own B-016 display-role machinery; the click gate must
    not interfere with text-bearing matches."""
    matcher = _matcher()
    pages = {
        "https://x.test/page": [
            _el(".confirmation", "order confirmed", tag="div", role="status"),
        ]
    }
    matched = asyncio.run(
        matcher.find_best_element_for_current_page(
            action="ASSERT",
            description="order confirmed",
            current_url="https://x.test/page",
            pages_data=pages,
        )
    )
    assert matched is not None
    assert matched.get("selector") == ".confirmation"


def test_batch_path_applies_same_gate_and_fallback() -> None:
    """find_best_elements_batch: clean candidates win; role-contradicted-only
    requests are filled from the deferred fallback instead of returning None."""
    matcher = _matcher()
    pages = {
        "https://x.test/page": [
            _el("h2.item-name", "Sauce Labs Backpack", computed_role="heading"),
            _el("#add-to-cart-sauce-labs-backpack", "Sauce Labs Backpack", tag="button", role="button"),
            _el("h2.cart-title", "lone heading", computed_role="heading"),
        ]
    }
    results = asyncio.run(
        matcher.find_best_elements_batch(
            requests=[
                {"action": "CLICK", "description": "Sauce Labs Backpack"},
                {"action": "CLICK", "description": "lone heading"},
            ],
            current_url="https://x.test/page",
            pages_data=pages,
        )
    )
    assert results[0] is not None
    assert results[0].get("selector") == "#add-to-cart-sauce-labs-backpack"
    # No clean alternative exists → deferred fallback fills the gap.
    assert results[1] is not None
    assert results[1].get("selector") == "h2.cart-title"


def test_excluded_selectors_never_leak_through_the_fallback() -> None:
    """A B-014-excluded candidate must not come back via the deferred slot."""
    matcher = _matcher()
    pages = {
        "https://x.test/page": [
            _el("h2.prev", "previous pick", computed_role="heading"),
        ]
    }
    matched = asyncio.run(
        matcher.find_best_element_for_current_page(
            action="CLICK",
            description="previous pick",
            current_url="https://x.test/page",
            pages_data=pages,
            excluded_selectors={"h2.prev"},
        )
    )
    assert matched is None
