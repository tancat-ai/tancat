#!/usr/bin/env python3
"""Pre-launch parity check, step 1: mode and reports.

Two axes, both OFFLINE - no model, no browser, no network:

  axis 1  mode     one fixed package, exported POM and flat, must yield the same
                   tests in the same order and the same logical step sequence.
  axis 2  reports  one fixed evidence set, rendered as HTML / JSON / NDJSON /
                   JUnit / CSV, must tell the same story in all five.

The point of the fixed input: with a live model every run differs, so parity is
measured on one recorded package and one recorded evidence set, never on a fresh
generation. See docs/parity.md for what parity is expected to mean, what is
allowed to differ, and which axes are not covered yet.

Usage:
    python scripts/parity_check.py                    # both axes, fixed fixture
    python scripts/parity_check.py --fixture DIR      # another recorded pair
    python scripts/parity_check.py --json             # machine-readable rows

Exit codes:
    0  every compared artefact agreed (allowed differences are listed, not failed)
    1  at least one unexpected difference
    2  the fixture itself is missing or unreadable
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PACKAGE = REPO_ROOT / "fixtures" / "golden_package"
DEFAULT_EVIDENCE = REPO_ROOT / "fixtures" / "parity" / "sidecars"

OK = "ok"
DIFF = "DIFF"
ALLOWED = "allowed"
PENDING = "pending"


@dataclass
class Row:
    """One comparison line in the parity table."""

    axis: str
    artefact: str
    expected: str
    actual: str
    verdict: str

    def as_dict(self) -> dict[str, str]:
        return {
            "axis": self.axis,
            "artefact": self.artefact,
            "expected": self.expected,
            "actual": self.actual,
            "verdict": self.verdict,
        }


@dataclass
class Report:
    rows: list[Row] = field(default_factory=list)

    def add(self, axis: str, artefact: str, expected: Any, actual: Any) -> None:
        same = expected == actual
        self.rows.append(Row(axis, artefact, str(expected), str(actual), OK if same else DIFF))

    def allowed(self, axis: str, artefact: str, expected: str, actual: str) -> None:
        self.rows.append(Row(axis, artefact, expected, actual, ALLOWED))

    def pending(self, axis: str, artefact: str, expected: str, actual: str) -> None:
        """A comparison the recorded input cannot answer yet, stated not skipped."""
        self.rows.append(Row(axis, artefact, expected, actual, PENDING))

    @property
    def failures(self) -> list[Row]:
        return [r for r in self.rows if r.verdict == DIFF]


# ── axis 1: mode ─────────────────────────────────────────────────────────────

_TRACKER_CALL = re.compile(r"\bevidence_tracker\.(\w+)\((.*)\)\s*$")
_POM_CALL = re.compile(r"\b(\w+_page)\.(\w+)\((.*)\)\s*$")
_LOCATOR_CALL = re.compile(r"page\.locator\((['\"])(.*?)\1\)\.(\w+)\((.*)\)\s*$")
_GOTO_CALL = re.compile(r"\bpage\.goto\((.*)\)\s*$")
_EXPECT_VISIBLE = re.compile(r"expect\(page\.locator\((['\"])(.*?)\1\)\)\.to_be_visible\(\)")
_ARG_LITERAL = re.compile(r"^['\"](.*)['\"]$")
_SELECTOR_KW = re.compile(r"selector=(['\"])(.*?)\1")
_POM_ACTION = {"click": "click", "fill": "fill", "assert_visible": "assert_visible"}


def _first_arg(arguments: str) -> str:
    return arguments.split(",", 1)[0].strip()


def actions_from_source(source: str) -> list[tuple[str, str]]:
    """Return the (action, target) sequence a test file performs.

    ``target`` is the selector or the URL, never the label: a page-object call
    carries its label and a flat call does not, and that difference is allowed.
    """
    steps: list[tuple[str, str]] = []
    for raw in source.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        goto = _GOTO_CALL.search(line)
        if goto:
            literal = _ARG_LITERAL.match(_first_arg(goto.group(1)))
            steps.append(("navigate", literal.group(1) if literal else "computed"))
            continue
        locator = _LOCATOR_CALL.search(line)
        if locator:
            steps.append((locator.group(3), locator.group(2)))
            continue
        visible = _EXPECT_VISIBLE.search(line)
        if visible:
            steps.append(("assert_visible", visible.group(2)))
            continue
        pom = _POM_CALL.search(line)
        if pom and pom.group(2) in _POM_ACTION:
            selector = _SELECTOR_KW.search(pom.group(3))
            steps.append((_POM_ACTION[pom.group(2)], selector.group(2) if selector else ""))
            continue
        tracker = _TRACKER_CALL.search(line)
        if tracker and tracker.group(1) in {"click", "fill", "assert_visible", "navigate"}:
            steps.append((tracker.group(1), _first_arg(tracker.group(2)).strip("'\"")))
    return steps


def test_names(source: str) -> list[str]:
    """Test function names, in file order."""
    return re.findall(r"^def (test_\w+)\(", source, flags=re.MULTILINE)


def _html_stat(html: str, label: str) -> int | None:
    """Read one number out of the rendered summary (``stat <label>``)."""
    match = re.search(rf"<div class='stat {label}'><div class='stat-value'>(\d+)</div>", html)
    return int(match.group(1)) if match else None


def _check_gates(report: Report, gate_dir: Path | None) -> None:
    """Gate 1 and gate 2 are properties of a RUN, not of emitted source.

    They are compared only when a recorded pair exists (``--gate-dir`` with
    ``pom.json`` and ``flat.json``, each ``{"gate1": <float>, "gate2": <int>}``).
    Until step 1b records that pair the row says so instead of guessing: an
    invented number would pass and prove nothing.
    """
    recorded = [gate_dir / "pom.json", gate_dir / "flat.json"] if gate_dir else []
    if recorded and all(path.exists() for path in recorded):
        pom = json.loads(recorded[0].read_text(encoding="utf-8"))
        flat = json.loads(recorded[1].read_text(encoding="utf-8"))
        report.add("mode", "gate 1 (resolution)", pom.get("gate1"), flat.get("gate1"))
        report.add("mode", "gate 2 (false positives)", pom.get("gate2"), flat.get("gate2"))
        return
    report.pending(
        "mode",
        "gate 1 / gate 2 numbers",
        "recorded pair of runs",
        "not recorded yet - needs the executable leg (step 1b)",
    )


def _load_export_service() -> Any:
    sys.path.insert(0, str(REPO_ROOT))
    from src.export_service import ExportMode, export_clean_suite

    return ExportMode, export_clean_suite


def check_mode(package: Path, report: Report, workdir: Path, gate_dir: Path | None = None) -> None:
    """Export one package both ways and compare what the product must agree on."""
    export_mode, export_clean_suite = _load_export_service()

    exports: dict[str, Path] = {}
    for name, mode in (("pom", export_mode.POM), ("flat", export_mode.FLAT)):
        result = export_clean_suite(
            source_package_dir=package,
            export_mode=mode,
            output_base_dir=str(workdir / name),
        )
        exports[name] = Path(result.export_dir)

    pom_tests = sorted(exports["pom"].glob("test_*.py"))
    flat_tests = sorted(exports["flat"].glob("test_*.py"))
    report.add("mode", "test files", [p.name for p in pom_tests], [p.name for p in flat_tests])

    pom_source = "\n".join(p.read_text(encoding="utf-8") for p in pom_tests)
    flat_source = "\n".join(p.read_text(encoding="utf-8") for p in flat_tests)
    report.add("mode", "test count", len(test_names(pom_source)), len(test_names(flat_source)))
    report.add("mode", "test names and order", test_names(pom_source), test_names(flat_source))

    report.add(
        "mode",
        "step sequence (action + target)",
        actions_from_source(pom_source),
        actions_from_source(flat_source),
    )

    def rel_files(root: Path) -> set[str]:
        return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}

    pom_files = rel_files(exports["pom"])
    flat_files = rel_files(exports["flat"])
    report.add(
        "mode",
        "shipped run-history DB",
        any(f.endswith("run_results.sqlite") for f in pom_files),
        any(f.endswith("run_results.sqlite") for f in flat_files),
    )

    _check_gates(report, gate_dir)

    report.allowed(
        "mode",
        "file layout",
        "pages/ + test files",
        "one test file, no pages/ (flat)",
    )
    report.allowed(
        "mode",
        "step labels",
        "carried on the page-object call",
        "dropped by the flat export",
    )
    report.add(
        "mode",
        "pages/ shipped only in POM",
        True,
        any(f.startswith("pages/") for f in pom_files) and not any(f.startswith("pages/") for f in flat_files),
    )
    report.add(
        "mode",
        "no tracker call left in either export",
        0,
        pom_source.count("evidence_tracker.") + flat_source.count("evidence_tracker."),
    )
    report.add("mode", "flat export is non-empty", True, bool(flat_files))


# ── axis 2: reports ──────────────────────────────────────────────────────────

_SIDECAR_GLOB = "*.evidence.json"


def _load_sidecars(evidence_dir: Path) -> list[dict[str, Any]]:
    sidecars: list[dict[str, Any]] = []
    for path in sorted(evidence_dir.glob(_SIDECAR_GLOB)):
        sidecars.append(json.loads(path.read_text(encoding="utf-8")))
    return sidecars


def _truth(sidecars: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """The facts every report must agree on, taken from the evidence itself."""
    tests = list(sidecars)
    return {
        "tests": len(tests),
        "passed": sum(1 for t in tests if t.get("test", {}).get("status") == "passed"),
        "failed": sum(1 for t in tests if t.get("test", {}).get("status") == "failed"),
        "steps": sum(len(t.get("steps", [])) for t in tests),
        "mismatches": sum(1 for t in tests for s in t.get("steps", []) if s.get("page_mismatch")),
        "redirects": sum(1 for t in tests for s in t.get("steps", []) if (s.get("navigation") or {}).get("redirected")),
    }


def _facts_from_csv(text: str) -> dict[str, Any]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    rows = list(lines[1:])
    statuses = [r.split(",")[3] for r in rows if len(r.split(",")) > 3]
    return {
        "tests": len(rows),
        "passed": statuses.count("passed"),
        "failed": statuses.count("failed"),
        "steps": sum(int(r.split(",")[5] or 0) for r in rows if len(r.split(",")) > 5 and r.split(",")[5].isdigit()),
    }


def _facts_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "tests": len(rows),
        "passed": sum(1 for r in rows if r.get("status") == "passed"),
        "failed": sum(1 for r in rows if r.get("status") == "failed"),
    }


def check_reports(evidence_dir: Path, report: Report, workdir: Path) -> None:
    """Render one evidence set five ways and compare the story they tell."""
    sys.path.insert(0, str(REPO_ROOT))
    from src.evidence_export import export_csv, export_junit_xml, export_ndjson
    from src.evidence_index import EvidenceIndex
    from src.report_formatters import generate_html_report
    from src.sqlite_persistence import SQLitePersistence

    sidecars = _load_sidecars(evidence_dir)
    if not sidecars:
        raise SystemExit(f"no {_SIDECAR_GLOB} under {evidence_dir}")
    truth = _truth(sidecars)

    # A throwaway index: the check must not touch the workspace's evidence DB.
    index = EvidenceIndex(SQLitePersistence(db_path=workdir / "parity_index.sqlite"))
    indexed = index.build_or_refresh(base_dir=evidence_dir, force=True)
    report.add("reports", "indexed sidecar count", truth["tests"], indexed)

    csv_text = export_csv(index)
    ndjson_text = export_ndjson(index)
    junit_text = export_junit_xml(index)
    rows = [
        {
            "test_name": s["test"]["name"],
            "status": s["test"]["status"],
            "step_count": len(s.get("steps", [])),
        }
        for s in sidecars
    ]
    json_text = json.dumps(rows)
    html_text = generate_html_report(rows, None, title="parity fixture")

    csv_facts = _facts_from_csv(csv_text)
    ndjson_facts = _facts_from_rows(
        [
            json.loads(ln)
            and {
                "status": json.loads(ln)["test"]["status"],
                "test_name": json.loads(ln)["test"]["name"],
            }
            for ln in ndjson_text.splitlines()
            if ln.strip()
        ]
    )
    junit_facts = {
        "tests": junit_text.count("<testcase "),
        "failed": junit_text.count("<failure"),
    }
    json_facts = _facts_from_rows(json.loads(json_text))

    for fmt, facts in (
        ("CSV", csv_facts),
        ("NDJSON", ndjson_facts),
        ("JSON", json_facts),
    ):
        report.add("reports", f"{fmt} test count", truth["tests"], facts["tests"])
        report.add("reports", f"{fmt} passed", truth["passed"], facts["passed"])
        report.add("reports", f"{fmt} failed", truth["failed"], facts["failed"])
    report.add("reports", "CSV step total", truth["steps"], csv_facts["steps"])
    report.add("reports", "JUnit testcases", truth["tests"], junit_facts["tests"])
    report.add("reports", "JUnit failures", truth["failed"], junit_facts["failed"])
    # The HTML is a rendered view of the same rows; compare what it states, not
    # its markup. Per-step detail inside the HTML overlay has its own tests
    # (tests/test_evidence_overlay_*).
    report.add(
        "reports", "HTML names every test", truth["tests"], sum(1 for s in sidecars if s["test"]["name"] in html_text)
    )
    # The rendered summary carries the counts; a word-search would pass on any
    # page that merely mentions the word "passed".
    for label, key in (("total", "tests"), ("passed", "passed"), ("failed", "failed")):
        report.add(
            "reports",
            f"HTML summary {label}",
            truth[key],
            _html_stat(html_text, label),
        )

    # Fields the owner named: page-mismatch and navigation survive into the
    # machine formats that carry the full sidecar.
    ndjson_objs = [json.loads(ln) for ln in ndjson_text.splitlines() if ln.strip()]
    report.add(
        "reports",
        "NDJSON keeps page_mismatch",
        truth["mismatches"],
        sum(1 for o in ndjson_objs for st in o.get("steps", []) if st.get("page_mismatch")),
    )
    report.add(
        "reports",
        "NDJSON keeps navigation.redirected",
        truth["redirects"],
        sum(1 for o in ndjson_objs for st in o.get("steps", []) if (st.get("navigation") or {}).get("redirected")),
    )


# ── table and entry point ────────────────────────────────────────────────────


def render_table(rows: list[Row]) -> str:
    headers = ("axis", "artefact", "expected", "actual", "verdict")
    cells = [(r.axis, r.artefact, r.expected, r.actual, r.verdict) for r in rows]
    widths = [max(len(h), *(len(c[i]) for c in cells)) if cells else len(h) for i, h in enumerate(headers)]
    widths = [min(w, 60) for w in widths]

    def line(cols: Iterable[str]) -> str:
        return "  ".join(str(c)[:w].ljust(w) for c, w in zip(cols, widths, strict=False))

    out = [line(headers), line("-" * w for w in widths)]
    out.extend(line(c) for c in cells)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline POM/flat and report parity check.")
    parser.add_argument("--package", default=str(DEFAULT_PACKAGE), help="package exported in both modes")
    parser.add_argument("--evidence", default=str(DEFAULT_EVIDENCE), help="evidence dir rendered five ways")
    parser.add_argument(
        "--gate-dir",
        default=str(REPO_ROOT / "fixtures" / "parity" / "gates"),
        help="recorded {pom,flat}.json gate numbers; absent means the row is pending",
    )
    parser.add_argument("--json", action="store_true", help="print rows as JSON")
    parser.add_argument("--keep", action="store_true", help="keep the temporary export dirs")
    args = parser.parse_args(argv)

    package = Path(args.package)
    evidence = Path(args.evidence)
    if not (package / "package_manifest.json").exists():
        print(f"fixture error: {package} is not a generated package", file=sys.stderr)
        return 2
    if not evidence.is_dir():
        print(f"fixture error: no evidence dir at {evidence}", file=sys.stderr)
        return 2

    report = Report()
    workdir = Path(tempfile.mkdtemp(prefix="parity_"))
    try:
        check_mode(package, report, workdir, Path(args.gate_dir))
        check_reports(evidence, report, workdir)
    finally:
        if not args.keep:
            shutil.rmtree(workdir, ignore_errors=True)
        else:
            print(f"exports kept in {workdir}")

    if args.json:
        print(json.dumps([r.as_dict() for r in report.rows], indent=1))
    else:
        print(render_table(report.rows))

    failures = report.failures
    allowed = sum(1 for r in report.rows if r.verdict == ALLOWED)
    pending = sum(1 for r in report.rows if r.verdict == PENDING)
    per_axis = ", ".join(
        f"{axis} {sum(1 for r in report.rows if r.axis == axis)}" for axis in dict.fromkeys(r.axis for r in report.rows)
    )
    print(
        f"\n{len(report.rows)} comparisons ({per_axis}), {len(failures)} unexpected difference(s), "
        f"{allowed} documented allowed difference(s), {pending} pending"
    )
    if failures:
        for r in failures:
            print(f"  DIFF  {r.axis}/{r.artefact}: expected {r.expected!r}, got {r.actual!r}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
