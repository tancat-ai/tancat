from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.evidence_tracker import EvidenceTracker


def test_evidence_tracker_records_navigation(tmp_path: Any) -> None:
    page_mock = MagicMock()
    tracker = EvidenceTracker(page_mock, "test_foo", "C01", "S01", evidence_root=Path(tmp_path))

    tracker.navigate("https://example.com")

    assert len(tracker.steps) == 1
    step = tracker.steps[0]
    assert step["type"] == "navigate"
    assert step["value"] == "https://example.com"
    assert step["screenshot"] is not None
    assert step["result"]["status"] == "passed"

    # Check history merge defaults
    assert tracker.run_history == {"total_runs": 0, "passed_runs": 0, "failed_runs": 0}


def test_evidence_tracker_records_failure(tmp_path: Any) -> None:
    page_mock = MagicMock()
    page_mock.goto.side_effect = Exception("Network Error")
    tracker = EvidenceTracker(page_mock, "test_foo", evidence_root=Path(tmp_path))

    try:
        tracker.navigate("https://fail.com")
    except Exception:
        pass

    assert len(tracker.steps) == 1
    assert tracker.steps[0]["result"]["status"] == "failed"
    assert tracker.steps[0]["result"]["error"] == "Network Error"


def test_evidence_tracker_click_failure_takes_screenshot(tmp_path: Any) -> None:
    page_mock = MagicMock()
    # Make click throw
    page_mock.locator.return_value.first.click.side_effect = Exception("Click Error")
    tracker = EvidenceTracker(page_mock, "test_click", evidence_root=Path(tmp_path))

    with pytest.raises(Exception, match="Click Error"):
        tracker.click("#does-not-exist")

    assert tracker.steps[-1]["type"] == "click"
    assert tracker.steps[-1]["result"]["status"] == "failed"
    assert tracker.steps[-1]["screenshot"] is not None


def test_evidence_tracker_click_attempts_scroll_into_view_before_click(tmp_path: Any) -> None:
    page_mock = MagicMock()
    tracker = EvidenceTracker(page_mock, "test_click_scroll", evidence_root=Path(tmp_path))

    tracker.click("div#thing")

    loc = page_mock.locator.return_value.first
    # Metadata collection may also scroll; require at least one attempt.
    assert loc.scroll_into_view_if_needed.call_count >= 1
    assert loc.click.call_count == 1


def test_evidence_tracker_increment_history(tmp_path: Any, monkeypatch: Any) -> None:
    page_mock = MagicMock()
    page_mock.url = "http://localhost"
    tracker = EvidenceTracker(page_mock, "test_write", evidence_root=Path(tmp_path))
    tracker.write("passed")

    # A passed write should increment totals
    assert tracker.run_history["total_runs"] == 1
    assert tracker.run_history["passed_runs"] == 1
    assert tracker.run_history["failed_runs"] == 0


def test_evidence_tracker_assert_visible_uses_first_locator(tmp_path: Any) -> None:
    page_mock = MagicMock()
    tracker = EvidenceTracker(page_mock, "test_assert", evidence_root=Path(tmp_path))

    tracker.assert_visible(".thing")

    loc = page_mock.locator.return_value.first
    assert loc.wait_for.call_count == 1


def test_evidence_tracker_cleans_placeholder_labels(tmp_path: Any) -> None:
    page_mock = MagicMock()
    tracker = EvidenceTracker(page_mock, "test_label", evidence_root=Path(tmp_path))

    tracker.click("#thing", label="{{CLICK:view cart link}}")

    assert tracker.steps[-1]["label"] == "Click: view cart link"
