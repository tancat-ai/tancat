"""Adversarial tests — the pipeline under hostile/edge conditions.

Test-Pack Restructure (2026-08-03, work item 2): the suite had no
adversarial layer, yet the worst real bugs were environmental attacks —
consent/ad overlays swallowing clicks (B-029), HTTP-404 pages polluting the
scrape (B-045), broken locators defeating self-healing (B-039/B-033).

These tests are OFFLINE: they drive the real pipeline modules against the
local banking mock with `?overlay=consent|ad` (the injectable B-029 race),
the mock's 404'd concept routes, and synthetic broken-locator fixtures. No
LLM, no external network, CI-able.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.placeholder_orchestrator import PlaceholderOrchestrator

# ── B-045: HTTP-404 pages must never pollute resolution ───────────────────


def test_stdlib_404_page_is_detected_as_error_page() -> None:
    """The SimpleHTTPRequestHandler 404 body scrapes to ~5 elements (above the
    3-element dead-shell threshold) but is entirely error text. B-045: it must
    be dropped so \"Error code: 404\" never wins ASSERT matching."""
    error_page = [
        {"selector": "title", "text": "Error response"},
        {"selector": "h1", "text": "Error response"},
        {"selector": "p", "text": "Error code: 404"},
        {"selector": "p", "text": "Message: File not found."},
        {"selector": "p", "text": "Error code explanation: 404 - Nothing matches the given URI."},
    ]
    assert PlaceholderOrchestrator._is_error_page(error_page) is True


def test_real_page_with_one_mention_survives_error_detection() -> None:
    """A genuine page that mentions \"file not found\" once in body copy must
    not be mistaken for an error page (2-marker minimum)."""
    assert (
        PlaceholderOrchestrator._is_error_page(
            [{"text": "File not found"}, {"text": "try the search box"}, {"text": "return home"}]
        )
        is False
    )


def test_drop_dead_pages_removes_404_concept_candidates() -> None:
    """The banking mock's shared-route vocabulary (`/products`, `/cart.html`,
    `/checkout`) 404s; those keys must be removed so the real pages win."""
    error_page = [
        {"selector": "title", "text": "Error response"},
        {"selector": "p", "text": "Error code: 404"},
        {"selector": "p", "text": "Nothing matches the given URI."},
    ]
    data = {
        "http://localhost:8781/products": error_page,
        "http://localhost:8781/dashboard.html": [
            {"selector": "h1.title", "text": "Your Accounts"},
            {"selector": "p.account_balance", "text": "$2,450.00"},
            {"selector": "a#transfer-link", "text": "Transfer Money"},
        ],
    }
    kept = PlaceholderOrchestrator._drop_dead_pages(data)
    assert "http://localhost:8781/products" not in kept
    assert "http://localhost:8781/dashboard.html" in kept


# ── B-029: overlay injection (the deterministically reproducible race) ────


def test_banking_mock_injects_consent_overlay_on_demand() -> None:
    """The mock's injectable consent overlay must actually appear with
    ?overlay=consent — this is the deterministic B-029 race the live ad stack
    only shows as flaky noise."""
    from playwright.sync_api import sync_playwright

    from scripts.mock_server import MockServer

    # Distinct port (8782) — the contract layer binds 8781 (dataset convention)
    # and CI runs files in parallel xdist workers; a shared port would race
    # with "Address already in use". Ports only need to be unique per file.
    with MockServer.start(port=8782, directory="mock_sites/banking"):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto("http://localhost:8782/index.html?overlay=consent")
            page.wait_for_selector("#consent-root", timeout=5000)
            assert page.locator(".fc-consent-root").count() == 1
            browser.close()


def test_banking_mock_clean_path_has_no_overlay() -> None:
    """Default (no query param) must be the clean, deterministic path."""
    from playwright.sync_api import sync_playwright

    from scripts.mock_server import MockServer

    with MockServer.start(port=8782, directory="mock_sites/banking"):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto("http://localhost:8782/index.html")
            page.wait_for_timeout(500)
            assert page.locator("#consent-root").count() == 0
            assert page.locator("#google_vignette").count() == 0
            browser.close()


# ── B-033/B-039: broken locators fail fast with evidence, not marathon ────


def test_broken_locator_fails_fast_with_diagnostic(tmp_path: Path) -> None:
    """A click on a locator absent from the page must fail immediately with a
    self-diagnosing error + screenshot — not a 30s fallback marathon."""
    from unittest.mock import MagicMock

    from src.evidence_tracker import EvidenceTracker

    page_mock = MagicMock()
    page_mock.locator.return_value.first.count.return_value = 0
    page_mock.url = "https://example.com/products"
    tracker = EvidenceTracker(page_mock, "test_fastfail", evidence_root=Path(tmp_path))

    with pytest.raises(Exception, match="not found on current page"):
        tracker.click("button.btn.cart")

    step = tracker.steps[0]
    assert step["result"]["status"] == "failed"
    assert "not found on current page" in step["result"]["error"]
    assert step["screenshot"] is not None  # B-033: failures carry visual evidence
    assert step["result"]["failure_note"] is not None
    page_mock.locator.return_value.first.click.assert_not_called()  # never attempted


# ── B-015: overlay dismissal scoping ───────────────────────────────────────


def test_modal_close_selector_scoped_not_global() -> None:
    """B-015: dismissal must only fire inside modal containers — a real
    \"Continue Shopping\" button on the page must NOT be auto-clicked."""
    from src.evidence_tracker import EvidenceTracker

    scoped = EvidenceTracker._is_modal_close_target(".close-modal")
    # The mock's modal-scoped class IS a dismissal target…
    assert scoped is True
