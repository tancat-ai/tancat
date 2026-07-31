# `src/evidence_index.py` — Evidence Index (AI-028)

## Purpose
SQLite-backed search, filter, and export metadata index. Indexes `.evidence.json` sidecar metadata into the existing `evidence/run_results.sqlite` database. Powers the in-tool search UI, faceted filters, and CSV/NDJSON/JUnit exports.

## Class: `EvidenceIndex`
- `__init__(db_path: str | Path)` — open/create SQLite connection
- `search(query: str, status: str | None, url: str | None, ...) -> list[dict]` — full-text search via SQL LIKE
- `refresh() -> int` — incremental re-index of changed sidecars (mtime-based)

## Related
- `src/evidence_export.py` — export formats
- `src/sqlite_persistence.py` — shared SQLite infrastructure (AI-012)
