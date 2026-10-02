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


## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 2 items):

### `EvidenceSearchResult` (class)

A single evidence sidecar returned by :meth:`EvidenceIndex.search`.

### `EvidenceFilterOptions` (class)

Distinct values available for faceted filter dropdowns.

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `EvidenceIndex.build_or_refresh` (method of `EvidenceIndex`): `EvidenceIndex.build_or_refresh(base_dir: Path | None = None, force: bool = False) -> int` - Scan all evidence sidecars and upsert into evidence_index. Parameters ---------- base_dir: Root directory to scan (default: storage singleton's generated_tests_dir()). force: If True, re-read every sidecar...
- `EvidenceIndex.get_filter_options` (method of `EvidenceIndex`): `EvidenceIndex.get_filter_options() -> EvidenceFilterOptions` - Return distinct values for faceted filter dropdowns.
- `EvidenceIndex.get_test_package_path` (method of `EvidenceIndex`): `EvidenceIndex.get_test_package_path(sidecar_path: str) -> Path` - Resolve a relative sidecar_path to an absolute :class:'Path'.
- `EvidenceIndex.get_sidecar_detail` (method of `EvidenceIndex`): `EvidenceIndex.get_sidecar_detail(sidecar_path: str) -> dict | None` - Load the full sidecar JSON for a given path.


## How It Works (Internals)

Private `_`-helpers - the module's real logic (10 items). Grouped under the public function that calls them.

### `EvidenceIndex.search(query: str = '', status: str | None = None, url_domain: str | None = None, condition_prefix: str | None = None, story_ref: str | None = None, step_type: str | None = None, locator: str | None = None, limit: int = 100) -> list[EvidenceSearchResult]` - method of `EvidenceIndex`

- `_execute(sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor` (method of `EvidenceIndex`): Execute with one-shot corruption recovery + retry (B-034).
- `_resolve_matched_field(query: str, row: sqlite3.Row) -> str` (method of `EvidenceIndex`): Determine which column(s) matched the search query.

### `EvidenceIndex.build_or_refresh(base_dir: Path | None = None, force: bool = False) -> int` - method of `EvidenceIndex`

- `_find_sidecars(base_dir: Path) -> list[str]` (method of `EvidenceIndex`): Yield relative paths to every *.evidence.json under *base_dir*.
- `_read_sidecar(abs_path: Path) -> dict | None` (method of `EvidenceIndex`): Read and return the parsed sidecar JSON, or None on failure.
- `_is_stale(sidecar_path: str, disk_mtime: float) -> bool` (method of `EvidenceIndex`): Return True if the sidecar is new or has changed on disk.
- `_upsert_sidecar(sidecar_path: str, data: dict, file_mtime: float, indexed_at: str, base_dir: Path) -> None` (method of `EvidenceIndex`): Insert or update a single sidecar row.

### `EvidenceIndex.get_filter_options() -> EvidenceFilterOptions` - method of `EvidenceIndex`

- `_extract_domain(url: str) -> str` (method of `EvidenceIndex`): Extract domain from a URL (e.g. automationexercise.com).

### Internal utilities

- `_health_ok() -> bool` (method of `EvidenceIndex`): True when PRAGMA integrity_check reports an intact database.
- `_recover() -> None` (method of `EvidenceIndex`): Self-heal a corrupt database. Ladder: (1) drop + recreate just the evidence_index table (keeps runs/test_results when the corruption is localised); (2) if the file itself is corrupt, delete it and let SQ...
- `_commit() -> None` (method of `EvidenceIndex`): Commit with one-shot corruption recovery + retry (B-034).
