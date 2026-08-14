"""Tests for the Phase 7a CI report core (``action/report.py``).

Covers the JUnit parsing, repair-candidate marking (spec §8/7a: marking only,
no adaptation execution) and the report payload shape the self-test workflow
asserts (the 7b comment shape). Offline — no Docker, no browser.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import action.report as ci_report

JUNIT_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="pytest" tests="{total}" failures="{failures}" errors="{errors}" skipped="{skipped}" time="12.50">
{cases}  </testsuite>
</testsuites>
"""


def _case(name: str, failure: str | None = None, skipped: bool = False) -> str:
    if skipped:
        return f'    <testcase name="{name}" classname="test_pkg" time="1.0"><skipped/></testcase>\n'
    if failure is not None:
        return (
            f'    <testcase name="{name}" classname="test_pkg" time="2.0">\n'
            f'      <failure message="{failure}">{failure}</failure>\n'
            f"    </testcase>\n"
        )
    return f'    <testcase name="{name}" classname="test_pkg" time="1.0"/>\n'


def _write_junit(tmp_path: Path) -> Path:
    cases = (
        _case("test_ok")
        + _case("test_bad_locator", failure="Locator '#add' not found — waiting for locator")
        + _case("test_assert", failure="assert 1 == 2")
        + _case("test_strict", failure="strict mode violation: #btn resolved to 2 elements")
        + _case("test_timeout", failure="Timeout 30000ms exceeded waiting for get_by_text")
        + _case("test_skip", skipped=True)
    )
    xml = JUNIT_TEMPLATE.format(
        total=6,
        failures=4,
        errors=0,
        skipped=1,
        cases=cases,
    )
    path = tmp_path / "junit.xml"
    path.write_text(xml, encoding="utf-8")
    return path


def test_parse_junit_counts_and_failures(tmp_path: Path) -> None:
    stats = ci_report._parse_junit(_write_junit(tmp_path))
    assert stats["total"] == 6
    assert stats["passed"] == 1
    assert stats["failed"] == 4
    assert stats["skipped"] == 1
    assert stats["duration_s"] == 12.5
    assert len(stats["failed_tests"]) == 4
    names = {ft["test"] for ft in stats["failed_tests"]}
    assert names == {"test_bad_locator", "test_assert", "test_strict", "test_timeout"}


def test_repair_candidate_marking(tmp_path: Path) -> None:
    """Locator-class failures are marked; assertion failures always surface."""
    stats = ci_report._parse_junit(_write_junit(tmp_path))
    candidates = {c["test"] for c in stats["repair_candidates"]}
    assert candidates == {"test_bad_locator", "test_strict", "test_timeout"}
    assert "test_assert" not in candidates


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Error: Locator '#x' not found", True),
        ("waiting for locator('body') to be visible", True),
        ("strict mode violation: resolved to 2 elements", True),
        ("Timeout 30000ms exceeded", True),
        ("Unable to locate element: #x", True),
        ("assert 1 == 2", False),
        ("Expected value 5 but got 3", False),
    ],
)
def test_is_repair_candidate(message: str, expected: bool) -> None:
    assert ci_report._is_repair_candidate(message) is expected


def test_report_main_writes_comment_payload(tmp_path: Path) -> None:
    junit = _write_junit(tmp_path)
    out = tmp_path / "out"
    rc = ci_report.main(
        [
            "--mode",
            "run-existing",
            "--junit",
            str(junit),
            "--package",
            "some/package",
            "--workspace",
            "ws",
            "--output",
            str(out),
        ]
    )
    assert rc == 0

    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["mode"] == "run-existing"
    assert report["package"] == "some/package"
    assert report["tests"]["total"] == 6
    assert report["tests"]["passed"] == 1
    assert report["tests"]["failed"] == 4
    assert len(report["repair_candidates"]) == 3
    assert isinstance(report["failed_tests"], list)

    md = (out / "report.md").read_text(encoding="utf-8")
    assert md.startswith("## 🤖 AI Test Generator — results")
    assert "Repair candidates" in md


def test_report_missing_junit_exits_2(tmp_path: Path) -> None:
    rc = ci_report.main(["--mode", "run-existing", "--junit", str(tmp_path / "nope.xml"), "--output", str(tmp_path)])
    assert rc == 2


def test_report_context_fields_and_site_line(tmp_path: Path) -> None:
    junit = _write_junit(tmp_path)
    out = tmp_path / "out"
    rc = ci_report.main(
        [
            "--mode",
            "generate-and-run",
            "--junit",
            str(junit),
            "--package",
            "pkg",
            "--workspace",
            "ws",
            "--url",
            "https://staging.example.com",
            "--story",
            "story.md",
            "--model",
            "gpt-4o",
            "--provider",
            "openai",
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["url"] == "https://staging.example.com"
    assert report["model"] == "gpt-4o"
    assert report["provider"] == "openai"
    md = (out / "report.md").read_text(encoding="utf-8")
    assert "**Site:** https://staging.example.com" in md
    assert "**Model:** gpt-4o" in md


def test_report_flaky_block_injected(tmp_path: Path) -> None:
    junit = _write_junit(tmp_path)
    out = tmp_path / "out"
    flaky_txt = tmp_path / "flaky.txt"
    flaky_txt.write_text(
        "**Flaky (last few runs):**\n- `test_timeout` — 1 failure(s) across 3 run(s)", encoding="utf-8"
    )
    rc = ci_report.main(
        [
            "--mode",
            "generate-and-run",
            "--junit",
            str(junit),
            "--package",
            "pkg",
            "--workspace",
            "ws",
            "--flaky",
            str(flaky_txt),
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert "Flaky" in report["flaky"]
    md = (out / "report.md").read_text(encoding="utf-8")
    assert "**Flaky (last few runs):**" in md
    assert "test_timeout" in md


def test_report_flaky_absent_when_empty(tmp_path: Path) -> None:
    junit = _write_junit(tmp_path)
    out = tmp_path / "out"
    rc = ci_report.main(
        ["--mode", "run-existing", "--junit", str(junit), "--package", "pkg", "--workspace", "ws", "--output", str(out)]
    )
    assert rc == 0
    md = (out / "report.md").read_text(encoding="utf-8")
    assert "**Flaky" not in md
