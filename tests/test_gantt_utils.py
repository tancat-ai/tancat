from __future__ import annotations

import json
from pathlib import Path

from src.gantt_utils import build_gantt_summary_sentences, group_gantt_entries, load_gantt_entries


def _write_sidecar(
    path: Path, *, name: str, condition_ref: str, story_ref: str, status: str, duration_s: float
) -> None:
    payload = {
        "schema_version": "1.0",
        "test": {
            "name": name,
            "condition_ref": condition_ref,
            "story_ref": story_ref,
            "status": status,
            "duration_s": duration_s,
        },
        "steps": [],
        "run_history": {"total_runs": 1, "passed_runs": 1, "failed_runs": 0},
        "page": {"url": "http://example"},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_gantt_entries_and_summary(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()

    _write_sidecar(
        evidence_dir / "test_a.evidence.json",
        name="test_a",
        condition_ref="BC01.01",
        story_ref="BC01",
        status="passed",
        duration_s=1.25,
    )
    _write_sidecar(
        evidence_dir / "test_b.evidence.json",
        name="test_b",
        condition_ref="BC01.02",
        story_ref="BC01",
        status="failed",
        duration_s=4.5,
    )

    entries = load_gantt_entries(evidence_dir)
    assert len(entries) == 2
    assert {e.condition_ref for e in entries} == {"BC01.01", "BC01.02"}

    fastest, slowest, coverage = build_gantt_summary_sentences(entries, total_expected=4)
    assert "BC01.01" in fastest
    assert "BC01.02" in slowest
    assert "2/4" in coverage


def test_group_gantt_entries_with_missing_meta(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    _write_sidecar(
        evidence_dir / "test_a.evidence.json",
        name="test_a",
        condition_ref="BC01.01",
        story_ref="BC01",
        status="passed",
        duration_s=1.0,
    )
    entries = load_gantt_entries(evidence_dir)
    grouped = group_gantt_entries(entries, "sprint", condition_meta=None)
    assert list(grouped.keys()) == ["unknown"]
    assert grouped["unknown"][0].condition_ref == "BC01.01"
