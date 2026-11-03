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
    tracker.journey_hooked = True  # the conftest's hand-shake (t-1066)

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
    tracker.journey_hooked = True  # the conftest's hand-shake (t-1066)

    tracker.assert_hidden(".thing")  # t-1057: recorded, not raised
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
    journey_unresolved_keys: dict[str, set[tuple[int, str]]] = {}

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
        journey_unresolved_keys=journey_unresolved_keys,
        journey_name="test_01",
    )

    assert 5 in line_resolutions
    assert line_resolutions[5][0][6] == "toBeHidden"
    assert journey_unresolved == {}


# ─── t-1251: whole words, and a positive term wins ──────────────────────────

#: Each case is (description, expected assertion type). t-1251 pins both the
#: presence checks the substring match used to swallow and the true absences
#: that must not change.
_T1251_CASES: list[tuple[str, str | None]] = [
    # presence checks the old substring match read as absence
    ("the hidden discount is now shown", None),
    ("the removed item reappears", None),
    ("the dismissed items list is visible", None),
    ("the enclosed receipt is shown", None),
    ("details disclosed", None),
    # positive word that is itself denied: still an absence
    ("the promo banner is not visible", "toBeHidden"),
    ("the discount is no longer shown", "toBeHidden"),
    # true absences that must NOT change
    ("the promo banner closed", "toBeHidden"),
    ("the success message is gone", "toBeHidden"),
    ("the error was dismissed", "toBeHidden"),
    ("popup closed", "toBeHidden"),
    ("item removed", "toBeHidden"),
    # residue: a positive verb outside the agreed set - reported, not fixed here
    ("the hidden menu opens", "toBeHidden"),
    ("the hidden field is revealed", "toBeHidden"),
    ("the cart badge is no longer grey", "toBeHidden"),
]


async def _emitted_assertion(description: str) -> str:
    """Resolve one ASSERT through the real path and return the emitted call name."""

    from src.journey_models import ObservedStep, ObservedTrail
    from src.pipeline_models import PageRequirement, PlaceholderUse, TestJourney, TestStep
    from src.placeholder_orchestrator import PlaceholderOrchestrator

    url = "https://example.com/page"
    token = f"{{{{ASSERT:{description}}}}}"
    journey = TestJourney(
        test_name="test_polarity",
        start_line=1,
        end_line=2,
        steps=[
            TestStep(
                line_number=2,
                raw_line=token,
                placeholders=[
                    PlaceholderUse(token=token, action="ASSERT", description=description, line_number=2, raw_line=token)
                ],
            )
        ],
    )
    scraped = {
        url: [
            {"selector": "#target", "role": "text", "text": "x", "assertion_type": "toBeVisible"},
        ]
    }
    trail = ObservedTrail(
        steps=[ObservedStep(0, "scrape", description=description, from_url=url, to_url=url)],
        records_landings=False,
    )
    orchestrator = PlaceholderOrchestrator(starting_url=url)

    class _M:
        async def find_best_element_for_current_page(self, *_a: Any, **_k: Any) -> dict[str, str]:
            return dict(scraped[url][0])

        async def find_best_elements_batch(self, requests: list[dict[str, Any]], *_a: Any, **_k: Any) -> list[Any]:
            return [dict(scraped[url][0])]

    orchestrator._element_matcher = _M()  # type: ignore[assignment]  # noqa: SLF001
    emitted = await orchestrator._replace_placeholders_sequentially(  # noqa: SLF001 - the unit under test
        skeleton_code=f"def test_polarity(page):\n    {token}\n",
        journeys=[journey],
        page_requirements=[PageRequirement(keyword="page")],
        seed_urls=[url],
        scraped_data=scraped,
        scraped_errors={},
        observed_trails={"test_polarity": trail},
    )
    line = next(line for line in emitted.splitlines() if "assert_" in line)
    return str(line.strip().split("(")[0].split(".")[-1])


def test_t1251_predicate_types() -> None:
    for description, expected in _T1251_CASES:
        assert polarity_assertion_type(description) == expected, description


def test_t1251_emitted_assertion_type() -> None:
    """The predicate reaches the emitted call: assert_hidden or assert_visible."""
    import asyncio

    for description, expected in _T1251_CASES:
        call = asyncio.run(_emitted_assertion(description))
        want = "assert_hidden" if expected == "toBeHidden" else "assert_visible"
        assert call == want, f"{description}: emitted {call}, wanted {want}"
