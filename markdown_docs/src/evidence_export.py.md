# `src/evidence_export.py` — Evidence Export (AI-028)

## Purpose
CSV, NDJSON, and JUnit XML exporters for evidence data. All exporters consume the same filter parameters as `EvidenceIndex.search()`, ensuring consistent filtering across all export formats.

## Functions
- `export_csv(index: EvidenceIndex, ...) -> str` — CSV export with filter support
- `export_ndjson(index: EvidenceIndex, ...) -> str` — NDJSON (newline-delimited JSON) export
- `export_junit_xml(index: EvidenceIndex, ...) -> str` — JUnit XML for CI/CD integration

## Related
- `src/evidence_index.py` — SQLite-backed search index
- `scripts/eval/eval_runner.py` — eval harness consumer

## How It Works (Internals)

Private `_`-helpers — the module's real logic (2 items). Grouped under the public function that uses them:

### `export_junit_xml`
- `_classname_from_url(url: str) -> str` (function) — Derive a JUnit ``classname`` from a page URL.
- `_first_step_error(sidecar: dict | None) -> str` (function) — Extract the first step error message from a sidecar.
