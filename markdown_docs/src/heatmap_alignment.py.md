# `src/heatmap_alignment.py`

## High-Level Purpose

**Heatmap overlay ↔ live-page alignment checks** (AI-043 Layer 3). Layer 1/2
(`src/artifact_validation.py`) validate the heatmap artifact's *internal*
invariants — points are document-relative percentages in `[0, 100]`, payloads
parse, counts add up. Layer 3 validates the artifact against the **live page**
it claims to depict:

1. render the suite heatmap for a URL (the shipped artifact),
2. open the live page in a real browser,
3. for every overlay box, map its centre (`x%`, `y%` of the document) to
   document pixels using the live document size, scroll the point into view,
   and assert the element hit by `document.elementFromPoint` is the element
   the box claims — the locator recorded in the sidecar.

This catches the two production failure classes:

- **wrong frame** — the heatmap picks one background screenshot per URL; if
  the page changed between steps, earlier boxes sit on elements that moved.
  The centre no longer hits the claimed element.
- **stale locator** — the recorded locator no longer resolves on the live
  page (element renamed / removed / hidden).

```
evidence sidecars → validate_heatmap_alignment(evidence_dir, url, page)
    ├─ generate_suite_heatmap()      # the shipped artifact (src/heatmap_utils)
    ├─ extract_points(html)          # parse the allPoints payload
    ├─ live_document_size(page)      # % → document pixels uses live doc size
    └─ check_point_alignment(point)  # one locator-scoped evaluate: hit + containment
    → list[ArtifactIssue]            # error per misaligned box
```

**Consumers:** `scripts/validate_report_artifacts.py --full` (browser gate,
exit 1 on errors) and the live integration test against the ecommerce mock
(`tests/test_heatmap_alignment_live.py`). The decision logic is unit-tested
offline (`tests/test_heatmap_alignment.py`) with a scriptable fake page.

## Module Metadata

- **Lines:** ~310
- **Imports:** `json`, `math`, `re`, `dataclasses`, `pathlib`, `typing`,
  `src.artifact_validation`, `src.heatmap_utils`; `playwright.sync_api`
  imported lazily inside `validate_evidence_dir_live`
- **Spec:** roadmap item AI-043 (Tier 3 §17) — Layer 3 of the output artifact
  quality gate
- **Shipped:** 2026-08-11

## Public API

### `HeatmapPoint` (dataclass)
One overlay box from the heatmap HTML payload: `type`, `x`/`y` (document-
relative %), `run_count`, `status`, `locator`, `label`, `element_id`, `tag`.

### `AlignmentCheck` (dataclass)
Outcome of checking one box against the live page: `kind` (`"pass"` | `"fail"`
| `"skip"`), `detail`, `target_px`, `hit_element`, `distance_px`.

### `extract_points(heatmap_html: str) -> list[HeatmapPoint]`
Parses the `allPoints` JSON payload embedded in the heatmap HTML. Empty list
when absent/unparseable (Layer 1 flags that as an error separately).

### `point_to_document_px(point, doc_w: float, doc_h: float) -> tuple[float, float]`
Maps a point's document-relative % centre to document pixels — the inverse of
`EvidenceTracker._get_element_metadata` (which records centre as a % of the
full document, scroll-corrected and clamped to `[0, 100]`).

### `classify_point(point) -> str`
`"skip"` for navigate points (synthetic 50/50 markers, no element claim) and
points without a recorded locator; `"check"` otherwise.

### `check_point_alignment(point, *, page, doc_size, viewport) -> AlignmentCheck`
The core check. Resolves the recorded locator (`missing` → fail, no bounding
box → fail), maps the centre to document pixels, scrolls it into view
(reading actual scrollX/Y back — the browser clamps at document edges), then
runs **one locator-scoped evaluate** that does `elementFromPoint` at the
viewport position and tests ancestor/descendant/same-node relation with the
claimed element. Passes when related; fails with `"wrong frame"` otherwise.
All DOM work happens inside that single evaluate because this Playwright
build serialises DOM-node returns from `page.evaluate` as plain strings —
handles cannot cross the protocol boundary.

### `validate_heatmap_alignment(evidence_dir, page_url, *, page, viewport) -> list[ArtifactIssue]`
Renders the suite heatmap for one URL and checks every extracted box against
the live page (which must already be navigated to `page_url`). Returns one
error-severity `ArtifactIssue` per misaligned box.

### `validate_evidence_dir_live(evidence_dir, page_urls, *, viewport, headless) -> ArtifactValidationResult`
Launches its own chromium, opens each URL (`wait_until="load"`, 30s timeout)
and runs the alignment checks; URL-open failures become error issues. Used by
the CLI `--full` gate.

## Design Notes

- **% coordinates are document-relative** (the AI-043 follow-up fix to
  `evidence_tracker._get_element_metadata`), so the inverse mapping uses the
  **live document size**, not the viewport. A changed document size between
  record and check time is exactly the wrong-frame drift Layer 3 detects.
- **Tolerance:** the gate is the containment test (strict-mode tolerant — a
  box centre landing on a child of the claimed element is correct, e.g. a
  button's inner `<span>`); the centre-to-centre distance is reported as
  context, not a gate.
- **Skip policy:** navigate markers and locator-less points are skipped — they
  make no element claim, so nothing to verify against.
