"""Heatmap overlay ↔ live-page alignment — AI-043 Layer 3.

Layer 1/2 validate the heatmap artifact's *internal* invariants (points are
document-relative percentages in [0, 100], payloads parse, aggregated counts
add up). Layer 3 validates the artifact against the **live page** it claims
to depict:

1. render the suite heatmap for a URL (the shipped artifact),
2. open the live page in a real browser,
3. for every overlay box, map its centre (``x%``, ``y%`` of the document) to
   document pixels using the live document size, scroll the point into view,
   and assert the element hit by ``document.elementFromPoint`` is the element
   the box claims — the locator recorded in the sidecar.

This catches the two production failure classes:

* **wrong frame** — the heatmap picks one background screenshot per URL; if
  the page changed between steps, earlier boxes sit on elements that moved.
  The centre no longer hits the claimed element.
* **stale locator** — the recorded locator no longer resolves on the live
  page (element renamed / removed / hidden).

The decision logic is pure and unit-tested offline; the browser check runs
against the deterministic mock sites in the integration test and against real
evidence dirs via ``scripts/validate_report_artifacts.py --full``.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.artifact_validation import ArtifactIssue, ArtifactValidationResult
from src.heatmap_utils import generate_suite_heatmap

#: Viewport used for the alignment browser session (matches the tracker's
#: default test run; the sidecar stores document-relative % so the exact
#: viewport does not change the mapping).
DEFAULT_VIEWPORT: tuple[int, int] = (1280, 720)

_NAVIGATE_MARKER = (50.0, 50.0)  # synthetic navigate points carry no element claim


@dataclass(frozen=True)
class HeatmapPoint:
    """One overlay box extracted from the rendered heatmap HTML payload."""

    type: str
    x: float  # % of document width
    y: float  # % of document height
    run_count: int
    status: str
    locator: str
    label: str
    element_id: str
    tag: str


@dataclass(frozen=True)
class AlignmentCheck:
    """Outcome of checking one overlay box against the live page."""

    point: HeatmapPoint
    kind: str  # "pass" | "fail" | "skip"
    detail: str
    target_px: tuple[float, float] | None = None
    hit_element: str | None = None
    distance_px: float | None = None


# ---------------------------------------------------------------------------
# Pure helpers (unit-testable offline)
# ---------------------------------------------------------------------------


def extract_points(heatmap_html: str) -> list[HeatmapPoint]:
    """Parse the ``allPoints`` payload embedded in the heatmap HTML.

    Returns an empty list when the payload is absent or unparseable — Layer 1
    (``validate_suite_heatmap``) already flags unparseable payloads as errors,
    so Layer 3 simply has nothing to check.
    """
    match = re.search(r"const allPoints = (.*?);\n", heatmap_html, re.DOTALL)
    if not match:
        return []
    try:
        raw = json.loads(match.group(1))
    except Exception:
        return []

    points: list[HeatmapPoint] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            x_raw = item.get("x")
            y_raw = item.get("y")
            if x_raw is None or y_raw is None:
                continue
            x = float(x_raw)
            y = float(y_raw)
        except TypeError, ValueError:
            continue
        points.append(
            HeatmapPoint(
                type=str(item.get("type", "") or ""),
                x=x,
                y=y,
                run_count=int(item.get("run_count", 1) or 1),
                status=str(item.get("status", "passed") or "passed"),
                locator=str(item.get("locator", "") or ""),
                label=str(item.get("label", "") or ""),
                element_id=str(item.get("element_id", "") or ""),
                tag=str(item.get("tag", "") or ""),
            )
        )
    return points


def point_to_document_px(point: HeatmapPoint, doc_w: float, doc_h: float) -> tuple[float, float]:
    """Map a point's document-relative % centre to document pixels.

    ``viewport_pct`` is recorded as a percentage of the **full document**
    (``evidence_tracker._get_element_metadata`` adds scrollX/scrollY), so the
    inverse mapping uses the live document size — not the viewport.
    """
    return (point.x / 100.0 * doc_w, point.y / 100.0 * doc_h)


def classify_point(point: HeatmapPoint) -> str:
    """Pre-browser classification: ``skip`` for points with no element claim.

    Navigate points are synthetic 50/50 markers (no element). Points without
    a recorded locator have nothing to verify against.
    """
    if "navigate" in point.type.lower():
        return "skip"
    if not point.locator:
        return "skip"
    return "check"


# ---------------------------------------------------------------------------
# Browser-side checks
# ---------------------------------------------------------------------------


def live_document_size(page: Any) -> tuple[float, float]:
    """Full scrollable document size of the currently-loaded page."""
    try:
        size = page.evaluate(
            "() => ({ w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight })"
        )
        return max(float(size.get("w", 0)), 1.0), max(float(size.get("h", 0)), 1.0)
    except Exception:
        return (1.0, 1.0)


def _locator_state(page: Any, locator: str) -> tuple[str, dict[str, float] | None]:
    """Resolve a recorded locator on the live page.

    Returns ``("missing" | "hidden" | "ok", box_or_None)``:
    - missing: locator does not match any element (stale locator class)
    - hidden: matches but has no bounding box (display:none / detached)
    - ok: has a bounding box
    """
    try:
        loc = page.locator(locator).first
        count = loc.count()
    except Exception:
        return "missing", None
    if not count:
        return "missing", None
    try:
        box = loc.bounding_box()
    except Exception:
        box = None
    if not box:
        return "hidden", None
    return "ok", box


def _scroll_point_into_view(page: Any, px: float, py: float, viewport: tuple[int, int]) -> tuple[float, float]:
    """Scroll so document point (px, py) sits at the viewport centre.

    Returns the point's viewport-relative position after the scroll (the
    browser clamps scroll at the document edges, so we read the actual
    scrollX/scrollY back instead of assuming the centre landed).
    """
    vw, vh = viewport
    try:
        info = page.evaluate(
            "([px, py, vw, vh]) => { window.scrollTo(px - vw / 2, py - vh / 2); "
            "return { sx: window.scrollX, sy: window.scrollY }; }",
            [px, py, vw, vh],
        )
        sx = float(info.get("sx", 0.0))
        sy = float(info.get("sy", 0.0))
    except Exception:
        sx = sy = 0.0
    return px - sx, py - sy


def _hit_check(page: Any, locator: str, vx: float, vy: float) -> dict[str, Any] | None:
    """One page-context evaluate: hit-test (vx, vy) against the claimed element.

    Returns ``{"hit": "tag#id" | None, "related": bool}`` or ``None`` when the
    evaluate fails (element detached between ``count`` and here). Everything
    runs inside a single evaluate so no DOM-node handles cross the protocol
    boundary (this Playwright build serialises node returns as plain strings).
    """
    try:
        return page.locator(locator).first.evaluate(
            "(el, args) => { const [x, y] = args; "
            "const hit = document.elementFromPoint(x, y); "
            "if (!hit) return { hit: null, related: false }; "
            "const hitDesc = hit.tagName.toLowerCase() + (hit.id ? '#' + hit.id : ''); "
            "const related = el === hit || (el.contains && el.contains(hit)) "
            "|| (hit.contains && hit.contains(el)); "
            "return { hit: hitDesc, related: !!related }; }",
            [vx, vy],
        )
    except Exception:
        return None


def check_point_alignment(
    point: HeatmapPoint,
    *,
    page: Any,
    doc_size: tuple[float, float],
    viewport: tuple[int, int] = DEFAULT_VIEWPORT,
) -> AlignmentCheck:
    """Check one overlay box against the live page (the page must already be
    on the URL the point was recorded for).

    Passes when the element hit by ``elementFromPoint`` at the box centre is
    the claimed element or an ancestor/descendant of it (strict-mode tolerant:
    a box centre landing on a child of the claimed element is correct, e.g. a
    button's inner ``<span>``).
    """
    if classify_point(point) == "skip":
        return AlignmentCheck(point=point, kind="skip", detail="no element claim (navigate / no locator)")

    state, box = _locator_state(page, point.locator)
    if state == "missing":
        return AlignmentCheck(
            point=point,
            kind="fail",
            detail=f"locator {point.locator!r} not found on live page (stale locator)",
        )
    if state == "hidden":
        return AlignmentCheck(
            point=point,
            kind="fail",
            detail=f"locator {point.locator!r} resolves but has no bounding box (hidden / not rendered)",
        )
    assert box is not None

    doc_w, doc_h = doc_size
    px, py = point_to_document_px(point, doc_w, doc_h)
    target: tuple[float, float] = (px, py)
    vw, vh = viewport
    vx, vy = _scroll_point_into_view(page, px, py, viewport)

    if not (0.0 <= vx <= vw and 0.0 <= vy <= vh):
        return AlignmentCheck(
            point=point,
            kind="fail",
            target_px=target,
            detail=f"point centre {target} falls outside the viewport after scroll — page smaller than recorded / off-page",
        )

    try:
        result = _hit_check(page, point.locator, vx, vy)
    except Exception:
        result = None
    if result is None:
        return AlignmentCheck(
            point=point,
            kind="fail",
            target_px=target,
            detail="point centre could not be checked (element detached while checking)",
        )
    hit_desc = result.get("hit")
    if hit_desc is None:
        return AlignmentCheck(
            point=point,
            kind="fail",
            target_px=target,
            detail="point centre hits nothing (elementFromPoint returned null)",
        )
    related = bool(result.get("related"))

    # Distance from the box centre to the claimed element centre (document px)
    # — reported as context, not a gate (small % drift is tolerated; the
    # containment test is the gate).
    distance_px: float | None = None
    try:
        scroll = page.evaluate("() => ({ x: window.scrollX, y: window.scrollY })")
        box_cx = box["x"] + float(scroll.get("x", 0)) + box["width"] / 2
        box_cy = box["y"] + float(scroll.get("y", 0)) + box["height"] / 2
        distance_px = math.hypot(px - box_cx, py - box_cy)
    except Exception:
        pass

    if related:
        return AlignmentCheck(
            point=point,
            kind="pass",
            detail=f"box centre hits {hit_desc} (claimed {point.locator!r})",
            target_px=target,
            hit_element=hit_desc,
            distance_px=distance_px,
        )

    return AlignmentCheck(
        point=point,
        kind="fail",
        detail=f"box centre hits {hit_desc}, NOT the claimed element {point.locator!r} "
        f"(wrong frame / page changed between steps)",
        target_px=target,
        hit_element=hit_desc,
        distance_px=distance_px,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def validate_heatmap_alignment(
    evidence_dir: Path,
    page_url: str,
    *,
    page: Any,
    viewport: tuple[int, int] = DEFAULT_VIEWPORT,
) -> list[ArtifactIssue]:
    """Validate every overlay box for one URL against the live page.

    ``page`` must already be navigated to ``page_url``. Returns error-severity
    issues for every box whose centre misses the element it claims.
    """
    html = generate_suite_heatmap(evidence_dir=evidence_dir, page_url=page_url)
    if "No evidence points found" in html:
        return []
    points = extract_points(html)
    doc_size = live_document_size(page)

    issues: list[ArtifactIssue] = []
    for point in points:
        check = check_point_alignment(point, page=page, doc_size=doc_size, viewport=viewport)
        if check.kind != "fail":
            continue
        issues.append(
            ArtifactIssue(
                artifact="heatmap-alignment",
                severity="error",
                message=check.detail,
                context={
                    "label": point.label,
                    "locator": point.locator,
                    "x": point.x,
                    "y": point.y,
                    "target_px": list(check.target_px) if check.target_px else None,
                    "hit": check.hit_element,
                    "distance_px": check.distance_px,
                },
            )
        )
    return issues


def validate_evidence_dir_live(
    evidence_dir: Path,
    page_urls: list[str],
    *,
    viewport: tuple[int, int] = DEFAULT_VIEWPORT,
    headless: bool = True,
) -> ArtifactValidationResult:
    """Layer 3 gate: launch a browser, open each URL, check alignment.

    Used by ``scripts/validate_report_artifacts.py --full``. Requires
    Playwright browsers installed and network access (or running mock sites)
    for the recorded URLs.
    """
    from playwright.sync_api import sync_playwright

    issues: list[ArtifactIssue] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
            for url in page_urls:
                try:
                    page.goto(url, wait_until="load", timeout=30_000)
                except Exception as exc:
                    issues.append(
                        ArtifactIssue(
                            artifact="heatmap-alignment",
                            severity="error",
                            message=f"could not open {url}: {exc}",
                            context={"url": url},
                        )
                    )
                    continue
                issues.extend(validate_heatmap_alignment(evidence_dir, url, page=page, viewport=viewport))
        finally:
            browser.close()
    return ArtifactValidationResult(issues=issues)
