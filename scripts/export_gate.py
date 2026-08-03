#!/usr/bin/env python3
"""Export gate — end-to-end validation that exported test suites actually run.

B-031: exports were never validated end-to-end. The CLI-review audit found 34
of 35 exports in exported_tests/ were ``def test_x(page): pass`` stubs, and
the one real export was non-importable (POM imports with no pages/ dir, dead
``@pytest.mark.evidence`` decorators, ``NameError`` from an unstripped tracker
argument). This script is the export analogue of verify_production.py:

  1. Exports a source package in BOTH modes (flat + POM)
  2. Validates the exported artifacts: no evidence_tracker remnants, no
     @pytest.mark.evidence decorators, no stub bodies, POM pages shipped,
     run_results.sqlite copied (B-032)
  3. Collects both exported suites with pytest (catches import errors)
  4. Runs both exported suites and asserts they pass

The default source is the bundled golden fixture (fixtures/golden_package/),
which mirrors a real generated package (arg-carrying evidence decorators,
POM pages with generated names, run-history DB) and targets a tiny localhost
site served by this script — fully deterministic, no external network, CI-able.

Use ``--source <pkg>`` to validate a real generated package instead
(offline artifact + collect gates only; add ``--run-remote`` to execute the
flat export against the package's live target, like verify_production).

Usage:
    python scripts/export_gate.py                  # golden fixture, full run
    python scripts/export_gate.py --keep           # keep export dirs on pass
    python scripts/export_gate.py --source <pkg>   # real package, offline
    python scripts/export_gate.py --source <pkg> --run-remote

Exit codes:
    0  All gates passed — exports are runnable
    1  One or more gates failed — do NOT ship
"""

from __future__ import annotations

import argparse
import ast
import http.server
import re
import shutil
import socketserver
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

GOLDEN_PACKAGE = PROJECT_ROOT / "fixtures" / "golden_package"
GOLDEN_SITE_DIR = PROJECT_ROOT / "fixtures" / "golden_site"
GOLDEN_PORT = 8123


# ---------------------------------------------------------------------------
# Gate results
# ---------------------------------------------------------------------------


@dataclass
class Gate:
    name: str
    passed: bool
    detail: str = ""


class GateResult:
    """Ordered gate list with pass/fail counts."""

    def __init__(self) -> None:
        self.gates: list[Gate] = []

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.gates.append(Gate(name=name, passed=passed, detail=detail))
        status = "OK  " if passed else "FAIL"
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))

    @property
    def passed(self) -> int:
        return sum(1 for g in self.gates if g.passed)

    @property
    def failed(self) -> int:
        return sum(1 for g in self.gates if not g.passed)

    @property
    def total(self) -> int:
        return len(self.gates)


# ---------------------------------------------------------------------------
# Golden site server (deterministic localhost target)
# ---------------------------------------------------------------------------


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass


class GoldenSiteServer:
    """Serve fixtures/golden_site on 127.0.0.1:GOLDEN_PORT from a thread."""

    def __enter__(self) -> GoldenSiteServer:
        handler = lambda *args, **kwargs: _QuietHandler(  # noqa: E731
            *args, directory=str(GOLDEN_SITE_DIR), **kwargs
        )
        self._httpd = socketserver.TCPServer(("127.0.0.1", GOLDEN_PORT), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


# ---------------------------------------------------------------------------
# Artifact validation helpers
# ---------------------------------------------------------------------------


def _stub_test_count(package_dir: Path) -> int:
    """Count test functions whose bodies are only pass/.../pytest.skip()."""
    from src.export_service import _is_stub_function

    count = 0
    for test_file in package_dir.glob("test_*.py"):
        try:
            tree = ast.parse(test_file.read_text(encoding="utf-8"))
        except OSError, SyntaxError:
            count += 1  # unparseable == broken export
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                if _is_stub_function(node):
                    count += 1
    return count


def _validate_flat_artifacts(export_dir: Path) -> list[str]:
    """Return a list of problems found in a flat export (empty == clean)."""
    problems: list[str] = []
    for test_file in export_dir.glob("test_*.py"):
        content = test_file.read_text(encoding="utf-8")
        if "evidence_tracker" in content:
            problems.append(f"{test_file.name}: evidence_tracker remnant")
        if "@pytest.mark.evidence" in content or "@ pytest.mark.evidence" in content:
            problems.append(f"{test_file.name}: evidence decorator survived")
        if "from pages." in content or "import pages" in content:
            problems.append(f"{test_file.name}: POM import survived flat export")
        if re.search(r"\b\w+Page\(page", content):
            problems.append(f"{test_file.name}: POM instantiation survived flat export")
        if "from playwright" not in content:
            problems.append(f"{test_file.name}: missing playwright import")
    stub_count = _stub_test_count(export_dir)
    if stub_count:
        problems.append(f"{stub_count} stub test function(s) in flat export")
    return problems


def _validate_pom_artifacts(export_dir: Path) -> list[str]:
    """Return a list of problems found in a POM export (empty == clean)."""
    problems: list[str] = []
    pages_dir = export_dir / "pages"
    shipped = sorted(f.name for f in pages_dir.glob("*.py") if f.name != "__init__.py") if pages_dir.exists() else []
    if not shipped:
        problems.append("POM export shipped no page-object modules in pages/")
    for po_file in sorted(pages_dir.glob("*.py")):
        if po_file.name == "__init__.py":
            continue
        content = po_file.read_text(encoding="utf-8")
        if "EvidenceTracker" in content:
            problems.append(f"pages/{po_file.name}: EvidenceTracker remnant")
        if "self.tracker" in content:
            problems.append(f"pages/{po_file.name}: self.tracker remnant")
        if "def __init__(self, page: Page, tracker" in content:
            problems.append(f"pages/{po_file.name}: tracker param survived")
    for test_file in export_dir.glob("test_*.py"):
        content = test_file.read_text(encoding="utf-8")
        if "evidence_tracker" in content:
            problems.append(f"{test_file.name}: evidence_tracker remnant")
        if "@pytest.mark.evidence" in content or "@ pytest.mark.evidence" in content:
            problems.append(f"{test_file.name}: evidence decorator survived")
        if "from pages." not in content:
            problems.append(f"{test_file.name}: POM import missing in POM-mode export")
    return problems


def _check_sqlite_copy(source: Path, export_dir: Path) -> tuple[bool, str]:
    """B-032: run_results.sqlite (or legacy name) must be copied when present.

    Returns (passed, detail). When the source package has no run-history DB
    at all, the gate passes with a "nothing to copy" note — the DB is an
    optional artifact and its absence in the source is not an export defect.
    """
    source_db = None
    for db_name in ("run_results.sqlite", "playwright_tests.db"):
        for candidate in (source / "evidence" / db_name, source / db_name):
            if candidate.exists():
                source_db = candidate
                break
        if source_db:
            break
    if source_db is None:
        return True, "source has no run-history DB — nothing to copy"
    for db_name in ("run_results.sqlite", "playwright_tests.db"):
        if (export_dir / "evidence" / db_name).exists():
            return True, f"evidence/{db_name} copied"
    return False, f"source DB {source_db.name} not copied to export evidence/"


# ---------------------------------------------------------------------------
# pytest helpers
# ---------------------------------------------------------------------------


def _run_pytest(paths: list[str], extra: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *paths,
        "-o",
        "addopts=",
        "-o",
        f"pythonpath={PROJECT_ROOT}",
        "--browser=chromium",
        "--screenshot=only-on-failure",
        "--timeout=120",
        "-q",
        "--tb=short",
        "--no-header",
        "-p",
        "no:cacheprovider",
    ]
    if extra:
        cmd.extend(extra)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=str(PROJECT_ROOT))


def _summary_line(stdout: str) -> str:
    match = re.search(r"=+ .*?=+", stdout)
    if not match:
        # Fallback: last "N passed" / "N failed" / "N errors" line
        counts = re.findall(r"(\d+) (passed|failed|errors?|skipped)", stdout)
        return ", ".join(f"{n} {kind}" for n, kind in counts[-4:]) if counts else "no summary"
    return match.group(0).strip("= ")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export gate — prove exported suites run")
    parser.add_argument(
        "--source",
        default="",
        help="Real generated package to validate (default: bundled golden fixture)",
    )
    parser.add_argument(
        "--run-remote",
        action="store_true",
        help="With --source: execute the flat export against the package's live target",
    )
    parser.add_argument("--keep", action="store_true", help="Keep export dirs on pass (default: delete)")
    parser.add_argument("--headed", action="store_true", help="Show browser during execution")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.headed:
        import os

        os.environ["PLAYWRIGHT_HEADLESS"] = "0"

    from src.export_service import _guard_stub_source, export_clean_suite
    from src.pipeline_models import ExportMode

    result = GateResult()
    exports: list[Path] = []

    source = Path(args.source).resolve() if args.source else GOLDEN_PACKAGE
    golden = not args.source

    if golden:
        print("=" * 60)
        print("EXPORT GATE — golden fixture (deterministic, localhost)")
        print("=" * 60)
    else:
        print("=" * 60)
        print(f"EXPORT GATE — source package: {source}")
        print("=" * 60)

    # --- Gate 1: source package is exportable (stub guard, B-031) ---
    if not source.exists():
        result.add("Source package exists", False, str(source))
        return _finish(result, exports, args.keep)
    try:
        _guard_stub_source(source)
        result.add("Source package passes stub guard", True)
    except ValueError as exc:
        result.add("Source package passes stub guard", False, str(exc))
        return _finish(result, exports, args.keep)

    # --- Gates 2-3: export both modes ---
    print("\n  [INFO] Exporting package (flat + POM)...")
    for mode in (ExportMode.FLAT, ExportMode.POM):
        try:
            export_result = export_clean_suite(
                source_package_dir=source,
                export_mode=mode,
                output_base_dir=str(PROJECT_ROOT / "exported_tests"),
                story_slug="gate_golden" if golden else "gate",
            )
            export_dir = Path(export_result.export_dir)
            exports.append(export_dir)
            result.add(f"Export {mode.value.upper()} succeeded", True, str(export_dir))
        except Exception as exc:  # noqa: BLE001
            result.add(f"Export {mode.value.upper()} succeeded", False, str(exc))
            return _finish(result, exports, args.keep)

    flat_dir, pom_dir = exports

    # --- Gates 4-5: artifact validation ---
    _report_problems(result, "Flat artifacts clean", _validate_flat_artifacts(flat_dir))
    _report_problems(result, "POM artifacts clean", _validate_pom_artifacts(pom_dir))

    # --- Gate 6: run-history DB copied (B-032) ---
    db_ok, db_detail = _check_sqlite_copy(source, flat_dir)
    result.add("Run-history DB copied (B-032)", db_ok, db_detail)

    # --- Gate 7: both suites collect (importability) ---
    # Collect each export in its own pytest invocation: same-named test files
    # in different dirs collide under pytest's default prepend import mode.
    collect_failed = False
    collected_total = 0
    for label, export_dir in (("Flat", flat_dir), ("POM", pom_dir)):
        collect = _run_pytest([str(export_dir), "--collect-only"])
        collected = re.search(r"(\d+) tests? collected", collect.stdout)
        collected_total += int(collected.group(1)) if collected else 0
        if collect.returncode != 0:
            collect_failed = True
            print(f"  [INFO] {label} collect output:")
            print(collect.stdout[-2000:])
    result.add(
        "Exported suites collect",
        not collect_failed and collected_total >= 2,
        f"{collected_total} tests collected across both modes",
    )

    # --- Gate 8+: execute the exported suites ---
    if golden:
        print(f"\n  [INFO] Serving golden site on 127.0.0.1:{GOLDEN_PORT}...")
        with GoldenSiteServer():
            for label, export_dir in (("Flat", flat_dir), ("POM", pom_dir)):
                run = _run_pytest([str(export_dir)])
                result.add(f"{label} export executes and passes", run.returncode == 0, _summary_line(run.stdout))
                if run.returncode != 0:
                    print(run.stdout[-3000:])
    elif args.run_remote:
        run = _run_pytest([str(flat_dir)])
        result.add(
            f"Flat export executes ({_summary_line(run.stdout)})",
            run.returncode == 0,
            _summary_line(run.stdout),
        )
        if run.returncode != 0:
            print(run.stdout[-3000:])
    else:
        result.add(
            "Offline mode (use --run-remote to execute against the live target)",
            True,
            "artifact + collect gates only",
        )

    return _finish(result, exports, args.keep)


def _report_problems(result: GateResult, name: str, problems: list[str]) -> None:
    if problems:
        result.add(name, False, "; ".join(problems))
    else:
        result.add(name, True, "clean")


def _finish(result: GateResult, exports: list[Path], keep: bool) -> int:
    print(f"\n{'=' * 60}")
    print(f"EXPORT GATE: {result.passed}/{result.total} gates passed ({result.failed} failed)")
    print(f"{'=' * 60}")

    if not keep:
        for export_dir in exports:
            if export_dir.exists():
                if result.failed == 0:
                    shutil.rmtree(export_dir, ignore_errors=True)
                else:
                    print(f"  [KEPT] {export_dir} (failed — keep for debugging)")

    if result.failed > 0:
        print("\nVERDICT: FAIL — exports are not runnable. Fix the failing gates above.")
        return 1
    print("\nVERDICT: PASS — exported suites are clean, importable and passing.")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = __import__("io").TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    sys.exit(main())
