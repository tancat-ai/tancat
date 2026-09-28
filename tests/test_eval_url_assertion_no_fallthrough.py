"""B-093: a URL assertion must never silently become an element assertion.

``eval_resolver._resolve_placeholder`` is the kind decision for the replay
harness. A criterion whose golden classification is ``url_assertion`` can only
be answered by the URL branch. When that branch yields no URL, the old code
fell through to element matching and returned a lookalike element (``.title``
for "cart page title"). The emitted check then passed while proving the wrong
kind of thing - a false green.

These tests pin the guard: no URL from the URL branch means no element assert.
The control test proves an ordinary element criterion is unchanged.
"""

from __future__ import annotations

from typing import Any

from scripts.eval.eval_resolver import _resolve_placeholder

CART = "http://localhost:8781/cart.html"

PAGES: dict[str, list[dict[str, str]]] = {
    CART: [{"selector": ".title", "tag": "h1", "text": "Shopping Cart"}],
}


class _LookalikeElementMatcher:
    """Returns a plausible wrong element and records that element matching ran."""

    def __init__(self) -> None:
        self.pass1_called = False

    def pass0_exact_text_match(self, *args: Any, **kwargs: Any) -> None:
        return None

    def pass1_text_match(self, *args: Any, **kwargs: Any) -> dict[str, str]:
        self.pass1_called = True
        return {"selector": ".title", "text": "Shopping Cart"}


def test_url_assertion_without_url_does_not_fall_through_to_elements() -> None:
    """Expected type is a URL assertion -> an element assert is the wrong check.

    The URL branch produced nothing (no flow store, so no URL). The resolver
    must refuse, not answer with ``.title``.
    """
    matcher = _LookalikeElementMatcher()

    resolved = _resolve_placeholder(
        action="ASSERT",
        description="cart page title",
        pages_data=PAGES,
        expected_page=CART,
        element_matcher=matcher,
        flow_store=None,
        expected_type="url_assertion",
    )

    assert resolved is None
    assert matcher.pass1_called is False


def test_url_assertion_goldens_reach_the_guard() -> None:
    """The harness must hand ``expected_type`` to the guard, or the guard is dead.

    ``run_resolver_eval`` reads its placeholders from
    ``_load_golden_placeholders``. If that loader drops ``expected_type``, every
    golden URL assertion reaches the resolver as a plain element criterion and
    the guard above never runs - the defect the guard exists to stop.
    """
    from scripts.eval.eval_resolver import _load_golden_placeholders

    placeholders = _load_golden_placeholders()
    url_asserts = [p for p in placeholders if p.get("expected_type") == "url_assertion"]
    assert url_asserts, "goldens must expose url_assertion placeholders"

    matcher = _LookalikeElementMatcher()
    target = url_asserts[0]
    resolved = _resolve_placeholder(
        action=target["action"],
        description=target["description"],
        pages_data=PAGES,
        expected_page=target["expected_page"],
        element_matcher=matcher,
        flow_store=None,
        expected_type=target["expected_type"],
    )

    assert resolved is None
    assert matcher.pass1_called is False


def test_element_criterion_still_resolves_by_element() -> None:
    """Control: a criterion with no URL classification is untouched."""
    matcher = _LookalikeElementMatcher()

    resolved = _resolve_placeholder(
        action="ASSERT",
        description="cart page title",
        pages_data=PAGES,
        expected_page=CART,
        element_matcher=matcher,
        flow_store=None,
        expected_type=None,
    )

    assert resolved == ".title"
    assert matcher.pass1_called is True
