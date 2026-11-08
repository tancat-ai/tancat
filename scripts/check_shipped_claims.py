#!/usr/bin/env python
"""A page may say "shipped" only when a named test proves it.

The rule comes from the half-finished-features audit (t-1350) and is the one
check that would have caught the ignore list the day the lie was written: the
code existed, the docs said shipped, and nothing ever exercised the promise.

How a section earns the word:

    > **Status:** shipped — Phase 7 (...)

    <!-- shipped-check: tests/test_ci_report.py::test_report_main_writes_comment_payload -->

A section whose status line claims **shipped** or **available** must carry one
marker naming a test id (``file::function``, optionally ``file::Class::method``).
The checker collects that id and runs it. Anything it cannot verify is reported
- no marker, a marker pointing at a test that does not exist, a marker whose
test fails - and the exit code is 1. It never passes quietly.

Scope, stated so nobody over-reads it: this checks the **status banner** of a
feature page (``docs/*.md``, the ``> **Status:** ...`` line), which is the one
place a page states its own shipping state. It deliberately does not scan
``docs/sessions/`` or ``docs/specs/`` - those are records of what a session did
and what a feature was meant to do, not a page asserting the product works. A
prose sentence elsewhere can still be wrong; the audit's other findings are
handled by their own items.

Usage::

    python scripts/check_shipped_claims.py            # the repository
    python scripts/check_shipped_claims.py --root DIR  # a checkout/copy
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

STATUS_RE = re.compile(r"^\s*>?\s*\*\*Status:\*\*\s*(?P<status>.+?)\s*$")
MARKER_RE = re.compile(r"<!--\s*shipped-check:\s*(?P<test>[^\s>]+\.py::[^\s>]+)\s*-->")
HEADING_RE = re.compile(r"^#{1,2}\s")
CLAIM_WORDS = ("shipped", "available")
#: A status line that says "not shipped" / "not available" claims nothing.
NEGATED_RE = re.compile(r"\b(?:not|never|un)\s*-?\s*(?:shipped|available)", re.IGNORECASE)


@dataclass(frozen=True)
class Claim:
    """One status line that claims the feature works."""

    doc: Path
    line: int
    section: str
    status: str
    marker_test: str | None
    marker_line: int | None


def _section_name(lines: list[str], index: int) -> str:
    """The nearest heading above *index*, for a message a reader can act on."""
    for back in range(index, -1, -1):
        if lines[back].startswith("#"):
            return lines[back].lstrip("#").strip()
    return "(top of file)"


def _claims_shipping(status: str) -> bool:
    """Whether a status line asserts the thing works (negations do not count)."""
    unnegated = NEGATED_RE.sub("", status).lower()
    return any(word in unnegated for word in CLAIM_WORDS)


def find_claims(root: Path, docs_dir: str = "docs") -> list[Claim]:
    """Every feature page's status line whose text claims shipped/available.

    Feature pages are ``<docs_dir>/*.md`` - the banners a reader consults. The
    session and spec directories are records, not claims, and are not scanned.
    """
    claims: list[Claim] = []
    for doc in sorted((root / docs_dir).glob("*.md")):
        lines = doc.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            match = STATUS_RE.match(line)
            if match is None:
                continue
            status = match.group("status")
            if not _claims_shipping(status):
                continue
            end = next(
                (later for later in range(index + 1, len(lines)) if HEADING_RE.match(lines[later])),
                len(lines),
            )
            marker_test, marker_line = None, None
            for later in range(index, end):
                marker = MARKER_RE.search(lines[later])
                if marker is not None:
                    marker_test, marker_line = marker.group("test"), later + 1
                    break
            claims.append(
                Claim(
                    doc=doc.relative_to(root),
                    line=index + 1,
                    section=_section_name(lines, index),
                    status=status,
                    marker_test=marker_test,
                    marker_line=marker_line,
                )
            )
    return claims


def _node_key(node_id: str) -> str:
    """``tests/x.py::C::t`` -> ``tests.x.C.t`` (the junit classname/name form)."""
    return node_id.replace(".py::", ".").replace("/", ".").replace("::", ".").replace(".py", "")


def run_tests(root: Path, node_ids: list[str]) -> dict[str, str]:
    """Run *node_ids* together; map each id to 'passed' | 'failed' | 'missing'."""
    if not node_ids:
        return {}
    with tempfile.TemporaryDirectory() as tmp:
        xml_path = Path(tmp) / "shipped.xml"
        command = [
            sys.executable,
            "-m",
            "pytest",
            *node_ids,
            "-q",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",  # no xdist, no repo-wide options: this is a probe
            f"--junitxml={xml_path}",
        ]
        subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=300)
        if not xml_path.is_file():
            return dict.fromkeys(node_ids, "missing")
        cases: dict[str, str] = {}
        for case in ET.parse(xml_path).iter("testcase"):
            key = f"{case.get('classname', '')}.{case.get('name', '')}"
            bad = any(child.tag in ("failure", "error") for child in case)
            cases[key] = "failed" if bad else "passed"
    results: dict[str, str] = {}
    for node in node_ids:
        key = _node_key(node)
        results[node] = cases.get(key, "missing")
    return results


#: ``runner(root, node_ids) -> {node_id: "passed" | "failed" | "missing"}``.
Runner = Callable[[Path, list[str]], dict[str, str]]


def verify(
    root: Path,
    docs_dir: str = "docs",
    *,
    runner: Runner | None = None,
) -> list[str]:
    """Every claim this repository cannot verify, as sentences naming the place.

    ``runner`` lets a caller inject a fake outcome map (the suite uses one so the
    failure paths are tested without nesting pytest inside pytest).
    """
    claims = find_claims(root, docs_dir)
    if not claims:
        return []
    to_run = sorted({claim.marker_test for claim in claims if claim.marker_test})
    outcomes: dict[str, str] = {}
    if to_run:
        outcomes = dict(runner(root, to_run) if runner is not None else run_tests(root, to_run))

    problems: list[str] = []
    for claim in claims:
        where = f"{claim.doc}:{claim.line} ('{claim.section}')"
        if claim.marker_test is None:
            problems.append(
                f"{where} says '{claim.status}' but carries no shipped-check marker - "
                "a section may claim shipped only when a named test proves it"
            )
            continue
        outcome = outcomes.get(claim.marker_test, "missing")
        if outcome == "missing":
            problems.append(
                f"{where} points at {claim.marker_test} (line {claim.marker_line}), which does not exist - "
                "a marker naming no test proves nothing"
            )
        elif outcome != "passed":
            problems.append(
                f"{where} points at {claim.marker_test} (line {claim.marker_line}), which FAILS - "
                "the page may not say shipped while its own proof is red"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A page may say shipped only when a named test proves it.")
    parser.add_argument("--root", default=".", help="checkout to check")
    parser.add_argument("--docs", default="docs", help="directory to scan, relative to --root")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    problems = verify(root, args.docs, runner=run_tests)
    if problems:
        print("SHIPPED CLAIMS THAT CANNOT BE VERIFIED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    claims = find_claims(root, args.docs)
    print(f"shipped claims: {len(claims)} checked, every one proved by a passing test")
    for claim in claims:
        print(f"  {claim.doc}:{claim.line} -> {claim.marker_test}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
