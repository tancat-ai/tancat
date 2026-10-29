"""The evidence overlay must reach the customer (B-105, t-0844).

The overlay was library code with no production caller: the bundle's
report.html did not show it and the Evidence page did not show it. These
tests pin the wiring:

- the bundle's report carries the per-test annotated overlay and the per-URL
  suite heatmap;
- the report states its embed-size policy (previews, not the full capture)
  and names the full-resolution file behind every preview;
- two overlays (or two heatmaps) in one document do not share element ids,
  so one instance's script cannot draw on another's frames;
- the Evidence page renders both artifacts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from src.evidence_image import EMBED_PREVIEW_MAX_WIDTH
from src.evidence_report import generate_annotated_screenshot
from src.heatmap_utils import generate_suite_heatmap, list_evidence_urls
from src.report_formatters import generate_html_report

# A 1x1 PNG - the renderers only need a real image file to embed.
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x1dIEND\xaeB`\x82"
)


def _write_package(tmp_path: Path, *, names: tuple[str, ...] = ("test_alpha", "test_beta")) -> Path:
    """Write a package directory with one evidence sidecar per name."""
    package = tmp_path / "package"
    evidence = package / "evidence"
    evidence.mkdir(parents=True)
    for name in names:
        (evidence / f"{name}.evidence.json").write_text(
            json.dumps(_sidecar(name)),
            encoding="utf-8",
        )
        (evidence / f"{name}_0.png").write_bytes(_PNG)
    return package


def _sidecar(name: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "test": {"name": name, "condition_ref": "TC01.01", "story_ref": "S1", "status": "passed"},
        "page": {"url": "https://example.com/"},
        "run_history": {"total_runs": 1, "passed_runs": 1, "failed_runs": 0},
        "steps": [
            {
                "step": 1,
                "type": "navigate",
                "label": "Navigate to https://example.com/",
                "value": "https://example.com/",
                "screenshot": f"evidence/{name}_0.png",
                "element": {},
                "url": "https://example.com/",
                "frame_url": "https://example.com/",
                "frame_doc_width": 1280,
                "frame_doc_height": 900,
                "result": {"status": "passed", "run_count": 1},
            },
            {
                "step": 2,
                "type": "click",
                "label": "Add to cart",
                "locator": "#add",
                "screenshot": f"evidence/{name}_0.png",
                "element": {
                    "viewport_pct": {"x": 40.0, "y": 60.0},
                    "doc_width": 1280,
                    "doc_height": 900,
                },
                "url": "https://example.com/",
                "frame_url": "https://example.com/",
                "frame_doc_width": 1280,
                "frame_doc_height": 900,
                "result": {"status": "passed", "run_count": 1},
            },
        ],
    }


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


# ---------------------------------------------------------------------------
# The bundle's report.html
# ---------------------------------------------------------------------------


def test_bundle_report_carries_the_annotated_overlay(tmp_path: Path) -> None:
    """Every test with evidence gets its annotated overlay in the report."""
    package = _write_package(tmp_path, names=("test_alpha",))

    html = generate_html_report(_rows(("test_alpha",)), screenshots_dir=package, title="demo")

    assert "Annotated overlay" in html
    assert 'class="ev-viewer"' in html
    assert 'class="ev-frame"' in html
    assert "const markers =" in html
    # The marker payload carries the step that was marked.
    assert '"locator": "#add"' in html


def test_bundle_report_carries_the_suite_heatmap(tmp_path: Path) -> None:
    """The per-URL suite heatmap is in the report, with the true hit count."""
    package = _write_package(tmp_path, names=("test_alpha", "test_beta"))

    html = generate_html_report(_rows(("test_alpha", "test_beta")), screenshots_dir=package, title="demo")

    assert "Suite Heatmap" in html
    assert 'class="suite-heatmap"' in html
    # Both tests hit the same element, so the element reads two hits.
    aggregated_match = re.search(r"const aggregated = (.*?);\n", html, re.DOTALL)
    assert aggregated_match is not None, "the report carries no aggregated payload"
    aggregated = json.loads(aggregated_match.group(1))
    assert len(aggregated) == 1
    assert aggregated[0]["total"] == 2


def test_bundle_report_states_the_embed_policy_and_names_the_source_file(tmp_path: Path) -> None:
    """The report says what the images are, and which file each came from."""
    package = _write_package(tmp_path, names=("test_alpha",))

    html = generate_html_report(_rows(("test_alpha",)), screenshots_dir=package, title="demo")

    assert f"preview scaled to {EMBED_PREVIEW_MAX_WIDTH}px wide" in html
    assert "evidence/" in html
    # The full-resolution file behind the preview is named.
    assert "test_alpha_0.png" in html


def test_bundle_report_embeds_a_preview_not_the_full_capture(tmp_path: Path) -> None:
    """The embed is scaled down: the file the customer keeps stays small."""
    package = _write_package(tmp_path, names=("test_alpha",))
    source = package / "evidence" / "test_alpha_0.png"
    source.write_bytes(_PNG + b"x" * 4096)

    html = generate_html_report(_rows(("test_alpha",)), screenshots_dir=package, title="demo")

    uris = re.findall(r"data:image/webp;base64,([A-Za-z0-9+/=]+)", html)
    assert uris, "the report embeds no preview"
    embedded_bytes = sum(len(u) * 3 // 4 for u in uris)
    assert embedded_bytes < source.stat().st_size


# ---------------------------------------------------------------------------
# Two instances in one document must not share state
# ---------------------------------------------------------------------------


def test_two_overlays_in_one_document_do_not_share_element_ids(tmp_path: Path) -> None:
    """Each viewer's script must scope itself to its own block.

    Both viewers used the same element ids, so the first viewer's script drew
    its markers on the second viewer's frames and overwrote its timeline.
    """
    package = _write_package(tmp_path, names=("test_alpha", "test_beta"))

    html = generate_html_report(_rows(("test_alpha", "test_beta")), screenshots_dir=package, title="demo")

    roots = re.findall(r'id="(ev-viewer-[^"]+)"', html)
    assert len(roots) == 2
    assert roots[0] != roots[1]
    # Every viewer script reaches for its own root, not a shared id.
    for root in roots:
        assert f'document.getElementById("{root}")' in html
    assert 'document.getElementById("ev-timeline")' not in html
    assert 'document.getElementById("ev-frames")' not in html


def test_two_heatmaps_in_one_document_do_not_share_element_ids(tmp_path: Path) -> None:
    """Each heatmap's script must scope itself to its own block."""
    package = _write_package(tmp_path, names=("test_alpha",))
    evidence = package / "evidence"
    # A second page, so the package has two URLs to show.
    second = json.loads((evidence / "test_alpha.evidence.json").read_text(encoding="utf-8"))
    second["page"]["url"] = "https://example.com/products"
    second["steps"][0]["url"] = "https://example.com/products"
    second["steps"][0]["value"] = "https://example.com/products"
    second["steps"][0]["frame_url"] = "https://example.com/products"
    second["steps"][1]["url"] = "https://example.com/products"
    second["steps"][1]["frame_url"] = "https://example.com/products"
    (evidence / "test_gamma.evidence.json").write_text(json.dumps(second), encoding="utf-8")

    html = generate_html_report(
        _rows(("test_alpha", "test_gamma")),
        screenshots_dir=package,
        title="demo",
    )

    roots = re.findall(r'id="(suite-heat-[^"]+)"', html)
    assert len(roots) == 2
    assert roots[0] != roots[1]
    for root in roots:
        assert f'document.getElementById("{root}")' in html
    assert 'document.getElementById("suite-svg")' not in html
    assert 'document.getElementById("element-table-body")' not in html


# ---------------------------------------------------------------------------
# The Evidence page
# ---------------------------------------------------------------------------


def test_evidence_page_renders_the_overlay_and_the_suite_heatmap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Evidence page shows both artifacts."""
    from src.ui import ui_evidence

    package = _write_package(tmp_path, names=("test_alpha",))
    evidence = package / "evidence"

    calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(ui_evidence.st, "html", lambda body, **kw: calls.append((body, kw)))
    monkeypatch.setattr(ui_evidence.st, "caption", lambda *a, **k: None)
    monkeypatch.setattr(ui_evidence.st, "subheader", lambda *a, **k: None)
    monkeypatch.setattr(ui_evidence.st, "info", lambda *a, **k: None)
    monkeypatch.setattr(ui_evidence.st, "error", lambda *a, **k: None)
    monkeypatch.setattr(ui_evidence.st, "selectbox", lambda *a, **k: "https://example.com/")

    viewer = ui_evidence.EvidenceViewer(base_dir=tmp_path)
    viewer._render_annotated_overlay(evidence / "test_alpha.evidence.json", "test alpha")
    viewer._render_suite_heatmap(evidence)

    bodies = [body for body, _kw in calls]
    assert any('class="ev-viewer"' in body for body in bodies), "the overlay is not rendered"
    assert any('class="suite-heatmap"' in body for body in bodies), "the suite heatmap is not rendered"
    # The page scripts must run: Streamlit strips them unless asked not to.
    assert all(kw.get("unsafe_allow_javascript") is True for _body, kw in calls)


def test_list_evidence_urls_ranks_the_most_covered_page_first(tmp_path: Path) -> None:
    """The page list drives the heatmap picker."""
    package = _write_package(tmp_path, names=("test_alpha",))
    evidence = package / "evidence"
    second = json.loads((evidence / "test_alpha.evidence.json").read_text(encoding="utf-8"))
    second["page"]["url"] = "https://example.com/products"
    for step in second["steps"]:
        step["url"] = "https://example.com/products"
        step["frame_url"] = "https://example.com/products"
    (evidence / "test_gamma.evidence.json").write_text(json.dumps(second), encoding="utf-8")

    urls = list_evidence_urls(evidence)

    assert set(urls) == {"https://example.com/", "https://example.com/products"}
    assert urls[0] == "https://example.com/", "the home page carries the navigation point"


def test_suite_heatmap_preview_is_smaller_than_the_full_capture(tmp_path: Path) -> None:
    """The heatmap background is a preview too."""
    package = _write_package(tmp_path, names=("test_alpha",))
    evidence = package / "evidence"
    source = evidence / "test_alpha_0.png"
    source.write_bytes(_PNG + b"x" * 8192)

    full = generate_suite_heatmap(evidence_dir=evidence, page_url="https://example.com/")
    preview = generate_suite_heatmap(
        evidence_dir=evidence,
        page_url="https://example.com/",
        max_width=EMBED_PREVIEW_MAX_WIDTH,
    )

    assert len(preview) < len(full)


def test_annotated_overlay_preview_names_the_source_file(tmp_path: Path) -> None:
    """A preview says which file it came from."""
    package = _write_package(tmp_path, names=("test_alpha",))
    sidecar = package / "evidence" / "test_alpha.evidence.json"

    html = generate_annotated_screenshot(
        sidecar_path=sidecar,
        title="test alpha",
        max_width=EMBED_PREVIEW_MAX_WIDTH,
    )

    assert "previews scaled to 640px wide" in html
    assert "test_alpha_0.png" in html
