#!/usr/bin/env python3
"""Verified adaptation engine core (Phase 7b, spec §8/7b + §9.6).

Locator-only, assertion-gated, transparent:

1. Find LocatorNotFound-class failures — the same classification the report's
   repair-candidate marking uses (assertion failures always surface, never
   auto-adapted). Two sources, because one is no longer enough:
   - the test-level ``junit.xml`` failure message, and
   - the evidence sidecar (``*.evidence.json``): since t-1057 a failed step no
     longer ends its test, so the sidecar records the dead locator and the test
     carries on until a later assertion fails. A junit-only read sees that
     assertion and reports "no candidates" for a locator that is right there
     (the nightly self-test was red for fifteen nights on exactly this, t-1426).
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


_HREF_LOCATOR_RE = re.compile(r"""href\s*=\s*(['"])(.*?)\1""", re.IGNORECASE)


def _identity_path(value: str) -> str:
    """A comparable path for a link: scheme, host, query and .html ignored.

    ``/cart``, ``/cart.html`` and ``https://site/cart.html`` all describe the
    cart page. The comparison is about WHICH page a link goes to, not its text.
    """
    from urllib.parse import urlsplit

    text = str(value or "").strip()
    if not text:
        return ""
    try:
        path = (
            urlsplit(text).path
            if "://" in text or text.startswith("//")
            else urlsplit("//x" + (text if text.startswith("/") else "/" + text)).path
        )
    except ValueError:
        return ""
    path = path.strip("/").lower()
    if path.endswith("/index.html"):
        path = path[: -len("/index.html")]
    if path.endswith(".html") or path.endswith(".htm"):
        path = path.rsplit(".", 1)[0]
    return path.strip("/")


def _target_href(old_locator: str) -> str:
    match = _HREF_LOCATOR_RE.search(old_locator or "")
    return _identity_path(match.group(2)) if match else ""


#: The fields an accessible name can come from, strongest first.
_NAME_FIELDS = ("accessible_name", "aria_label", "text", "title", "name")


def _accessible_text(element: dict[str, Any]) -> str:
    """The words a person hears for an element, normalised for comparison."""
    parts = [element.get(field) for field in _NAME_FIELDS]
    return " ".join(str(part).strip() for part in parts if part and str(part).strip()).lower()


#: Generic UI nouns an author puts in a step label but a screen reader never
#: announces. "Cart link" names the element "Cart"; "Add to cart link" names the
#: button "Add to cart". The words are removed from BOTH sides so the comparison
#: is about what identifies the element, not how the sentence describes it.
_GENERIC_LABEL_WORDS = {
    "a",
    "an",
    "the",
    "link",
    "button",
    "anchor",
    "element",
    "control",
    "nav",
    "navigation",
    "clickable",
    "select",
    "text",
    "field",
    "input",
}


def _label_matches(description: str, element: dict[str, Any]) -> bool:
    """Identity match on ONE name field, not on the union of them all.

    ``cart`` and ``Cart link`` both match a link named ``Cart``; neither matches
    ``Add to cart``, which is exactly the prominent button that used to win.
    Generic UI nouns are dropped on both sides; every identifying word must then
    be equal.

    The comparison is per FIELD. Unioning the fields let a link to the RIGHT page
    whose ``aria-label`` was ``Cart`` but whose visible text was ``Proceed`` fail
    the label test (the union read "cart proceed"), so a link to the WRONG page
    with visible text ``Cart`` won. A field that names the element is a name in
    its own right; combining them invents one the page never shows.
    """

    def words(text: str) -> set[str]:
        return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if word and word not in _GENERIC_LABEL_WORDS}

    wanted = words(description)
    if not wanted:
        return False
    for name_field in _NAME_FIELDS:
        value = element.get(name_field)
        if value and words(str(value)) == wanted:
            return True
    return False


def find_replacement_locator(
    url: str,
    action: str,
    description: str,
    old_locator: str,
) -> str | None:
    """Re-resolve *description* to a locator; None when nothing better exists.

    The product's scorer still supplies the page's candidates, but IDENTITY
    evidence outranks prominence (j-0312). A candidate whose href points at the
    same page as the broken link, or whose accessible name is the step label, is
    a better repair than a big button that happens to share a word:

    1. both href and label match;
    2. exact label match, even with a different href;
    3. href match, with no exact label;
    4. the scorer's order unchanged.

    A right label therefore always outranks a wrong href (tier 2 > tier 3),
    which is what stops a link to another page stealing a named step. The
    assertion gate still decides whether the patch survives.
    """
    if not description.strip():
        return None
    from src.placeholder_resolver import PlaceholderResolver

    elements = scrape_elements(url)
    resolver = PlaceholderResolver()
    ranked = resolver.rank_candidates(action, description, elements)

    target = _target_href(old_locator)
    usable: list[tuple[int, int, int, str]] = []
    for order, (score, element) in enumerate(ranked):
        selector = str(element.get("selector", "")).strip()
        if not selector or selector == old_locator or score < 1:
            continue  # same locator, no adaptation; scorer already rejected it
        label = _label_matches(description, element)
        href = bool(target) and _identity_path(str(element.get("href") or "")) == target
        tier = 3 if label and href else 2 if label else 1 if href else 0
        usable.append((tier, score, order, selector))

    if not usable:
        return None
    # Stable sort: within an identity tier the product's own ranking stands.
    usable.sort(key=lambda row: (-row[0], -row[1], row[2]))
    return usable[0][3]


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


_EVIDENCE_SUFFIX = ".evidence.json"


def _evidence_repair_candidates(package: Path) -> list[dict[str, str]]:
    """At most ONE candidate per test: the EARLIEST failed step, if it is locator-class.

    The carry-on rule (t-1057) means a dead locator does not end its test: the step
    is written to the sidecar with status ``failed`` and an error naming the
    locator, and the test carries on. After that first failure the journey is off
    course - the tracker stamps every later step with ``off_course`` naming the
    ``failed_step`` (and the page it did not reach, when known). Later failures are
    consequences of the first one, so repairing them chases symptoms: three dead
    locators in one test are not three repairs, they are one lost journey. Only the
    first failure is an honest candidate; if that one is an assertion, the test
    yields none and the later steps stay off course.
    """
    records: list[dict[str, str]] = []
    for path in sorted(package.rglob(f"*{_EVIDENCE_SUFFIX}")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError, OSError:
            continue
        test = str((data.get("test") or {}).get("name") or path.name[: -len(_EVIDENCE_SUFFIX)])
        steps = data.get("steps") or []
        first_failed: tuple[int, dict[str, Any]] | None = None
        for index, step in enumerate(steps):
            result = step.get("result") or {}
            if result.get("status") == "failed":
                first_failed = (index + 1, result)
                break
        if first_failed is None:
            continue
        number, result = first_failed
        message = str(result.get("error") or result.get("failure_note") or "").strip()
        if not message or not is_repair_candidate(message):
            continue
        # The tracker's stamp is the reason: later failures were marked off course
        # FROM this step, so they cannot be independent repair targets.
        later = steps[number:]  # steps after the first failed one
        stamped = sum(1 for step in later if ((step.get("result") or {}).get("off_course")))
        reason = f"first failed step {number}; {stamped} later step(s) stamped off_course by the tracker"
        records.append({"test": test, "message": message, "reason": reason})
    return records


def repair_candidates(package: Path, junit: Path) -> list[dict[str, str]]:
    """Every locator-class candidate from both sources, one per (test, locator).

    The junit record wins when both sources name the same failure: it carries the
    test name the runner reported.
    """
    merged: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for record in [*_junit_repair_candidates(junit), *_evidence_repair_candidates(package)]:
        base = record["test"].split("[", 1)[0]
        key = (base, _extract_locator(record["message"]) or record["message"][:120])
        if key in seen:
            continue
        seen.add(key)
        merged.append(record)
    return merged


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
    candidates = repair_candidates(package, junit)
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
        if cand.get("reason"):
            entry["reason"] = cand["reason"]

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
