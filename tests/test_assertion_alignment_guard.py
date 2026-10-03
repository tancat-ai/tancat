"""t-0354: the deterministic half of step / expected-result alignment.

The prompt asks the model to match an ASSERT's specificity to the criterion's
openness. These tests cover the deterministic guard that enforces it where the
criterion's cue survives into the emitted description.

Directions:

- OPEN criterion + instance-pinned (DIRECT) check -> refuse (honest skip): the
  check would false-negative if the run legitimately picked a different outcome.
- FIXED criterion + generic (PROPERTY) check -> flag only: the instance the
  criterion meant is not recoverable, so nothing is rewritten.
- Aligned pairs -> emitted unchanged.
"""

from __future__ import annotations

from src.assertion_alignment import (
    AlignmentDecision,
    alignment_decision,
    classify_assertion,
    classify_openness,
    locator_is_loose,
)
from src.code_postprocessor import replace_token_in_line

TOKEN = "{{ASSERT:cart}}"


def _emit(description: str, locator: str, assertion_type: str = "toBeVisible") -> str:
    # A bare token line is the shape that reaches the single-element ASSERT path
    # (the count / page-fact / section routers are tried first and would divert
    # a description that carries their wording).
    line = f"    {TOKEN}"
    return replace_token_in_line(
        line,
        "ASSERT",
        TOKEN,
        repr(locator),
        set(),
        description,
        assertion_type=assertion_type,
    )


# -- the two directions ------------------------------------------------------


def test_open_criterion_with_instance_pinned_check_is_refused() -> None:
    """OPEN + DIRECT -> refuse. The example instance must not become the check.

    Live case (t-0316): an open step "add at least one item (e.g. Sauce Labs
    Backpack)" resolved to `#remove-sauce-labs-backpack`; asserting that instance
    fails when a different, equally valid item was added.
    """
    decision = alignment_decision(
        "at least one added item is shown in the cart", "assert_visible", "#remove-sauce-labs-backpack"
    )
    assert decision.action == "refuse"
    assert decision.reason

    code = _emit("at least one added item is shown in the cart", "#remove-sauce-labs-backpack")
    assert "pytest.skip(" in code
    assert "evidence_tracker.assert_visible" not in code


def test_fixed_criterion_with_generic_check_is_flagged_not_rewritten() -> None:
    """FIXED + PROPERTY -> flag only; the intended instance is not recoverable.

    Live case (t-0316): "Navigate to the main page" asserted `assert_visible`
    on `#content`, the page-wide wrapper.
    """
    decision = alignment_decision("home page loaded", "assert_visible", "#content")
    assert decision.action == "flag"
    assert decision.reason

    # Flagging is non-destructive: the emitted check is unchanged.
    code = _emit("home page loaded", "#content")
    assert "evidence_tracker.assert_visible('#content', label=" in code
    assert "pytest.skip(" not in code


# -- aligned pairs: unchanged -------------------------------------------------


def test_aligned_pairs_are_left_unchanged() -> None:
    """OPEN + PROPERTY and FIXED + DIRECT are aligned; neither is touched."""
    open_property = alignment_decision("at least one item row is present", "assert_count_at_least", ".cart_item")
    assert open_property == AlignmentDecision(action="aligned", reason="")

    fixed_direct = alignment_decision("the add to cart button is shown", "assert_visible", "#add-to-cart-blue-top")
    assert fixed_direct == AlignmentDecision(action="aligned", reason="")

    code = _emit("the add to cart button is shown", "#add-to-cart-blue-top")
    assert "evidence_tracker.assert_visible('#add-to-cart-blue-top', label=" in code
    assert "pytest.skip(" not in code


# -- the cue classifier -------------------------------------------------------


def test_openness_cues() -> None:
    assert classify_openness("add at least one item to the cart") == "OPEN"
    assert classify_openness("select a radio option (e.g. Male)") == "OPEN"
    assert classify_openness("verify the Blue Top price") == "FIXED"
    assert classify_openness("") == "FIXED"


def test_assertion_classification() -> None:
    assert classify_assertion("to_have_url", "https://x/cart.html") == "DIRECT"
    assert classify_assertion("assert_visible", "#remove-sauce-labs-backpack") == "DIRECT"
    assert classify_assertion("assert_visible", "#content") == "PROPERTY"
    assert classify_assertion("assert_visible", ".text") == "PROPERTY"
    assert classify_assertion("assert_count_at_least", "#anything") == "PROPERTY"
    assert locator_is_loose("#content") is True
    assert locator_is_loose("#gender-radio-1") is False
