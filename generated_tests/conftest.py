"""Pytest fixtures for generated Playwright tests.

This file lives under `generated_tests/` so it is discovered when executing
generated packages directly (e.g. `pytest generated_tests/test_x.py -v`).

Evidence is written to <test_file_directory>/evidence/ so each test package
gets its own evidence folder alongside its tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page

from src.evidence_tracker import JOURNEY_PROTOCOL, EvidenceTracker

# t-1063: the tracker carries on after a failed step and the conftest fails the
# test once, at its end. Both halves are needed, so both declare the same marker.
# A package with a new tracker and an old conftest would carry on and NEVER fail
# the test - a silent success. The fixture refuses to run when they disagree, and
# it registers ``tracker.journey_hooked`` - the hand-shake that lets the tracker
# carry on at all. A new tracker under a conftest that never registers therefore
# raises at the failed step instead of passing silently (t-1066). What the marker
# catches: drift between two versions that both carry the check, and a new
# conftest with an old tracker (which fails even earlier, at import).
CONFTEST_JOURNEY_PROTOCOL = "carry-on-2"


def _check_journey_protocol() -> None:
    """Fail loudly when the tracker and this conftest do not belong together."""
    if JOURNEY_PROTOCOL != CONFTEST_JOURNEY_PROTOCOL:
        raise RuntimeError(
            "evidence_tracker and conftest.py disagree about the journey protocol: "
            f"tracker={JOURNEY_PROTOCOL!r}, conftest={CONFTEST_JOURNEY_PROTOCOL!r}. "
            "A failed step would carry on and the test would never fail. "
            "Re-copy generated_tests/conftest.py from the same version as the tracker."
        )


@dataclass(frozen=True)
class _EvidenceRefs:
    condition_ref: str
    story_ref: str


def _get_evidence_refs(request: pytest.FixtureRequest) -> _EvidenceRefs:
    marker = request.node.get_closest_marker("evidence")
    if marker is None:
        return _EvidenceRefs(condition_ref="unknown", story_ref="unknown")
    condition_ref = str(marker.kwargs.get("condition_ref", "unknown"))
    story_ref = str(marker.kwargs.get("story_ref", "unknown"))
    return _EvidenceRefs(condition_ref=condition_ref, story_ref=story_ref)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: Any, call: Any) -> Any:
    """Attach per-phase reports on the node so fixtures can read pass/fail.

    t-1057: a failed step no longer ends its test. The tracker records the failed
    step and the journey carries on; this hook fails the test ONCE, at the end,
    with ``journey_summary()`` - the failed step, what it expected, what the
    browser reached, and what the later steps did. A raise in fixture teardown
    would be reported as an ERROR instead of a FAILED test, so the report is what
    carries it.
    """
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)

    if rep.when != "call":
        return
    tracker = getattr(item, "_evidence_tracker", None)
    if tracker is None or not rep.passed:
        return
    summary = tracker.journey_summary()
    if summary:
        rep.outcome = "failed"
        rep.longrepr = summary


@pytest.fixture
def evidence_tracker(page: Page, request: pytest.FixtureRequest) -> EvidenceTracker:
    """Provide an EvidenceTracker instance for generated tests.

    Evidence is written to <test_file_directory>/evidence/ so each test package
    gets its own evidence folder alongside its tests.

    The test_package_dir is determined from the test file's location (not this
    conftest's location) so that each subdirectory under generated_tests/ that
    contains a test file gets its own isolated evidence folder.
    """
    _check_journey_protocol()
    refs = _get_evidence_refs(request)

    # Determine the test file's directory (not this conftest's directory).
    # request.fspath is the path to the test file being run.
    test_package_dir = Path(request.fspath).parent

    tracker = EvidenceTracker(
        page=page,
        test_name=request.node.name,
        condition_ref=refs.condition_ref,
        story_ref=refs.story_ref,
        test_package_dir=test_package_dir,
    )
    # t-1057: the report hook needs the tracker to fail the test once, at the end,
    # with what failed and what the later steps did.
    setattr(request.node, "_evidence_tracker", tracker)  # noqa: B010 - a pytest Item has no declared slot
    # t-1066: the hand-shake. The tracker only swallows a failed step when
    # something promises to fail the test afterwards; this hook is that promise.
    tracker.journey_hooked = True
    yield tracker

    rep_call = getattr(request.node, "rep_call", None)
    if rep_call is not None and getattr(rep_call, "skipped", False):
        status = "skipped"
    elif rep_call is not None and getattr(rep_call, "passed", False):
        status = "passed"
    else:
        status = "failed"
    tracker.write(status=status)

    # B-036 Phase 3 (AI-035): learn from a fully-passing run. The resolved
    # (action, description, locator, site) pairs are verified by execution —
    # feed them to the local RAG store (dedup'd, site-scoped) so the next
    # generation for the same site resolves faster. Guarded: learning must
    # never break the test run, and a repeat is a no-op hit bump.
    # ``RAG_ENABLED=0`` opts out of the RAG write leg. AI-059's explicit
    # ``AI059_DISABLE_AUTO_LEARN=1`` gate opts out of BOTH write legs while
    # preserving RAG reads for warm measurement legs.
    if (
        status == "passed"
        and os.environ.get("AI059_DISABLE_AUTO_LEARN", "0") != "1"
        and os.environ.get("RAG_ENABLED", "1") != "0"
    ):
        try:
            from src.rag_learn import learn_from_evidence

            learn_from_evidence(tracker.steps)
        except Exception:
            # learning is best-effort — never fail a passing test on it.
            # A repeat (dedup) is a silent hit bump; a failure means the
            # next run retries. See docs/plans/AI-035_B036_P3_plan.md §7.
            pass
    # AI-042: learn cross-site flow transitions from the same passing run
    # (login → dashboard → cart → checkout navigation shape generalizes
    # across sites even though locators don't). Same best-effort contract;
    # AI-059 disables this write leg explicitly to keep comparison legs
    # independent.
    if status == "passed" and os.environ.get("AI059_DISABLE_AUTO_LEARN", "0") != "1":
        try:
            from src.flow_memory import FlowMemoryStore

            FlowMemoryStore().learn_from_evidence(tracker.steps)
        except Exception:
            pass
