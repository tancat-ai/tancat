# `src/rag_bundled.py`

## High-Level Purpose

Ships the **bundled golden pack** with the product and auto-seeds it into the
RAG store on first run (B-036 Phase 2) — so consumers never run
`rag_ingest.py` by hand. Also provides the canonical dataset/docs loaders and
the store-diagnostics helpers (`--stats`, `--prune-learned`).

This module is the home of the bundled-pack loading logic; `scripts/rag_ingest.py`
re-exports `load_golden_patterns`, `load_docs`, and `chunk_markdown_file` from
it for its power-user CLI.

## Module Metadata

- **Lines:** ~380
- **Imports:** `json`, `logging`, `re`, `time`, `collections.Counter`, `pathlib.Path`, `src.rag_store`, `src.storage`
- **Spec:** `docs/specs/FEATURE_SPEC_B036_consumer_config.md` §4/§8-Phase-2
- **Shipped:** 2026-08-03 (B-036 Phase 2)

## Key Concepts

### The bundled golden pack
- **Golden patterns**: all keys from `scripts/eval/dataset/eval-*.json`
  (eval-001..006, 83 patterns incl. both mock sites — mock keys never decay).
- **Doc chunks**: curated Playwright docs from `docs/rag_corpus/playwright/`
  (27 chunks, heading-chunked at `##` boundaries).

### First-run auto-seed (idempotent, self-healing)
`ensure_bundled_seeded()` runs automatically from `TestOrchestrator.__init__`
(when the retriever is built) and via `rag_ingest.py --bundled`. A versioned
marker file at `evidence/.rag_bundled_seeded.json` makes re-runs a no-op.

**B-048 (2026-09-06) — marker truth:** the marker now means "seeded AND the
store holds golden patterns". If the marker survives while the store is
pattern-less (the AI-059 lab-wipe signature: `{golden: 0, doc: 66}`), the pack
is re-added and the result reports `"status": "reseeded"` — a measurement can
never silently run against a pattern-less store again. Guarded lab wipe:
`src/learning_impact.restore_store_snapshot` refuses production-store targets
(see that module's doc).

## Functions

### Loaders (moved from `scripts/rag_ingest.py`)

| Function | Signature | Returns | Purpose |
|----------|-----------|---------|---------|
| `load_golden_patterns` | `(dataset_dir: Path)` | `list[GoldenPattern]` | Parse eval dataset JSONs → golden patterns |
| `build_bundled_patterns` | `(repo_root: Path \| None = None)` | `list[GoldenPattern]` | Load the shipped eval-001..006 pack |
| `chunk_markdown_file` | `(filepath: Path)` | `list[DocChunk]` | Split markdown at `##` headings (~500 tokens, 50 overlap) |
| `load_docs` | `(docs_dir: Path)` | `list[DocChunk]` | Load + chunk all `*.md` in a dir |
| `build_bundled_docs` | `(repo_root: Path \| None = None)` | `list[DocChunk]` | Load the shipped Playwright corpus |
| `bundled_dataset_dir` / `bundled_docs_dir` | `(repo_root=None)` | `Path` | Resolve pack source dirs |

### Seed + diagnostics

| Function | Signature | Returns | Purpose |
|----------|-----------|---------|---------|
| `bundled_marker_path` | `(storage=None)` | `Path` | Marker path in the evidence dir |
| `build_default_store` | `()` | `RAGStore` | Production store (lazy embedder + lazy Milvus client) |
| `ensure_bundled_seeded` | `(store=None, *, marker_path=None, force=False)` | `dict[str, object]` | Idempotent, self-healing seed → `{"status": "skipped"\|"seeded"\|"reseeded"\|"marked", "golden": N, "docs": M}` (`reseeded` = stale marker on a pattern-less store, B-048) |
| `store_stats` | `(store=None)` | `dict[str, int]` | Per-`entry_type` counts + `total` |
| `prune_learned` | `(store=None)` | `int` | Delete learned patterns, keep golden/docs |

## Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `BUNDLED_PACK_VERSION` | `1` | Bump when the shipped set changes; recorded in the marker |
| `_MARKER_FILENAME` | `".rag_bundled_seeded.json"` | Marker file name |
| `CHUNK_TARGET_TOKENS` / `CHUNK_OVERLAP_TOKENS` | `500` / `50` | Doc chunking parameters |

## Seed State Machine

- **`skipped`** — marker present (and not `force`): steady state for every run after the first.
- **`seeded`** — store was empty: bundled pack added, marker written. With `force`, re-adds even to a populated store (documented duplication; harmless to scoring — a direct match returns once).
- **`marked`** — store already populated (e.g. manual `--golden` ingest): marker written, nothing added.

Failures **propagate** to the caller — the orchestrator wraps the seed in a
try/except so RAG can never block generation, and a failed seed retries on the
next run (marker not written).

## Depended On By

- `src/orchestrator.py` — first-run auto-seed hook
- `scripts/rag_ingest.py` — re-exports loaders; `--bundled/--force/--stats/--prune-learned`
- `src/rag_learn.py` — `build_default_store()` reuse

## Notes

- Loaders were moved here from `scripts/rag_ingest.py` (B-036 Phase 2) so
  testable logic lives in `src/` per project convention.
- Milvus dynamic-field queries (`counts_by_type`, `delete_learned`) were
  verified against Milvus-lite before shipping.
- `--prune-learned` is a no-op today (no learned patterns yet) — it ships so
  consumers have the reset lever before AI-035 learning lands.

## How It Works (Internals)

Private `_`-helpers — the module's real logic (1 item). Grouped under the public function that uses them:

### `ensure_bundled_seeded`
- `_write_marker(marker_path: Path) -> None` (function) — (no docstring)

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `DocSummary` (class): Per-document ingestion outcome. skipped_pages records, for each skipped page, the (page_number, reason) pair where reason is "no_engine" (the OCR engine is not installed - the [ocr] extra is missin...
- `IngestionSummary` (class): Aggregated ingestion quality summary for a CLI run.
- `IngestionSummary.docs_total` (method of `IngestionSummary`): `IngestionSummary.docs_total() -> int`
- `IngestionSummary.docs_full` (method of `IngestionSummary`): `IngestionSummary.docs_full() -> int`
- `IngestionSummary.docs_partial` (method of `IngestionSummary`): `IngestionSummary.docs_partial() -> int`
- `IngestionSummary.chunks_total` (method of `IngestionSummary`): `IngestionSummary.chunks_total() -> int`
- `IngestionSummary.render` (method of `IngestionSummary`): `IngestionSummary.render() -> str` - Human-readable multi-line summary (CLI output). Uses plain-text markers ([OK] / [WARN]) rather than emoji so the output renders on every terminal, including Windows cp1252 consoles (an emoji like raises...
- `doc_outcome_from_pages` (function): `doc_outcome_from_pages(pages_total: int, pages_text: int, pages_ocr: int, pages_skipped: int) -> str` - Derive a per-doc outcome from its page counts. * full - every page was read (text or OCR), none skipped. * partial - at least one page was skipped (no text/OCR). * skipped - no pages were read at all (unre...
- `doc_summaries_from_page_report` (function): `doc_summaries_from_page_report(page_report: list[tuple[str, int, str, str]]) -> list[DocSummary]` - Build per-doc summaries from the per-page report ((source, page, outcome, reason)) collected by :func:'src.pdf_ingest.ingest_pdf_directory'. For a skipped page the reason is carried through to DocSummary.ski...
- `check_supported_formats` (function): `check_supported_formats(paths: Sequence[str | Path]) -> tuple[list[str | Path], list[str]]` - Split a sequence of doc paths into (supported, rejected) by format scope. supported = paths whose extension is in :data:'SUPPORTED_FORMATS' (pdf + md). rejected = filenames of unsupported formats (reported lou...
- `build_summary` (function): `build_summary(page_report: list[tuple[str, int, str, str]], chunks_new: int, chunks_present: int, unreadable_docs: list[str] | None = None, skipped_formats: list[str] | None = None) -> IngestionSummary` - Build an :class:'IngestionSummary' from in-memory ingestion data.
- `CHARS_PER_TOKEN` (constant): `CHARS_PER_TOKEN = 4`
- `SUPPORTED_FORMATS` (constant): `SUPPORTED_FORMATS = ('.pdf', '.md')`


### Additional helpers (docs refresh 2026-10-02)

Private helpers with real logic not listed above.

### `load_golden_patterns(dataset_dir: Path) -> list[GoldenPattern]` - function

- `_site_identity_hash(site_name: str, base_url: str) -> str` (function): One-way hash of a golden pattern's canonical site identity (B-047). Golden patterns are site-scoped so a saucedemo golden cannot award a +20 bonus while resolving another site. Identity comes from the dataset base_u...
