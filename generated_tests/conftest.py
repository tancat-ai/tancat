"""Pytest fixtures for generated Playwright tests.

This file lives under `generated_tests/` so it is discovered when executing
generated packages directly (e.g. `pytest generated_tests/test_x.py -v`).

Evidence is written to <test_file_directory>/evidence/ so each test package
gets its own evidence folder alongside its tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page

from src.evidence_tracker import EvidenceTracker


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
    """Attach per-phase reports on the node so fixtures can read pass/fail."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


@pytest.fixture
def evidence_tracker(page: Page, request: pytest.FixtureRequest) -> EvidenceTracker:
    """Provide an EvidenceTracker instance for generated tests.

    Evidence is written to <test_file_directory>/evidence/ so each test package
    gets its own evidence folder alongside its tests.

    The test_package_dir is determined from the test file's location (not this
    conftest's location) so that each subdirectory under generated_tests/ that
    contains a test file gets its own isolated evidence folder.
    """
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
    yield tracker

    rep_call = getattr(request.node, "rep_call", None)
    if rep_call is not None and getattr(rep_call, "skipped", False):
        status = "skipped"
    elif rep_call is not None and getattr(rep_call, "passed", False):
        status = "passed"
    else:
        status = "failed"
    tracker.write(status=status)
