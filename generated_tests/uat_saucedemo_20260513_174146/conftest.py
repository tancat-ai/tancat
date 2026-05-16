"""Conftest for generated tests — provides evidence_tracker fixture."""
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

import pytest
from src.evidence_tracker import EvidenceTracker


@pytest.fixture()
def evidence_tracker(page: Page, request: Any) -> EvidenceTracker:
    """Create an EvidenceTracker bound to the Playwright page fixture."""
    test_name = getattr(request.node, "name", "unknown_test")
    condition_ref = ""
    story_ref = ""
    for mark in request.node.iter_markers("evidence"):
        condition_ref = mark.kwargs.get("condition_ref", condition_ref)
        story_ref = mark.kwargs.get("story_ref", story_ref)
    tracker = EvidenceTracker(
        page=page,
        test_name=test_name,
        condition_ref=condition_ref or "unknown",
        story_ref=story_ref or "unknown",
    )
    yield tracker
    # Teardown: write sidecar if steps were recorded
    if tracker.steps:
        tracker.write(status="passed")
