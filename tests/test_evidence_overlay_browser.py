"""The rendered overlay must be right in a real browser (B-105, t-0844).

The static tests cannot see a JavaScript bug. These two bugs were found by
rendering the shipped report in headless Chromium and are pinned here:

- both the annotated viewer and the suite heatmap used fixed element ids, so
  the second instance in a document found the first instance's elements and
  drew its own markers on the wrong frames (and overwrote its timeline);
- the frames were laid out at their full height, so a report with one overlay
  per test grew from 4,000 px to 35,000 px.

Chromium is skipped when it is not installed; the CI test job installs it.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, sync_playwright

from src.evidence_report import generate_annotated_screenshot
from src.heatmap_utils import generate_suite_heatmap
from src.report_formatters import generate_html_report

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x1dIEND\xaeB`\x82"
)


@pytest.fixture(scope="module")
def browser() -> Generator[Browser]:
    with sync_playwright() as p:
        try:
            instance = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - environment dependent
            pytest.skip(f"chromium is not available: {exc}")
        yield instance
        instance.close()


def _sidecar(name: str, url: str, label: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "test": {"name": name, "condition_ref": "TC01.01", "story_ref": "S1", "status": "passed"},
        "page": {"url": url},
        "run_history": {"total_runs": 1, "passed_runs": 1, "failed_runs": 0},
        "steps": [
            {
                "step": 1,
                "type": "navigate",
                "label": f"Navigate to {url}",
                "value": url,
                "screenshot": f"evidence/{name}.png",
                "element": {},
                "url": url,
                "frame_url": url,
                "frame_doc_width": 1280,
                "frame_doc_height": 900,
                "result": {"status": "passed", "run_count": 1},
            },
            {
                "step": 2,
                "type": "click",
                "label": label,
                "locator": "#add",
                "screenshot": f"evidence/{name}.png",
                "element": {
                    "viewport_pct": {"x": 40.0, "y": 60.0},
                    "doc_width": 1280,
                    "doc_height": 900,
                },
                "url": url,
                "frame_url": url,
                "frame_doc_width": 1280,
                "frame_doc_height": 900,
                "result": {"status": "passed", "run_count": 1},
            },
        ],
    }


def _package(tmp_path: Path) -> Path:
    package = tmp_path / "package"
    evidence = package / "evidence"
    evidence.mkdir(parents=True)
    for name, url, label in (
        ("test_alpha", "https://example.com/", "Alpha button"),
        ("test_beta", "https://example.com/products", "Beta button"),
    ):
        (evidence / f"{name}.evidence.json").write_text(json.dumps(_sidecar(name, url, label)), encoding="utf-8")
        (evidence / f"{name}.png").write_bytes(_PNG)
    return package


def _rows(names: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        {
            "test_name": f"criterion for {name}",
            "status": "passed",
            "tc_id": "TC01.01",
            "story_ref": "S1",
            "expected_locators": [name],
            "duration": 1.0,
            "screenshots": [],
            "screenshot_paths": [],
            "verification": {},
        }
        for name in names
    ]


def test_each_overlay_draws_only_its_own_markers(tmp_path: Path, browser: Browser) -> None:
    """Two overlays in one document must not draw on each other's frames."""
    package = _package(tmp_path)
    html = generate_html_report(_rows(("test_alpha", "test_beta")), screenshots_dir=package, title="demo")
    page_file = tmp_path / "report.html"
    page_file.write_text(html, encoding="utf-8")

    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(page_file.as_uri())
    page.wait_for_timeout(800)

    markers = page.eval_on_selector_all(
        "svg.ev-svg g.point-group title",
        "els => els.map(e => e.textContent)",
    )
    assert sorted(markers) == ["Alpha button (status: passed)", "Beta button (status: passed)"], (
        f"each overlay must carry only its own marker, got {markers}"
    )

    # Each viewer keeps its own timeline.
    timelines = page.eval_on_selector_all(
        ".ev-timeline [data-step-id]",
        "els => els.map(e => e.textContent.trim().slice(0, 40))",
    )
    assert len(timelines) == 4, "each viewer must keep its own step list"

    assert not errors, f"the report threw in the browser: {errors}"
    page.close()


def test_each_heatmap_draws_only_its_own_circles(tmp_path: Path, browser: Browser) -> None:
    """Two heatmaps in one document must not share their circles or table."""
    package = _package(tmp_path)
    html = generate_html_report(_rows(("test_alpha", "test_beta")), screenshots_dir=package, title="demo")
    page_file = tmp_path / "report.html"
    page_file.write_text(html, encoding="utf-8")

    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(page_file.as_uri())
    page.wait_for_timeout(800)

    heatmaps = page.eval_on_selector_all(
        ".suite-heatmap",
        """els => els.map(e => ({
            circles: e.querySelectorAll("svg.suite-svg g.point-group").length,
            rows: e.querySelectorAll(".element-table-body tr").length,
            url: e.querySelector("div") ? e.querySelector("div").textContent : "",
        }))""",
    )
    assert len(heatmaps) == 2, "the report must carry one heatmap per page"
    for heatmap in heatmaps:
        assert heatmap["circles"] >= 1, "a heatmap must draw its circles"
        assert heatmap["rows"] >= 1, "a heatmap must fill its element table"

    assert not errors, f"the report threw in the browser: {errors}"
    page.close()


def test_the_report_page_stays_a_readable_length(tmp_path: Path, browser: Browser) -> None:
    """One overlay per test must not stretch the report to tens of thousands of px.

    The frames are full-page captures, so each one sits in a fixed-height
    scroll box: the report stays a document the reader can scan.
    """
    package = _package(tmp_path)
    html = generate_html_report(_rows(("test_alpha", "test_beta")), screenshots_dir=package, title="demo")
    page_file = tmp_path / "report.html"
    page_file.write_text(html, encoding="utf-8")

    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(page_file.as_uri())
    page.wait_for_timeout(800)
    height = page.evaluate("document.body.scrollHeight")

    assert height < 8000, f"the report page grew to {height}px - the frames are not in scroll boxes"
    page.close()


def test_the_viewer_renders_on_its_own(tmp_path: Path, browser: Browser) -> None:
    """A single viewer (the Evidence page case) draws its marker."""
    package = _package(tmp_path)
    html = generate_annotated_screenshot(
        sidecar_path=package / "evidence" / "test_alpha.evidence.json",
        title="test alpha",
    )
    page_file = tmp_path / "viewer.html"
    page_file.write_text(html, encoding="utf-8")

    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(page_file.as_uri())
    page.wait_for_timeout(800)

    markers = page.eval_on_selector_all("svg.ev-svg g.point-group title", "els => els.map(e => e.textContent)")
    assert markers == ["Alpha button (status: passed)"]
    assert not errors, f"the viewer threw in the browser: {errors}"
    page.close()


def test_the_heatmap_renders_on_its_own(tmp_path: Path, browser: Browser) -> None:
    """A single heatmap (the Evidence page case) draws its circles."""
    package = _package(tmp_path)
    html = generate_suite_heatmap(evidence_dir=package / "evidence", page_url="https://example.com/")
    page_file = tmp_path / "heatmap.html"
    page_file.write_text(html, encoding="utf-8")

    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(page_file.as_uri())
    page.wait_for_timeout(800)

    circles = page.eval_on_selector_all("svg.suite-svg g.point-group text", "els => els.map(e => e.textContent)")
    assert circles == ["1"], f"the heatmap must show the hit count, got {circles}"
    rows = page.eval_on_selector_all(".element-table-body tr", "els => els.length")
    assert rows == 1, "the element table must be filled"
    assert not errors, f"the heatmap threw in the browser: {errors}"
    page.close()
