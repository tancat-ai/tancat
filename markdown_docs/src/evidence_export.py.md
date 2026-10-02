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

### Additional helpers (docs refresh 2026-10-02)

Private helpers with real logic not listed above.

### `export_junit_xml(index: EvidenceIndex, *, query: str = '', status: str | None = None, url_domain: str | None = None, condition_prefix: str | None = None, story_ref: str | None = None, step_type: str | None = None, output: str | Path | None = None, suite_name: str = 'evidence_export') -> str` - function

- `_load_sidecar(index: EvidenceIndex, sidecar_path: str) -> dict | None` (function): Load the full sidecar JSON from disk.
- `_meter_record(format_name: str, output: str | Path) -> None` (function): Best-effort record of one evidence export in the usage ledger. Phase 6e - metering must never break an export: any failure here is swallowed (a log line at most). The ledger lives inside the storage evidence dir; read...
