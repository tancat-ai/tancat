"""A page may say "shipped" only when a named test proves it (t-1350 audit, t-1371).

This is the durable check the owner asked for, and it targets the failure class
that let the ignore list be documented as shipped for months: the section named
no test, so nothing could ever notice that the matcher was never called.

`scripts/check_shipped_claims.py` finds every status banner (``> **Status:**``)
in ``docs/*.md`` that claims shipped/available and requires a marker in the same
section::

    <!-- shipped-check: tests/test_ci_report.py::test_report_main_writes_comment_payload -->

It then collects that test id and runs it. Three ways to fail, and the first
test below runs the real checker over this repository: no marker, a marker
naming a test that does not exist, and a marker whose test fails.

## The companion scan, and what it is NOT

`test_no_new_dead_code_in_src` runs vulture at ``--min-confidence 100`` (vulture
2.16, via ``uv run --with vulture``; no package added to the project) and fails
when it finds something that is not on ``scripts/dead_code_baseline.txt``. The
100% tier is the highest that gives no false positives on ``src/``: the 60-80%
tiers produced ~327 findings, almost all public API. Today it reports 9 dead
locals / unreachable statements, which the audit's "20 unreferenced names" item
owns - this job does not fix them.

**It would NOT have caught the ignore list.** The matcher was referenced,
imported and unit-tested; what was missing was a caller on a real run. Dead-code
scanners answer "is this name used?", not "does this feature work?". They are
bought together because they are both cheap, not because either substitutes for
the other.
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


def _fake_runner(outcomes: dict[str, str]) -> Any:
    def runner(_root: Path, node_ids: list[str]) -> dict[str, str]:
        return {node: outcomes.get(node, "missing") for node in node_ids}

    return runner


def _docs_with(tmp_path: Path, status: str, marker: str | None = None) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    body = f"# A feature\n\n> **Status:** {status}\n"
    if marker is not None:
        body += f"\n<!-- shipped-check: {marker} -->\n"
    (docs / "feature.md").write_text(body, encoding="utf-8")
    return tmp_path


class TestTheRepository:
    def test_no_shipped_claim_is_unverified(self) -> None:
        """The real check: every status banner that claims shipped is proved by a test.

        This one shells out to pytest for the marker's test id - it is the check
        the pre-commit hook runs, and it must stay cheap: one collection per run.
        """
        problems = shipped.verify(ROOT, "docs", runner=shipped.run_tests)
        assert problems == [], "a page claims shipped without a passing named test:\n" + "\n".join(problems)

    def test_the_rule_is_written_down_in_the_repo(self) -> None:
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        assert "A feature is shipped when a named test proves it" in contributing
        assert "shipped-check:" in contributing


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
        node = "tests/test_ci_report.py::test_report_main_writes_comment_payload"
        root = _docs_with(tmp_path, "shipped", node)
        problems = shipped.verify(root, "docs", runner=_fake_runner({node: "failed"}))
        assert len(problems) == 1
        assert "FAILS" in problems[0]

    def test_a_verified_marker_passes(self, tmp_path: Path) -> None:
        node = "tests/test_ci_report.py::test_report_main_writes_comment_payload"
        root = _docs_with(tmp_path, "shipped", node)
        assert shipped.verify(root, "docs", runner=_fake_runner({node: "passed"})) == []

    def test_a_negated_status_claims_nothing(self, tmp_path: Path) -> None:
        root = _docs_with(tmp_path, "NOT SHIPPED - code exists, nothing proves it")
        assert shipped.find_claims(root, "docs") == []

    def test_a_status_that_does_not_claim_shipping_is_ignored(self, tmp_path: Path) -> None:
        root = _docs_with(tmp_path, "draft - being designed")
        assert shipped.find_claims(root, "docs") == []


class TestTheDeadCodeCompanion:
    def test_no_new_dead_code_in_src(self) -> None:
        """Vulture at 100%: nothing new is dead. It would NOT have caught the ignore list."""
        allowed = {
            line.strip()
            for line in BASELINE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
        try:
            result = subprocess.run(VULTURE_COMMAND, cwd=ROOT, capture_output=True, text=True, timeout=600)
        except FileNotFoundError:  # pragma: no cover - uv missing
            pytest.skip("uv is not on PATH, so the dead-code scan cannot run")
        if result.returncode not in (0, 3):
            pytest.skip(f"vulture could not run (offline?): {result.stderr.strip()[:200]}")

        findings = set()
        for line in result.stdout.splitlines():
            match = re.match(r"^(?P<path>[^:]+):\d+:\s+(?P<what>.+?)\s+\(\d+% confidence\)$", line.strip())
            if match:
                findings.add(f"{match.group('path').replace(chr(92), '/')}: {match.group('what')}")

        new = sorted(findings - allowed)
        assert new == [], (
            "new dead code at vulture's 100% tier - fix it, or add it to "
            f"scripts/dead_code_baseline.txt with a reason: {new}"
        )
        assert findings, (
            "the scan found nothing at all, which is not credible for this tree - check that vulture ran against src/"
        )
