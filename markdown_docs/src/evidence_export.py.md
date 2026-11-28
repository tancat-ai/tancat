# `src/evidence_export.py` — Evidence Export (AI-028)

## Purpose
CSV, NDJSON, and JUnit XML exporters for evidence data. **One public function owns an export** (t-1488): `export_evidence` checks the Free-tier cap, builds the bytes, charges the meter, then writes a file or returns the text. The per-format builders are private (`_csv_text`, `_ndjson_text`, `_junit_text`), so no caller can obtain export bytes without the check. Filters are the same parameters as `EvidenceIndex.search()`, so all formats filter consistently.

## Functions
- `export_evidence(index, format_name, *, output=None, charge_meter=True, enforce_cap=True, **filters) -> str` — the one export path. `output` writes a file; no `output` returns the text for the browser.
  - `enforce_cap=False` — the named tooling bypass, used only by `scripts/parity_check.py`.
  - `charge_meter=False` — used only by the UI, which charges on the download click (Streamlit re-runs would otherwise count every render).
- `EXPORT_FORMATS` — `("csv", "ndjson", "junit")`.

The guard that keeps this true is `tests/test_export_single_path.py`: it fails if a second public export appears, if any module outside this one calls a private builder, or if either flag is used outside its named caller.

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
