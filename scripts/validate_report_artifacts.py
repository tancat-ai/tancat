"""Validate output artifacts (heatmap / Gantt / charts) — AI-043 Layer 1 gate.

Runs the deterministic invariants in ``src/artifact_validation.py`` against an
evidence directory and reports violations. Exit code 1 when any error-severity
issue is found (warnings tolerated) — the same convention as the eval-harness
quality gate.

Usage::

    python scripts/validate_report_artifacts.py --evidence-dir generated_tests/resolved/saucedemo/evidence
    python scripts/validate_report_artifacts.py --evidence-dir <dir> --page-url https://www.saucedemo.com/ --page-url https://www.saucedemo.com/inventory.html
    python scripts/validate_report_artifacts.py            # scan all generated_tests/*/evidence dirs

Note: page URLs default to the distinct URLs recorded in the sidecars'
``navigate`` steps when ``--page-url`` is omitted.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.artifact_validation import ArtifactValidationResult, validate_evidence_artifacts
from src.gantt_utils import safe_read_sidecar

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _discover_evidence_dirs() -> list[Path]:
    """All evidence dirs under generated_tests (resolved/verify/run outputs)."""
    root = PROJECT_ROOT / "generated_tests"
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("evidence") if p.is_dir())


def _page_urls_from_sidecars(evidence_dir: Path) -> list[str]:
    """Distinct normalized navigate-step URLs recorded in the sidecars."""
    urls: list[str] = []
    for sidecar_path in sorted(evidence_dir.glob("*.evidence.json")):
        sidecar = safe_read_sidecar(sidecar_path)
        if not sidecar:
            continue
        for step in sidecar.get("steps", []):
            if isinstance(step, dict) and "navigate" in str(step.get("type", "")).lower():
                url = str(step.get("value", "") or "")
                if url and url not in urls:
                    urls.append(url)
    return urls


def _report(result: ArtifactValidationResult, evidence_dir: Path, urls: list[str]) -> None:
    print(f"\n=== Artifact validation: {evidence_dir} ({len(urls)} URL(s)) ===")
    for issue in result.issues:
        marker = "[ERROR]" if issue.severity == "error" else "[warn ]"
        print(f"  {marker} {issue.artifact:<9} {issue.message}")
    if not result.issues:
        print("  no issues — artifacts are internally consistent")
    print(f"  -> {len(result.errors)} error(s), {len(result.warnings)} warning(s)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence-dir", type=Path, help="Evidence directory to validate (default: all under generated_tests)"
    )
    parser.add_argument(
        "--page-url",
        action="append",
        default=[],
        help="Page URL(s) to heatmap-validate (default: from sidecar navigations)",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable report")
    args = parser.parse_args()

    dirs = [args.evidence_dir] if args.evidence_dir else _discover_evidence_dirs()
    if not dirs:
        print("No evidence directories found.", file=sys.stderr)
        return 2

    all_results: list[dict[str, object]] = []
    exit_code = 0
    for evidence_dir in dirs:
        urls = args.page_url or _page_urls_from_sidecars(evidence_dir)
        result = validate_evidence_artifacts(evidence_dir, urls)
        all_results.append(
            {"evidence_dir": str(evidence_dir), "errors": len(result.errors), "warnings": len(result.warnings)}
        )
        if args.json:
            continue
        _report(result, evidence_dir, urls)
        if result.errors:
            exit_code = 1

    if args.json:
        print(json.dumps(all_results, indent=2))
        exit_code = 1 if any(r["errors"] for r in all_results) else 0

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
