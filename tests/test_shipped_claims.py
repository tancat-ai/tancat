"""A page may say "shipped" only when a named test proves it (t-1350, t-1371, t-1374).

This is the durable check the owner asked for, and it targets the failure class
that let the ignore list be documented as shipped for months: the section named
no test, so nothing could ever notice that the matcher was never called.

`scripts/check_shipped_claims.py` finds every status banner (``> **Status:**``)
in the claiming pages that says shipped/available and requires markers in the
same section::

    <!-- shipped-check: tests/test_ci_report.py::test_report_main_writes_comment_payload -->

**Every** marker in the section is run - a broad claim with three proofs must be
proved three times - and a marker only counts when its test *passes with an
assertion*. The refusals, each proven below:

* a **skipped** test - a skip is the absence of proof, not a pass;
* an **xfail** test - an expected failure proves nothing;
* a test that **asserts nothing** - its green means nothing;
* a test that **fails** or **does not exist**;
* a marker that **breaks pytest's collection** (exit 4) - reported against that
  marker, not against every other page, which is what a batch failure used to do.

Section boundary: a banner's section runs to the next ``## ``/``#`` heading, so a
marker in a ``###`` subsection counts for the ``##`` claim and the report names
the subsection that proved it.

## The companion scan, and what it is NOT

`test_no_new_dead_code_outside_the_baseline` runs vulture at ``--min-confidence
100`` (vulture 2.16, via ``uv run --with vulture``; no package added) and fails on
anything not on ``scripts/dead_code_baseline.txt``; a baseline entry with no
current finding is also a failure (staleness). Keys carry the enclosing scope
(``path: Class.method: finding``) so the same message in a new class cannot
collapse onto an existing entry.

What the 100% tier catches: **unused locals and parameters, and unreachable
statements**. It does **not** catch unused functions or methods - those surface at
vulture's 60% tier, which returned 327 findings on ``src/`` (nearly all public
API) and is not usable as a gate without a large allowance list. The audit's "20
unreferenced names" item owns that gap.

**It would NOT have caught the ignore list.** The matcher was referenced, imported
and unit-tested; what was missing was a caller on a real run. A dead-code scan
answers "is this name used?", not "does this feature work?".
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_shipped_claims as shipped  # noqa: E402

BASELINE = ROOT / "scripts" / "dead_code_baseline.txt"
VULTURE_COMMAND = ["uv", "run", "--with", "vulture", "vulture", "src", "--min-confidence", "100"]
SCOPE_RE = re.compile(r"^(?P<indent>\s*)(?:async\s+)?(?:def|class)\s+(?P<name>\w+)")
GOOD = "tests/test_ci_report.py::test_report_main_writes_comment_payload"


def _fake_runner(outcomes: dict[str, str]) -> Any:
    def runner(_root: Path, node_ids: list[str]) -> dict[str, str]:
        return {node: outcomes.get(node, "missing") for node in node_ids}

    return runner


def _docs_with(tmp_path: Path, status: str, *markers: str, subsection: str = "") -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    body = f"# A feature\n\n> **Status:** {status}\n"
    if subsection:
        body += f"\n### {subsection}\n"
    for marker in markers:
        body += f"\n<!-- shipped-check: {marker} -->\n"
    (docs / "feature.md").write_text(body, encoding="utf-8")
    return tmp_path


class TestTheRepository:
    def test_no_shipped_claim_is_unverified(self) -> None:
        """The real check: every claiming banner is proved by a passing, asserting test."""
        problems = shipped.verify(ROOT, "docs", runner=shipped.run_tests)
        assert problems == [], "a page claims shipped without a passing named test:\n" + "\n".join(problems)

    def test_the_rule_is_written_down_in_the_repo(self) -> None:
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        assert "A feature is shipped when a named test proves it" in contributing
        assert "shipped-check:" in contributing

    def test_every_docs_directory_with_a_banner_is_classified(self) -> None:
        """Scope is closed: a new docs directory with banners fails until it is classified."""
        banner_dirs = set()
        for doc in (ROOT / "docs").rglob("*.md"):
            if "**Status:**" in doc.read_text(encoding="utf-8", errors="replace"):
                rel = doc.relative_to(ROOT / "docs")
                banner_dirs.add("(root)" if len(rel.parts) == 1 else rel.parts[0])
        unclassified = banner_dirs - set(shipped.OUT_OF_SCOPE) - {"(root)"}
        assert unclassified == set(), (
            f"docs directories carrying status banners that are neither scanned nor listed in "
            f"OUT_OF_SCOPE: {sorted(unclassified)}"
        )


class TestTheCheckerBites:
    def test_a_claim_with_no_marker_is_reported(self, tmp_path: Path) -> None:
        root = _docs_with(tmp_path, "shipped - everything works")
        problems = shipped.verify(root, "docs", runner=_fake_runner({}))
        assert len(problems) == 1
        assert "no shipped-check marker" in problems[0]
        assert "docs/feature.md:3" in problems[0].replace("\\", "/")

    def test_a_marker_naming_a_missing_test_is_reported(self, tmp_path: Path) -> None:
        root = _docs_with(tmp_path, "shipped", "tests/test_nothing.py::test_absent")
        problems = shipped.verify(root, "docs", runner=_fake_runner({}))
        assert len(problems) == 1
        assert "does not exist" in problems[0]
        assert "tests/test_nothing.py::test_absent" in problems[0]

    def test_a_marker_whose_test_fails_is_reported(self, tmp_path: Path) -> None:
        root = _docs_with(tmp_path, "shipped", GOOD)
        problems = shipped.verify(root, "docs", runner=_fake_runner({GOOD: "failed"}))
        assert len(problems) == 1
        assert "FAILS" in problems[0]

    def test_a_verified_marker_passes(self, tmp_path: Path) -> None:
        root = _docs_with(tmp_path, "shipped", GOOD)
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_ci_report.py").write_text(
            "def test_report_main_writes_comment_payload():\n    assert True\n", encoding="utf-8"
        )
        assert shipped.verify(root, "docs", runner=_fake_runner({GOOD: "passed"})) == []


class TestSkipsAreNotProof:
    """t-1374: a skip is the absence of proof, and a green test that asserts nothing is too."""

    def test_a_skipped_test_is_refused(self, tmp_path: Path) -> None:
        root = _docs_with(tmp_path, "shipped", GOOD)
        problems = shipped.verify(root, "docs", runner=_fake_runner({GOOD: "skipped"}))
        assert len(problems) == 1
        assert "SKIPPED" in problems[0] and "absence of proof" in problems[0]

    def test_an_xfail_test_is_refused(self, tmp_path: Path) -> None:
        root = _docs_with(tmp_path, "shipped", GOOD)
        problems = shipped.verify(root, "docs", runner=_fake_runner({GOOD: "xfail"}))
        assert len(problems) == 1
        assert "XFAIL" in problems[0]

    def test_a_test_that_asserts_nothing_is_refused(self, tmp_path: Path) -> None:
        node = "tests/test_hollow.py::test_no_assert"
        root = _docs_with(tmp_path, "shipped", node)
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_hollow.py").write_text(
            "def test_no_assert():\n    value = 1 + 1\n    print(value)\n", encoding="utf-8"
        )
        problems = shipped.verify(root, "docs", runner=_fake_runner({node: "passed"}))
        assert len(problems) == 1
        assert "asserts nothing" in problems[0]

    def test_a_test_the_checker_cannot_read_is_refused(self, tmp_path: Path) -> None:
        node = "tests/test_gone.py::test_unreadable"
        root = _docs_with(tmp_path, "shipped", node)
        problems = shipped.verify(root, "docs", runner=_fake_runner({node: "passed"}))
        assert len(problems) == 1
        assert "could not be read" in problems[0]

    def test_a_collection_error_names_the_marker_that_broke_it(self, tmp_path: Path) -> None:
        """One bad id must not be reported against every other page (t-1374)."""
        bad = "tests/test_nothing.py::test_absent"
        root = _docs_with(tmp_path, "shipped", GOOD, bad)
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_ci_report.py").write_text(
            "def test_report_main_writes_comment_payload():\n    assert True\n", encoding="utf-8"
        )
        outcomes = {GOOD: "passed", bad: "collect_error"}
        problems = shipped.verify(root, "docs", runner=_fake_runner(outcomes))
        assert len(problems) == 1, problems
        assert bad in problems[0] and "collection" in problems[0]
        assert GOOD not in problems[0]


class TestEveryMarkerCounts:
    """t-1374: only the first marker used to be read; a broad claim needs all of them."""

    def test_two_markers_are_both_checked(self, tmp_path: Path) -> None:
        second = "tests/test_ci_report.py::test_other_proof"
        root = _docs_with(tmp_path, "shipped", GOOD, second)
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_ci_report.py").write_text(
            "def test_report_main_writes_comment_payload():\n    assert True\n"
            "def test_other_proof():\n    assert True\n",
            encoding="utf-8",
        )
        outcomes = {GOOD: "passed", second: "failed"}

        problems = shipped.verify(root, "docs", runner=_fake_runner(outcomes))

        assert len(problems) == 1, problems
        assert second in problems[0]

    def test_both_markers_passing_is_clean(self, tmp_path: Path) -> None:
        second = "tests/test_ci_report.py::test_other_proof"
        root = _docs_with(tmp_path, "shipped", GOOD, second)
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_ci_report.py").write_text(
            "def test_report_main_writes_comment_payload():\n    assert True\n"
            "def test_other_proof():\n    assert True\n",
            encoding="utf-8",
        )
        outcomes = {GOOD: "passed", second: "passed"}
        assert shipped.verify(root, "docs", runner=_fake_runner(outcomes)) == []


class TestSectionBoundary:
    """t-1374: a marker in a `###` subsection counts for the `##` claim, and says so."""

    def test_a_subsection_marker_proves_the_section_and_is_named(self, tmp_path: Path) -> None:
        root = _docs_with(tmp_path, "shipped", GOOD, subsection="Login flow")
        claims = shipped.find_claims(root, "docs")
        assert len(claims) == 1
        assert claims[0].markers[0].subsection == "Login flow"
        described = "\n".join(shipped.describe(root, "docs"))
        assert "under 'Login flow'" in described
        assert "docs/feature.md:3" in described.replace("\\", "/")

    def test_a_marker_after_the_next_h2_does_not_count(self, tmp_path: Path) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "feature.md").write_text(
            f"# Page\n\n> **Status:** shipped\n\n## Next feature\n\n<!-- shipped-check: {GOOD} -->\n",
            encoding="utf-8",
        )
        claims = shipped.find_claims(tmp_path, "docs")
        assert claims and claims[0].markers == ()


class TestNegations:
    def test_a_negated_status_claims_nothing(self, tmp_path: Path) -> None:
        root = _docs_with(tmp_path, "NOT SHIPPED - code exists, nothing proves it")
        assert shipped.find_claims(root, "docs") == []

    def test_a_status_that_does_not_claim_shipping_is_ignored(self, tmp_path: Path) -> None:
        root = _docs_with(tmp_path, "draft - being designed")
        assert shipped.find_claims(root, "docs") == []


# -- the dead-code companion -------------------------------------------------


def _scope_for(path: Path, line_no: int) -> str:
    """Nearest enclosing def/class names (``Class.method``), from the source text."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if line_no - 1 >= len(lines):
        return ""
    target = lines[line_no - 1]
    threshold = len(target) - len(target.lstrip())
    names: list[str] = []
    for index in range(line_no - 1, -1, -1):
        match = SCOPE_RE.match(lines[index])
        if match is None:
            continue
        indent = len(match.group("indent"))
        if indent <= threshold:
            names.append(match.group("name"))
            threshold = indent - 1
            if indent == 0:
                break
    return ".".join(reversed(names))


def _baseline_entries() -> set[str]:
    return {
        line.strip()
        for line in BASELINE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


#: The baseline was recorded with this vulture; message wording and the finding set
#: are version-dependent, so a bump is a deliberate re-record, not a silent churn.
PINNED_VULTURE = "2.16"


def _vulture_version() -> str:
    result = subprocess.run(VULTURE_COMMAND[:5] + ["--version"], cwd=ROOT, capture_output=True, text=True, timeout=300)
    return (result.stdout or result.stderr).strip()


def _vulture_findings() -> set[str]:
    """The scan's findings as ``path: scope: message``, resolved against ROOT.

    Vulture prints paths relative to the directory it ran in; joining them to the
    *process* cwd (a test run from tests/ does that) made every path miss and the
    scan read as "found nothing".
    """
    version = _vulture_version()
    if PINNED_VULTURE not in version:
        pytest.fail(
            f"vulture {version or 'unknown'} != the pinned {PINNED_VULTURE}: the baseline in "
            "scripts/dead_code_baseline.txt is version-specific (message wording and finding set "
            "change between releases). Re-record it deliberately, then update PINNED_VULTURE."
        )
    result = subprocess.run(VULTURE_COMMAND, cwd=ROOT, capture_output=True, text=True, timeout=600)
    findings: set[str] = set()
    for line in result.stdout.splitlines():
        match = re.match(r"^(?P<path>[^:]+):(?P<line>\d+):\s+(?P<what>.+?)\s+\(\d+% confidence\)$", line.strip())
        if not match:
            continue
        reported = Path(match.group("path").replace(chr(92), "/"))
        path = reported if reported.is_absolute() else ROOT / reported
        if not path.is_file():
            continue
        findings.add(f"{reported.as_posix()}: {_scope_for(path, int(match.group('line')))}: {match.group('what')}")
    assert findings, f"the scan found nothing at all, which is not credible for this tree (ran in {ROOT})"
    return findings


def _dead_code_problems(findings: set[str], baseline: set[str]) -> list[str]:
    """New findings, and baseline entries that no longer exist (staleness)."""
    problems = [f"new dead code: {item}" for item in sorted(findings - baseline)]
    problems += [f"stale baseline entry (no current finding): {item}" for item in sorted(baseline - findings)]
    return problems


class TestTheDeadCodeCompanion:
    def test_no_new_dead_code_outside_the_baseline(self) -> None:
        """Vulture at 100%. It catches dead locals/params, NOT unused functions - and NOT the ignore list."""
        problems = _dead_code_problems(_vulture_findings(), _baseline_entries())
        assert problems == [], problems

    def test_the_baseline_does_not_keep_ghosts(self) -> None:
        """A baseline entry whose finding is gone is a failure, so the list cannot rot."""
        problems = _dead_code_problems({"src/x.py: f: unused variable 'a'"}, {"src/x.py: f: unused variable 'b'"})
        assert any("stale baseline entry" in problem for problem in problems)
        assert any("new dead code" in problem for problem in problems)

    def test_a_second_class_exit_does_not_collapse_onto_the_first(self, tmp_path: Path) -> None:
        """The key carries the enclosing scope, so a new class's __exit__ is not hidden."""
        sample = tmp_path / "src" / "sample.py"
        sample.parent.mkdir(parents=True)
        sample.write_text(
            "class StoreLock:\n"
            "    def __exit__(self, exc_type, tb):\n"
            "        return False\n"
            "\n"
            "class OtherLock:\n"
            "    def __exit__(self, exc_type, tb):\n"
            "        return False\n",
            encoding="utf-8",
        )
        assert _scope_for(sample, 2) == "StoreLock.__exit__"
        assert _scope_for(sample, 6) == "OtherLock.__exit__"


class TestBatchBlameAttribution:
    """t-1376: a file that fails to IMPORT still writes junit, so 'no junit' was the wrong trigger."""

    def test_a_missing_id_triggers_the_per_marker_fallback(self, tmp_path: Path, monkeypatch: Any) -> None:
        good = "tests/test_good.py::test_good"
        broken = "tests/test_broken.py::test_broken"
        _docs_with(tmp_path, "shipped", good, broken)

        calls: list[list[str]] = []

        def fake_once(_root: Path, ids: list[str]) -> dict[str, str] | None:
            calls.append(list(ids))
            if len(ids) > 1:
                # The batch answered the good id and wrote a junit holding only the
                # import error - so this is NOT "no junit", which is what the old
                # fallback keyed on.
                return {shipped._node_key(good): "passed"}
            if ids == [broken]:
                return {shipped._node_key(broken): "failed"}
            return {}

        monkeypatch.setattr(shipped, "_pytest_once", fake_once)

        outcomes = shipped.run_tests(tmp_path, [good, broken])

        assert outcomes == {good: "passed", broken: "failed"}
        assert calls[0] == [good, broken], "the batch run comes first"
        assert [broken] in calls, "the id the batch did not answer is re-run on its own"

    def test_a_good_page_keeps_its_verdict_beside_a_broken_file(self, tmp_path: Path, monkeypatch: Any) -> None:
        good = "tests/test_good.py::test_good"
        broken = "tests/test_broken.py::test_broken"
        root = _docs_with(tmp_path, "shipped", good, broken)
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_good.py").write_text("def test_good():\n    assert True\n", encoding="utf-8")

        monkeypatch.setattr(
            shipped, "_pytest_once", lambda _root, ids: {shipped._node_key(good): "passed"} if len(ids) > 1 else None
        )
        problems = shipped.verify(root, "docs")

        assert len(problems) == 1, problems
        assert broken in problems[0] and "collection" in problems[0]
        assert good not in problems[0], "the good page must not be blamed for the broken file"


class TestTheAssertionRead:
    """t-1376: a parametrized test with a real assert was refused as 'could not be read'."""

    def test_a_parametrized_id_is_read(self, tmp_path: Path) -> None:
        node = "tests/test_param.py::test_amount[100]"
        root = _docs_with(tmp_path, "shipped", node)
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_param.py").write_text(
            "import pytest\n\n\n@pytest.mark.parametrize('amount', [100])\n"
            "def test_amount(amount):\n    assert amount > 0\n",
            encoding="utf-8",
        )
        assert shipped.verify(root, "docs", runner=_fake_runner({node: "passed"})) == []

    def test_the_bare_function_name_is_also_read(self, tmp_path: Path) -> None:
        path = tmp_path / "tests" / "test_param.py"
        path.parent.mkdir()
        path.write_text("def test_amount(amount):\n    assert amount > 0\n", encoding="utf-8")
        assert shipped._has_assertion(tmp_path, "tests/test_param.py::test_amount[100]") is True


class TestKnownLimits:
    """t-1376: the heuristic says where it is weak, in the docstring and in its output."""

    def test_the_limits_are_in_the_docstring(self) -> None:
        text = (ROOT / "scripts" / "check_shipped_claims.py").read_text(encoding="utf-8")
        for phrase in ("known ways to be dodged", "assert True", "class part of a node id", "nested helper"):
            assert phrase in text, phrase

    def test_the_limits_are_printed(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert shipped.main(["--root", str(ROOT), "--docs", "docs"]) == 0
        out = capsys.readouterr().out
        assert "what this does NOT prove" in out
        assert "assert True" in out and "class part of a node id" in out


class TestTheScopeReport:
    """t-1376: counts are measured, never hardcoded, and absent directories are not claimed."""

    def test_the_report_counts_what_is_there(self) -> None:
        lines = "\n".join(shipped.scope_report(ROOT, "docs"))
        plans = next(line for line in lines.splitlines() if "plans/" in line)
        assert "page(s)" in plans and "status line(s)" in plans
        assert "design records" in plans

    def test_an_absent_directory_is_not_reported(self, tmp_path: Path) -> None:
        (tmp_path / "docs").mkdir()
        lines = shipped.scope_report(tmp_path, "docs")
        assert not any("plans/" in line for line in lines)
        assert any("none of the known record directories" in line for line in lines)

    def test_the_docstring_does_not_hardcode_counts(self) -> None:
        text = (ROOT / "scripts" / "check_shipped_claims.py").read_text(encoding="utf-8")
        docstring = text.split('"""', 2)[1]
        assert "13 files" not in docstring and "42 files" not in docstring
        assert "The counts are not" in docstring or "measured" in docstring


class TestTheJunitShapes:
    """t-1376: the two ways a single-id run answers with no testcase are different faults."""

    def test_a_module_level_error_is_a_collection_failure(self, tmp_path: Path) -> None:
        junit = tmp_path / "j.xml"
        junit.write_text(
            '<?xml version="1.0"?><testsuites><testsuite>'
            '<testcase classname="" name="tests.test_broken"><error message="collection failure" />'
            "</testcase></testsuite></testsuites>",
            encoding="utf-8",
        )
        outcomes = shipped._parse_junit(junit)
        assert outcomes["file:tests.test_broken"] == "collect_error"

    def test_an_empty_testsuite_is_no_testcase_at_all(self, tmp_path: Path) -> None:
        junit = tmp_path / "j.xml"
        junit.write_text('<?xml version="1.0"?><testsuites><testsuite /></testsuites>', encoding="utf-8")
        assert shipped._parse_junit(junit) == {}
