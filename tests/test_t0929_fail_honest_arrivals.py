"""t-0929: fail honestly when the browser and the assertion disagree.

Owner's decision (2026-10-25): when an observation exists and the observed page
differs from the assertion's candidate, the pipeline must NOT rewrite the
candidate to the observed page (AI-051) and must NOT turn the divergence into a
skip (the t-0890 rule's second path). It emits a real failing assertion that
names both pages. Currently-green stories may go red; those reds are capture
defects, and exposing them is the point.

The no-observation skip stays exactly as it is: two shapes, two results.

    no observation at all          -> skip (unchanged)
    an observation of the wrong page -> failure (new)
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.evidence_tracker import EvidenceTracker
from src.journey_models import ObservedStep, ObservedTrail
from src.pipeline_models import PlaceholderUse, TestJourney, TestStep
from src.placeholder_orchestrator import PlaceholderOrchestrator

SHOP = "https://shop.example.com/"
CART = "https://shop.example.com/checkout.html"


def _el(selector: str, text: str, **extra: Any) -> dict[str, Any]:
    element: dict[str, Any] = {"selector": selector, "text": text, "tag": "a", "role": "link"}
    element.update(extra)
    return element


def _scraped() -> dict[str, list[dict[str, Any]]]:
    return {
        SHOP: [
            _el("#submit-order", "Submit order", tag="button", role="button"),
            _el("#cancel", "Cancel", tag="button", role="button"),
        ],
        CART: [_el("h1", "Checkout", tag="h1")],
    }


def _journey() -> tuple[str, TestJourney]:
    lines = [
        "def test_go_to_cart(page, evidence_tracker) -> None:",
        "    act('{{CLICK:Submit order}}')",
        "    act('{{ASSERT:checkout page loaded}}')",
    ]
    steps = [
        TestStep(
            line_number=2,
            raw_line=lines[1],
            placeholders=[
                PlaceholderUse(
                    token="{{CLICK:Submit order}}",
                    action="CLICK",
                    description="Submit order",
                    line_number=2,
                    raw_line=lines[1],
                )
            ],
        ),
        TestStep(
            line_number=3,
            raw_line=lines[2],
            placeholders=[
                PlaceholderUse(
                    token="{{ASSERT:checkout page loaded}}",
                    action="ASSERT",
                    description="checkout page loaded",
                    line_number=3,
                    raw_line=lines[2],
                )
            ],
        ),
    ]
    return "\n".join(lines), TestJourney(test_name="test_go_to_cart", start_line=1, end_line=3, steps=steps)


def _resolve(trail: ObservedTrail) -> str:
    skeleton, journey = _journey()
    orch = PlaceholderOrchestrator(starting_url=SHOP)
    return asyncio.run(
        orch._replace_placeholders_sequentially(  # noqa: SLF001
            skeleton_code=skeleton,
            journeys=[journey],
            page_requirements=[],
            seed_urls=[SHOP],
            scraped_data=_scraped(),
            observed_trails={"test_go_to_cart": trail},
        )
    )


def _trail(*, navigated: bool, with_assert_step: bool = True) -> ObservedTrail:
    steps = [
        ObservedStep(
            0,
            "click",
            description="Submit order",
            from_url=SHOP,
            to_url=CART if navigated else SHOP,
            navigated=navigated,
            scraped=True,
            selector_used="#submit-order",
            timestamp=1_760_000_000.0,
        )
    ]
    if with_assert_step:
        steps.append(
            ObservedStep(
                1,
                "scrape",
                description="checkout page loaded",
                from_url=CART if navigated else SHOP,
                to_url=CART if navigated else SHOP,
                navigated=False,
                scraped=True,
                timestamp=1_760_000_001.0,
            )
        )
    return ObservedTrail(steps=steps)


class _Expectation:
    """Minimal Playwright-like URL expectation (names both pages on failure)."""

    def __init__(self, page: Any) -> None:
        self.page = page

    def to_have_url(self, expected: str) -> None:
        received = str(self.page.url)
        if received != expected:
            raise AssertionError(f"Expected string: {expected!r}\nReceived string: {received!r}")


def _fake_expect(page: Any) -> _Expectation:
    return _Expectation(page)


class _FakePage:
    def __init__(self, url: str) -> None:
        self.url = url


class _FakeTracker:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def click(self, *args: Any, **kwargs: Any) -> None:
        return None

    def record_page_expectation(self, expected_url: str, **kwargs: Any) -> None:
        self.records.append({"expected_url": expected_url, **kwargs})


def _run_emitted(code: str, page: Any, tracker: _FakeTracker) -> None:
    namespace: dict[str, Any] = {
        "expect": _fake_expect,
        "page": page,
        "evidence_tracker": tracker,
    }
    exec(code, namespace)  # noqa: S102 - test-only execution of emitted source
    namespace["test_go_to_cart"](page, tracker)


# -- 1. candidate checkout, browser stayed on shop -> failing assertion ----


def test_candidate_vs_observed_checkout_failure_names_both_pages() -> None:
    code = _resolve(_trail(navigated=False))
    tracker = _FakeTracker()

    with pytest.raises(AssertionError) as excinfo:
        _run_emitted(code, _FakePage(SHOP), tracker)

    message = str(excinfo.value)
    assert CART in message, f"the failure did not name the candidate page:\n{message}"
    assert SHOP in message, f"the failure did not name the observed page:\n{message}"

    assert "pytest.skip" not in code, f"an observed mismatch was hidden as a skip:\n{code}"
    assert len(tracker.records) == 1, code
    record = tracker.records[0]
    assert record["expected_url"] == CART
    assert record["observed_url"] == SHOP
    assert record["producer"] == "keyword"
    assert record["trail_step"].startswith("index=1; action=scrape;")
    assert "timestamp=1760000001.0" in record["trail_step"], record["trail_step"]
    assert record["reason"], "the honest failure reason was not recorded"


# -- 2. nothing observed for the step -> skip, unchanged -------------------


def test_nothing_observed_for_step_still_skips() -> None:
    code = _resolve(_trail(navigated=False, with_assert_step=False))

    assert "pytest.skip" in code
    assert "to_have_url" not in code, f"an arrival was asserted without observation:\n{code}"
    assert "page arrival not asserted" in code
    assert "no observed landing" in code


# -- 3. candidate matches the observed page -> passes, unchanged ----------


def test_candidate_matches_observation_still_passes() -> None:
    code = _resolve(_trail(navigated=True))
    tracker = _FakeTracker()

    _run_emitted(code, _FakePage(CART), tracker)

    assert f'to_have_url("{CART}")' in code
    assert "pytest.skip" not in code
    assert tracker.records[0]["expected_url"] == CART
    assert tracker.records[0]["observed_url"] == CART


# -- 4. the assertion line stays literal for golden_validator gate 1 ------


def test_emitted_source_has_literal_to_have_url_with_candidate_url() -> None:
    code = _resolve(_trail(navigated=False))

    literal = re.search(r'^\s*expect\(page\)\.to_have_url\("([^"]+)"\)\s*$', code, re.MULTILINE)
    assert literal is not None, f"the literal assertion line is missing:\n{code}"
    assert literal.group(1) == CART
    # The record line is immediately before the assertion (only a comment may
    # separate nothing: the record must be the previous code line).
    lines = [line for line in code.splitlines() if line.strip()]
    assertion_index = next(i for i, line in enumerate(lines) if "to_have_url(" in line)
    assert "record_page_expectation(" in lines[assertion_index - 1], code


# -- 5. the evidence record is provable in the sidecar ---------------------


def test_evidence_record_carries_timestamp_trail_step_and_producer(tmp_path: Path) -> None:
    page = MagicMock()
    page.url = SHOP
    tracker = EvidenceTracker(page, "test_checkout", evidence_root=tmp_path)

    tracker.record_page_expectation(
        expected_url=CART,
        observed_url=SHOP,
        trail_step="index=1; action=scrape; timestamp=1760000001.0",
        producer="keyword",
        description="checkout page loaded",
        reason="the browser was not seen leaving the shop page",
    )

    sidecar = json.loads(tracker.sidecar_path.read_text(encoding="utf-8"))
    assert len(sidecar["page_expectations"]) == 1
    record = sidecar["page_expectations"][0]
    assert record["timestamp"] > 0
    assert record["expected_url"] == CART
    assert record["observed_url"] == SHOP
    assert record["actual_url"] == SHOP
    assert record["trail_step"].startswith("index=1; action=scrape;")
    assert record["producer"] == "keyword"
    assert record["reason"]
