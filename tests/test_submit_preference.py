"""A commit-verb CLICK must prefer the submit control over a nav/back anchor (t-0572).

t-0567 diagnosed the trail gap: on the banking mock the commit step "Pay"
matched both the nav link ``a[href="/payments.html"]`` ("Pay Bills") and the
submit ``#pay-bill`` ("Pay Bill") at the fast-path 100, and the nav link won
the longest-text tie-break. The click never navigated, so the success ASSERT
was scoped to ``payments.html`` (``#payment-error``) instead of
``payment_success.html`` (``#payment-success-title``).

Before -> after (scorer, RAG off, ``match_threshold=1``):

| description | before | after |
|-------------|--------|-------|
| "Pay" | nav 100 / submit 100 -> nav wins (longer text) | submit 115 / nav 100 |
| "Pay Bill" | nav 100 / submit 100 -> nav wins | submit 115 / nav 100 |
| "Place Order" | back link matched first | submit 115 |
| "Cart" (non-commit) | unchanged | unchanged |
"""

from __future__ import annotations

from typing import Any

import pytest

from src.placeholder_resolver import PlaceholderResolver
from src.placeholder_scorers import PlaceholderScorer


def _element(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    base: dict[str, Any] = {
        "selector": "#x",
        "text": "",
        "name": "",
        "role": "",
        "tag": "",
        "href": "",
        "id": "",
        "data_test": "",
        "classes": "",
        "aria_label": "",
        "placeholder": "",
        "title": "",
        "value": "",
        "icon_classes": "",
        "visual_description": "",
        "parent_text": "",
        "is_visible": True,
        "is_icon": False,
        "is_decorative": False,
        "computed_role": "",
        "type": "",
    }
    if overrides:
        base.update(overrides)
    return base


_NAV_PAY_BILLS = _element(
    {"selector": 'a[href="/payments.html"]', "text": "Pay Bills", "role": "a", "tag": "a", "href": "/payments.html"}
)
_SUBMIT_PAY_BILL = _element(
    {"selector": "#pay-bill", "text": "Pay Bill", "role": "button", "tag": "button", "id": "pay-bill", "type": "submit"}
)
_BACK_TO_STORE = _element(
    {"selector": "#back-to-store", "text": "Back to Store", "role": "a", "tag": "a", "href": "/index.html"}
)
_SUBMIT_PLACE_ORDER = _element(
    {
        "selector": "#place-order",
        "text": "Place Order",
        "role": "button",
        "tag": "button",
        "id": "place-order",
        "type": "submit",
    }
)


def _ranked(description: str, pool: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    return PlaceholderResolver().rank_candidates("CLICK", description, pool)


def test_before_the_bonus_the_nav_link_wins_the_tie(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the pre-t-0572 behaviour: both score 100 and the nav link wins."""
    monkeypatch.setattr(PlaceholderScorer, "_commit_control_bonus", staticmethod(lambda *a, **k: 0))
    ranked = _ranked("Pay", [_NAV_PAY_BILLS, _SUBMIT_PAY_BILL])
    assert [s for s, _ in ranked] == [100, 100]
    assert ranked[0][1]["selector"] == 'a[href="/payments.html"]'


def test_commit_verb_pay_prefers_the_submit_control() -> None:
    """After: the submit control outranks the nav link for "Pay"."""
    ranked = _ranked("Pay", [_NAV_PAY_BILLS, _SUBMIT_PAY_BILL])
    assert ranked[0][1]["selector"] == "#pay-bill"
    assert ranked[0][0] > ranked[1][0]


def test_commit_verb_pay_bill_prefers_the_submit_control() -> None:
    ranked = _ranked("Pay Bill", [_NAV_PAY_BILLS, _SUBMIT_PAY_BILL])
    assert ranked[0][1]["selector"] == "#pay-bill"


def test_place_order_prefers_the_submit_over_the_back_link() -> None:
    ranked = _ranked("Place Order", [_BACK_TO_STORE, _SUBMIT_PLACE_ORDER])
    assert ranked[0][1]["selector"] == "#place-order"


def test_confirm_prefers_a_submit_control() -> None:
    confirm = _element({"selector": "#confirm", "text": "Confirm", "role": "button", "tag": "button", "type": "submit"})
    cancel = _element({"selector": "#cancel", "text": "Cancel order", "role": "a", "tag": "a", "href": "/cart.html"})
    ranked = _ranked("Confirm", [cancel, confirm])
    assert ranked[0][1]["selector"] == "#confirm"


def test_non_commit_click_is_unchanged() -> None:
    """A nav click ("Cart") must not get the commit bonus."""
    assert PlaceholderScorer._commit_control_bonus("CLICK", "Cart", _SUBMIT_PAY_BILL) == 0
    assert PlaceholderScorer._commit_control_bonus("CLICK", "Add to cart", _SUBMIT_PAY_BILL) == 0


def test_commit_bonus_only_applies_to_click() -> None:
    assert PlaceholderScorer._commit_control_bonus("FILL", "Pay", _SUBMIT_PAY_BILL) == 0
    assert PlaceholderScorer._commit_control_bonus("ASSERT", "payment success message", _SUBMIT_PAY_BILL) == 0


def test_submit_control_shapes_are_recognised() -> None:
    button = _element({"tag": "button", "text": "Pay"})
    input_submit = _element({"tag": "input", "type": "submit", "value": "Pay"})
    role_submit = _element({"tag": "div", "role": "submit", "text": "Pay"})
    plain_anchor = _element({"tag": "a", "href": "/pay", "text": "Pay"})
    assert PlaceholderScorer._commit_control_bonus("CLICK", "Pay", button) == 15
    assert PlaceholderScorer._commit_control_bonus("CLICK", "Pay", input_submit) == 15
    assert PlaceholderScorer._commit_control_bonus("CLICK", "Pay", role_submit) == 15
    assert PlaceholderScorer._commit_control_bonus("CLICK", "Pay", plain_anchor) == 0
