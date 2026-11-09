#!/usr/bin/env python
"""A page may say "shipped" only when a named test proves it.

The rule comes from the half-finished-features audit (t-1350): the ignore list
was documented as shipped, the code existed, and nothing ever exercised the
promise. A named test is the difference between "the code is there" and "this
works".

How a section earns the word:

    > **Status:** shipped — Phase 7 (...)

    <!-- shipped-check: tests/test_ci_report.py::test_report_main_writes_comment_payload -->

A status banner claiming **shipped** or **available** must carry one or more
markers in its section (a negation - "NOT SHIPPED" - claims nothing). Every
marker in the section is run; a broad claim with three proofs must be proved
three times. Five outcomes count as proof, and only the first is proof at all:

* **passed with an assertion** - the test exists, it is not skipped or xfailed,
  and its own source contains an assertion (a test that runs and asserts nothing
  proves nothing, however green it is);
* **skipped / xfail** - refused: a skip is the absence of proof, not a pass;
* **failed** - refused;
* **missing** - refused: a marker naming no test proves nothing;
* **collection error** - refused and attributed to the marker that broke the
  collection, so one bad id cannot blame every other page (the checker falls back
  to running markers one at a time when the batch leaves no junit).

Section boundary: a banner's section runs to the next `## ` (or `#`) heading, so
a marker inside a `###` subsection counts for the `##` claim - and the report
names the subsection that proved it.

Scope, stated exactly: the checker scans `docs/*.md` - the feature pages whose
banner states the product's own shipping state. The other directories are
records, not claims: a plan's status describes the session that wrote it ("Complete"
there means the plan was executed, not that the product works today); a spec's
status is intent; a session log records what a session did; `docs/archived/` keeps
superseded pages; `docs/private/` is gitignored local notes. **The counts are not
written here** - the checker measures them every run and prints them
(``--root`` aware), because a hardcoded count goes stale the day a page is added.
A new directory under `docs/` that starts carrying status banners is not silently
out of scope: `tests/test_shipped_claims.py` requires every such directory to be
scanned or listed in `OUT_OF_SCOPE`, so the limit cannot drift.

What this fence proves, and what it does not - it is a heuristic, and these are
its known ways to be dodged (written down rather than papered over with more AST
rules):

* it proves a **named test exists, is not skipped or xfail, runs green, and the
  function's body contains something assertion-shaped**. It does not prove the
  assertion is meaningful;
* `assert True`, or an `assert` inside a nested helper of the test, counts - a
  tautology and a delegated proof both pass;
* a call whose name merely *contains* `fail`, `raises`, `to_be_`, `to_have_` or
  `to_contain` counts, even if it asserts nothing;
* when a node id names a class (``file.py::Class::test``), the class part is not
  matched: the first function with that name in the file is read, so one class's
  assertion can vouch for another's test;
* a green test can still pass for the wrong reason (a mock, a fixture, a scenario
  it never reaches). The proof is "someone wrote an assertion and it ran", not
  "the assertion would catch the regression".

Usage::

    python scripts/check_shipped_claims.py            # the repository
    python scripts/check_shipped_claims.py --root DIR  # a checkout/copy
"""

from __future__ import annotations

import argparse
import ast
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
H2_RE = re.compile(r"^#{1,2}\s")
H3_RE = re.compile(r"^###\s")
CLAIM_WORDS = ("shipped", "available")
NEGATED_RE = re.compile(r"\b(?:not|never|un)\s*-?\s*(?:shipped|available)", re.IGNORECASE)

#: Directories under docs/ that are records, not claims. Kept honest by the suite.
OUT_OF_SCOPE: dict[str, str] = {
    "plans": "design records: a plan's status describes the session that wrote it",
    "specs": "design records: intent, not state",
    "sessions": "session logs: what a session did, not what the product does",
    "archived": "superseded pages kept for history",
    "private": "untracked private notes",
}

#: Calls that assert, for a test that proves its claim through a framework call.
_ASSERT_CALL_HINTS = ("raises", "fail", "warns", "to_have_", "to_be_", "to_contain", "to_equal")


@dataclass(frozen=True)
class Marker:
    """One ``shipped-check`` comment: the test that must prove the claim."""

    test: str
    line: int
    subsection: str


@dataclass(frozen=True)
class Claim:
    """One status line that claims the feature works."""

    doc: Path
    line: int
    section: str
    status: str
    markers: tuple[Marker, ...]


def _claims_shipping(status: str) -> bool:
    """Whether a status line asserts the thing works (negations do not count)."""
    return any(word in NEGATED_RE.sub("", status).lower() for word in CLAIM_WORDS)


def _section_name(lines: list[str], index: int) -> str:
    """The nearest heading above *index*, for a message a reader can act on."""
    for back in range(index, -1, -1):
        if lines[back].startswith("#"):
            return lines[back].lstrip("#").strip()
    return "(top of file)"


def _subsection_at(lines: list[str], start: int, index: int) -> str:
    """The `###` heading covering *index* inside the section starting at *start*."""
    for back in range(index, start - 1, -1):
        if H3_RE.match(lines[back]):
            return lines[back].lstrip("#").strip()
    return ""


def find_claims(root: Path, docs_dir: str = "docs") -> list[Claim]:
    """Every feature page's status line that claims shipped/available.

    Feature pages are ``<docs_dir>/*.md``; see the module docstring for what is
    out of scope and why. Every marker in the section is collected, not just the
    first: a broad claim may need several proofs.
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
                (later for later in range(index + 1, len(lines)) if H2_RE.match(lines[later])),
                len(lines),
            )
            markers: list[Marker] = []
            for later in range(index, end):
                marker = MARKER_RE.search(lines[later])
                if marker is not None:
                    markers.append(
                        Marker(
                            test=marker.group("test"),
                            line=later + 1,
                            subsection=_subsection_at(lines, index, later),
                        )
                    )
            claims.append(
                Claim(
                    doc=doc.relative_to(root),
                    line=index + 1,
                    section=_section_name(lines, index),
                    status=status,
                    markers=tuple(markers),
                )
            )
    return claims


def _has_assertion(root: Path, node_id: str) -> bool | None:
    """Whether the named test's own body asserts something.

    True = an ``assert``, a ``pytest.raises``/``fail``/``warns`` call, or a
    Playwright ``expect(...).to_have_*`` style call. False = the body runs and
    asserts nothing, so its green means nothing. None = the source cannot be read
    (reported as a problem, never as a pass).

    A test that delegates its proof entirely to an opaque helper is refused: the
    rule is that the proof is visible where the claim is made.
    """
    path_part, _, rest = node_id.partition("::")
    parts = [part for part in rest.split("::") if part]
    if not parts:
        return None
    # A parametrized id is ``test_name[case]``: the function is ``test_name``.
    name = parts[-1].split("[", 1)[0]
    source = root / path_part
    if not source.is_file():
        return None
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"))
    except OSError, SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            for inner in ast.walk(node):
                if isinstance(inner, ast.Assert):
                    return True
                if isinstance(inner, ast.Call):
                    target = inner.func
                    attr = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
                    if any(hint in str(attr) for hint in _ASSERT_CALL_HINTS):
                        return True
            return False
    return None


def _node_key(node_id: str) -> str:
    """``tests/x.py::C::t`` -> ``tests.x.C.t`` (the junit classname/name form)."""
    return node_id.replace(".py::", ".").replace("/", ".").replace("::", ".").replace(".py", "")


def _parse_junit(xml_path: Path) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    if not xml_path.is_file():
        return outcomes
    for case in ET.parse(xml_path).iter("testcase"):
        classname = case.get("classname", "") or ""
        name = case.get("name", "") or ""
        key = f"{classname}.{name}" if classname else name
        kinds = {child.tag: child for child in case}
        if not classname:
            # A collection failure is reported as an error case named after the
            # MODULE (no classname): a file that failed to import, not a test id.
            outcomes[f"file:{name}"] = "collect_error"
            continue
        if "failure" in kinds or "error" in kinds:
            outcomes[key] = "failed"
        elif "skipped" in kinds:
            skipped = kinds["skipped"]
            kind = str(skipped.get("type") or "")
            outcomes[key] = "xfail" if "xfail" in kind.lower() else "skipped"
        else:
            outcomes[key] = "passed"
    return outcomes


def _pytest_once(root: Path, node_ids: list[str]) -> dict[str, str] | None:
    """Run *node_ids* together; ``None`` when pytest wrote no junit (collection died)."""
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
        parsed = _parse_junit(xml_path)
    if not parsed:
        return None
    return parsed


def run_tests(root: Path, node_ids: list[str]) -> dict[str, str]:
    """Run *node_ids*; map each to passed|failed|skipped|xfail|missing|collect_error.

    The batch run is one process. When it leaves no junit - pytest exits 4 on a
    bad id - the markers are re-run one at a time so the failure is attributed to
    the marker that broke it instead of being reported against every page.
    """
    if not node_ids:
        return {}
    batched = _pytest_once(root, node_ids)
    results: dict[str, str] = {}
    missing: list[str] = []
    if batched is not None:
        for node in node_ids:
            outcome = batched.get(_node_key(node))
            if outcome is None:
                # A file that fails to IMPORT still writes a junit - holding only
                # the error case - so "no junit" is not the only way a marker goes
                # missing. Any id the batch did not answer is re-run on its own.
                missing.append(node)
            else:
                results[node] = outcome
    else:
        missing = list(node_ids)

    for node in missing:
        single = _pytest_once(root, [node])
        if single is None:
            results[node] = "collect_error"
            continue
        outcome = single.get(_node_key(node))
        if outcome is not None:
            results[node] = outcome
            continue
        # The id itself is absent. If junit carries a module-level error instead,
        # the FILE is what broke (an import error), and that is a collection
        # failure to name - not "this marker does not exist".
        module = node.split("::", 1)[0].removesuffix(".py").replace("/", ".")
        results[node] = "collect_error" if f"file:{module}" in single else "missing"
    return results


#: ``runner(root, node_ids) -> {node_id: outcome}``.
Runner = Callable[[Path, list[str]], dict[str, str]]

_OUTCOME_PROBLEMS = {
    "skipped": "is SKIPPED - a skip is the absence of proof, not a pass",
    "xfail": "is XFAIL (expected to fail) - an expected failure proves nothing",
    "failed": "FAILS - the page may not say shipped while its own proof is red",
    "missing": "does not exist - a marker naming no test proves nothing",
    "collect_error": "broke pytest's collection (exit 4) - the marker itself is wrong",
}


def verify(
    root: Path,
    docs_dir: str = "docs",
    *,
    runner: Runner | None = None,
) -> list[str]:
    """Every claim this repository cannot verify, as sentences naming the place.

    Exercises every marker in every claiming section, and refuses a test that
    passes without asserting anything. ``runner`` lets a caller inject outcomes
    (the suite uses it so the failure paths do not nest pytest in pytest).
    """
    claims = find_claims(root, docs_dir)
    if not claims:
        return []
    to_run = sorted({marker.test for claim in claims for marker in claim.markers})
    outcomes: dict[str, str] = {}
    if to_run:
        outcomes = dict(runner(root, to_run) if runner is not None else run_tests(root, to_run))

    problems: list[str] = []
    for claim in claims:
        where = f"{claim.doc}:{claim.line} ('{claim.section}')"
        if not claim.markers:
            problems.append(
                f"{where} says '{claim.status}' but carries no shipped-check marker - "
                "a section may claim shipped only when a named test proves it"
            )
            continue
        for marker in claim.markers:
            outcome = outcomes.get(marker.test, "missing")
            if outcome == "passed":
                asserted = _has_assertion(root, marker.test)
                if asserted is not True:
                    problems.append(
                        f"{where} points at {marker.test} (line {marker.line}), which passes but "
                        + (
                            "asserts nothing - a green test that asserts nothing proves nothing"
                            if asserted is False
                            else "could not be read, so it is not proof"
                        )
                    )
                continue
            problem = _OUTCOME_PROBLEMS.get(outcome, "could not be verified")
            problems.append(f"{where} points at {marker.test} (line {marker.line}), which {problem}")
    return problems


def describe(root: Path, docs_dir: str = "docs") -> list[str]:
    """One line per claim: where it is, and which test (and subsection) proves it."""
    lines: list[str] = []
    for claim in find_claims(root, docs_dir):
        for marker in claim.markers:
            where = f" under '{marker.subsection}'" if marker.subsection else ""
            lines.append(f"  {claim.doc}:{claim.line}{where} -> {marker.test}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A page may say shipped only when a named test proves it.")
    parser.add_argument("--root", default=".", help="checkout to check")
    parser.add_argument("--docs", default="docs", help="directory to scan, relative to --root")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    problems = verify(root, args.docs)
    if problems:
        print("SHIPPED CLAIMS THAT CANNOT BE VERIFIED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    claims = find_claims(root, args.docs)
    marker_count = sum(len(claim.markers) for claim in claims)
    print(f"shipped claims: {len(claims)} section(s), {marker_count} marker(s), every one proved by a passing test")
    for line in describe(root, args.docs):
        print(line)
    for line in scope_report(root, args.docs):
        print(line)
    print("  what this does NOT prove (a heuristic - see the module docstring for the full list):")
    print("    - `assert True` counts; an assert inside a nested helper counts;")
    print("    - a call whose name merely contains fail/raises/to_have_ counts;")
    print("    - the class part of a node id is not matched; a green test can pass for the wrong reason.")
    return 0


def scope_report(root: Path, docs_dir: str = "docs") -> list[str]:
    """Live counts for what is out of scope - measured, never hardcoded."""
    lines = ["  out of scope (records, not claims), as found in this checkout:"]
    found = False
    for name, reason in sorted(OUT_OF_SCOPE.items()):
        directory = root / docs_dir / name
        if not directory.is_dir():
            continue
        found = True
        files = sorted(directory.rglob("*.md"))
        banners = 0
        for doc in files:
            banners += sum(
                1 for line in doc.read_text(encoding="utf-8", errors="replace").splitlines() if "**Status:**" in line
            )
        lines.append(f"    {name + '/':<14} {len(files):>3} page(s), {banners:>3} status line(s) - {reason}")
    if not found:
        lines.append("    (none of the known record directories is present in this checkout)")
    return lines


if __name__ == "__main__":
    sys.exit(main())
