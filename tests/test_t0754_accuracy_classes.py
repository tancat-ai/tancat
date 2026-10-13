"""t-0754 - the two still-open held-out accuracy classes.

Class A (wrong page pool for deferred ASSERTs, the hollow passes): in
``PlaceholderOrchestrator._batch_resolve_deferred_asserts`` each ASSERT is now
resolved against its own page cursor with its own previous-selector exclusion,
instead of one page and one exclusion for the whole batch.

Class C (no identity / success-vs-error polarity floor): in
``PlaceholderScorer.compute_element_score`` a message-like ASSERT that shares no
identity token with its criterion, or that names the opposite outcome, returns
``None`` (an honest skip) instead of a wrong-element match.

Every test here fails without its change.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.placeholder_orchestrator import PlaceholderOrchestrator
from src.placeholder_scorers import PlaceholderScorer

# ---------------------------------------------------------------------------
# Class C - identity + polarity floor
# ---------------------------------------------------------------------------


def _element(**overrides: Any) -> dict[str, Any]:
    element: dict[str, Any] = {
        "selector": "",
        "id": "",
        "text": "",
        "role": "",
        "tag": "",
        "classes": "",
        "href": "",
        "name": "",
        "aria_label": "",
        "aria_role": "",
        "data_test": "",
    }
    element.update(overrides)
    return element


def test_success_message_rejects_the_error_sibling() -> None:
    """eval-007 c5: "transfer success message" must not accept #transfer-error."""
    error = _element(
        selector="#transfer-error",
        id="transfer-error",
        text="Transfer failed",
        role="heading",
        tag="h2",
        classes="error",
    )

    score = PlaceholderScorer.compute_element_score(
        "ASSERT", "transfer success message", error, "#transfer-error", match_threshold=1
    )

    assert score is None
    assert PlaceholderScorer._message_outcome_conflict("transfer success message", error) is True


def test_success_message_accepts_the_success_sibling() -> None:
    """The floor must not reject the element the criterion actually names."""
    success = _element(
        selector="#transfer-success-title",
        id="transfer-success-title",
        text="Transfer successful",
        role="heading",
        tag="h1",
    )

    score = PlaceholderScorer.compute_element_score(
        "ASSERT", "transfer success message", success, "#transfer-success-title", match_threshold=1
    )

    assert score is not None
    assert score >= 1
    assert PlaceholderScorer._message_outcome_conflict("transfer success message", success) is False


def test_error_message_rejects_the_success_sibling() -> None:
    """The mirror: an error criterion must not accept a success element."""
    success = _element(
        selector="#payment-success-title",
        id="payment-success-title",
        text="Payment complete",
        role="heading",
        tag="h1",
    )

    score = PlaceholderScorer.compute_element_score(
        "ASSERT", "payment error message", success, "#payment-success-title", match_threshold=1
    )

    assert score is None


def test_message_identity_floor_rejects_a_bare_wrapper() -> None:
    """eval-003 c5: a bare ``.text`` wrapper shares no identity token -> skip."""
    wrapper = _element(selector=".text", classes="text", tag="div")

    score = PlaceholderScorer.compute_element_score(
        "ASSERT", "submission success message", wrapper, ".text", match_threshold=1
    )

    assert score is None
    assert PlaceholderScorer._assert_message_floor_rejects("submission success message", wrapper) is True


def test_non_message_assert_is_not_floored() -> None:
    """The floor is scoped to message-like ASSERTs; ordinary asserts are untouched."""
    item = _element(selector="[data-test='remove-sauce-labs-backpack']", text="Sauce Labs Backpack")

    floor_rejects = PlaceholderScorer._assert_message_floor_rejects("backpack item in cart", item)
    score = PlaceholderScorer.compute_element_score(
        "ASSERT", "backpack item in cart", item, "[data-test='remove-sauce-labs-backpack']", match_threshold=1
    )

    assert floor_rejects is False
    assert score is not None


def test_absence_assert_is_exempt_from_polarity() -> None:
    """An absence check ("no error message") asks for the opposite on purpose."""
    error = _element(selector="#transfer-error", id="transfer-error", text="Transfer failed", role="alert")

    assert PlaceholderScorer._message_outcome_conflict("no error message appears", error) is False


# ---------------------------------------------------------------------------
# Class A - deferred ASSERTs use their own page cursor and exclusion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deferred_asserts_use_own_exclusion_and_advance_the_page_cursor() -> None:
    """Each deferred ASSERT resolves on its own page and excludes its own previous element.

    Without the fix the batch uses one ``current_url`` (start) and one exclusion
    (the first ASSERT's ``#login``) for both ASSERTs, so ``#transfer-link`` is
    not excluded for the second ASSERT and the cursor never advances to the page
    the first match lived on.
    """
    orchestrator = PlaceholderOrchestrator()

    pages: dict[str, list[dict[str, str]]] = {
        "start": [{"selector": "#login", "role": "button"}],
        "dashboard": [{"selector": "#transfer-link", "role": "link", "href": "/transfer.html"}],
        "transfer_success": [{"selector": "#transfer-success-title", "role": "heading"}],
    }

    calls: list[dict[str, Any]] = []

    async def fake_batch(
        requests: list[dict[str, str]],
        current_url: str | None,
        pages_data: dict[str, list[dict[str, str]]],
        excluded_selectors: set[str] | None = None,
    ) -> list[dict[str, str] | None]:
        description = requests[0]["description"]
        calls.append(
            {
                "description": description,
                "current_url": current_url,
                "excluded": set(excluded_selectors or set()),
            }
        )
        if description == "transfer money link":
            return [{"selector": "#transfer-link", "role": "link"}]
        return [{"selector": "#transfer-success-title", "role": "heading"}]

    orchestrator._element_matcher.find_best_elements_batch = fake_batch  # type: ignore[method-assign]

    line_resolutions: dict[int, list[tuple[str, str, str, str, str, str | None, str | None]]] = {}
    journey_unresolved: dict[str, list[str]] = {}
    journey_unresolved_keys: dict[str, set[tuple[int, str]]] = {}

    await orchestrator._batch_resolve_deferred_asserts(
        deferred_asserts=[
            {
                "placeholder": SimpleNamespace(line_number=10, token="{{ASSERT:transfer money link}}"),
                "action": "ASSERT",
                "description": "transfer money link",
                "fill_value": "",
                "current_url": "start",
                "previous_selector": "#login",
                "previous_description": "sign in button",
            },
            {
                "placeholder": SimpleNamespace(line_number=11, token="{{ASSERT:transfer success message}}"),
                "action": "ASSERT",
                "description": "transfer success message",
                "fill_value": "",
                "current_url": "start",
                "previous_selector": "#transfer-link",
                "previous_description": "transfer money link",
            },
        ],
        scraped_data=pages,
        scraped_errors=None,
        fallback_url="start",
        line_resolutions=line_resolutions,
        journey_unresolved=journey_unresolved,
        journey_unresolved_keys=journey_unresolved_keys,
        journey_name="test_01",
    )

    # One resolution call per ASSERT (the old code made a single batched call).
    assert [call["current_url"] for call in calls] == ["start", "dashboard"]
    # The second ASSERT excludes its OWN previous element, not the first's #login.
    assert "#transfer-link" in calls[1]["excluded"]
    assert calls[1]["description"] == "transfer success message"
    # Both resolved; the second was found on the page the cursor advanced to.
    assert 10 in line_resolutions
    assert 11 in line_resolutions
    assert "#transfer-success-title" in line_resolutions[11][0][2]
    assert journey_unresolved == {}
