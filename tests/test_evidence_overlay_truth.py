"""The evidence overlay must tell the truth (B-105).

Four defects were found in the t-0838 scout pass and are pinned here:

1. the per-test viewer drew every step's marker on ONE background frame, so a
   marker landed on a different element than the step touched (-68px drift in
   the flagship demo);
2. the suite heatmap OVERWROTE the element it matched instead of merging into
   it, so an element hit by eight tests showed one hit and the status of the
   last hit only;
3. the URL bucket switched only on navigate steps, so the home page heatmap
   showed a products-page background and the products page got zero points;
4. a failed step was painted in the passing colour and a failed assertion got
   no marker at all.

Each test names the defect it pins, so a regression says which truth broke.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from src.artifact_validation import validate_suite_heatmap
from src.evidence_report import generate_annotated_screenshot
from src.heatmap_utils import generate_suite_heatmap

# A 1x1 PNG — the viewer only needs a real image file to embed.
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x1dIEND\xaeB`\x82"
)


def _payload(html: str, name: str) -> Any:
    """Return a JSON payload embedded in the rendered HTML."""
    match = re.search(rf"const {re.escape(name)} = (.*?);\n", html, re.DOTALL)
    assert match, f"payload {name!r} not found in the rendered HTML"
    return json.loads(match.group(1))


def _write_image(path: Path, marker: bytes = b"") -> Path:
    """Write a distinguishable image file and return it."""
    path.write_bytes(_PNG + marker)
    return path


def _data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("utf-8")


#: JS keywords and builtins that are never defined in the generated script.
_JS_BUILTINS = frozenset(
    {
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "return",
        "function",
        "typeof",
        "new",
        "do",
        "else",
        "try",
        "throw",
        "delete",
        "void",
        "await",
        "Array",
        "String",
        "Number",
        "Boolean",
        "Object",
        "Math",
        "JSON",
        "Date",
        "RegExp",
        "Error",
        "Map",
        "Set",
        "Promise",
        "parseFloat",
        "parseInt",
        "isNaN",
        "setTimeout",
        "setInterval",
        "ResizeObserver",
        # CSS functions that appear inside the generated style strings.
        "rgba",
        "rgb",
        "calc",
        "var",
        "url",
    }
)


def _script(html: str) -> str:
    """Return the inline script of the rendered HTML."""
    match = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    assert match, "the rendered HTML has no inline script"
    return match.group(1)


def _assert_no_undefined_helper(html: str) -> None:
    """Every helper the script calls must be defined in the same script.

    The suite heatmap's element table called ``escapeHtml()`` with no such
    function in the script: the table threw on the first render and never
    appeared. This check is what the browser render found.
    """
    script = _script(html)
    # Comments are not code ("free text (site copy)" is not a call). The ":"
    # guard keeps a URL inside a string from being read as a comment.
    script = re.sub(r"(?<!:)//[^\n]*", "", script)
    called = set(re.findall(r"(?<![.\w$-])([A-Za-z_$][\w$]*)\s*\(", script))
    defined = set(re.findall(r"function\s+([A-Za-z_$][\w$]*)\s*\(", script))
    missing = called - defined - _JS_BUILTINS
    assert not missing, f"the rendered script calls helpers it never defines: {sorted(missing)}"


def _sidecar(
    *,
    steps: list[dict[str, Any]],
    name: str = "test_example",
    status: str = "passed",
    page_url: str = "https://example.com/",
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "test": {"name": name, "condition_ref": "TC01.01", "story_ref": "S1", "status": status},
        "page": {"url": page_url},
        "run_history": {"total_runs": 1, "passed_runs": 1, "failed_runs": 0},
        "steps": steps,
    }


def _step(
    step_type: str,
    *,
    label: str = "step",
    locator: str | None = None,
    value: str | None = None,
    screenshot: str | None = None,
    pct: tuple[float, float] | None = None,
    doc: tuple[int, int] | None = None,
    url: str | None = None,
    frame_url: str | None = None,
    frame_doc: tuple[int, int] | None = None,
    status: str = "passed",
    error: str | None = None,
) -> dict[str, Any]:
    element: dict[str, Any] = {}
    if pct is not None:
        element["viewport_pct"] = {"x": pct[0], "y": pct[1]}
    if doc is not None:
        element["doc_width"] = doc[0]
        element["doc_height"] = doc[1]
    step: dict[str, Any] = {
        "step": 1,
        "type": step_type,
        "label": label,
        "locator": locator,
        "value": value,
        "screenshot": screenshot,
        "element": element,
        "url": url,
        "result": {"status": status, "run_count": 1, "error": error},
    }
    if frame_url is not None:
        step["frame_url"] = frame_url
    if frame_doc is not None:
        step["frame_doc_width"] = frame_doc[0]
        step["frame_doc_height"] = frame_doc[1]
    return step


# ---------------------------------------------------------------------------
# Defect 1 — the marker must sit on the frame it was measured in
# ---------------------------------------------------------------------------


def test_marker_is_drawn_on_the_frame_it_was_measured_in(tmp_path: Path) -> None:
    """A click measured on the home page is drawn on the home frame.

    The step's OWN screenshot is the page the click navigated TO, so the home
    frame is the only place its percentage means anything.
    """
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    home = _write_image(evidence / "home.png", b"home")
    products = _write_image(evidence / "products.png", b"products")
    sidecar = evidence / "test.evidence.json"
    sidecar.write_text(
        json.dumps(
            _sidecar(
                steps=[
                    _step(
                        "navigate",
                        label="Navigate to https://example.com/",
                        value="https://example.com/",
                        screenshot="evidence/home.png",
                        url="https://example.com/",
                        frame_url="https://example.com/",
                        frame_doc=(1280, 8604),
                    ),
                    _step(
                        "click",
                        label="Products",
                        locator='a[href="/products"]',
                        screenshot="evidence/products.png",
                        pct=(47.4, 0.45),
                        doc=(1280, 8604),
                        url="https://example.com/products",
                        frame_url="https://example.com/products",
                        frame_doc=(1280, 8304),
                    ),
                ]
            )
        ),
        encoding="utf-8",
    )

    html = generate_annotated_screenshot(sidecar_path=sidecar, view_mode="annotated", title="demo")

    markers = _payload(html, "markers")
    assert len(markers) == 1, "the click must have exactly one marker"
    frames = _payload(html, "frames")
    marker_frame = next(f for f in frames if f["id"] == markers[0]["frame"])
    assert marker_frame["label"] == "Frame 1 - captured at step 1 (navigate)"
    # The home frame is the one the marker belongs on.
    assert _data_uri(home) in html
    # The products frame carries no marker, so it is not rendered at all.
    assert _data_uri(products) not in html


def test_marker_is_not_drawn_on_a_frame_of_a_different_height(tmp_path: Path) -> None:
    """No frame matches the page the step was measured on -> no marker.

    This is the flagship-demo defect: the step was measured on an 8604px page
    and the viewer's background was 8304px, so the marker landed on a
    different card's button. A wrong marker is worse than no marker.
    """
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _write_image(evidence / "shot.png")
    sidecar = evidence / "evidence_sidecar.json"
    sidecar = evidence / "test.evidence.json"
    sidecar.write_text(
        json.dumps(
            _sidecar(
                steps=[
                    _step(
                        "assertion",
                        label="product list",
                        locator='a[href="/product_details/11"]',
                        screenshot="evidence/shot.png",
                        pct=(84.5, 22.8),
                        doc=(1280, 8604),
                        url="https://example.com/products",
                        frame_url="https://example.com/products",
                        frame_doc=(1280, 8304),
                    )
                ]
            )
        ),
        encoding="utf-8",
    )

    html = generate_annotated_screenshot(sidecar_path=sidecar, view_mode="annotated", title="demo")

    assert _payload(html, "markers") == []
    assert "no captured frame shows the page this step was measured on" in html


def test_each_step_gets_its_own_frame(tmp_path: Path) -> None:
    """Two steps measured on two pages are drawn on two frames."""
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _write_image(evidence / "a.png", b"a")
    _write_image(evidence / "b.png", b"b")
    sidecar = evidence / "test.evidence.json"
    sidecar.write_text(
        json.dumps(
            _sidecar(
                steps=[
                    _step(
                        "assertion",
                        label="first",
                        locator="#one",
                        screenshot="evidence/a.png",
                        pct=(10.0, 20.0),
                        doc=(1280, 1000),
                        url="https://example.com/",
                        frame_url="https://example.com/",
                        frame_doc=(1280, 1000),
                    ),
                    _step(
                        "assertion",
                        label="second",
                        locator="#two",
                        screenshot="evidence/b.png",
                        pct=(30.0, 40.0),
                        doc=(1280, 2000),
                        url="https://example.com/",
                        frame_url="https://example.com/",
                        frame_doc=(1280, 2000),
                    ),
                ]
            )
        ),
        encoding="utf-8",
    )

    html = generate_annotated_screenshot(sidecar_path=sidecar, view_mode="annotated", title="demo")

    markers = _payload(html, "markers")
    assert len(markers) == 2
    assert markers[0]["frame"] != markers[1]["frame"]
    frames = _payload(html, "frames")
    labels = {f["id"]: f["label"] for f in frames}
    assert labels[markers[0]["frame"]] == "Frame 1 - captured at step 1 (assertion)"
    assert labels[markers[1]["frame"]] == "Frame 2 - captured at step 2 (assertion)"


# ---------------------------------------------------------------------------
# Defect 4 — failure must be visible on the picture
# ---------------------------------------------------------------------------


def test_failed_step_is_painted_in_the_failure_colour(tmp_path: Path) -> None:
    """A failed click is not painted in the passing click blue."""
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _write_image(evidence / "shot.png")
    sidecar = evidence / "test.evidence.json"
    sidecar.write_text(
        json.dumps(
            _sidecar(
                status="failed",
                steps=[
                    _step(
                        "click",
                        label="Add to cart",
                        locator="#add",
                        screenshot="evidence/shot.png",
                        pct=(50.0, 30.0),
                        doc=(1280, 1000),
                        url="https://example.com/",
                        frame_url="https://example.com/",
                        frame_doc=(1280, 1000),
                        status="failed",
                        error="Timeout 5000ms exceeded",
                    )
                ],
            )
        ),
        encoding="utf-8",
    )

    html = generate_annotated_screenshot(sidecar_path=sidecar, view_mode="annotated", title="demo")

    markers = _payload(html, "markers")
    assert len(markers) == 1
    assert markers[0]["failed"] is True
    assert markers[0]["status"] == "failed"
    # The renderer paints a failed marker with the status red, not the type blue.
    assert "STATUS_COLORS.failed" in html
    assert "markerColor(marker)" in html


def test_failed_assertion_without_a_position_gets_a_visible_failure_marker(tmp_path: Path) -> None:
    """A failed assertion has no geometry, so it gets a ribbon, not a circle.

    The picture must still say the step failed — the reader must not have to
    read the timeline to learn the test failed.
    """
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _write_image(evidence / "shot.png")
    sidecar = evidence / "test.evidence.json"
    sidecar.write_text(
        json.dumps(
            _sidecar(
                status="failed",
                steps=[
                    _step(
                        "assertion",
                        label="newsletter subscribed",
                        locator="#success-subscribe",
                        screenshot="evidence/shot.png",
                        url="https://example.com/",
                        frame_url="https://example.com/",
                        frame_doc=(1280, 1000),
                        status="failed",
                        error="Timeout 5000ms exceeded",
                    )
                ],
            )
        ),
        encoding="utf-8",
    )

    html = generate_annotated_screenshot(sidecar_path=sidecar, view_mode="annotated", title="demo")

    assert _payload(html, "markers") == []
    assert "Step 1 failed - no element position was recorded" in html
    assert "this step failed before the element was located" in html


# ---------------------------------------------------------------------------
# Defect 2 — the heatmap aggregation must merge, not overwrite
# ---------------------------------------------------------------------------


def test_suite_heatmap_merges_hits_instead_of_overwriting(tmp_path: Path) -> None:
    """Three tests, one element, two passes and one failure -> 3 hits."""
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _write_image(evidence / "shot.png")
    for index, status in enumerate(("passed", "passed", "failed")):
        sidecar = {
            "schema_version": "1.0",
            "test": {"name": f"test_{index}", "status": status},
            "page": {"url": "https://example.com/products"},
            "steps": [
                {
                    "type": "navigate",
                    "value": "https://example.com/products",
                    "screenshot": "evidence/shot.png",
                    "url": "https://example.com/products",
                    "result": {"status": "passed", "run_count": 1},
                },
                {
                    "type": "click",
                    "label": "Add to cart",
                    "locator": ".add-to-cart",
                    "screenshot": "evidence/shot.png",
                    "url": "https://example.com/products",
                    "element": {"viewport_pct": {"x": 40.0 + index * 0.5, "y": 60.0}},
                    "result": {"status": status, "run_count": 1},
                },
            ],
        }
        (evidence / f"test_{index}.evidence.json").write_text(json.dumps(sidecar), encoding="utf-8")

    html = generate_suite_heatmap(evidence_dir=evidence, page_url="https://example.com/products")

    aggregated = _payload(html, "aggregated")
    assert len(aggregated) == 1, "the three hits are one element"
    element = aggregated[0]
    assert element["total"] == 3
    assert element["passed"] == 2
    assert element["failed"] == 1
    # The element passed twice and failed once: it passed.
    assert element["dominant_status"] == "passed"

    # The shipped validator must certify this heatmap (it used to certify a
    # heatmap whose counts were wrong).
    assert validate_suite_heatmap(evidence, "https://example.com/products") == []


def test_suite_heatmap_a_tie_keeps_the_worse_status(tmp_path: Path) -> None:
    """One pass and one failure -> the element reads as failed."""
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    for index, status in enumerate(("passed", "failed")):
        sidecar = {
            "schema_version": "1.0",
            "test": {"name": f"test_{index}", "status": status},
            "page": {"url": "https://example.com/products"},
            "steps": [
                {
                    "type": "click",
                    "label": "Add to cart",
                    "locator": ".add-to-cart",
                    "screenshot": None,
                    "url": "https://example.com/products",
                    "element": {"viewport_pct": {"x": 40.0, "y": 60.0}},
                    "result": {"status": status, "run_count": 1},
                }
            ],
        }
        (evidence / f"test_{index}.evidence.json").write_text(json.dumps(sidecar), encoding="utf-8")

    html = generate_suite_heatmap(evidence_dir=evidence, page_url="https://example.com/products")

    aggregated = _payload(html, "aggregated")
    assert len(aggregated) == 1
    assert aggregated[0]["total"] == 2
    assert aggregated[0]["dominant_status"] == "failed"


# ---------------------------------------------------------------------------
# Defect 3 — the URL bucket follows the step, not the navigation
# ---------------------------------------------------------------------------


def test_suite_heatmap_attributes_each_step_to_its_own_page(tmp_path: Path) -> None:
    """A click that navigates stays on the page it was measured on.

    The old code only switched the bucket on a navigate step, so every point
    landed on the home page and the products page showed nothing.
    """
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    home = _write_image(evidence / "home.png", b"home")
    products = _write_image(evidence / "products.png", b"products")
    sidecar = {
        "schema_version": "1.0",
        "test": {"name": "test_1", "status": "passed"},
        "page": {"url": "https://example.com/"},
        "steps": [
            {
                "type": "navigate",
                "label": "Navigate to https://example.com/",
                "value": "https://example.com/",
                "screenshot": "evidence/home.png",
                "url": "https://example.com/",
                "frame_url": "https://example.com/",
                "frame_doc_width": 1280,
                "frame_doc_height": 4000,
                "element": {},
                "result": {"status": "passed", "run_count": 1},
            },
            {
                "type": "click",
                "label": "Products",
                "locator": 'a[href="/products"]',
                "screenshot": "evidence/products.png",
                "url": "https://example.com/products",
                "frame_url": "https://example.com/products",
                "frame_doc_width": 1280,
                "frame_doc_height": 8000,
                "element": {
                    "viewport_pct": {"x": 47.4, "y": 0.45},
                    "doc_width": 1280,
                    "doc_height": 4000,
                },
                "result": {"status": "passed", "run_count": 1},
            },
            {
                "type": "assertion",
                "label": "products visible",
                "locator": ".product",
                "screenshot": "evidence/products.png",
                "url": "https://example.com/products",
                "frame_url": "https://example.com/products",
                "frame_doc_width": 1280,
                "frame_doc_height": 8000,
                "element": {
                    "viewport_pct": {"x": 20.0, "y": 30.0},
                    "doc_width": 1280,
                    "doc_height": 8000,
                },
                "result": {"status": "passed", "run_count": 1},
            },
        ],
    }
    (evidence / "test_1.evidence.json").write_text(json.dumps(sidecar), encoding="utf-8")

    home_html = generate_suite_heatmap(evidence_dir=evidence, page_url="https://example.com/")
    products_html = generate_suite_heatmap(evidence_dir=evidence, page_url="https://example.com/products")

    home_points = _payload(home_html, "allPoints")
    products_points = _payload(products_html, "allPoints")

    # The click was measured on the home page -> it belongs to the home page.
    assert [p["type"] for p in home_points if not p.get("arrival")] == ["click"]
    # The products page gets the products-page assertion, not nothing.
    assert [p["type"] for p in products_points if not p.get("arrival")] == ["assertion"]

    # Each page is drawn on its own frame.
    assert _data_uri(home) in home_html
    assert _data_uri(products) not in home_html
    assert _data_uri(products) in products_html


def test_suite_heatmap_does_not_draw_a_point_from_another_page_layout(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _write_image(evidence / "shot.png")
    sidecar = {
        "schema_version": "1.0",
        "test": {"name": "test_1", "status": "passed"},
        "page": {"url": "https://example.com/products"},
        "steps": [
            {
                "type": "assertion",
                "label": "before the modal",
                "locator": "#one",
                "screenshot": "evidence/shot.png",
                "url": "https://example.com/products",
                "frame_url": "https://example.com/products",
                "frame_doc_width": 1280,
                "frame_doc_height": 8000,
                "element": {
                    "viewport_pct": {"x": 10.0, "y": 20.0},
                    "doc_width": 1280,
                    "doc_height": 4000,
                },
                "result": {"status": "passed", "run_count": 1},
            },
            {
                "type": "assertion",
                "label": "in the modal",
                "locator": "#two",
                "screenshot": "evidence/shot.png",
                "url": "https://example.com/products",
                "frame_url": "https://example.com/products",
                "frame_doc_width": 1280,
                "frame_doc_height": 8600,
                "element": {
                    "viewport_pct": {"x": 30.0, "y": 40.0},
                    "doc_width": 1280,
                    "doc_height": 8600,
                },
                "result": {"status": "passed", "run_count": 1},
            },
        ],
    }
    (evidence / "test_1.evidence.json").write_text(json.dumps(sidecar), encoding="utf-8")

    html = generate_suite_heatmap(evidence_dir=evidence, page_url="https://example.com/products")

    plotted = _payload(html, "plottedPoints")
    assert len(plotted) == 1
    assert plotted[0]["label"] == "in the modal"
    assert "Not drawn: 1" in html
    # The validator must not certify a heatmap that dropped a point.
    assert validate_suite_heatmap(evidence, "https://example.com/products") == []


# ---------------------------------------------------------------------------
# The rendered script must actually run
# ---------------------------------------------------------------------------


def test_suite_heatmap_script_defines_every_helper_it_calls(tmp_path: Path) -> None:
    """The element table's escape helper must exist.

    It did not: the table threw on the first render and never appeared, so the
    counts the reader needed were never on the page. Found by rendering the
    shipped heatmap in a browser.
    """
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    sidecar = {
        "schema_version": "1.0",
        "test": {"name": "test_1", "status": "passed"},
        "page": {"url": "https://example.com/products"},
        "steps": [
            {
                "type": "click",
                "label": "Add to cart",
                "locator": ".add-to-cart",
                "screenshot": None,
                "url": "https://example.com/products",
                "element": {"viewport_pct": {"x": 40.0, "y": 60.0}},
                "result": {"status": "passed", "run_count": 1},
            }
        ],
    }
    (evidence / "test_1.evidence.json").write_text(json.dumps(sidecar), encoding="utf-8")

    html = generate_suite_heatmap(evidence_dir=evidence, page_url="https://example.com/products")

    _assert_no_undefined_helper(html)
    assert "escapeHtml(locator)" in html


def test_viewer_script_defines_every_helper_it_calls(tmp_path: Path) -> None:
    """The viewer's script must run: every helper it calls is defined."""
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _write_image(evidence / "shot.png")
    sidecar = evidence / "test.evidence.json"
    sidecar.write_text(
        json.dumps(
            _sidecar(
                steps=[
                    _step(
                        "click",
                        label="Add to cart",
                        locator="#add",
                        screenshot="evidence/shot.png",
                        pct=(50.0, 30.0),
                        doc=(1280, 1000),
                        url="https://example.com/",
                        frame_url="https://example.com/",
                        frame_doc=(1280, 1000),
                    )
                ]
            )
        ),
        encoding="utf-8",
    )

    html = generate_annotated_screenshot(sidecar_path=sidecar, view_mode="annotated", title="demo")

    _assert_no_undefined_helper(html)
