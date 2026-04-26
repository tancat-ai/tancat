from __future__ import annotations

import json
from pathlib import Path

from src.evidence_report import _normalise_url
from src.heatmap_utils import (
    _extract_step_points_by_url,
    build_story_confidence,
    generate_suite_heatmap,
)


def _write_sidecar(path: Path, *, story_ref: str, condition_ref: str, status: str) -> None:
    payload = {
        "schema_version": "1.0",
        "test": {
            "name": path.stem,
            "condition_ref": condition_ref,
            "story_ref": story_ref,
            "status": status,
            "duration_s": 1.0,
        },
        "steps": [],
        "run_history": {"total_runs": 1, "passed_runs": 1, "failed_runs": 0},
        "page": {"url": "http://example"},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_story_confidence_failed_is_gap(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    _write_sidecar(evidence_dir / "a.evidence.json", story_ref="S1", condition_ref="S1.01", status="failed")
    stories = build_story_confidence(evidence_dir)
    assert len(stories) == 1
    assert stories[0].story_ref == "S1"
    assert stories[0].level == "gap_open_question"


def test_build_story_confidence_confirmed(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    _write_sidecar(evidence_dir / "a.evidence.json", story_ref="S1", condition_ref="S1.01", status="passed")
    _write_sidecar(evidence_dir / "b.evidence.json", story_ref="S1", condition_ref="S1.02", status="passed")

    test_plan_state = {"confirmed_ids": {"S1.01", "S1.02"}}
    stories = build_story_confidence(evidence_dir, test_plan_state=test_plan_state)
    assert stories[0].level == "tester_confirmed"


# --- New tests for Tier 3 heatmap features ---


def test_normalise_url_handles_trailing_slash() -> None:
    assert _normalise_url("https://example.com/path/") == "https://example.com/path"


def test_normalise_url_handles_case() -> None:
    assert _normalise_url("HTTPS://EXAMPLE.COM/Path") == "https://example.com/Path"


def test_extract_step_points_by_url_with_status(tmp_path: Path) -> None:
    """Test that step points include status from result dict."""
    sidecar = {
        "test": {"name": "test_1", "status": "failed"},
        "page": {"url": "https://example.com/page1"},
        "steps": [
            {
                "type": "navigate",
                "value": "https://example.com/page1",
                "screenshot": "screenshots/1.png",
                "result": {"run_count": 3},
            },
            {
                "type": "click",
                "label": "{{CLICK:Add to Cart}}",
                "element": {
                    "viewport_pct": {"x": 30.0, "y": 50.0},
                    "element_id": "add-to-cart",
                    "tag": "button",
                },
                "locator": "button#add-to-cart",
                "screenshot": "screenshots/2.png",
                "result": {"status": "partial_pass", "run_count": 3, "fallback_used": True},
            },
            {
                "type": "assertion",
                "label": "Assert cart badge visible",
                "element": {
                    "viewport_pct": {"x": 70.0, "y": 10.0},
                    "element_id": "cart-badge",
                    "tag": "span",
                },
                "locator": "span#cart-badge",
                "screenshot": "screenshots/3.png",
                "result": {"status": "failed", "run_count": 3, "error": "Element not visible"},
            },
        ],
    }
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "test_1.evidence.json").write_text(json.dumps(sidecar))

    points_by_url, bg_by_url = _extract_step_points_by_url(sidecar)
    url_norm = "https://example.com/page1"
    assert url_norm in points_by_url

    points = points_by_url[url_norm]
    assert len(points) == 3

    # Check click point has status
    click_point = [p for p in points if p["type"] == "click"][0]
    assert click_point["status"] == "partial_pass"
    assert click_point["locator"] == "button#add-to-cart"
    assert click_point["element_id"] == "add-to-cart"
    assert click_point["tag"] == "button"

    # Check assertion point has status
    assert_point = [p for p in points if p["type"] == "assertion"][0]
    assert assert_point["status"] == "failed"


def test_generate_suite_heatmap_includes_status_colors(tmp_path: Path) -> None:
    """Test that suite heatmap HTML includes status color references."""
    sidecar = {
        "test": {"name": "test_1"},
        "page": {"url": "https://example.com/page1"},
        "steps": [
            {
                "type": "navigate",
                "value": "https://example.com/page1",
                "result": {"run_count": 1},
            },
            {
                "type": "click",
                "label": "{{CLICK:Submit}}",
                "element": {
                    "viewport_pct": {"x": 40.0, "y": 60.0},
                    "element_id": "submit-btn",
                    "tag": "button",
                },
                "locator": "button#submit-btn",
                "result": {"status": "passed", "run_count": 2},
            },
        ],
    }
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "test_1.evidence.json").write_text(json.dumps(sidecar))

    html = generate_suite_heatmap(evidence_dir=evidence_dir, page_url="https://example.com/page1")
    assert "Suite Heatmap" in html
    assert "Per-URL Element Coverage" in html
    # Should include status color references
    assert "#1D9E75" in html  # passed green
    assert "#FAC775" in html  # partial_pass yellow
    assert "#F09595" in html  # failed red


def test_generate_suite_heatmap_element_aggregation(tmp_path: Path) -> None:
    """Test that elements within tolerance are merged."""
    # Two points very close to each other (within 2% tolerance)
    sidecar = {
        "test": {"name": "test_1"},
        "page": {"url": "https://example.com/page1"},
        "steps": [
            {
                "type": "navigate",
                "value": "https://example.com/page1",
                "result": {"run_count": 1},
            },
            {
                "type": "click",
                "label": "{{CLICK:Submit}}",
                "element": {
                    "viewport_pct": {"x": 40.0, "y": 60.0},
                    "element_id": "submit-btn",
                    "tag": "button",
                },
                "locator": "button#submit-btn",
                "result": {"status": "passed", "run_count": 1},
            },
        ],
    }
    # Second sidecar with same element (slightly different position)
    sidecar2 = {
        "test": {"name": "test_2"},
        "page": {"url": "https://example.com/page1"},
        "steps": [
            {
                "type": "navigate",
                "value": "https://example.com/page1",
                "result": {"run_count": 1},
            },
            {
                "type": "click",
                "label": "{{CLICK:Submit}}",
                "element": {
                    "viewport_pct": {"x": 41.5, "y": 61.0},  # Within 2% tolerance
                    "element_id": "submit-btn",
                    "tag": "button",
                },
                "locator": "button#submit-btn",
                "result": {"status": "passed", "run_count": 1},
            },
        ],
    }
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "test_1.evidence.json").write_text(json.dumps(sidecar))
    (evidence_dir / "test_2.evidence.json").write_text(json.dumps(sidecar2))

    html = generate_suite_heatmap(evidence_dir=evidence_dir, page_url="https://example.com/page1")
    # Should show run_count of 2 (both tests hit same element)
    assert "2" in html  # run count appears in circle
    assert "Suite Heatmap" in html


def test_generate_suite_heatmap_no_points_returns_message(tmp_path: Path) -> None:
    """Test that heatmap returns message when no evidence points found."""
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    # No sidecars at all
    html = generate_suite_heatmap(evidence_dir=evidence_dir, page_url="https://example.com/page1")
    assert "No evidence points found" in html
