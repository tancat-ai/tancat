"""t-1095: when a generated test carries on, and the four reasons it stops.

The owner's rule, 2026-10-29: as a manual tester he would not stop at "couldn't add
driver" - he would carry on through the other pages and extras, because that is
where other defects are. So CONTINUE by default, and stop only for a reason that
has nothing to do with what the step wanted.

CONTINUE after: an element not found; a click that does nothing; a click that lands
on a page other than the expected one; an assertion failure; a 404/500 page that
still has a document.

STOP, and only for these four:
1. ``page_gone``       - the page/context closed, the target crashed, protocol error.
2. ``unresponsive``    - a liveness probe after the failure raised.
3. ``no_arrival``      - a step whose job is to change the page did not change it.
4. ``time_limit``      - the per-test backstop.

Rule 3 arms only for steps the emitter knows must move: ``navigate`` always, and
``click`` only when the caller passes ``must_move=True``. A fill or an assertion
never arms it, and a click the story does not expect to navigate must not either.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import src.evidence_tracker as tracker_module
from src.evidence_tracker import (
    STOP_NO_ARRIVAL,
    STOP_PAGE_GONE,
    STOP_TIME_LIMIT,
    STOP_UNRESPONSIVE,
    EvidenceTracker,
    JourneyStopped,
)
from src.report_formatters import generate_html_report, journey_lines


class _Locator:
    def __init__(self, page: _Page, fail: bool) -> None:
        self._page = page
        self._fail = fail

    @property
    def first(self) -> _Locator:
        return self

    def count(self) -> int:
        return 0 if self._fail else 1

    def _action(self) -> None:
        if self._fail:
            raise TimeoutError("element not visible")
        self._page.clicks += 1

    def wait_for(self, **_: Any) -> None:
        self._action()

    def fill(self, _value: str) -> None:
        self._action()

    def click(self, **_kwargs: Any) -> None:
        self._action()
        if self._page.click_moves:
            self._page.url = self._page.click_moves

    def scroll_into_view_if_needed(self, **_kwargs: Any) -> None:
        return None

    def text_content(self) -> str:
        return "text"

    def get_attribute(self, _name: str) -> str | None:
        return None

    def is_visible(self) -> bool:
        return not self._fail

    def bounding_box(self) -> dict[str, float]:
        return {"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0}

    def evaluate(self, _script: str, *_args: Any) -> Any:
        return None


class _Page:
    """A page whose evidence is plain JSON; behaviour is switched per test."""

    def __init__(
        self,
        url: str,
        *,
        failing: str = "",
        probe_raises: bool = False,
        click_moves: str = "",
        goto_moves: bool = True,
    ) -> None:
        self.url = url
        self.failing = failing
        self.probe_raises = probe_raises
        self.click_moves = click_moves
        self.goto_moves = goto_moves
        self.clicks = 0
        self.context = self
        self.pages = [self]

    def is_closed(self) -> bool:
        return False

    def wait_for_timeout(self, _ms: int) -> None:
        return None

    def evaluate(self, _script: str, *_args: Any) -> Any:
        if self.probe_raises and "1" in _script:
            raise RuntimeError("Target page, context or browser has been closed")
        return None

    def screenshot(self, **_kwargs: Any) -> None:
        return None

    def goto(self, url: str) -> Any:
        if self.goto_moves:
            self.url = url
        from unittest.mock import MagicMock

        response = MagicMock()
        response.status = 200
        response.request = None
        return response

    def locator(self, selector: str) -> _Locator:
        return _Locator(self, bool(self.failing) and self.failing in selector)


def _tracker(page: Any, tmp_path: Path) -> EvidenceTracker:
    tracker = EvidenceTracker(page, "test_rules", "C01", "S01", evidence_root=Path(tmp_path))
    tracker.journey_hooked = True
    return tracker


def _statuses(tracker: EvidenceTracker) -> list[str]:
    return [step["result"]["status"] for step in tracker.steps]


# ---------------------------------------------------------------------------
# CONTINUE
# ---------------------------------------------------------------------------


def test_a_missing_element_continues(tmp_path: Path) -> None:
    page = _Page("https://shop.example.com/catalog.html", failing="#promo")
    tracker = _tracker(page, tmp_path)

    tracker.assert_visible("#promo")
    tracker.fill("#filters", "sale")
    tracker.assert_visible("#results")

    assert _statuses(tracker) == ["failed", "passed", "passed"]
    assert tracker.stop is None


def test_two_dead_clicks_continue(tmp_path: Path) -> None:
    page = _Page("https://shop.example.com/catalog.html", failing="#dead")
    tracker = _tracker(page, tmp_path)

    tracker.click("#dead")
    tracker.click("#dead")
    tracker.fill("#filters", "sale")

    assert _statuses(tracker) == ["failed", "failed", "passed"]
    assert tracker.stop is None


def test_a_click_to_an_unexpected_page_continues(tmp_path: Path) -> None:
    page = _Page("https://shop.example.com/checkout.html")
    tracker = _tracker(page, tmp_path)

    # The click moves the browser (to a page the click's expected page does not
    # name) - a real arrival, so the journey carries on.
    page.click_moves = "https://shop.example.com/login"
    tracker.click("#pay", expected_page="https://shop.example.com/cart.html")
    tracker.fill("#user", "shopper")

    assert tracker.steps[0]["result"]["status"] == "failed"
    assert tracker.steps[-1]["result"]["status"] == "passed"
    assert tracker.stop is None


def test_an_assertion_failure_continues(tmp_path: Path) -> None:
    page = _Page("https://shop.example.com/", failing="#total")
    tracker = _tracker(page, tmp_path)

    tracker.assert_visible("#total")
    tracker.assert_visible("#header")

    assert _statuses(tracker) == ["failed", "passed"]
    assert tracker.stop is None


def test_a_404_page_with_a_document_continues(tmp_path: Path) -> None:
    page = _Page("https://shop.example.com/missing.html")
    tracker = _tracker(page, tmp_path)
    page.goto = lambda url: _not_found(page, url)  # type: ignore[method-assign]

    tracker.navigate("https://shop.example.com/missing.html")
    tracker.assert_visible("#header")

    assert _statuses(tracker) == ["failed", "passed"]
    assert tracker.stop is None


def _not_found(page: _Page, url: str) -> Any:
    from unittest.mock import MagicMock

    page.url = url
    response = MagicMock()
    response.status = 404
    response.request = None
    return response


# ---------------------------------------------------------------------------
# STOP
# ---------------------------------------------------------------------------


def test_a_dead_navigate_stops_with_reason_three(tmp_path: Path) -> None:
    page = _Page("https://shop.example.com/cart.html", goto_moves=False)
    tracker = _tracker(page, tmp_path)

    with pytest.raises(JourneyStopped) as raised:
        tracker.navigate("https://shop.example.com/checkout.html")
    assert STOP_NO_ARRIVAL in str(raised.value)

    assert tracker.stop is not None
    assert tracker.stop["reason"] == "no_arrival"
    assert "did not change the page" in tracker.journey_summary()
    assert "stayed on" in tracker.journey_summary()
    # t-1098: exactly one step - the failing one - and no invented second step.
    assert len(tracker.steps) == 1
    assert tracker.steps[0]["result"]["status"] == "failed"
    assert [f["step"] for f in tracker.journey_failures()] == [1]
    assert "then the journey stopped" in tracker.journey_summary().splitlines()[0]
    assert "carried on" not in tracker.journey_summary().splitlines()[0]


def test_a_dead_must_move_click_stops_with_reason_three(tmp_path: Path) -> None:
    page = _Page("https://shop.example.com/cart.html")
    tracker = _tracker(page, tmp_path)

    with pytest.raises(JourneyStopped):
        tracker.click("#pay", must_move=True)

    assert tracker.stop is not None
    assert tracker.stop["reason"] == "no_arrival"
    assert "was expected to move the browser" in tracker.stop["detail"]
    assert len(tracker.steps) == 1  # t-1098: one step, the failing one
    assert tracker.steps[0]["result"]["status"] == "failed"


def test_a_stop_naming_a_hidden_label_is_not_caught_by_the_fallback(tmp_path: Path) -> None:
    """t-1100: the mention of "hidden" in a stop message must not hand the stop to
    the hover/scoring fallback, which would record a second, passing click step."""
    page = _Page("https://shop.example.com/catalog.html")
    tracker = _tracker(page, tmp_path)

    with pytest.raises(JourneyStopped):
        tracker.click("#hidden-tab", label="hidden tab", must_move=True)

    assert len(tracker.steps) == 1
    assert tracker.steps[0]["result"]["status"] == "failed"
    assert [f["step"] for f in tracker.journey_failures()] == [1]
    assert tracker.stop is not None
    assert tracker.stop["reason"] == "no_arrival"


def test_a_click_the_story_does_not_expect_to_move_never_arms_rule_three(tmp_path: Path) -> None:
    page = _Page("https://shop.example.com/catalog.html")
    tracker = _tracker(page, tmp_path)

    tracker.click("#add-to-cart")  # must_move defaults to False
    tracker.fill("#q", "boots")

    assert tracker.stop is None
    assert _statuses(tracker) == ["passed", "passed"]


def test_a_closed_page_stops_with_reason_one(tmp_path: Path) -> None:
    page = _Page("https://shop.example.com/")
    page.is_closed = lambda: True  # type: ignore[method-assign]
    tracker = _tracker(page, tmp_path)

    with pytest.raises(Exception, match="has been closed"):
        page.goto = lambda url: (_ for _ in ()).throw(  # type: ignore[method-assign]
            RuntimeError("Target page, context or browser has been closed")
        )
        tracker.navigate("https://shop.example.com/cart.html")

    assert tracker.stop is not None
    assert tracker.stop["reason"] == "page_gone"
    assert STOP_PAGE_GONE in tracker.journey_summary()


def test_a_failing_probe_stops_with_reason_two(tmp_path: Path) -> None:
    page = _Page("https://shop.example.com/catalog.html", failing="#promo", probe_raises=True)
    tracker = _tracker(page, tmp_path)

    with pytest.raises(JourneyStopped):
        tracker.assert_visible("#promo")

    assert tracker.stop is not None
    assert tracker.stop["reason"] == "unresponsive"
    assert STOP_UNRESPONSIVE in tracker.journey_summary()
    # The failed step is still recorded before the stop.
    assert tracker.steps[-1]["result"]["status"] == "failed"


def test_the_time_limit_stops_with_reason_four(tmp_path: Path) -> None:
    page = _Page("https://shop.example.com/")
    tracker = _tracker(page, tmp_path)
    tracker._time_limit_s = 0.001
    tracker.start_time -= 10

    with pytest.raises(JourneyStopped) as raised:
        tracker.fill("#q", "boots")

    assert STOP_TIME_LIMIT in str(raised.value)
    assert tracker.stop is not None
    assert tracker.stop["reason"] == "time_limit"
    assert "per-test limit" in tracker.stop["detail"]
    assert tracker.stop["detail"][0].isupper()  # t-1100: "... reached. The test ran 10s ..."


def test_the_time_limit_can_be_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITEST_TEST_TIME_LIMIT", "0")
    tracker = _tracker(_Page("https://shop.example.com/"), tmp_path)

    assert tracker._time_limit_s == 0.0
    assert tracker_module._test_time_limit_s() == 0.0


def test_the_other_tests_in_the_story_still_report(tmp_path: Path) -> None:
    """A stopped test is one test. Its siblings keep running and keep reporting."""
    page = _Page("https://shop.example.com/cart.html", goto_moves=False)
    stopped = _tracker(page, tmp_path)
    with pytest.raises(JourneyStopped):
        stopped.navigate("https://shop.example.com/checkout.html")

    sibling = EvidenceTracker(page, "test_sibling", "C02", "S01", evidence_root=Path(tmp_path))  # type: ignore[arg-type]
    sibling.journey_hooked = True
    sibling.fill("#q", "boots")

    assert sibling.stop is None
    assert _statuses(sibling) == ["passed"]


def test_a_query_only_move_continues(tmp_path: Path) -> None:
    """The page identity rule ignores the query by design; a MOVE does not (t-1098)."""
    page = _Page("https://shop.example.com/products")  # starts BEFORE the query
    tracker = _tracker(page, tmp_path)

    tracker.navigate("https://shop.example.com/products?page=2")
    tracker.assert_visible("#grid")

    assert _statuses(tracker) == ["passed", "passed"]
    assert tracker.stop is None


def test_a_fragment_only_move_continues(tmp_path: Path) -> None:
    page = _Page("https://shop.example.com/")  # starts BEFORE the fragment
    tracker = _tracker(page, tmp_path)

    tracker.navigate("https://shop.example.com/#pricing")
    tracker.assert_visible("#plans")

    assert _statuses(tracker) == ["passed", "passed"]
    assert tracker.stop is None


def test_a_trailing_slash_only_change_is_not_a_move(tmp_path: Path) -> None:
    """The other side of t-1098: "/cart" and "/cart/" are the same address."""
    page = _Page("https://shop.example.com/cart/")
    tracker = _tracker(page, tmp_path)
    page.url = "https://shop.example.com/cart/"  # the goto will not move it

    with pytest.raises(JourneyStopped):
        tracker.navigate("https://shop.example.com/cart/")

    assert tracker.stop is not None
    assert tracker.stop["reason"] == "no_arrival"


# ---------------------------------------------------------------------------
# The record and the report name the stop
# ---------------------------------------------------------------------------


def test_every_stop_reason_appears_in_the_report_text(tmp_path: Path) -> None:
    for reason, text in (
        ("page_gone", STOP_PAGE_GONE),
        ("unresponsive", STOP_UNRESPONSIVE),
        ("no_arrival", STOP_NO_ARRIVAL),
        ("time_limit", STOP_TIME_LIMIT),
    ):
        tracker = _tracker(_Page("https://shop.example.com/"), tmp_path)
        tracker.stop = {"reason": reason, "detail": "because"}
        summary = tracker.journey_summary()
        assert text in summary, reason
        assert "Journey stopped:" in summary
        assert "carried on" not in summary.splitlines()[0]

        record = tracker.journey_record()
        assert record["stop_text"] == text
        rows = journey_lines({"journey": record})
        assert rows[0][0] == "Stopped"
        assert text in rows[0][1]


def test_the_sidecar_carries_the_stop(tmp_path: Path) -> None:
    page = _Page("https://shop.example.com/cart.html", goto_moves=False)
    tracker = _tracker(page, tmp_path)
    with pytest.raises(JourneyStopped):
        tracker.navigate("https://shop.example.com/checkout.html")
    tracker.write(status="failed")

    payload = json.loads(Path(tracker.sidecar_path).read_text(encoding="utf-8"))
    assert payload["journey"]["stop"]["reason"] == "no_arrival"
    assert payload["journey"]["stop_text"] == STOP_NO_ARRIVAL
    assert "Journey stopped" in payload["journey"]["summary"]


def test_the_html_report_names_the_stop() -> None:
    row = {
        "test_name": "stopped journey",
        "status": "failed",
        "journey": {
            "failed_steps": [],
            "stop": {"reason": "no_arrival", "detail": "stayed on /cart"},
            "stop_text": STOP_NO_ARRIVAL,
        },
    }

    html = generate_html_report([row])

    assert "Stopped" in html
    assert "never reached its next page" in html


# ---------------------------------------------------------------------------
# The rules are named in the protocol the conftest checks
# ---------------------------------------------------------------------------


def test_the_protocol_marker_moved_with_the_rules() -> None:
    assert tracker_module.JOURNEY_PROTOCOL == "carry-on-2"
