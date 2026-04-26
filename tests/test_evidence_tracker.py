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


class TestLocatorFallback:
    """Tier 2: Locator scoring + controlled fallback tests.

    NOTE: These tests verify the _record_step integration with fallback_used
    and fallback_chain parameters. Full end-to-end fallback testing requires
    real browser interactions which are beyond unit test scope.
    """

    def test_record_step_sets_partial_pass_when_fallback_used(self, tmp_path: Any) -> None:
        """_record_step should set status='partial_pass' when fallback_used=True."""
        page_mock = MagicMock()
        tracker = EvidenceTracker(page_mock, "test_partial", evidence_root=Path(tmp_path))

        # Directly call _record_step with fallback_used=True
        tracker._record_step(
            "click",
            "Click button",
            locator=".btn",
            fallback_used=True,
            fallback_chain=[
                {
                    "locator": ".btn",
                    "type": "css-class",
                    "score": 35,
                    "confidence": "medium-low",
                    "result": "failed",
                },
                {
                    "locator": "#addToCart",
                    "type": "id",
                    "score": 85,
                    "confidence": "high",
                    "result": "success",
                },
            ],
        )

        assert tracker.steps[-1]["type"] == "click"
        assert tracker.steps[-1]["result"]["status"] == "partial_pass"
        assert tracker.steps[-1]["result"]["fallback_used"] is True
        assert len(tracker.steps[-1]["result"]["fallback_chain"]) == 2

    def test_record_step_sets_passed_when_no_fallback(self, tmp_path: Any) -> None:
        """_record_step should set status='passed' when no error and no fallback."""
        page_mock = MagicMock()
        tracker = EvidenceTracker(page_mock, "test_passed", evidence_root=Path(tmp_path))

        tracker._record_step("click", "Click button", locator="#btn")

        assert tracker.steps[-1]["result"]["status"] == "passed"
        assert "fallback_used" not in tracker.steps[-1]["result"]

    def test_record_step_sets_failed_when_error_no_fallback(self, tmp_path: Any) -> None:
        """_record_step should set status='failed' when there's an error."""
        page_mock = MagicMock()
        tracker = EvidenceTracker(page_mock, "test_failed", evidence_root=Path(tmp_path))

        tracker._record_step("click", "Click button", locator="#btn", error="timeout")

        assert tracker.steps[-1]["result"]["status"] == "failed"
        assert "fallback_used" not in tracker.steps[-1]["result"]

    def test_fallback_chain_structure(self, tmp_path: Any) -> None:
        """Fallback chain entries should contain locator, type, score, confidence, result."""
        page_mock = MagicMock()
        tracker = EvidenceTracker(page_mock, "test_chain", evidence_root=Path(tmp_path))

        fallback_chain = [
            {"locator": ".btn", "type": "css-class", "score": 35, "confidence": "medium-low", "result": "failed"},
            {"locator": "#addToCart", "type": "id", "score": 85, "confidence": "high", "result": "success"},
        ]

        tracker._record_step(
            "click",
            "Click button",
            locator=".btn",
            fallback_used=True,
            fallback_chain=fallback_chain,
        )

        chain = tracker.steps[-1]["result"]["fallback_chain"]
        assert len(chain) == 2
        for entry in chain:
            assert "locator" in entry
            assert "type" in entry
            assert "score" in entry
            assert "confidence" in entry
            assert "result" in entry
        assert chain[0]["result"] == "failed"
        assert chain[1]["result"] == "success"
