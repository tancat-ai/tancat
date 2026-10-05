"""Tests for the evidence-tab package scoping (F1).

The Coverage Heatmap and Gantt Timeline used to read ``evidence_dirs[0]``,
the alphabetically-first (oldest) package, so they showed stale data. These
tests pin the picker to the loaded/generated package, then the newest.
"""

from __future__ import annotations

import os
from pathlib import Path

from src.ui.ui_evidence import _evidence_dir_for_root, _pick_current_evidence_dir


def _make_package(tmp_path: Path, name: str) -> Path:
    """Create ``<tmp>/<name>/evidence`` with one sidecar; return the evidence dir."""
    evidence = tmp_path / name / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "test_01.evidence.json").write_text("{}", encoding="utf-8")
    return evidence


def test_evidence_dir_for_root_accepts_dir_file_and_evidence(tmp_path: Path) -> None:
    evidence = _make_package(tmp_path, "test_20260101_000000_story")
    package = evidence.parent
    test_file = package / "test_01_story.py"
    test_file.write_text("", encoding="utf-8")

    assert _evidence_dir_for_root(package) == evidence
    assert _evidence_dir_for_root(test_file) == evidence
    assert _evidence_dir_for_root(evidence) == evidence
    assert _evidence_dir_for_root("") is None
    assert _evidence_dir_for_root(tmp_path / "missing") is None


def test_pick_prefers_the_package_the_user_loaded(tmp_path: Path) -> None:
    loaded = _make_package(tmp_path, "test_20260101_000000_loaded")
    other = _make_package(tmp_path, "test_20260303_000000_other")
    os.utime(loaded, (1, 1))
    os.utime(other, (10, 10))

    # Even though ``other`` is newer, the loaded package wins.
    picked = _pick_current_evidence_dir([loaded, other], [str(loaded.parent)])
    assert picked == loaded


def test_pick_falls_back_to_newest_not_alphabetically_first(tmp_path: Path) -> None:
    oldest = _make_package(tmp_path, "test_20260101_000000_a")
    newest = _make_package(tmp_path, "test_20260303_000000_z")
    os.utime(oldest, (1, 1))
    os.utime(newest, (10, 10))

    # Alphabetically first is the oldest; the picker must choose the newest.
    picked = _pick_current_evidence_dir([oldest, newest], [])
    assert picked == newest


def test_pick_returns_none_when_nothing_exists() -> None:
    assert _pick_current_evidence_dir([], [None, ""]) is None
