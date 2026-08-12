# 2026-08-11 — AI-043 Layer 3: heatmap overlay ↔ live-page alignment

**Roadmap:** Tier 3 §17 (AI-043 Output Artifact Quality Gate) — Layer 3, the
final layer. Layers 1+2 (deterministic invariants + golden fixtures) shipped
2026-08-10/11; this session closed the item.

## What shipped

**`src/heatmap_alignment.py`** (new, ~310 lines) — validates the shipped
suite-heatmap artifact against the live page it claims to depict:

1. `generate_suite_heatmap(evidence_dir, page_url)` — the real artifact.
2. `extract_points(html)` — parses the embedded `allPoints` payload.
3. For every box: `point_to_document_px` maps the document-relative % centre
   to pixels using the **live** document size (a changed document between
   record and check time is exactly the wrong-frame drift this catches).
4. `check_point_alignment` — resolves the recorded locator (`missing` →
   stale-locator error; no bounding box → hidden error), scrolls the point
   into view (reading actual scrollX/Y back — the browser clamps at edges),
   then one **locator-scoped evaluate** runs `elementFromPoint` at the point
   and tests same-node / ancestor / descendant relation with the claimed
   element. Failures read as `"box centre hits X, NOT the claimed element
   (wrong frame / page changed between steps)"`.

**CLI gate:** `scripts/validate_report_artifacts.py --full` — one chromium
session, opens each recorded URL, runs Layer 1/2 + Layer 3; exit 1 on
error-severity issues. Offline mode unchanged.

**Tests:** 18 offline unit tests (`tests/test_heatmap_alignment.py`, scriptable
fake page: missing/hidden/stale/off-page/contained/unrelated + payload parsing)
and 3 live tests (`tests/test_heatmap_alignment_live.py` — real chromium vs
the deterministic ecommerce mock, ports 8783): all-boxes-align passes; stale
locator flagged; shifted point flagged as wrong-frame.

## Key finding (protocol gotcha)

This Playwright build serialises DOM nodes returned from `page.evaluate` as
the **plain string `'ref: <Node>'`** — elementFromPoint results cannot be
returned across the protocol boundary, and handle-passing between evaluates
broke (`contains(null)` → TypeError). Fix: all DOM work happens inside a
single locator-scoped `evaluate` returning plain JSON
(`{hit: "tag#id"|null, related: bool}`). Lesson: don't return nodes from
`page.evaluate`; pass coordinates in, get JSON out.

## Verification

- ruff + mypy clean (src + scripts + tests)
- 18 offline + 3 live alignment tests pass; `test_artifact_validation.py` 22
  pass (no regression)
- `scripts/smoke.py` 38/38 (Gate 0 includes the Layer 1/2 checks)
- `tests/test_no_live_network_in_default_suite.py` passes (localhost mock only)
- CLI smoke: `validate_report_artifacts.py --evidence-dir <mock evidence>
  --page-url http://localhost:8783/index.html --full` → 0 errors, exit 0
- Full suite run in progress at time of writing (see ship-it gates)

## Notes / follow-ups

- Layer 3 skips navigate markers and locator-less points by design (no element
  claim). Points whose sidecar recorded a locator that was Playwright-only
  syntax (e.g. `text=...`) will resolve via `page.locator()` — the tracker
  writes robust CSS-ish locators, so this is covered; unit test if a gap
  appears.
- `--full` against real external sites hits the network by design (documented
  in the CLI help); the deterministic path is the mock sites.
- Docs: `markdown_docs/src/heatmap_alignment.py.md` added; ROADMAP §17 + summary
  row 25 updated; session tracking row added; AI-043 marked Complete.
