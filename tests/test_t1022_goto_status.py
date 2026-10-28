"""t-1022 / d-0032: a plain goto step must not pass on a 404.

Measured 2026-10-28 (t-1017): ``EvidenceTracker.navigate`` threw away the response
from ``page.goto`` and ``_record_step`` recorded "passed" on "no exception
raised". Playwright raises only on network, protocol and timeout failures, so a
404, a 500 or a bounce home became a PASSED navigation step with a screenshot of
the error page as its evidence.

The owner's standing rule is fail honestly: a page the browser was not seen to
reach is not asserted. The fix reads the response:

- 4xx/5xx -> the step is failed and names the status and both addresses
  (``NavigationStatusError``).
- an ``expected_page`` the caller supplied, and the browser is not on it ->
  the failed shape a wrong-page step already uses (``page_mismatch``,
  ``PageMismatchError``).
- a redirect to another address with no expected page supplied -> the step is
  recorded with both addresses and a note, and is not judged: a canonical
  redirect and an auth bounce look identical from here, so failing both would be
  a false red.

The screenshot and the final address stay on the step in every case.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.evidence_tracker import (
    EvidenceTracker,
    NavigationStatusError,
    PageMismatchError,
    _response_status,
)


def _page(url: str, status: int | None) -> MagicMock:
    """A page double whose goto returns a response with *status*."""
    page = MagicMock()
    page.url = url
    response = MagicMock()
    if status is None:
        response.status = None
    else:
        response.status = status
    page.goto.return_value = response
    return page


def _tracker(page: Any, tmp_path: Path) -> EvidenceTracker:
    return EvidenceTracker(page, "test_goto", "C01", "S01", evidence_root=Path(tmp_path))


def test_404_goto_is_failed_and_names_both_urls(tmp_path: Path) -> None:
    requested = "https://shop.example.com/missing.html"
    landed = "https://shop.example.com/not-found"
    tracker = _tracker(_page(landed, 404), tmp_path)

    with pytest.raises(NavigationStatusError) as raised:
        tracker.navigate(requested)

    message = str(raised.value)
    assert "HTTP 404" in message
    assert requested in message
    assert landed in message

    step = tracker.steps[-1]
    assert step["type"] == "navigate"
    assert step["result"]["status"] == "failed"
    error = step["result"]["error"]
    assert "HTTP 404" in error
    assert requested in error
    assert landed in error
    # The evidence is kept: the screenshot and the address the browser reached.
    assert step["screenshot"] is not None
    assert step["url"] == landed
    assert step["result"]["navigation"] == {"requested": requested, "final": landed, "status": 404}
    assert len(tracker.steps) == 1  # recorded once, not twice


def test_500_goto_is_failed(tmp_path: Path) -> None:
    tracker = _tracker(_page("https://shop.example.com/error", 500), tmp_path)

    with pytest.raises(NavigationStatusError):
        tracker.navigate("https://shop.example.com/server")

    assert tracker.steps[-1]["result"]["status"] == "failed"
    assert "HTTP 500" in tracker.steps[-1]["result"]["error"]


def test_200_goto_on_the_right_page_passes(tmp_path: Path) -> None:
    url = "https://shop.example.com/cart.html"
    tracker = _tracker(_page(url, 200), tmp_path)

    tracker.navigate(url)

    step = tracker.steps[-1]
    assert step["result"]["status"] == "passed"
    assert step["result"]["error"] is None
    assert step["result"]["navigation"] == {"requested": url, "final": url, "status": 200}
    assert "redirected" not in step["result"]["navigation"]


def test_redirect_to_the_right_page_passes(tmp_path: Path) -> None:
    """A 302 to the same page (trailing slash) is arrival, not a failure."""
    tracker = _tracker(_page("https://shop.example.com/cart/", 200), tmp_path)

    tracker.navigate("https://shop.example.com/cart")

    step = tracker.steps[-1]
    assert step["result"]["status"] == "passed"
    assert "redirected" not in step["result"]["navigation"]


def test_redirect_to_a_named_expected_page_passes_and_is_recorded(tmp_path: Path) -> None:
    """The caller said where it should land; the redirect got it there."""
    tracker = _tracker(_page("https://shop.example.com/cart.html", 200), tmp_path)

    tracker.navigate("https://shop.example.com/old-cart", expected_page="https://shop.example.com/cart.html")

    step = tracker.steps[-1]
    assert step["result"]["status"] == "passed"
    nav = step["result"]["navigation"]
    assert nav["redirected"] is True
    assert nav["requested"] == "https://shop.example.com/old-cart"
    assert nav["final"] == "https://shop.example.com/cart.html"


def test_bounce_home_is_recorded_not_silent(tmp_path: Path) -> None:
    """No expected page supplied: both addresses are named on the step.

    Not judged, because a canonical redirect and an auth bounce are the same
    shape from here. The record says so rather than passing silently.
    """
    tracker = _tracker(_page("https://shop.example.com/", 200), tmp_path)

    tracker.navigate("https://shop.example.com/inventory.html")

    step = tracker.steps[-1]
    assert step["result"]["status"] == "passed"
    nav = step["result"]["navigation"]
    assert nav["redirected"] is True
    assert "inventory.html" in nav["note"]
    assert "https://shop.example.com/" in nav["note"]
    assert "recorded, not judged" in nav["note"]


def test_explicit_expected_page_mismatch_is_a_failed_step(tmp_path: Path) -> None:
    tracker = _tracker(_page("https://shop.example.com/", 200), tmp_path)

    with pytest.raises(PageMismatchError) as raised:
        tracker.navigate("https://shop.example.com/inventory.html", expected_page="https://shop.example.com/cart.html")

    message = str(raised.value)
    assert "https://shop.example.com/" in message
    assert "https://shop.example.com/cart.html" in message

    step = tracker.steps[-1]
    assert step["result"]["status"] == "failed"
    assert step["result"]["page_mismatch"] == {
        "expected": "https://shop.example.com/cart.html",
        "actual": "https://shop.example.com/",
    }
    assert "the step was asked for" in str(step["result"]["failure_note"])
    assert len(tracker.steps) == 1


def test_network_failure_still_records_one_failed_step(tmp_path: Path) -> None:
    page = MagicMock()
    page.goto.side_effect = Exception("Network Error")
    tracker = _tracker(page, tmp_path)

    with pytest.raises(Exception, match="Network Error"):
        tracker.navigate("https://fail.com")

    assert len(tracker.steps) == 1
    assert tracker.steps[0]["result"]["status"] == "failed"
    assert tracker.steps[0]["result"]["error"] == "Network Error"


def test_a_test_double_page_still_passes(tmp_path: Path) -> None:
    """Unknown status is never an error status (the double returns a MagicMock)."""
    tracker = _tracker(MagicMock(), tmp_path)

    tracker.navigate("https://example.com")

    assert tracker.steps[0]["result"]["status"] == "passed"


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (None, None),
        (MagicMock(), None),
        (MagicMock(status=None), None),
        (MagicMock(status=200), 200),
        (MagicMock(status=404), 404),
        (MagicMock(status=True), None),
        (MagicMock(status="404"), None),
    ],
)
def test_response_status_reads_only_a_real_status_code(response: Any, expected: int | None) -> None:
    assert _response_status(response) == expected


# ---------------------------------------------------------------------------
# t-1031 (j-0217 review): the goto mismatch must compare the page it LANDED on,
# not the page the previous step was entered on.
# ---------------------------------------------------------------------------


def test_navigate_with_expected_page_after_an_element_step_still_passes(tmp_path: Path) -> None:
    """The entry URL of the previous step must not leak into the goto's check.

    fill/click/assert_visible record ``_step_entry_url`` before they act. A
    navigate never did, so the goto compared its expected page against the
    PREVIOUS step's page and failed a correct arrival.
    """
    page = _page("https://shop.example.com/login", 200)
    tracker = _tracker(page, tmp_path)
    tracker.fill("#user-name", "standard_user")  # an element step on /login
    assert tracker._step_entry_url == "https://shop.example.com/login"

    landed = "https://shop.example.com/cart.html"
    page.url = landed
    page.goto.return_value.status = 200

    tracker.navigate(landed, expected_page=landed)

    step = tracker.steps[-1]
    assert step["type"] == "navigate"
    assert step["result"]["status"] == "passed"
    assert "page_mismatch" not in step["result"]
    assert tracker._step_entry_url == landed


def test_navigate_with_a_wrong_expected_page_after_an_element_step_still_fails(tmp_path: Path) -> None:
    """The fix must not weaken the check: the landed page is still compared."""
    page = _page("https://shop.example.com/login", 200)
    tracker = _tracker(page, tmp_path)
    tracker.fill("#user-name", "standard_user")

    page.url = "https://shop.example.com/inventory.html"
    page.goto.return_value.status = 200

    with pytest.raises(PageMismatchError):
        tracker.navigate(
            "https://shop.example.com/inventory.html",
            expected_page="https://shop.example.com/cart.html",
        )

    assert tracker.steps[-1]["result"]["page_mismatch"] == {
        "expected": "https://shop.example.com/cart.html",
        "actual": "https://shop.example.com/inventory.html",
    }


def test_an_element_step_still_compares_the_page_it_entered_on(tmp_path: Path) -> None:
    """AI-067 is unchanged: an element step is judged against its entry page."""
    page = _page("https://shop.example.com/cart.html", 200)
    tracker = _tracker(page, tmp_path)

    with pytest.raises(PageMismatchError):
        tracker.fill("#coupon", "SAVE10", expected_page="https://shop.example.com/login")

    assert tracker.steps[-1]["result"]["page_mismatch"] == {
        "expected": "https://shop.example.com/login",
        "actual": "https://shop.example.com/cart.html",
    }
