"""Tests for assertion-state polarity ("popup closed" → assert_hidden).

2026-08-03 — a production test asserted ``assert_visible('p.text-center',
label='popup closed')`` — the opposite of what "popup closed" means. Negative-
state ASSERT descriptions must emit a hidden/absence assertion (Playwright
``to_be_hidden()`` semantics), not ``assert_visible``.

Layers:
1. ``polarity_assertion_type`` (placeholder_orchestrator) — generic negative-
   state vocabulary (closed/gone/removed/hidden/...) → ``"toBeHidden"``.
2. ``_ASSERTION_TO_ET_METHOD`` (code_postprocessor) — ``toBeHidden`` →
   ``assert_hidden``.
3. ``EvidenceTracker.assert_hidden`` — ``wait_for(state="hidden")`` (passes for
   hidden OR detached nodes).
4. Orchestrator hooks apply the polarity at both resolution paths.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.code_postprocessor import _ASSERTION_TO_ET_METHOD, replace_token_in_line
from src.evidence_tracker import EvidenceTracker
from src.placeholder_orchestrator import PlaceholderOrchestrator, polarity_assertion_type

# ---------------------------------------------------------------------------
# polarity_assertion_type — description-side detection
# ---------------------------------------------------------------------------


def test_polarity_detection_matrix() -> None:
    cases: dict[str, str | None] = {
        "popup closed": "toBeHidden",
        "item removed from cart": "toBeHidden",
        "modal dismissed": "toBeHidden",
        "item disappeared": "toBeHidden",
        "product gone": "toBeHidden",
        "item hidden": "toBeHidden",
        "no longer visible": "toBeHidden",
        "not shown": "toBeHidden",
        # Positive / neutral descriptions must NOT be polarity-flipped
        "confirmation popup": None,
        "popup appears": None,
        "cart badge updated": None,
        "welcome message": None,
        "the close button is visible": None,
        "home page loaded": None,
        "product list": None,
    }
    for desc, expected in cases.items():
        got = polarity_assertion_type(desc)
        assert got == expected, f"{desc!r} → {got!r}, expected {expected!r}"


def test_polarity_ignores_present_tense_action_words() -> None:
    """'remove'/'close' as actions are NOT absence states."""
    assert polarity_assertion_type("remove button is visible") is None
    assert polarity_assertion_type("close button") is None
    assert polarity_assertion_type("item removed") == "toBeHidden"


# ---------------------------------------------------------------------------
# Emission — toBeHidden → assert_hidden
# ---------------------------------------------------------------------------


def test_assertion_type_to_et_method_maps_to_be_hidden() -> None:
    assert _ASSERTION_TO_ET_METHOD["toBeHidden"] == "assert_hidden"


def test_replace_token_in_line_emits_assert_hidden() -> None:
    emitted = replace_token_in_line(
        "    {{ASSERT:popup closed}}",
        "ASSERT",
        "{{ASSERT:popup closed}}",
        "'p.text-center'",
        set(),
        description="popup closed",
        assertion_type="toBeHidden",
    )
    assert emitted == "    evidence_tracker.assert_hidden('p.text-center', label='popup closed')"


def test_replace_token_in_line_default_still_assert_visible() -> None:
    emitted = replace_token_in_line(
        "    {{ASSERT:confirmation popup}}",
        "ASSERT",
        "{{ASSERT:confirmation popup}}",
        "'.modal-body'",
        set(),
        description="confirmation popup",
    )
    assert emitted == "    evidence_tracker.assert_visible('.modal-body', label='confirmation popup')"


# ---------------------------------------------------------------------------
# EvidenceTracker.assert_hidden
# ---------------------------------------------------------------------------


def test_assert_hidden_waits_for_hidden_state(tmp_path: Any) -> None:
    page_mock = MagicMock()
    tracker = EvidenceTracker(page_mock, "test_foo", "C01", "S01", evidence_root=Path(tmp_path))

    tracker.assert_hidden(".thing")

    loc = page_mock.locator.return_value.first
    assert loc.wait_for.call_count == 1
    assert loc.wait_for.call_args.kwargs.get("state") == "hidden"
    assert loc.wait_for.call_args.kwargs.get("timeout") == 5000
    assert tracker.steps[-1]["result"]["status"] == "passed"


def test_assert_hidden_records_failure_when_still_visible(tmp_path: Any) -> None:
    page_mock = MagicMock()
    loc = MagicMock()
    loc.first.wait_for.side_effect = TimeoutError("element still visible")
    page_mock.locator.return_value = loc
    tracker = EvidenceTracker(page_mock, "test_foo", evidence_root=Path(tmp_path))

    with pytest.raises(TimeoutError):
        tracker.assert_hidden(".thing")

    assert tracker.steps[-1]["result"]["status"] == "failed"
    assert "still visible" in tracker.steps[-1]["result"]["error"]


# ---------------------------------------------------------------------------
# Orchestrator hooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_placeholder_for_page_applies_polarity() -> None:
    orchestrator = PlaceholderOrchestrator()
    orchestrator._element_matcher.find_best_element_for_current_page = AsyncMock(  # type: ignore[method-assign]
        return_value={"selector": "p.text-center", "role": "p", "is_visible": False, "in_modal": True}
    )
    pages: dict[str, list[dict[str, str]]] = {"https://example.com": [{"selector": "p.text-center", "role": "p"}]}

    selector, _next_url, assertion_type = await orchestrator._resolve_placeholder_for_page(
        action="ASSERT",
        description="popup closed",
        current_url="https://example.com",
        scraped_data=pages,
        scraped_errors=None,
    )
    assert assertion_type == "toBeHidden"
    assert "text-center" in selector


@pytest.mark.asyncio
async def test_resolve_placeholder_for_page_positive_assert_unchanged() -> None:
    orchestrator = PlaceholderOrchestrator()
    orchestrator._element_matcher.find_best_element_for_current_page = AsyncMock(  # type: ignore[method-assign]
        return_value={"selector": ".modal-body", "role": "p"}
    )
    pages: dict[str, list[dict[str, str]]] = {"https://example.com": [{"selector": ".modal-body", "role": "p"}]}

    _selector, _next_url, assertion_type = await orchestrator._resolve_placeholder_for_page(
        action="ASSERT",
        description="confirmation popup",
        current_url="https://example.com",
        scraped_data=pages,
        scraped_errors=None,
    )
    assert assertion_type is None  # default toBeVisible applied at emission


@pytest.mark.asyncio
async def test_batch_resolve_applies_polarity() -> None:
    orchestrator = PlaceholderOrchestrator()
    orchestrator._element_matcher.find_best_elements_batch = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"selector": "p.text-center", "role": "p"}]
    )
    pages: dict[str, list[dict[str, str]]] = {"https://example.com": [{"selector": "p.text-center", "role": "p"}]}
    placeholder = SimpleNamespace(line_number=5, token="{{ASSERT:popup closed}}")
    line_resolutions: dict[int, list[tuple[str, str, str, str, str, str | None, str | None]]] = {}
    journey_unresolved: dict[str, list[str]] = {}

    await orchestrator._batch_resolve_deferred_asserts(
        deferred_asserts=[
            {
                "placeholder": placeholder,
                "action": "ASSERT",
                "description": "popup closed",
                "fill_value": "",
                "current_url": "https://example.com",
                "previous_selector": None,
                "previous_description": None,
            }
        ],
        scraped_data=pages,
        scraped_errors=None,
        fallback_url="https://example.com",
        line_resolutions=line_resolutions,
        journey_unresolved=journey_unresolved,
        journey_name="test_01",
    )

    assert 5 in line_resolutions
    assert line_resolutions[5][0][6] == "toBeHidden"
    assert journey_unresolved == {}
