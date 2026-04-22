from __future__ import annotations

import json
from pathlib import Path

from src.heatmap_utils import build_story_confidence


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
