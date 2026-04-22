"""Pytest fixtures for generated Playwright tests.

This file lives under `generated_tests/` so it is discovered when executing
generated packages directly (e.g. `pytest generated_tests/test_x.py -v`).
"""

from __future__ import annotations

from dataclasses import dataclass
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
    """Provide an EvidenceTracker instance for generated tests."""
    refs = _get_evidence_refs(request)
    tracker = EvidenceTracker(
        page=page,
        test_name=request.node.name,
        condition_ref=refs.condition_ref,
        story_ref=refs.story_ref,
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
