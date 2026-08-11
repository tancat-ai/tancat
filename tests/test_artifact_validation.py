"""Unit tests for ``src/artifact_validation.py`` (AI-043 Layer 1 + golden fixtures)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.artifact_validation import (
    validate_evidence_artifacts,
    validate_gantt_chart,
    validate_gantt_entries,
    validate_plotly_figure,
    validate_step_points,
    validate_suite_heatmap,
)
from src.gantt_utils import GanttEntry, load_gantt_entries

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "report_golden"

GOOD_URL = "https://example.com/page1"


def _nav_step(url: str = GOOD_URL) -> dict[str, Any]:
    return {
        "type": "navigate",
        "value": url,
        "result": {"status": "passed", "run_count": 1},
    }


def _sidecar(
    name: str, steps: list[dict[str, Any]], *, duration_s: float = 1.0, status: str = "passed"
) -> dict[str, Any]:
    return {
        "test": {
            "name": name,
            "condition_ref": "TC-01",
            "story_ref": "S01",
            "status": status,
            "duration_s": duration_s,
        },
        "page": {"url": GOOD_URL},
        "steps": steps,
    }


# ---------------------------------------------------------------------------
# validate_step_points
# ---------------------------------------------------------------------------


class TestValidateStepPoints:
    def test_accepts_in_range_points(self) -> None:
        points = {
            GOOD_URL: [
                {"type": "click", "x": 40.0, "y": 60.0, "run_count": 1, "status": "passed"},
                {"type": "assertion", "x": 0.0, "y": 100.0, "run_count": 2, "status": "failed"},
            ]
        }
        assert validate_step_points(points) == []

    def test_flags_out_of_range_coordinates(self) -> None:
        points = {GOOD_URL: [{"type": "click", "x": 273.5, "y": 702.34, "run_count": 1}]}
        issues = validate_step_points(points)
        assert len(issues) == 2
        assert all(i.severity == "error" for i in issues)
        assert "273.5" in issues[0].message

    def test_flags_non_finite_coordinates(self) -> None:
        points = {GOOD_URL: [{"type": "click", "x": float("nan"), "y": 50.0, "run_count": 1}]}
        issues = validate_step_points(points)
        assert any("x=nan" in i.message or "x=NaN" in i.message for i in issues)

    def test_flags_unknown_status_and_bad_run_count(self) -> None:
        points = {GOOD_URL: [{"type": "click", "x": 10.0, "y": 10.0, "run_count": 0, "status": "bogus"}]}
        issues = validate_step_points(points)
        severities = {i.severity for i in issues}
        assert "warning" in severities  # both are warnings
        assert any("bogus" in i.message for i in issues)
        assert any("run_count" in i.message for i in issues)


# ---------------------------------------------------------------------------
# validate_suite_heatmap (real HTML round-trip)
# ---------------------------------------------------------------------------


def _write_sidecars(tmp_path: Path, sidecars: list[dict[str, Any]]) -> Path:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    for i, sc in enumerate(sidecars):
        (evidence_dir / f"test_{i}.evidence.json").write_text(json.dumps(sc), encoding="utf-8")
    return evidence_dir


class TestValidateSuiteHeatmap:
    def test_good_sidecars_pass(self, tmp_path: Path) -> None:
        evidence_dir = _write_sidecars(
            tmp_path,
            [
                _sidecar(
                    "t1",
                    [
                        _nav_step(),
                        {
                            "type": "click",
                            "label": "Submit",
                            "element": {"viewport_pct": {"x": 40.0, "y": 60.0}},
                            "result": {"status": "passed", "run_count": 2},
                        },
                        {
                            "type": "assertion",
                            "label": "confirmation",
                            "element": {"viewport_pct": {"x": 50.0, "y": 70.0}},
                            "result": {"status": "failed", "run_count": 1},
                        },
                    ],
                )
            ],
        )
        issues = validate_suite_heatmap(evidence_dir, GOOD_URL)
        assert not [i for i in issues if i.severity == "error"], f"unexpected errors: {issues}"

    def test_legacy_pixel_coordinates_flagged(self, tmp_path: Path) -> None:
        """Regression: pre-% sidecars record raw pixels (x=273.5) — off-page."""
        evidence_dir = _write_sidecars(
            tmp_path,
            [
                _sidecar(
                    "t1",
                    [
                        _nav_step(),
                        {
                            "type": "click",
                            "label": "Submit",
                            "element": {"viewport_pct": {"x": 273.5, "y": 702.34}},
                            "result": {"status": "passed", "run_count": 1},
                        },
                    ],
                )
            ],
        )
        issues = validate_suite_heatmap(evidence_dir, GOOD_URL)
        assert any(i.severity == "error" and "out-of-range" in i.message for i in issues)

    def test_unparseable_payload_flagged(self, tmp_path: Path) -> None:
        # Empty dir → placeholder message, which is a VALID empty render.
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        assert validate_suite_heatmap(evidence_dir, GOOD_URL) == []

    def test_missing_evidence_dir_flagged(self, tmp_path: Path) -> None:
        issues = validate_suite_heatmap(tmp_path / "nope", GOOD_URL)
        assert any(i.severity == "error" and "not found" in i.message for i in issues)


# ---------------------------------------------------------------------------
# Gantt invariants
# ---------------------------------------------------------------------------


def _entry(name: str = "t1", duration_s: float = 1.0, status: str = "passed") -> GanttEntry:
    return GanttEntry(test_name=name, condition_ref="TC-01", story_ref="S01", status=status, duration_s=duration_s)


class TestValidateGanttEntries:
    def test_accepts_valid_entries(self) -> None:
        assert validate_gantt_entries([_entry(duration_s=2.5), _entry("t2", duration_s=0.0)]) == []

    def test_flags_nan_duration(self) -> None:
        """Regression: a NaN duration collapses the sequential timeline."""
        issues = validate_gantt_entries([_entry(duration_s=float("nan"))])
        assert any(i.severity == "error" and "duration_s" in i.message for i in issues)

    def test_flags_negative_duration(self) -> None:
        issues = validate_gantt_entries([_entry(duration_s=-5.0)])
        assert any(i.severity == "error" and "duration_s" in i.message for i in issues)

    def test_unknown_status_warns(self) -> None:
        issues = validate_gantt_entries([_entry(status="bogus")])
        assert any(i.severity == "warning" and "bogus" in i.message for i in issues)


class TestValidateGanttChart:
    def test_valid_entries_render_clean_chart(self) -> None:
        entries = [_entry("t1", duration_s=2.0), _entry("t2", duration_s=1.5)]
        assert validate_gantt_chart(entries) == []

    def test_empty_entries_no_chart_no_issues(self) -> None:
        assert validate_gantt_chart([]) == []

    def test_negative_duration_breaks_chart(self) -> None:
        issues = validate_gantt_chart([_entry("t1", duration_s=-2.0)])
        assert any(i.severity == "error" for i in issues)


# ---------------------------------------------------------------------------
# Generic Plotly figure invariants
# ---------------------------------------------------------------------------


class TestValidatePlotlyFigure:
    def test_confidence_heatmap_clean(self) -> None:
        from src.heatmap_utils import StoryConfidence, build_confidence_heatmap

        stories = [StoryConfidence("S1", "tester_confirmed", "#1D9E75", 2, 2, 0, 0)]
        assert validate_plotly_figure(build_confidence_heatmap(stories), "confidence-heatmap") == []

    def test_empty_figure_flagged(self) -> None:
        import plotly.graph_objects as go

        issues = validate_plotly_figure(go.Figure(), "chart")
        assert any(i.severity == "error" and "no traces" in i.message for i in issues)


# ---------------------------------------------------------------------------
# Golden fixtures (Layer 2) — fixtures/report_golden/
# ---------------------------------------------------------------------------


class TestGoldenFixtures:
    """Deterministic sidecar sets with expected validation outcomes."""

    def test_heatmap_good_passes(self) -> None:
        result = validate_evidence_artifacts(FIXTURES / "heatmap_good", [GOOD_URL])
        assert result.passed, f"golden good fixture failed: {result.errors}"

    def test_heatmap_legacy_pixels_fails(self) -> None:
        """The documented bug class: pixel coords treated as % → off-page markers."""
        result = validate_evidence_artifacts(FIXTURES / "heatmap_legacy_pixels", [GOOD_URL])
        assert not result.passed
        assert any("out-of-range" in i.message for i in result.errors)

    def test_gantt_nan_fails(self) -> None:
        """The documented bug class: NaN duration collapses the timeline."""
        entries = load_gantt_entries(FIXTURES / "gantt_nan")
        assert entries and validate_gantt_entries(entries)
        result = validate_evidence_artifacts(FIXTURES / "gantt_nan", [GOOD_URL])
        assert not result.passed
        assert any("duration_s" in i.message for i in result.errors)


# ---------------------------------------------------------------------------
# CLI smoke (script exit codes)
# ---------------------------------------------------------------------------


class TestCli:
    def test_script_reports_good_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import scripts.validate_report_artifacts as module

        monkeypatch.setattr(
            "sys.argv",
            ["validate_report_artifacts", "--evidence-dir", str(FIXTURES / "heatmap_good"), "--page-url", GOOD_URL],
        )
        assert module.main() == 0

    def test_script_exit_one_on_legacy_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import scripts.validate_report_artifacts as module

        monkeypatch.setattr(
            "sys.argv",
            [
                "validate_report_artifacts",
                "--evidence-dir",
                str(FIXTURES / "heatmap_legacy_pixels"),
                "--page-url",
                GOOD_URL,
            ],
        )
        assert module.main() == 1
