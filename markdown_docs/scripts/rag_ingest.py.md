# `scripts/rag_ingest.py`

## High-Level Purpose

RAG Ingestion CLI — builds or rebuilds the RAG vector store from two knowledge sources:

1. **Golden patterns** from `scripts/eval/dataset/` — verified placeholder → selector mappings (4 sites, 43 placeholders)
2. **Playwright documentation** from `docs/rag_corpus/playwright/` — curated markdown files chunked by heading

The store file is written to `<workspace>/evidence/rag_store.db` via `get_storage().rag_path()`.

**Runs fully offline** — no LLM or browser needed. SentenceTransformer downloads the embedding model on first use (~80 MB, cached by Hugging Face).

## Module Metadata

- **Lines:** ~270
- **Imports:** `argparse`, `json`, `logging`, `re`, `pathlib.Path`, `src.rag_store`, `src.storage`
- **Spec:** `docs/specs/FEATURE_SPEC_phase3_rag.md` §3c
- **Shipped:** 2026-07-21

## CLI Usage

```bash
python scripts/rag_ingest.py --golden --docs    # Full rebuild
python scripts/rag_ingest.py --golden             # Golden patterns only
python scripts/rag_ingest.py --docs               # Docs only
```

## Key Functions

### `load_golden_patterns(dataset_dir: Path) -> list[GoldenPattern]`
Parse golden eval dataset JSON files (`eval-*.json`) into `GoldenPattern` entries. Each dataset file contains `golden_resolutions` — a list of criterion-level objects, each with a `placeholders` array containing `action`, `description`, `expected_locator`, `tolerance_selectors`, and `expected_page`.

### `chunk_markdown_file(filepath: Path) -> list[DocChunk]`
Split a markdown file into chunks at `##` heading boundaries. Each chunk targets ~500 tokens with ~50 tokens of overlap between consecutive chunks. The heading path (doc title + section headings) is stored as metadata for prompt citations.

**Chunking strategy:**
- Split on `##` heading boundaries
- Skip bare `# Title` lines (no useful retrieval signal beyond subsequent sections)
- Sections ≤ target tokens: use as-is
- Larger sections: split further at paragraph boundaries (`\n\n+`)
- Overlap: keep last ~50 tokens worth of text between consecutive chunks

### `load_docs(docs_dir: Path) -> list[DocChunk]`
Load and chunk all `.md` files from the docs directory. Logs per-file chunk counts.

### `rebuild_store(patterns, docs) -> dict[str, int]`
(Re)build the vector store from patterns and docs. Deletes any existing store file, creates a fresh `MilvusLiteBackend` + `RAGStore`, and upserts both knowledge sources. Returns a count summary: `{"golden": N, "docs": M}`.

### `main(argv=None) -> dict[str, int]`
CLI entry point. Parses args, loads data, calls `rebuild_store()`. Returns count summary.

## Token Estimation

| Constant | Value | Purpose |
|----------|-------|---------|
| `CHARS_PER_TOKEN` | `4` | Rough estimate for GPT-style tokenizers |
| `CHUNK_TARGET_TOKENS` | `500` | Target size per chunk |
| `CHUNK_OVERLAP_TOKENS` | `50` | Overlap between consecutive chunks |

`_estimate_tokens(text)` returns `max(1, len(text) // CHARS_PER_TOKEN)` — fast, offline character-based estimate.

## Key Design Decisions

- **Fully offline:** No network calls at runtime (model download cached by Hugging Face)
- **Deterministic rebuild:** Deletes existing store before rebuild — no incremental updates (store is small enough for full rebuild)
- **Path resolution relative to repo root:** `Path(__file__).resolve().parent.parent` — works regardless of CWD
- **Store location:** `get_storage().rag_path()` — workspace-aware via AI-029

## Dependencies

- `src.rag_store` — `RAGStore`, `MilvusLiteBackend`, `SentenceTransformerEmbedder`, data classes
- `src.storage.get_storage()` — workspace-aware path resolution
- `scripts/eval/dataset/` — golden pattern JSON files
- `docs/rag_corpus/playwright/` — curated markdown doc files

## Depended On By

- Manual/automated setup step (run once after repo clone or after golden dataset updates)
- `tests/test_rag_ingest.py` — 15 unit tests
