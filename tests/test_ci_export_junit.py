"""Tests for the AI-028 evidence JUnit exporter used by the CI action
(``action/export_evidence_junit.py``).

Offline: writes a tiny sidecar, indexes it with the REAL EvidenceIndex /
SQLitePersistence, asserts the emitted JUnit is well-formed and carries the
sidecar-derived testcase. Mirrors the action's run-existing flow.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import action.export_evidence_junit as exporter


def _sidecar(package_dir: Path, name: str, status: str = "passed") -> Path:
    evidence_dir = package_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    sidecar = evidence_dir / f"{name}.evidence.json"
    sidecar.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "test": {
                    "name": name,
                    "condition_ref": "TC-01",
                    "story_ref": "S01",
                    "status": status,
                    "duration_s": 1.25,
                },
                "page": {"url": "http://127.0.0.1:8123/index.html"},
                "steps": [
                    {
                        "type": "navigate",
                        "label": "Navigate to http://127.0.0.1:8123/index.html",
                        "value": "http://127.0.0.1:8123/index.html",
                        "locator": None,
                        "screenshot": None,
                        "element": {},
                        "url": "http://127.0.0.1:8123/index.html",
                        "result": {"status": "passed", "run_count": 1},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return sidecar


def test_export_writes_enriched_junit(tmp_path: Path) -> None:
    _sidecar(tmp_path, "test_flow")
    _sidecar(tmp_path, "test_failed", status="failed")
    out = tmp_path / "junit-evidence.xml"

    rc = exporter.main(
        [
            "--evidence-dir",
            str(tmp_path / "evidence"),
            "--output",
            str(out),
            "--suite-name",
            "ai-test-generator",
        ]
    )
    assert rc == 0
    assert out.exists()

    root = ET.parse(out).getroot()
    suites = [root] if root.tag == "testsuite" else list(root)
    total = sum(int(s.get("tests", 0) or 0) for s in suites)
    assert total == 2
    failures = sum(int(s.get("failures", 0) or 0) for s in suites)
    assert failures == 1

    names = [n for n in (c.get("name") for c in root.iter("testcase")) if n]
    assert any("test_flow" in n for n in names)
    assert any("test_failed" in n for n in names)


def test_export_empty_evidence_is_valid_junit(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    out = tmp_path / "junit-evidence.xml"
    rc = exporter.main(
        [
            "--evidence-dir",
            str(tmp_path / "evidence"),
            "--output",
            str(out),
            "--suite-name",
            "ai-test-generator",
        ]
    )
    assert rc == 0
    root = ET.parse(out).getroot()
    total = sum(int(s.get("tests", 0) or 0) for s in ([root] if root.tag == "testsuite" else list(root)))
    assert total == 0


def test_export_missing_dir_is_valid_junit(tmp_path: Path) -> None:
    out = tmp_path / "junit-evidence.xml"
    rc = exporter.main(
        [
            "--evidence-dir",
            str(tmp_path / "nope"),
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    assert ET.parse(out).getroot().tag in {"testsuites", "testsuite"}
