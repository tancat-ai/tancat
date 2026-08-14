#!/usr/bin/env python3
"""Verified adaptation engine core (Phase 7b, spec §8/7b + §9.6).

Locator-only, assertion-gated, transparent:

1. Parse junit.xml failure messages; keep ONLY LocatorNotFound-class failures
   (the same classification the report's repair-candidate marking uses —
   assertion failures always surface, never auto-adapted).
2. For each candidate, find the source step(s) in the package that use the
   failing locator (``tracker.click/fill/assert_visible('…', label=…)`` in
   POM pages, or ``page.locator('…')`` in flat tests).
3. Scrape the target page and re-resolve the step's semantic label to a NEW
   locator using the product's own resolution machinery (PageScraper +
   PlaceholderResolver — the same core the debug CLI's ``resolve`` command
   uses, minus the LLM).
4. Patch the locator, re-run ONLY that test, and keep the patch only if the
   test's own assertions still pass. Revert otherwise.
5. Emit ``adaptation.json`` with every patch attempt kept/reverted + reasons
   — transparent reporting; CI never mutates tests silently (spec §9.7).

Platform seam (spec §5.5): zero GitHub imports. The entrypoint / slash-command
workflow posts the results. The GitLab adapter (7c) reuses this unchanged.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from action.report import is_repair_candidate

# Locators inside failure messages come in two shapes:
#   - Playwright native: ``waiting for locator('a[href=…]')``
#   - evidence_tracker's own fast-fail: ``Locator 'a[href=…]' not found on
#     current page (…)`` (src/evidence_tracker._LocatorNotFoundError)
# Both may contain quotes of the other kind (``a[href="/x"]``) — backreference
# to the OPENING quote so nested quotes are allowed.
_PLAYWRIGHT_LOCATOR_RE = re.compile(r"locator\(\s*(['\"])(.*?)\1\s*\)")
_TRACKER_LOCATOR_RE = re.compile(r"\bLocator\s+(['\"])(.*?)\1\s+not found", re.IGNORECASE)


def _extract_locator(message: str) -> str | None:
    """Return the failing locator from a Playwright or tracker failure message."""
    for pattern in (_PLAYWRIGHT_LOCATOR_RE, _TRACKER_LOCATOR_RE):
        match = pattern.search(message or "")
        if match:
            return match.group(2)
    return None


# Action hint from the failing call site in the failure message.
_ACTION_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\.fill\b|fill\(", re.IGNORECASE), "FILL"),
    (re.compile(r"to_be_visible|to_have_text|expect\(", re.IGNORECASE), "ASSERT"),
    (re.compile(r"\.click\b|press\b", re.IGNORECASE), "CLICK"),
)

# Source-step classifiers: which tracker/page method the line uses.
_TRACKER_CLICK = re.compile(r"\.click\s*\(")
_TRACKER_FILL = re.compile(r"\.fill\s*\(")
_TRACKER_ASSERT = re.compile(r"assert_visible\s*\(|assert_text\s*\(")
_LABEL_RE = re.compile(r"label\s*=\s*['\"]([^'\"]*)['\"]")


@dataclass
class SourceStep:
    """One source line that uses a failing locator."""

    path: str
    lineno: int
    line: str
    action: str  # CLICK | FILL | ASSERT
    label: str
    old_locator: str


@dataclass
class AdaptationRecord:
    """Result of one attempted patch."""

    test: str
    source: str
    old_locator: str
    new_locator: str
    status: str  # adapted | reverted | no-candidate | not-repair
    message: str = ""


@dataclass
class AdaptationReport:
    """Full run result — mirrors the report cores' JSON-file style."""

    generated_at: str = ""
    package: str = ""
    url: str = ""
    candidates: list[dict[str, Any]] = field(default_factory=list)
    kept: list[dict[str, Any]] = field(default_factory=list)
    reverted: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "package": self.package,
            "url": self.url,
            "candidates": self.candidates,
            "kept": self.kept,
            "reverted": self.reverted,
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_failure(message: str) -> dict[str, str] | None:
    """Extract ``{"locator", "action"}`` from a failure message, or None."""
    locator = _extract_locator(message)
    if locator is None:
        return None
    action = "CLICK"
    for pattern, name in _ACTION_HINTS:
        if pattern.search(message or ""):
            action = name
            break
    return {"locator": locator, "action": action}


def _classify_line(line: str, locator: str) -> SourceStep | None:
    if locator not in line:
        return None
    label_match = _LABEL_RE.search(line)
    label = label_match.group(1) if label_match else ""
    if _TRACKER_CLICK.search(line):
        action = "CLICK"
    elif _TRACKER_FILL.search(line):
        action = "FILL"
    elif _TRACKER_ASSERT.search(line):
        action = "ASSERT"
    elif "expect(" in line or "to_be_visible" in line:
        action = "ASSERT"
    elif ".locator(" in line:
        action = "CLICK"
    else:
        return None
    return SourceStep(path="", lineno=0, line=line.strip(), action=action, label=label, old_locator=locator)


def find_source_steps(package: Path, locator: str) -> list[SourceStep]:
    """Locate every source line in *package* that uses *locator*."""
    steps: list[SourceStep] = []
    for path in sorted(package.rglob("*.py")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for idx, line in enumerate(lines, start=1):
            step = _classify_line(line, locator)
            if step is not None:
                step.path = str(path)
                step.lineno = idx
                steps.append(step)
    return steps


# ---------------------------------------------------------------------------
# Replacement resolution (product machinery, no LLM)
# ---------------------------------------------------------------------------


def scrape_elements(url: str) -> list[dict[str, Any]]:
    """Scrape *url* and return elements (sync wrapper over the async scraper)."""
    from src.scraper import PageScraper

    scraper = PageScraper()
    elements, error, _final = asyncio.run(scraper.scrape_url(url))
    if error:
        raise RuntimeError(f"scrape failed for {url}: {error}")
    return elements


def find_replacement_locator(
    url: str,
    action: str,
    description: str,
    old_locator: str,
) -> str | None:
    """Re-resolve *description* to a locator; None when nothing better exists.

    Uses the product's own scorer, so the replacement is as good as a
    fresh resolution — and the assertion gate decides whether it survives.
    """
    if not description.strip():
        return None
    from src.placeholder_resolver import PlaceholderResolver

    elements = scrape_elements(url)
    resolver = PlaceholderResolver()
    ranked = resolver.rank_candidates(action, description, elements)
    for score, element in ranked:
        selector = str(element.get("selector", "")).strip()
        if not selector:
            continue
        if selector == old_locator:
            continue  # same locator — not an adaptation
        if score < 1:
            continue
        return selector
    return None


# ---------------------------------------------------------------------------
# Patching + verification
# ---------------------------------------------------------------------------


def patch_locator(path: str, old_locator: str, new_locator: str) -> int:
    """Replace *old_locator* with *new_locator* in a source file.

    Returns the number of lines changed. Replacing the quoted-string form is
    inherently idempotent: once replaced, *old_locator* is gone and the next
    call returns 0. The *new_locator* may legitimately already exist elsewhere
    in the file (other steps can already use it) — that must not abort.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old_locator not in text:
        return 0
    # Replace only the quoted-string occurrences of the old locator.
    new_text = text.replace(f"'{old_locator}'", f"'{new_locator}'")
    new_text = new_text.replace(f'"{old_locator}"', f'"{new_locator}"')
    if new_text == text:
        return 0
    p.write_text(new_text, encoding="utf-8")
    return 1


def run_single_test(package: Path, test_name: str, repo_root: Path) -> tuple[int, str]:
    """Run one test via pytest; returns (exit_code, tail_of_output)."""
    base_name = test_name.split("[", 1)[0]
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(package),
        "-o",
        "addopts=",
        "-o",
        f"pythonpath={repo_root}",
        "--browser=chromium",
        "-q",
        "--tb=short",
        "--no-header",
        "-p",
        "no:cacheprovider",
        "-k",
        base_name,
        "-m",
        "not slow",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    tail = (proc.stdout or "").strip().splitlines()
    tail = tail[-8:] + ((proc.stderr or "").strip().splitlines()[-4:] if proc.stderr else [])
    return proc.returncode, "\n".join(tail)


def _package_url(package: Path, url: str) -> str:
    """URL from the explicit input, else the package manifest's starting_url.

    The package may be nested (cache restore lays out ``<key>/<pkg>/`` or the
    slash-command flow points at the whole cache dir) — search recursively for
    the first manifest with a starting_url.
    """
    if url:
        return url
    for manifest in package.rglob("package_manifest.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError, OSError:
            continue
        if data.get("starting_url"):
            return str(data["starting_url"])
    return ""


def _junit_repair_candidates(junit: Path) -> list[dict[str, str]]:
    """(test, message) pairs for LocatorNotFound-class failures in junit.xml."""
    root = ET.parse(junit).getroot()
    suites: list[ET.Element] = list(root) if root.tag == "testsuites" else [root]
    records: list[dict[str, str]] = []
    for suite in suites:
        for case in suite.iter("testcase"):
            failure = case.find("failure")
            if failure is None:
                continue
            message = failure.get("message", "") or (failure.text or "").strip()
            if is_repair_candidate(message):
                records.append({"test": case.get("name", "unknown"), "message": message})
    return records


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def adapt_package(
    package: Path,
    junit: Path,
    url: str = "",
    only_test: str = "",
    repo_root: Path | None = None,
) -> AdaptationReport:
    """Run verified adaptation over a package's repair candidates.

    Returns a full report; the *only_test* filter lets a slash-command
    adapt a single named test.
    """
    repo_root = repo_root or Path(__file__).resolve().parent.parent
    report = AdaptationReport(
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        package=str(package),
        url=_package_url(package, url),
    )
    candidates = _junit_repair_candidates(junit)
    if only_test:
        base = only_test.split("[", 1)[0]
        candidates = [c for c in candidates if c["test"].split("[", 1)[0] == base]

    for cand in candidates:
        test = cand["test"]
        parsed = parse_failure(cand["message"])
        if parsed is None:
            report.candidates.append({"test": test, "status": "not-repair", "message": cand["message"][:300]})
            continue
        old_locator = parsed["locator"]
        steps = find_source_steps(package, old_locator)
        if not steps:
            report.candidates.append(
                {"test": test, "status": "no-source", "message": f"no source step uses locator {old_locator!r}"}
            )
            continue
        step = steps[0]
        action = parsed["action"] or step.action
        description = step.label or old_locator

        entry: dict[str, Any] = {
            "test": test,
            "source": f"{step.path}:{step.lineno}",
            "old_locator": old_locator,
            "label": description,
            "action": action,
        }

        if not report.url:
            entry["status"] = "no-url"
            entry["message"] = "no target URL (input or package manifest)"
            report.candidates.append(entry)
            continue

        try:
            new_locator = find_replacement_locator(report.url, action, description, old_locator)
        except Exception as exc:  # scrape/resolve failure — never crash the run
            entry["status"] = "resolve-error"
            entry["message"] = str(exc)[:300]
            report.candidates.append(entry)
            continue

        if new_locator is None:
            entry["status"] = "no-candidate"
            entry["message"] = f"no better locator found for {description!r} on {report.url}"
            report.candidates.append(entry)
            continue

        entry["new_locator"] = new_locator
        changed = patch_locator(step.path, old_locator, new_locator)
        if changed == 0:
            entry["status"] = "patch-failed"
            entry["message"] = "locator present but patch did not apply (quote mismatch?)"
            report.candidates.append(entry)
            continue

        rc, tail = run_single_test(package, test, repo_root)
        if rc == 0:
            entry["status"] = "adapted"
            entry["message"] = "re-run passed — patch kept (assertion gate green)"
            report.kept.append(entry)
        else:
            # Revert — the patch did not satisfy the test's own assertions.
            patch_locator(step.path, new_locator, old_locator)
            entry["status"] = "reverted"
            entry["message"] = f"re-run failed after patch — reverted (assertion gate). tail: {tail[-300:]}"
            report.reverted.append(entry)
        report.candidates.append(entry)

    report.summary = {
        "candidates": len(report.candidates),
        "adapted": len(report.kept),
        "reverted": len(report.reverted),
        "not_repair_or_no_source": sum(
            1 for c in report.candidates if c.get("status") in {"not-repair", "no-source", "no-url"}
        ),
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ci_adapt",
        description="Verified adaptation: locator-only patch -> re-run -> assertion gate -> keep-or-revert.",
    )
    parser.add_argument("--package", required=True, help="Generated test package directory")
    parser.add_argument("--junit", required=True, help="Raw pytest junit.xml (failures source)")
    parser.add_argument("--url", default="", help="Target URL (default: package manifest starting_url)")
    parser.add_argument("--test", default="", help="Adapt only this test name (slash-command /adapt)")
    parser.add_argument("--output", default="", help="Output dir for adaptation.json (default: package dir)")
    parser.add_argument("--repo-root", default="", help="Repo root for pythonpath (default: this repo)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    package = Path(args.package)
    junit = Path(args.junit)
    if not package.exists() or not package.is_dir():
        print(f"ERROR: package dir not found: {package}", file=sys.stderr)
        return 2
    if not junit.exists():
        print(f"ERROR: junit not found: {junit}", file=sys.stderr)
        return 2

    report = adapt_package(
        package,
        junit,
        url=args.url,
        only_test=args.test,
        repo_root=Path(args.repo_root) if args.repo_root else None,
    )
    out_dir = Path(args.output) if args.output else package
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "adaptation.json").write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    print(
        f"adaptation: {report.summary['candidates']} candidate(s), "
        f"{report.summary['adapted']} kept, {report.summary['reverted']} reverted"
    )
    if report.summary["adapted"]:
        print(f"  kept: {[c['test'] for c in report.kept]}")
    if report.summary["reverted"]:
        print(f"  reverted: {[c['test'] for c in report.reverted]}")
    return 0 if report.summary["reverted"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
