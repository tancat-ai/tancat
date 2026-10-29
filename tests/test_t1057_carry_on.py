"""t-1057: a failed step must not end its test - finish the journey, report once.

Owner's decision, 2026-10-29: "carry on as well... some links might not be static
so they might change every single time... in that situation we want the test to be
able to carry on."

Each criterion is its own pytest test (no ``-x``), so a failed step never stopped
the RUN - but it did end that test, and the sidecar held no step after it. Now:

- the tracker records the failed step and CARRIES ON with the remaining steps;
- every later step is stamped ``result.off_course`` with the page the journey did
  not reach, so a pass after a redirect is never a clean pass;
- the generated conftest fails the test ONCE, at its end, with
  ``journey_summary()`` - the failed step, what it expected, what the browser
  reached, and how many later steps ran and passed;
- the single stop condition is a page or browser context that is closed, because
  no later step could run at all.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.evidence_tracker import EvidenceTracker

_CONFTEST = Path(__file__).resolve().parent.parent / "generated_tests" / "conftest.py"


def _conftest_module() -> Any:
    import sys

    spec = importlib.util.spec_from_file_location("generated_conftest_t1057", _CONFTEST)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # A dataclass in the module needs its own entry while the body executes.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _page(url: str, *, closed: bool = False) -> MagicMock:
    page = MagicMock()
    page.url = url
    page.is_closed.return_value = closed
    page.context.is_closed.return_value = False
    response = MagicMock()
    response.status = 200
    page.goto.return_value = response
    return page


def _tracker(page: Any, tmp_path: Path) -> EvidenceTracker:
    tracker = EvidenceTracker(page, "test_journey", "C01", "S01", evidence_root=Path(tmp_path))
    # The hand-shake the generated conftest performs: from here, a failed step is
    # recorded and the journey carries on, and the test is failed at its end.
    tracker.journey_hooked = True
    return tracker


def _journey_that_fails_at_step_three(tmp_path: Path) -> EvidenceTracker:
    """Five steps: the third is a goto that lands on the login page."""
    page = _page("https://shop.example.com/login")
    # Step 2 finds the field; step 4 and 5 find their targets. Step 3 is the
    # navigation, which the tracker judges against the page it asked for.
    page.locator.return_value.first.count.return_value = 1
    tracker = _tracker(page, tmp_path)

    tracker.navigate("https://shop.example.com/login")  # 1 passes
    tracker.fill("#user-name", "shopper")  # 2 passes
    tracker.navigate(  # 3 FAILS - the browser is on /login, not the cart
        "https://shop.example.com/cart.html",
        expected_page="https://shop.example.com/cart.html",
    )
    tracker.fill("#coupon", "SAVE10")  # 4 passes, on the page it did not expect
    tracker.assert_visible("#cart-summary")  # 5 passes, on that page too
    return tracker


def test_a_journey_that_fails_at_step_three_carries_on_and_reports_once(tmp_path: Path) -> None:
    tracker = _journey_that_fails_at_step_three(tmp_path)

    statuses = [step["result"]["status"] for step in tracker.steps]
    assert statuses == ["passed", "passed", "failed", "passed", "passed"]

    failures = tracker.journey_failures()
    assert len(failures) == 1
    assert failures[0]["step"] == 3

    summary = tracker.journey_summary()
    assert "Step 3" in summary
    assert "https://shop.example.com/cart.html" in summary  # what it expected
    assert "https://shop.example.com/login" in summary  # what it got
    assert "2 later step(s) ran" in summary
    assert "None of those passes is a clean pass" in summary


def test_later_steps_are_marked_as_off_course(tmp_path: Path) -> None:
    tracker = _journey_that_fails_at_step_three(tmp_path)

    first, second, failed, fourth, fifth = tracker.steps
    assert "off_course" not in first["result"]
    assert "off_course" not in second["result"]
    assert "off_course" not in failed["result"]  # the failing step is the failure itself
    for step in (fourth, fifth):
        assert step["result"]["off_course"] == {
            "failed_step": 3,
            "expected": "https://shop.example.com/cart.html",
            "actual": "https://shop.example.com/login",
        }


def test_the_generated_conftest_fails_the_test_once_with_the_summary() -> None:
    """The end-of-test failure: one report, the summary as its text."""
    conftest = _conftest_module()
    tracker = MagicMock()
    tracker.journey_summary.return_value = "Step 3 'x' failed: expected A, reached B"

    class _Item:
        _evidence_tracker: Any = None

    item = _Item()
    item._evidence_tracker = tracker

    class _Rep:
        when = "call"
        outcome = "passed"
        longrepr = None

        @property
        def passed(self) -> bool:
            return self.outcome == "passed"

    rep = _Rep()

    class _Outcome:
        def get_result(self) -> _Rep:
            return rep

    hook = conftest.pytest_runtest_makereport(item, None)
    next(hook)
    with pytest.raises(StopIteration):
        hook.send(_Outcome())

    assert rep.outcome == "failed"
    assert rep.longrepr == "Step 3 'x' failed: expected A, reached B"


def test_a_journey_with_no_failure_is_unchanged(tmp_path: Path) -> None:
    page = _page("https://shop.example.com/cart.html")
    tracker = _tracker(page, tmp_path)

    tracker.navigate("https://shop.example.com/cart.html", expected_page="https://shop.example.com/cart.html")
    tracker.fill("#coupon", "SAVE10")
    tracker.assert_visible("#cart-summary")

    assert [step["result"]["status"] for step in tracker.steps] == ["passed", "passed", "passed"]
    assert all("off_course" not in step["result"] for step in tracker.steps)
    assert tracker.journey_failures() == []
    assert tracker.journey_summary() == ""

    # The conftest hook must leave a clean test alone.
    conftest = _conftest_module()

    class _Item:
        _evidence_tracker: Any = None

    item = _Item()
    item._evidence_tracker = tracker

    class _Rep:
        when = "call"
        outcome = "passed"
        longrepr = None

        @property
        def passed(self) -> bool:
            return self.outcome == "passed"

    rep = _Rep()
    hook = conftest.pytest_runtest_makereport(item, None)
    next(hook)
    with pytest.raises(StopIteration):
        hook.send(type("O", (), {"get_result": lambda self: rep})())
    assert rep.outcome == "passed"


def test_a_closed_page_stops_the_journey_and_says_so(tmp_path: Path) -> None:
    """The only stop condition: later steps could not run at all."""
    page = _page("https://shop.example.com/", closed=True)
    page.goto.side_effect = Exception("Target page, context or browser has been closed")
    tracker = _tracker(page, tmp_path)

    with pytest.raises(Exception, match="has been closed"):
        tracker.navigate("https://shop.example.com/cart.html")

    step = tracker.steps[-1]
    assert step["result"]["status"] == "failed"
    assert "has been closed" in step["result"]["error"]


def test_a_same_identity_redirect_still_passes_and_is_recorded(tmp_path: Path) -> None:
    page = _page("https://shop.example.com/cart/")
    tracker = _tracker(page, tmp_path)

    tracker.navigate("https://shop.example.com/cart", expected_page="https://shop.example.com/cart")

    step = tracker.steps[-1]
    assert step["result"]["status"] == "passed"
    assert step["result"]["navigation"]["redirected"] is True
    assert tracker.journey_summary() == ""
