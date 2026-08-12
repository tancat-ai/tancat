"""Unit tests for ``src/heatmap_alignment.py`` (AI-043 Layer 3 — offline).

The decision logic (extract → map → classify → check) is pure and tested here
with a scriptable fake page; the real-browser contract lives in
``tests/test_heatmap_alignment_live.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.heatmap_alignment import (
    HeatmapPoint,
    check_point_alignment,
    classify_point,
    extract_points,
    point_to_document_px,
    validate_heatmap_alignment,
)
from src.heatmap_utils import generate_suite_heatmap

URL = "https://example.com/page1"


def _sidecar(steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "test": {
            "name": "test_align",
            "condition_ref": "TC-01",
            "story_ref": "S01",
            "status": "passed",
            "duration_s": 1.0,
        },
        "page": {"url": URL},
        "steps": steps,
    }


def _nav_step() -> dict[str, Any]:
    return {"type": "navigate", "value": URL, "result": {"status": "passed", "run_count": 1}}


def _point_step(
    locator: str,
    x: float,
    y: float,
    *,
    type_: str = "click",
    element_id: str = "submit-btn",
    tag: str = "button",
    status: str = "passed",
) -> dict[str, Any]:
    return {
        "type": type_,
        "label": locator,
        "locator": locator,
        "element": {"viewport_pct": {"x": x, "y": y}, "element_id": element_id, "tag": tag},
        "result": {"status": status, "run_count": 1},
    }


def _write_sidecar(evidence_dir: Path, steps: list[dict[str, Any]]) -> Path:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / "test_align.evidence.json"
    path.write_text(json.dumps(_sidecar(steps)))
    return path


# ---------------------------------------------------------------------------
# Fake browser surface
# ---------------------------------------------------------------------------


class _FakeElementHandle:
    """Stand-in for the locator's claimed element — not needed for hit checks
    anymore, kept for clarity of the locator surface."""

    def __init__(self, tag: str = "button", el_id: str | None = "submit") -> None:
        self.tag = tag
        self.el_id = el_id

    def evaluate(self, expr: str) -> str:  # noqa: ARG002
        return self.tag

    def get_attribute(self, name: str) -> str | None:
        return self.el_id if name == "id" else None


class _FakeLocator:
    def __init__(
        self,
        *,
        count: int = 1,
        box: dict[str, float] | None = None,
        claimed: _FakeElementHandle | None = None,
        hit_desc: str | None = None,
        related: bool = True,
    ) -> None:
        self._count = count
        self._box = box
        self._claimed = claimed
        self._hit_desc = hit_desc
        self._related = related

    @property
    def first(self) -> _FakeLocator:
        return self

    def count(self) -> int:
        return self._count

    def bounding_box(self) -> dict[str, float] | None:
        return self._box

    def element_handle(self) -> _FakeElementHandle:
        assert self._claimed is not None
        return self._claimed

    def evaluate(self, expr: str, arg: Any = None) -> dict[str, Any]:  # noqa: ARG002
        return {"hit": self._hit_desc, "related": self._related}


class _FakePage:
    """Scriptable Playwright page: dispatch on the JS expression string."""

    def __init__(
        self,
        *,
        locators: dict[str, _FakeLocator],
        doc: tuple[float, float] = (1280.0, 800.0),
        scroll: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        self.locators = locators
        self.doc = doc
        self.scroll = scroll

    def locator(self, selector: str) -> _FakeLocator:
        return self.locators.get(selector, _FakeLocator(count=0, box=None))

    def evaluate(self, expr: str, arg: Any = None) -> Any:  # noqa: ARG002
        if "scrollTo" in expr:
            return {"sx": self.scroll[0], "sy": self.scroll[1]}
        if "scrollWidth" in expr:
            return {"w": self.doc[0], "h": self.doc[1]}
        if "scrollX" in expr:
            return {"x": self.scroll[0], "y": self.scroll[1]}
        return None


def _passing_page() -> _FakePage:
    """A page where a ``#submit-btn`` at (40, 60) is present and hit."""
    return _FakePage(
        locators={
            "#submit-btn": _FakeLocator(
                count=1,
                box={"x": 400.0, "y": 400.0, "width": 112.0, "height": 80.0},
                claimed=_FakeElementHandle(tag="button", el_id="submit"),
                hit_desc="button#submit",
                related=True,
            )
        }
    )


def _click_point(x: float = 40.0, y: float = 60.0) -> HeatmapPoint:
    return HeatmapPoint(
        type="click",
        x=x,
        y=y,
        run_count=1,
        status="passed",
        locator="#submit-btn",
        label="Submit",
        element_id="submit-btn",
        tag="button",
    )


# ---------------------------------------------------------------------------
# extract_points
# ---------------------------------------------------------------------------


class TestExtractPoints:
    def test_parses_generated_heatmap_payload(self, tmp_path: Path) -> None:
        _write_sidecar(
            tmp_path,
            [_nav_step(), _point_step("#submit-btn", 40.0, 60.0), _point_step("#cart-link", 80.0, 20.0)],
        )
        html = generate_suite_heatmap(evidence_dir=tmp_path, page_url=URL)
        points = extract_points(html)

        # navigate marker + 2 click points
        assert [p.type for p in points] == ["navigate", "click", "click"]
        submit = next(p for p in points if p.locator == "#submit-btn")
        assert submit.x == 40.0 and submit.y == 60.0
        assert submit.element_id == "submit-btn"
        assert submit.tag == "button"
        assert submit.status == "passed"
        assert submit.run_count == 1

    def test_empty_when_no_payload(self) -> None:
        assert extract_points("<div>nothing here</div>") == []

    def test_empty_when_unparseable_payload(self) -> None:
        assert extract_points("const allPoints = not-json;\n") == []

    def test_skips_junk_entries(self) -> None:
        html = 'const allPoints = [{"x": 1, "y": 2, "type": "click"}, "junk", {"x": "bad", "y": 3, "type": "click"}];\n'
        points = extract_points(html)
        assert len(points) == 1
        assert points[0].x == 1.0 and points[0].y == 2.0


# ---------------------------------------------------------------------------
# point_to_document_px / classify_point
# ---------------------------------------------------------------------------


class TestPureMapping:
    def test_percent_to_document_pixels(self) -> None:
        point = _click_point(x=50.0, y=25.0)
        px, py = point_to_document_px(point, 1280.0, 800.0)
        assert (px, py) == (640.0, 200.0)

    def test_edge_positions(self) -> None:
        top_left = point_to_document_px(_click_point(x=0.0, y=0.0), 1280.0, 800.0)
        bottom_right = point_to_document_px(_click_point(x=100.0, y=100.0), 1280.0, 800.0)
        assert top_left == (0.0, 0.0)
        assert bottom_right == (1280.0, 800.0)


class TestClassifyPoint:
    def test_navigate_points_are_skipped(self) -> None:
        point = HeatmapPoint("navigate", 50.0, 50.0, 1, "passed", "", "", "", "")
        assert classify_point(point) == "skip"

    def test_no_locator_is_skipped(self) -> None:
        point = HeatmapPoint("assertion", 10.0, 10.0, 1, "passed", "", "visible?", "", "")
        assert classify_point(point) == "skip"

    def test_locator_carrying_point_is_checked(self) -> None:
        assert classify_point(_click_point()) == "check"


# ---------------------------------------------------------------------------
# check_point_alignment
# ---------------------------------------------------------------------------


class TestCheckPointAlignment:
    def test_skip_kind_for_navigate_point(self) -> None:
        point = HeatmapPoint("navigate", 50.0, 50.0, 1, "passed", "", "", "", "")
        check = check_point_alignment(point, page=_passing_page(), doc_size=(1280.0, 800.0))
        assert check.kind == "skip"

    def test_missing_locator_fails(self) -> None:
        page = _FakePage(locators={})
        check = check_point_alignment(_click_point(), page=page, doc_size=(1280.0, 800.0))
        assert check.kind == "fail"
        assert "not found" in check.detail

    def test_hidden_locator_fails(self) -> None:
        page = _FakePage(locators={"#submit-btn": _FakeLocator(count=1, box=None)})
        check = check_point_alignment(_click_point(), page=page, doc_size=(1280.0, 800.0))
        assert check.kind == "fail"
        assert "bounding box" in check.detail

    def test_contained_hit_passes(self) -> None:
        check = check_point_alignment(_click_point(), page=_passing_page(), doc_size=(1280.0, 800.0))
        assert check.kind == "pass"
        assert check.hit_element == "button#submit"
        assert check.target_px == (512.0, 480.0)  # 40% * 1280, 60% * 800

    def test_unrelated_hit_fails_as_wrong_frame(self) -> None:
        page = _FakePage(
            locators={
                "#submit-btn": _FakeLocator(
                    count=1,
                    box={"x": 400.0, "y": 400.0, "width": 112.0, "height": 80.0},
                    claimed=_FakeElementHandle(tag="button", el_id="submit"),
                    hit_desc="div#ad-overlay",
                    related=False,
                )
            }
        )
        check = check_point_alignment(_click_point(), page=page, doc_size=(1280.0, 800.0))
        assert check.kind == "fail"
        assert "ad-overlay" in check.detail
        assert "wrong frame" in check.detail

    def test_off_page_after_scroll_fails(self) -> None:
        # Point at 100% height of an 800px page with an unclamped scroll → the
        # centre lands at vy=800, outside a 720px viewport.
        page = _FakePage(
            locators={
                "#submit-btn": _FakeLocator(
                    count=1,
                    box={"x": 400.0, "y": 750.0, "width": 112.0, "height": 50.0},
                    claimed=_FakeElementHandle(),
                    hit_desc="button#submit",
                    related=True,
                )
            },
            scroll=(0.0, 0.0),
        )
        check = check_point_alignment(
            _click_point(x=50.0, y=100.0), page=page, doc_size=(1280.0, 800.0), viewport=(1280, 720)
        )
        assert check.kind == "fail"
        assert "outside the viewport" in check.detail


# ---------------------------------------------------------------------------
# validate_heatmap_alignment (orchestration)
# ---------------------------------------------------------------------------


class TestValidateHeatmapAlignment:
    def test_clean_when_all_points_align(self, tmp_path: Path) -> None:
        _write_sidecar(
            tmp_path,
            [
                _nav_step(),
                _point_step("#submit-btn", 40.0, 60.0),
                _point_step("#cart-link", 80.0, 20.0, element_id="cart-link", tag="a"),
            ],
        )
        page = _FakePage(
            locators={
                "#submit-btn": _FakeLocator(
                    count=1,
                    box={"x": 400.0, "y": 400.0, "width": 112.0, "height": 80.0},
                    claimed=_FakeElementHandle(tag="button", el_id="submit"),
                    hit_desc="a#cart-link",
                    related=True,
                ),
                "#cart-link": _FakeLocator(
                    count=1,
                    box={"x": 900.0, "y": 100.0, "width": 124.0, "height": 60.0},
                    claimed=_FakeElementHandle(tag="a", el_id="cart-link"),
                    hit_desc="a#cart-link",
                    related=True,
                ),
            }
        )
        issues = validate_heatmap_alignment(tmp_path, URL, page=page)
        assert issues == []

    def test_stale_locator_produces_error(self, tmp_path: Path) -> None:
        _write_sidecar(
            tmp_path,
            [_nav_step(), _point_step("#submit-btn", 40.0, 60.0), _point_step("#ghost", 10.0, 10.0)],
        )
        page = _FakePage(
            locators={
                "#submit-btn": _FakeLocator(
                    count=1,
                    box={"x": 400.0, "y": 400.0, "width": 112.0, "height": 80.0},
                    claimed=_FakeElementHandle(),
                    hit_desc="button#submit",
                    related=True,
                )
            }
        )
        issues = validate_heatmap_alignment(tmp_path, URL, page=page)
        assert len(issues) == 1
        assert issues[0].artifact == "heatmap-alignment"
        assert issues[0].severity == "error"
        assert "#ghost" in issues[0].message

    def test_no_evidence_returns_no_issues(self, tmp_path: Path) -> None:
        _write_sidecar(tmp_path, [_nav_step()])
        issues = validate_heatmap_alignment(tmp_path, URL, page=_passing_page())
        assert issues == []
