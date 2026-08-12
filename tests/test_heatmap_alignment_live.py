"""AI-043 Layer 3 live alignment — real chromium against the ecommerce mock.

Records element metadata for known elements of the deterministic ecommerce
mock using the *same document-relative percentage math the EvidenceTracker
writes to sidecars*, renders the suite heatmap, re-opens the live page, and
asserts every overlay box centre hits the element it claims.

Deterministic: localhost mock + local chromium, no LLM, no external network —
same convention as ``tests/adversarial/test_overlay_and_error_pages.py``
(contract layer binds 8781, adversarial 8782, this file 8783).

One browser is launched per module (module-scoped fixtures) — the Windows box
this suite runs on exhausts its paging file when every browser test launches
its own process under ``-n 4`` parallelism (WinError 1455), and the tests in
one file always run in a single xdist worker (``--dist=loadfile``).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, sync_playwright

from scripts.mock_server import MockServer
from src.evidence_tracker import EvidenceTracker
from src.heatmap_alignment import validate_heatmap_alignment

PORT = 8783
BASE = f"http://localhost:{PORT}/index.html"

#: Known elements of the ecommerce mock home page — deterministic targets.
TARGETS: list[tuple[str, str]] = [
    ("a[href='/products.html']", "products nav link"),
    ("button[data-product-id='1']", "add Blue Top to cart"),
    ("h2.price", "product 1 price"),
]


@pytest.fixture(scope="module")
def mock_site() -> Iterator[None]:
    with MockServer.start(port=PORT, directory="mock_sites/ecommerce"):
        yield


@pytest.fixture(scope="module")
def browser(mock_site: None) -> Browser:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


def _write_sidecar(evidence_dir: Path, steps: list[dict[str, object]]) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    sidecar = {
        "test": {
            "name": "test_align",
            "condition_ref": "TC-01",
            "story_ref": "S01",
            "status": "passed",
            "duration_s": 1.0,
        },
        "page": {"url": BASE},
        "steps": steps,
    }
    (evidence_dir / "test_align.evidence.json").write_text(json.dumps(sidecar))


def _capture_steps(tracker: EvidenceTracker) -> list[dict[str, object]]:
    """Capture real metadata for the target elements (production math)."""
    steps: list[dict[str, object]] = [
        {"type": "navigate", "value": BASE, "result": {"status": "passed", "run_count": 1}}
    ]
    for locator, label in TARGETS:
        meta = tracker._get_element_metadata(locator)  # noqa: SLF001
        assert meta.get("viewport_pct"), f"no viewport_pct captured for {locator!r}: {meta!r}"
        steps.append(
            {
                "type": "click",
                "label": label,
                "locator": locator,
                "element": meta,
                "result": {"status": "passed", "run_count": 1},
            }
        )
    return steps


def test_layer3_alignment_passes_against_live_mock(browser: Browser, tmp_path: Path) -> None:
    """Every overlay box centre must hit the element it claims on the live page."""
    page = browser.new_page(viewport={"width": 1280, "height": 720})
    try:
        page.goto(BASE, wait_until="load")
        tracker = EvidenceTracker(page, "test_align", test_package_dir=tmp_path)
        evidence_dir = tmp_path / "evidence"
        _write_sidecar(evidence_dir, _capture_steps(tracker))

        issues = validate_heatmap_alignment(evidence_dir, BASE, page=page)
        assert issues == [], f"overlay boxes misaligned: {[i.message for i in issues]}"
    finally:
        page.close()


def test_layer3_flags_stale_locator(browser: Browser, tmp_path: Path) -> None:
    """A recorded locator that no longer exists on the live page must error."""
    page = browser.new_page(viewport={"width": 1280, "height": 720})
    try:
        page.goto(BASE, wait_until="load")
        tracker = EvidenceTracker(page, "test_align", test_package_dir=tmp_path)
        good = _capture_steps(tracker)
        # A click on a product that does not exist on the mock.
        good.append(
            {
                "type": "click",
                "label": "add ghost product",
                "locator": "button[data-product-id='99']",
                "element": tracker._get_element_metadata("h2.price"),  # noqa: SLF001
                "result": {"status": "passed", "run_count": 1},
            }
        )
        evidence_dir = tmp_path / "evidence"
        _write_sidecar(evidence_dir, good)

        issues = validate_heatmap_alignment(evidence_dir, BASE, page=page)
        assert len(issues) == 1
        assert "not found" in issues[0].message
        assert "data-product-id='99'" in issues[0].message
    finally:
        page.close()


def test_layer3_flags_shifted_point_wrong_frame(browser: Browser, tmp_path: Path) -> None:
    """A box recorded against a different document position must miss the
    element it claims — the 'wrong frame' failure class."""
    page = browser.new_page(viewport={"width": 1280, "height": 720})
    try:
        page.goto(BASE, wait_until="load")
        tracker = EvidenceTracker(page, "test_align", test_package_dir=tmp_path)
        steps = _capture_steps(tracker)
        # Claim the products nav link, but place the box at the top-left
        # corner where the brand/home elements live.
        steps.append(
            {
                "type": "click",
                "label": "products link (shifted)",
                "locator": "a[href='/products.html']",
                "element": {"viewport_pct": {"x": 10.0, "y": 10.0}, "tag": "a"},
                "result": {"status": "passed", "run_count": 1},
            }
        )
        evidence_dir = tmp_path / "evidence"
        _write_sidecar(evidence_dir, steps)

        issues = validate_heatmap_alignment(evidence_dir, BASE, page=page)
        assert len(issues) == 1
        assert "NOT the claimed element" in issues[0].message
    finally:
        page.close()
