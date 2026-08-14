#!/usr/bin/env python3
"""AI-028 evidence -> JUnit XML exporter for the CI action (Phase 7a).

Runs after pytest in run-existing mode: indexes the package's evidence
sidecars (``<package>/evidence/*.evidence.json``) with :class:`EvidenceIndex`
and emits the enriched JUnit report via :func:`export_junit_xml` — the
condition/story refs and per-step failure messages the raw ``pytest
--junitxml`` cannot carry (spec §5.4: sidecars > pytest raw).

The index DB is a scratch file next to the output (``<output>.index.sqlite``)
so nothing outside the caller's workspace is touched. The DB is only an
index — sidecar contents are resolved package-relative.

Platform seam (spec §5.5): reads argv + env, writes a file. Zero GitHub
imports — reusable by the GitLab adapter in 7c.

Usage::

    python action/export_evidence_junit.py \\
        --evidence-dir <pkg>/evidence --output junit-evidence.xml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="export_evidence_junit",
        description="Index evidence sidecars and emit an enriched JUnit XML report (AI-028).",
    )
    parser.add_argument("--evidence-dir", required=True, help="Directory containing *.evidence.json sidecars")
    parser.add_argument("--output", required=True, help="Output JUnit XML path")
    parser.add_argument("--suite-name", default="evidence_export", help="JUnit testsuite name")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    from src.evidence_export import export_junit_xml
    from src.evidence_index import EvidenceIndex
    from src.sqlite_persistence import SQLitePersistence

    evidence_dir = Path(args.evidence_dir).resolve()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    sidecars = list(evidence_dir.glob("*.evidence.json")) if evidence_dir.exists() else []
    if not sidecars:
        # Valid empty report — keeps every downstream consumer (dorny/test-
        # reporter, GitLab) happy even when the package wrote no sidecars.
        print(f"export_evidence_junit: no sidecars under {evidence_dir} — writing empty JUnit")

    index_db = Path(str(output) + ".index.sqlite")
    index = EvidenceIndex(db=SQLitePersistence(db_path=index_db))
    indexed = index.build_or_refresh(base_dir=evidence_dir, force=True)
    export_junit_xml(index, output=str(output), suite_name=args.suite_name)
    print(f"export_evidence_junit: indexed {indexed} sidecar(s) -> {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
