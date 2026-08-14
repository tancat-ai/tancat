"""Flaky-history tests (Phase 7b, AI-011 markers from the action's cached
per-branch run history)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from action.flaky_history import (
    MAX_RUNS_KEPT,
    get_flaky,
    merge_run,
    render_flaky_section,
    save_history,
)


def _write_junit(path: Path, cases: list[tuple[str, str]]) -> None:
    """cases: [(test_name, status)] with status in passed|failed|skipped|error."""
    suite = ET.Element("testsuite", {"tests": str(len(cases))})
    for name, status in cases:
        case = ET.SubElement(suite, "testcase", {"name": name, "classname": "pkg"})
        if status == "failed":
            ET.SubElement(case, "failure", {"message": "Locator 'a' not found"}).text = "waiting for locator"
        elif status == "error":
            ET.SubElement(case, "error", {"message": "boom"}).text = "boom"
        elif status == "skipped":
            ET.SubElement(case, "skipped")
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=False)


def test_merge_run_appends_and_trims(tmp_path: Path) -> None:
    junit = tmp_path / "junit.xml"
    _write_junit(junit, [("t1", "passed"), ("t2", "failed")])
    history: dict[str, Any] = {"runs": []}
    merged = merge_run(history, junit, package="pkg1", run_id="r1")
    assert len(merged["runs"]) == 1
    assert merged["runs"][0]["run_id"] == "r1"
    assert merged["runs"][0]["package"] == "pkg1"
    assert merged["runs"][0]["results"] == [{"name": "t1", "status": "passed"}, {"name": "t2", "status": "failed"}]

    # Trim: MAX_RUNS_KEPT runs kept.
    for i in range(MAX_RUNS_KEPT + 3):
        merge_run(history, junit, run_id=f"r{i}")
    assert len(history["runs"]) == MAX_RUNS_KEPT


def test_flaky_detection_both_pass_and_fail(tmp_path: Path) -> None:
    junit = tmp_path / "junit.xml"
    history: dict[str, Any] = {"runs": []}
    # Run 1: t1 passes, t2 fails
    _write_junit(junit, [("t1", "passed"), ("t2", "failed")])
    merge_run(history, junit, run_id="r1")
    # Run 2: t1 fails, t2 passes -> both are flaky now
    _write_junit(junit, [("t1", "failed"), ("t2", "passed")])
    merge_run(history, junit, run_id="r2")

    flaky = dict(get_flaky(history))
    assert set(flaky) == {"t1", "t2"}
    assert flaky["t1"] == {"passed": 1, "failed": 1, "error": 0, "skipped": 0}
    # Sorted by flakiness ratio (minority/total = 0.5 both) — stable.

    # A consistently-passing test is NOT flaky.
    _write_junit(junit, [("t3", "passed"), ("t3", "passed")])
    merged = merge_run(history, junit, run_id="r3")
    flaky2 = dict(get_flaky(merged))
    assert "t3" not in flaky2


def test_flaky_requires_min_runs(tmp_path: Path) -> None:
    junit = tmp_path / "junit.xml"
    _write_junit(junit, [("t1", "passed")])
    history = merge_run({"runs": []}, junit, run_id="r1")
    assert get_flaky(history, min_runs=2) == []
    _write_junit(junit, [("t1", "failed")])
    merged = merge_run(history, junit, run_id="r2")
    flaky = get_flaky(merged, min_runs=2)
    assert [name for name, _ in flaky] == ["t1"]


def test_render_flaky_section() -> None:
    assert render_flaky_section([]) == ""
    block = render_flaky_section([("test_08[chromium]", {"passed": 2, "failed": 1, "error": 0, "skipped": 0})])
    assert "Flaky" in block
    assert "test_08[chromium]" in block
    assert "1 failure" in block


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    junit = tmp_path / "junit.xml"
    _write_junit(junit, [("t1", "passed")])
    path = tmp_path / "run-history.json"
    save_history(merge_run({"runs": []}, junit, run_id="r1"), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["runs"][0]["results"][0] == {"name": "t1", "status": "passed"}
