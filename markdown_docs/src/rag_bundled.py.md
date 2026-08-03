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

### First-run auto-seed (idempotent)
`ensure_bundled_seeded()` runs automatically from `TestOrchestrator.__init__`
(when the retriever is built) and via `rag_ingest.py --bundled`. A versioned
marker file at `evidence/.rag_bundled_seeded.json` makes re-runs a no-op.

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
| `ensure_bundled_seeded` | `(store=None, *, marker_path=None, force=False)` | `dict[str, object]` | Idempotent seed → `{"status": "skipped"\|"seeded"\|"marked", "golden": N, "docs": M}` |
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
