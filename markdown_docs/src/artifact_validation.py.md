# `src/artifact_validation.py`

## High-Level Purpose

**Deterministic validation of output report artifacts** (AI-043 Layer 1+2).
The pipeline's evidence reports render heatmap overlays, Gantt timelines and
Plotly charts from sidecar data — but unit tests only exercised the chart
*builders*, never the truthfulness of what ships. This module checks the
rendered artifacts and their source data against invariants:

- heatmap points must be document-percentages in `[0, 100]` (legacy sidecars
  recorded raw pixels → markers painted off-page)
- the JSON payloads embedded in the shipped HTML must be parseable, finite,
  and internally consistent
- Gantt durations must be finite and ≥ 0 (one NaN/negative `duration_s`
  collapses the sequential timeline)
- Plotly figures must carry no NaN/None/empty series

```
evidence sidecars → validate_evidence_artifacts(evidence_dir, urls)
    ├─ validate_suite_heatmap()      # renders the real HTML, parses embedded payloads
    ├─ validate_gantt_entries()      # duration/status invariants
    └─ validate_gantt_chart()        # rendered figure data invariants
    → ArtifactValidationResult (issues; passed == no error-severity issues)
```

**Consumers:** `scripts/validate_report_artifacts.py` (CLI gate, exit 1 on
errors) and three Gate-0 checks in `scripts/smoke.py` that validate the
`fixtures/report_golden/` corpus every CI run.

## Module Metadata

- **Lines:** ~270
- **Imports:** `json`, `math`, `re`, `dataclasses`, `pathlib`, `typing`,
  `src.gantt_utils`, `src.heatmap_utils`
- **Spec:** roadmap item AI-043 (Tier 3 §17) — Layers 1+2 of the output
  artifact quality gate
- **Shipped:** 2026-08-10

## Public API

### `ArtifactIssue` (dataclass)
`artifact: str` (e.g. `"heatmap"` / `"gantt"` / `"chart"`), `severity: str`
(`"error"` | `"warning"`), `message: str`, `context: dict`.

### `ArtifactValidationResult` (dataclass)
Wraps `issues: list[ArtifactIssue]`. Properties: `errors` (error-severity
issues), `warnings`, `passed` (True when no error-severity issues).

### `validate_step_points(points_by_url: dict[str, list[dict]]) -> list[ArtifactIssue]`
Invariants on extracted step points (I1/I5/I6): coordinates are finite
percentages in `[0, 100]`, `status` is a known status, `run_count` ≥ 1.

### `validate_suite_heatmap(evidence_dir: Path, page_url: str) -> list[ArtifactIssue]`
Runs the real `generate_suite_heatmap` (the shipped artifact), extracts the
embedded `allPoints` / `aggregated` payloads from the HTML, and checks:
payloads present + parseable; every rendered point has finite in-range
coordinates and a known status; aggregated element counts sum correctly;
the HTML's rendered totals match the payload; a background screenshot exists
when points are rendered (else a warning — markers on an imaginary 16:9 box).

### `validate_gantt_entries(entries: Iterable[GanttEntry]) -> list[ArtifactIssue]`
G1/G3: every `duration_s` is finite and ≥ 0; every status is known.

### `validate_gantt_chart(entries: list[GanttEntry]) -> list[ArtifactIssue]`
Builds the real Gantt figure and checks each bar's `base` (start) and `x`
(duration) are finite, ≥ 0, and paired 1:1 — a NaN/negative anywhere means
the sequential timeline is broken.

### `validate_plotly_figure(fig, artifact: str) -> list[ArtifactIssue]`
Generic chart sanity: no traces (error), no `None` / non-finite values in any
trace's `x`/`y`/`base`/`values`/`labels`.

### `validate_evidence_artifacts(evidence_dir: Path, page_urls: list[str]) -> ArtifactValidationResult`
Orchestrator: heatmap validation per URL + Gantt entries/chart. This is what
the CLI gate calls.

## How It Works (internals)

### `validate_suite_heatmap` — end-to-end artifact validation
- `_extract_js_payload(html, var_name)` — regex-extracts a payload embedded as
  `const <var> = ...;` in the heatmap HTML and `json.loads` it. Validates the
  *shipped* HTML rather than intermediate structures.
- `_count_statuses(statuses)` — counts status strings into a dict (used to
  verify aggregated `passed/partial_pass/failed/skipped` sums equal `total`).

### `validate_gantt_chart` — rendered-data validation
- Reads `trace.base` / `trace.x` directly off the built Plotly figure (they
  are numpy arrays — the code guards against truthiness-on-array pitfalls by
  normalising via `list(...) if raw is not None else []`).

### Internal utilities
- `_finite(value)` — True for finite int/float (excludes bool).
- `_in_range(value, lo, hi)` — `_finite` plus bounds check.

## Verification

- 22 unit tests in `tests/test_artifact_validation.py` (step points, HTML
  round-trip, legacy-pixel regression, NaN Gantt, golden fixtures, CLI exits)
- Ran against all 51 production evidence dirs — flagged 5 with real negative-y
  off-page markers (the `evidence_tracker` fix this validator caught)
