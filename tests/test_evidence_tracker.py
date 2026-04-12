from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from src.evidence_tracker import EvidenceTracker


def test_evidence_tracker_records_navigation() -> None:
    page_mock = MagicMock()
    tracker = EvidenceTracker(page_mock, "test_foo", "C01", "S01")

    tracker.navigate("https://example.com")

    assert len(tracker.steps) == 1
    step = tracker.steps[0]
    assert step["type"] == "navigate"
    assert step["value"] == "https://example.com"
    assert step["screenshot"] is not None
    assert step["result"]["status"] == "passed"

    # Check history merge defaults
    assert tracker.run_history == {"total_runs": 0, "passed_runs": 0, "failed_runs": 0}


def test_evidence_tracker_records_failure() -> None:
    page_mock = MagicMock()
    page_mock.goto.side_effect = Exception("Network Error")
    tracker = EvidenceTracker(page_mock, "test_foo")

    try:
        tracker.navigate("https://fail.com")
    except Exception:
        pass

    assert len(tracker.steps) == 1
    assert tracker.steps[0]["result"]["status"] == "failed"
    assert tracker.steps[0]["result"]["error"] == "Network Error"


def test_evidence_tracker_increment_history(tmp_path: Any, monkeypatch: Any) -> None:
    # Force the evidence directory to tmp_path so it doesn't load real history across test runs
    monkeypatch.setattr("src.evidence_tracker.Path", lambda p: tmp_path if p == "evidence" else Path(p))

    page_mock = MagicMock()
    page_mock.url = "http://localhost"
    tracker = EvidenceTracker(page_mock, "test_write")
    tracker.write("passed")

    # A passed write should increment totals
    assert tracker.run_history["total_runs"] == 1
    assert tracker.run_history["passed_runs"] == 1
    assert tracker.run_history["failed_runs"] == 0
