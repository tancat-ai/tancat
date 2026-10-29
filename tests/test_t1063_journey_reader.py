"""t-1063: three follow-ons from the j-0228 review.

1. ``off_course`` is stamped after ANY first failure, not only one that names a
   page. A missing element names no page, and the marking does not need to know
   what failed - a pass after it must still never look clean.
2. The new record has a reader: the journey summary reaches the report the user
   reads (HTML and JSON), one short line per failed step plus the off-course note.
3. The tracker and the generated conftest agree on a protocol marker. A package
   with a new tracker and an old conftest would carry on and never fail the test -
   a silent success - so a mismatch fails loudly.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import src.evidence_tracker as tracker_module
from src.evidence_loader import get_failure_diagnostics
from src.evidence_serializer import EvidenceSerializer
from src.evidence_tracker import JOURNEY_PROTOCOL, EvidenceTracker
from src.report_builder import build_report_dicts
from src.report_formatters import generate_html_report, generate_local_report, journey_lines

_CONFTEST = Path(__file__).resolve().parent.parent / "generated_tests" / "conftest.py"


class _FakeLocator:
    """Minimal locator: visible unless it was built to fail."""

    def __init__(self, page: _FakePage, fail: bool) -> None:
        self._page = page
        self._fail = fail

    @property
    def first(self) -> _FakeLocator:
        return self

    def count(self) -> int:
        return 0 if self._fail else 1

    def wait_for(self, **_: Any) -> None:
        if self._fail:
            raise TimeoutError("element not visible")

    def fill(self, _value: str) -> None:
        if self._fail:
            raise TimeoutError("element not visible")

    def click(self) -> None:
        if self._fail:
            raise TimeoutError("element not visible")

    def text_content(self) -> str:
        return "filters"

    def get_attribute(self, _name: str) -> str | None:
        return None

    def is_visible(self) -> bool:
        return not self._fail

    def bounding_box(self) -> dict[str, float]:
        return {"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0}

    def evaluate(self, _script: str, *_args: Any) -> Any:
        return None


class _FakePage:
    """A page whose evidence is plain JSON, so the sidecar can be written."""

    def __init__(self, url: str, *, failing_locator: str = "") -> None:
        self.url = url
        self._failing = failing_locator
        self.context = self
        self.pages = [self]

    def is_closed(self) -> bool:
        return False

    def wait_for_timeout(self, _ms: int) -> None:
        return None

    def evaluate(self, _script: str, *_args: Any) -> Any:
        return None

    def screenshot(self, **_kwargs: Any) -> None:
        return None

    def goto(self, _url: str) -> Any:
        response = MagicMock()
        response.status = 200
        response.request = None
        return response

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator(self, bool(self._failing) and self._failing in selector)


def _page(url: str) -> MagicMock:
    page = MagicMock()
    page.url = url
    page.is_closed.return_value = False
    page.context.is_closed.return_value = False
    response = MagicMock()
    response.status = 200
    page.goto.return_value = response
    return page


def _tracker(page: Any, tmp_path: Path) -> EvidenceTracker:
    return EvidenceTracker(page, "test_journey", "C01", "S01", evidence_root=Path(tmp_path))


def _journey_with_a_missing_element(tmp_path: Path) -> EvidenceTracker:
    """Step 2 fails on a missing element - a failure that names no page."""
    page = _FakePage("https://shop.example.com/catalog.html", failing_locator="#promo-banner")
    tracker = _tracker(page, tmp_path)

    tracker.fill("#search", "boots")
    tracker.assert_visible("#promo-banner")  # fails: no such element
    tracker.fill("#filters", "sale")
    tracker.assert_visible("#results")
    return tracker


def test_a_missing_element_failure_marks_the_later_steps(tmp_path: Path) -> None:
    tracker = _journey_with_a_missing_element(tmp_path)

    assert [step["result"]["status"] for step in tracker.steps] == [
        "passed",
        "failed",
        "passed",
        "passed",
    ]
    later = tracker.steps[2:]
    for step in later:
        assert step["result"]["off_course"] == {"failed_step": 2}
    assert "off_course" not in tracker.steps[1]["result"]


def test_a_page_failure_still_marks_the_later_steps_with_both_pages(tmp_path: Path) -> None:
    page = _page("https://shop.example.com/login")
    tracker = _tracker(page, tmp_path)

    tracker.fill("#user", "u")
    tracker.navigate("https://shop.example.com/cart.html", expected_page="https://shop.example.com/cart.html")
    tracker.fill("#coupon", "X")

    marker = tracker.steps[2]["result"]["off_course"]
    assert marker == {
        "failed_step": 2,
        "expected": "https://shop.example.com/cart.html",
        "actual": "https://shop.example.com/login",
    }


def test_a_clean_test_carries_no_journey_record(tmp_path: Path) -> None:
    tracker = _tracker(_page("https://shop.example.com/"), tmp_path)
    tracker.fill("#q", "boots")

    assert tracker.journey_record() == {}


def test_the_sidecar_carries_the_journey(tmp_path: Path) -> None:
    tracker = _journey_with_a_missing_element(tmp_path)
    payload = json.loads(Path(tracker.write(status="failed")).read_text(encoding="utf-8"))

    journey = payload["journey"]
    assert journey["protocol"] == JOURNEY_PROTOCOL
    assert [f["step"] for f in journey["failed_steps"]] == [2]
    assert journey["later_steps"] == 2
    assert journey["summary"].startswith("1 step(s) failed")


def test_the_serializer_accepts_and_defaults_the_journey_block() -> None:
    without = json.loads(
        EvidenceSerializer.serialize(
            test_name="t",
            condition_ref="C",
            story_ref="S",
            status="passed",
            page_url="https://x/",
            run_history={},
            steps=[],
        )
    )
    assert without["journey"] == {}


# ---------------------------------------------------------------------------
# 2. The reader
# ---------------------------------------------------------------------------


def _report_row(tmp_path: Path, tracker: EvidenceTracker, status: str = "failed") -> dict[str, Any]:
    tracker.write(status=status)
    evidence = json.loads(Path(tracker.sidecar_path).read_text(encoding="utf-8"))
    diagnostics = get_failure_diagnostics(evidence)
    return {
        "test_name": "goes to the cart",
        "status": status,
        "journey": diagnostics.get("journey", {}),
    }


def test_the_report_row_carries_the_journey_summary(tmp_path: Path) -> None:
    tracker = _journey_with_a_missing_element(tmp_path)
    row = _report_row(tmp_path, tracker)

    assert row["journey"]["failed_steps"][0]["step"] == 2
    rows = journey_lines(row)
    assert rows[0][0] == "Step 2"
    assert rows[-1][0] == "Later steps"
    assert "2 ran, 2 passed" in rows[-1][2]


def test_the_html_report_contains_the_summary_and_the_off_course_note(tmp_path: Path) -> None:
    tracker = _journey_with_a_missing_element(tmp_path)
    html = generate_html_report([_report_row(tmp_path, tracker)])

    assert "Step 2" in html
    assert "Later steps" in html
    assert "none of those passes is clean" in html


def test_the_local_report_contains_the_journey_block(tmp_path: Path) -> None:
    tracker = _journey_with_a_missing_element(tmp_path)
    report = generate_local_report([_report_row(tmp_path, tracker)])

    assert "#### Journey" in report
    assert "Step 2" in report
    assert "Later steps" in report


def test_a_clean_test_adds_no_journey_line_to_the_report() -> None:
    row = {"test_name": "clean", "status": "passed", "journey": {}}

    assert journey_lines(row) == []
    assert "Later steps" not in generate_html_report([row])
    assert "#### Journey" not in generate_local_report([row])


def test_the_report_builder_passes_the_journey_through(tmp_path: Path) -> None:
    """The dict the app and the JSON export read carries the journey block."""
    tracker = _journey_with_a_missing_element(tmp_path)
    tracker.write(status="failed")
    package_dir = Path(tracker.sidecar_path).parent.parent
    coverage = {
        "requirements": [
            {"id": "TC01", "description": "goes to the cart", "status": "covered", "linked_tests": ["test_journey"]}
        ]
    }

    rows = build_report_dicts(coverage, None, package_dir=str(package_dir))

    assert rows and "journey" in rows[0]


# ---------------------------------------------------------------------------
# 3. The guard
# ---------------------------------------------------------------------------


def _conftest_module() -> Any:
    spec = importlib.util.spec_from_file_location("generated_conftest_t1063", _CONFTEST)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_the_tracker_and_the_conftest_agree_today() -> None:
    conftest = _conftest_module()

    assert conftest.CONFTEST_JOURNEY_PROTOCOL == JOURNEY_PROTOCOL
    conftest._check_journey_protocol()  # does not raise


def test_a_mismatched_conftest_marker_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    conftest = _conftest_module()
    monkeypatch.setattr(conftest, "CONFTEST_JOURNEY_PROTOCOL", "carry-on-0")

    with pytest.raises(RuntimeError) as raised:
        conftest._check_journey_protocol()

    message = str(raised.value)
    assert "journey protocol" in message
    assert "carry-on-0" in message
    assert JOURNEY_PROTOCOL in message
    assert "never fail" in message


def test_a_mismatched_tracker_marker_also_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    conftest = _conftest_module()
    monkeypatch.setattr(conftest, "JOURNEY_PROTOCOL", "carry-on-2")

    with pytest.raises(RuntimeError):
        conftest._check_journey_protocol()


def test_the_tracker_still_carries_the_marker() -> None:
    assert tracker_module.JOURNEY_PROTOCOL == JOURNEY_PROTOCOL
