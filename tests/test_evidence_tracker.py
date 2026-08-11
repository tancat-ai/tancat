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


def test_failed_step_skips_metadata_capture(tmp_path: Any) -> None:
    """B-041: failed steps must not run the un-timed locator metadata capture.

    A failing locator (e.g. an assertion on an element that never appears) made
    _get_element_metadata's un-timed evaluate/get_attribute/bounding_box calls
    wait the full 30s default each (~120s) — pytest-timeout then killed the
    whole suite, leaving later tests unrecorded. Failed steps now record {}.
    """
    page_mock = MagicMock()
    page_mock.locator.return_value.first.wait_for.side_effect = TimeoutError("element not visible")
    tracker = EvidenceTracker(page_mock, "test_assert_fail", evidence_root=Path(tmp_path))

    with pytest.raises(TimeoutError):
        tracker.assert_visible("h2.heading")

    step = tracker.steps[-1]
    assert step["result"]["status"] == "failed"
    assert step["result"]["error"] == "element not visible"
    # Metadata capture must be skipped — no locator-level calls beyond wait_for.
    loc = page_mock.locator.return_value.first
    assert loc.evaluate.call_count == 0
    assert loc.get_attribute.call_count == 0
    assert loc.bounding_box.call_count == 0


def test_evidence_tracker_click_attempts_scroll_into_view_before_click(tmp_path: Any) -> None:
    page_mock = MagicMock()
    # First count() call = the click target (exists); subsequent calls are the
    # proactive modal-dismissal probes (no visible modals -> no-op).
    page_mock.locator.return_value.first.count.side_effect = [1, 0, 0, 0, 0, 0, 0, 0, 0, 0]
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


def test_click_fast_fails_when_locator_missing_on_page(tmp_path: Any) -> None:
    """B-028 follow-up: a click on a locator that does not exist on the current
    page must fail immediately (no fallback marathon). B-033: fast-fail steps
    now DO capture a screenshot + failure note — the missing-element error is
    self-diagnosing, but the visual artifact is the most useful evidence."""
    page_mock = MagicMock()
    # Element not on the page: count() == 0
    page_mock.locator.return_value.first.count.return_value = 0
    page_mock.url = "https://example.com/products"
    tracker = EvidenceTracker(page_mock, "test_fastfail", evidence_root=Path(tmp_path))

    with pytest.raises(Exception, match="not found on current page"):
        tracker.click("button.btn.cart")

    assert len(tracker.steps) == 1
    step = tracker.steps[0]
    assert step["type"] == "click"
    assert step["result"]["status"] == "failed"
    assert "not found on current page" in step["result"]["error"]
    # B-033: failed steps must carry a screenshot and a failure note.
    assert step["screenshot"] is not None
    assert step["result"]["failure_note"] is not None
    assert step["url"] == "https://example.com/products"
    # The 5s click must never have been attempted.
    page_mock.locator.return_value.first.click.assert_not_called()


def test_click_missing_locator_does_not_run_fallback(tmp_path: Any) -> None:
    """The fallback chain (hover/locator-scoring) must not run for a locator
    that does not exist — it builds candidates from the same DOM and cannot
    recover a non-existent element."""
    from unittest.mock import patch

    page_mock = MagicMock()
    page_mock.locator.return_value.first.count.return_value = 0
    page_mock.url = "https://example.com"
    tracker = EvidenceTracker(page_mock, "test_fallback", evidence_root=Path(tmp_path))

    with (
        patch("src.evidence_tracker.try_hover_and_click") as mock_hover,
        patch("src.evidence_tracker.LocatorFallback") as mock_fallback,
    ):
        with pytest.raises(Exception, match="not found"):
            tracker.click("button.btn.cart")

    mock_hover.assert_not_called()
    mock_fallback.try_fallback.assert_not_called()


# ── B-029: post-click navigation verification ───────────────────────────────


class _UrlFlipPage:
    """Minimal stub page: URL flips from start to /cart on the second read.

    Simulates a link click that DOES navigate. All other Playwright surface
    (locators, evaluate, keyboard) is a permissive MagicMock.
    """

    def __init__(self) -> None:
        self._n = 0

    @property
    def url(self) -> str:
        self._n += 1
        return "https://example.com/start" if self._n == 1 else "https://example.com/cart"

    def locator(self, *args: Any, **kwargs: Any) -> Any:
        return MagicMock()

    evaluate = MagicMock()
    keyboard = MagicMock()


class _StaticPage:
    """Stub page whose URL never changes — simulates an overlay-swallowed click."""

    url = "https://example.com/start"

    def locator(self, *args: Any, **kwargs: Any) -> Any:
        return MagicMock()

    evaluate = MagicMock()
    keyboard = MagicMock()


def test_b029_navigation_verified_when_url_changes(tmp_path: Any) -> None:

    tracker = EvidenceTracker(_UrlFlipPage(), "t", evidence_root=Path(tmp_path))
    # href on a different path + URL changes → no raise, step stays passed.
    tracker._record_step("click", "Cart", locator='a[href="/cart"]')
    tracker._verify_click_navigation('a[href="/cart"]', "Cart", {"href": "/cart"}, "https://example.com/start")
    assert tracker.steps[-1]["result"]["status"] == "passed"


def test_b029_same_page_and_non_link_hrefs_skipped(tmp_path: Any) -> None:
    tracker = EvidenceTracker(_StaticPage(), "t", evidence_root=Path(tmp_path))
    # Anchor / javascript: / no-href links never require navigation.
    for href in (None, "", "#section", "javascript:void(0)", "/start"):
        tracker._verify_click_navigation("x", "Click", {"href": href}, "https://example.com/start")


def test_b029_swallowed_click_amended_to_failure(tmp_path: Any) -> None:
    from src.evidence_tracker import _LocatorNotFoundError

    tracker = EvidenceTracker(_StaticPage(), "t", evidence_root=Path(tmp_path))
    tracker._record_step("click", "Cart", locator='a[href="/cart"]')
    with pytest.raises(_LocatorNotFoundError, match="did not navigate"):
        tracker._verify_click_navigation('a[href="/cart"]', "Cart", {"href": "/cart"}, "https://example.com/start")
    # The recorded step must be flipped from a false pass to a truthful failure.
    last = tracker.steps[-1]
    assert last["result"]["status"] == "failed"
    assert "did not navigate" in last["result"]["error"]
    assert last["result"]["failure_note"] is not None


def test_fill_select_uses_select_option_when_tag_is_select(tmp_path: Any) -> None:
    """B-044: a native <select> rejects .fill(); the tracker must route to
    .select_option(). Regression: banking mock payee/from-account selects
    made the generated tests fail at runtime (Playwright "Element is not an
    <input>, <textarea> or [contenteditable]")."""
    page_mock = MagicMock()
    locator_mock = MagicMock()
    locator_mock.evaluate.return_value = "SELECT"
    page_mock.locator.return_value = locator_mock
    tracker = EvidenceTracker(page_mock, "t", evidence_root=Path(tmp_path))

    tracker.fill("#payee", "Electric Company")

    locator_mock.select_option.assert_called_once_with("Electric Company")
    locator_mock.fill.assert_not_called()
    assert tracker.steps[-1]["type"] == "fill"
    assert tracker.steps[-1]["result"]["status"] == "passed"


def test_fill_select_falls_back_to_substring_option_label(tmp_path: Any) -> None:
    """B-044: when the fill value matches no option value/label exactly, select
    the first option whose label contains the requested text ("Electric
    Company" vs option "City Electric Company")."""
    page_mock = MagicMock()
    locator_mock = MagicMock()
    # tag=SELECT; exact value fails; exact label fails; substring matches
    # option with value="electric".
    locator_mock.evaluate.side_effect = ["SELECT", "electric"]
    locator_mock.select_option.side_effect = [Exception("no exact value"), Exception("no exact label"), None]
    page_mock.locator.return_value = locator_mock
    tracker = EvidenceTracker(page_mock, "t", evidence_root=Path(tmp_path))

    tracker.fill("#payee", "Electric Company")

    assert locator_mock.select_option.call_count == 3
    # Substring pass selected by resolved value.
    assert locator_mock.select_option.call_args_list[-1] == (("electric",),)


def test_fill_plain_input_uses_fill_not_select_option(tmp_path: Any) -> None:
    """B-044: non-select elements must keep using .fill() (no behavior change)."""
    page_mock = MagicMock()
    locator_mock = MagicMock()
    locator_mock.evaluate.return_value = "INPUT"
    page_mock.locator.return_value = locator_mock
    tracker = EvidenceTracker(page_mock, "t", evidence_root=Path(tmp_path))

    tracker.fill("#amount", "100")

    locator_mock.fill.assert_called_once_with("100")
    locator_mock.select_option.assert_not_called()


def test_fill_select_evaluate_failure_falls_back_to_fill(tmp_path: Any) -> None:
    """B-044: if the tag probe fails (element not present yet), fall back to
    plain .fill() so the original error path is unchanged."""
    page_mock = MagicMock()
    locator_mock = MagicMock()
    locator_mock.evaluate.side_effect = Exception("no element")
    page_mock.locator.return_value = locator_mock
    tracker = EvidenceTracker(page_mock, "t", evidence_root=Path(tmp_path))

    tracker.fill("#maybe-late", "x")

    locator_mock.fill.assert_called_once_with("x")
    locator_mock.select_option.assert_not_called()


def _mock_metadata_page(*, doc_size: tuple[float, float], scroll: tuple[float, float], bbox: dict[str, float]) -> Any:
    """Build a mock page whose evaluate() serves doc-size then scroll offsets."""
    page_mock = MagicMock()
    locator_mock = MagicMock()
    page_mock.locator.return_value = locator_mock
    locator_mock.first = locator_mock  # .first returns itself
    locator_mock.evaluate.return_value = "button"
    locator_mock.get_attribute.side_effect = ["btn-id", None, None]

    def fake_evaluate(expr: str) -> dict[str, float]:
        if "scrollWidth" in expr:
            return {"width": doc_size[0], "height": doc_size[1]}
        return {"x": scroll[0], "y": scroll[1]}

    page_mock.evaluate.side_effect = fake_evaluate
    locator_mock.bounding_box.return_value = bbox
    return page_mock


def test_metadata_viewport_pct_is_document_relative(tmp_path: Any) -> None:
    """AI-043: viewport_pct must be % of the FULL DOCUMENT (full-page screenshot).

    bbox is viewport-relative (element scrolled 800px down); without the scroll
    correction the recorded y% would be ~7% instead of the true ~34%."""
    page_mock = _mock_metadata_page(
        doc_size=(1000.0, 3000.0),
        scroll=(0.0, 800.0),
        bbox={"x": 100.0, "y": 200.0, "width": 50.0, "height": 30.0},
    )
    tracker = EvidenceTracker(page_mock, "t", evidence_root=Path(tmp_path))
    meta = tracker._get_element_metadata("#btn")

    pct = meta["viewport_pct"]
    # doc center: x=125, y=1015 → 12.5% / 33.83%
    assert abs(pct["x"] - 12.5) < 0.01
    assert abs(pct["y"] - 33.833) < 0.01


def test_metadata_clamps_negative_y_to_zero(tmp_path: Any) -> None:
    """AI-043: an element above the viewport (negative bbox y) must not paint an
    off-page marker — the % is clamped into [0, 100]."""
    page_mock = _mock_metadata_page(
        doc_size=(1000.0, 3000.0),
        scroll=(0.0, 0.0),
        bbox={"x": 100.0, "y": -100.0, "width": 50.0, "height": 30.0},
    )
    tracker = EvidenceTracker(page_mock, "t", evidence_root=Path(tmp_path))
    meta = tracker._get_element_metadata("#btn")

    pct = meta["viewport_pct"]
    assert pct["y"] == 0.0
    assert 0.0 <= pct["x"] <= 100.0


def test_metadata_scroll_probe_failure_falls_back_to_bbox(tmp_path: Any) -> None:
    """If the scroll probe fails, degrade gracefully (no scroll correction)."""
    page_mock = _mock_metadata_page(
        doc_size=(1000.0, 3000.0),
        scroll=(0.0, 0.0),
        bbox={"x": 100.0, "y": 200.0, "width": 50.0, "height": 30.0},
    )

    def fake_evaluate(expr: str) -> dict[str, float]:
        if "scrollWidth" in expr:
            return {"width": 1000.0, "height": 3000.0}
        raise Exception("page gone")

    page_mock.evaluate.side_effect = fake_evaluate
    tracker = EvidenceTracker(page_mock, "t", evidence_root=Path(tmp_path))
    meta = tracker._get_element_metadata("#btn")
    assert 0.0 <= meta["viewport_pct"]["x"] <= 100.0
    assert 0.0 <= meta["viewport_pct"]["y"] <= 100.0
