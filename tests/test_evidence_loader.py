"""Unit tests for src.evidence_loader."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from src.evidence_loader import (
    get_failure_diagnostics,
    get_screenshot_paths,
    load_evidence_for_package,
    match_evidence_to_test,
)

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_evidence(
    test_name: str = "test_01_example[chromium]",
    status: str = "failed",
    steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a minimal evidence payload for testing."""
    if steps is None:
        steps = [
            {
                "step": 1,
                "type": "navigate",
                "label": "Navigate to URL",
                "locator": None,
                "screenshot": "evidence/test_01_example[chromium]_0_navigate.png",
                "result": {
                    "status": "passed",
                    "elapsed_ms": 0,
                    "run_count": 1,
                    "matched_text": None,
                    "error": None,
                    "failure_note": None,
                    "diagnosis": None,
                },
            },
            {
                "step": 2,
                "type": "click",
                "label": "Click button",
                "locator": "#my-btn",
                "screenshot": "evidence/test_01_example[chromium]_1_click.png",
                "result": {
                    "status": "failed",
                    "elapsed_ms": 0,
                    "run_count": 1,
                    "matched_text": None,
                    "error": "Timeout 5000ms exceeded",
                    "failure_note": "STEP FAILED on https://example.com",
                    "diagnosis": {
                        "url": "https://example.com",
                        "title": "Example Page",
                        "suggested_locators": [
                            {"locator": "#alt-btn", "type": "id", "score": "90", "confidence": "high"}
                        ],
                        "available_elements": [{"tag": "button", "text": "Submit", "role": "button"}],
                    },
                },
            },
        ]

    return {
        "schema_version": "1.0",
        "test": {
            "name": test_name,
            "condition_ref": "TC01.01",
            "story_ref": "S01",
            "status": status,
            "duration_s": 5.2,
        },
        "page": {"url": "https://example.com"},
        "steps": steps,
    }


# ── load_evidence_for_package ──────────────────────────────────────────────


class TestLoadEvidenceForPackage:
    def test_returns_empty_dict_when_no_evidence_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = load_evidence_for_package(tmp)
        assert result == {}

    def test_returns_empty_dict_when_evidence_dir_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "evidence").mkdir()
            result = load_evidence_for_package(tmp)
        assert result == {}

    def test_loads_single_evidence_file(self) -> None:
        payload = _make_evidence("test_01_foo[chromium]")
        with tempfile.TemporaryDirectory() as tmp:
            ev_dir = Path(tmp, "evidence")
            ev_dir.mkdir()
            (ev_dir / "test_01_foo[chromium].evidence.json").write_text(json.dumps(payload), encoding="utf-8")
            result = load_evidence_for_package(tmp)

        assert "test_01_foo[chromium]" in result
        assert result["test_01_foo[chromium]"]["test"]["status"] == "failed"

    def test_loads_multiple_evidence_files(self) -> None:
        payloads = [
            _make_evidence("test_01_a[chromium]"),
            _make_evidence("test_02_b[chromium]", status="passed"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            ev_dir = Path(tmp, "evidence")
            ev_dir.mkdir()
            for p in payloads:
                name = p["test"]["name"]
                (ev_dir / f"{name}.evidence.json").write_text(json.dumps(p), encoding="utf-8")
            result = load_evidence_for_package(tmp)

        assert len(result) == 2
        assert "test_01_a[chromium]" in result
        assert "test_02_b[chromium]" in result

    def test_skips_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ev_dir = Path(tmp, "evidence")
            ev_dir.mkdir()
            (ev_dir / "bad.evidence.json").write_text("not json", encoding="utf-8")
            result = load_evidence_for_package(tmp)
        assert result == {}


# ── get_failure_diagnostics ───────────────────────────────────────────────


class TestGetFailureDiagnostics:
    def test_returns_failed_steps(self) -> None:
        evidence = _make_evidence()
        diag = get_failure_diagnostics(evidence)

        assert diag["test_status"] == "failed"
        assert diag["condition_ref"] == "TC01.01"
        assert diag["story_ref"] == "S01"
        assert len(diag["failed_steps"]) == 1

        failed = diag["failed_steps"][0]
        assert failed["step_type"] == "click"
        assert failed["locator"] == "#my-btn"
        assert "Timeout" in failed["error_summary"]
        assert failed["failure_note"]
        assert failed["suggested_locators"]
        assert failed["available_elements"]

    def test_returns_empty_failed_steps_when_all_passed(self) -> None:
        evidence = _make_evidence(status="passed")
        # Override steps to all passed
        evidence["steps"] = [
            {
                "step": 1,
                "type": "navigate",
                "label": "Nav",
                "locator": None,
                "result": {"status": "passed", "error": None, "failure_note": None, "diagnosis": None},
            }
        ]
        diag = get_failure_diagnostics(evidence)
        assert diag["failed_steps"] == []

    def test_includes_page_url(self) -> None:
        evidence = _make_evidence()
        diag = get_failure_diagnostics(evidence)
        assert diag["page_url"] == "https://example.com"


# ── get_screenshot_paths ──────────────────────────────────────────────────


class TestGetScreenshotPaths:
    def test_returns_screenshots_for_failed_steps(self) -> None:
        evidence = _make_evidence()
        paths = get_screenshot_paths(evidence)
        assert len(paths) == 1
        assert "1_click" in paths[0]

    def test_returns_empty_when_no_failures(self) -> None:
        evidence = _make_evidence(status="passed")
        evidence["steps"] = [
            {
                "step": 1,
                "result": {"status": "passed"},
                "screenshot": "evidence/foo.png",
            }
        ]
        paths = get_screenshot_paths(evidence)
        assert paths == []


# ── match_evidence_to_test ────────────────────────────────────────────────


class TestMatchEvidenceToTest:
    def test_exact_match(self) -> None:
        evidence_map = {"test_01_foo[chromium]": {"test": {"name": "test_01_foo[chromium]"}}}
        result = match_evidence_to_test(evidence_map, "test_01_foo[chromium]")
        assert result is not None
        assert result["test"]["name"] == "test_01_foo[chromium]"

    def test_prefix_match(self) -> None:
        evidence_map = {"test_01_foo[chromium]": {"test": {"name": "test_01_foo[chromium]"}}}
        result = match_evidence_to_test(evidence_map, "test_01_foo")
        assert result is not None

    def test_returns_none_when_no_match(self) -> None:
        evidence_map: dict[str, dict] = {"test_01_foo[chromium]": {}}
        result = match_evidence_to_test(evidence_map, "test_99_other")
        assert result is None

    def test_empty_map(self) -> None:
        result = match_evidence_to_test({}, "test_01")
        assert result is None
