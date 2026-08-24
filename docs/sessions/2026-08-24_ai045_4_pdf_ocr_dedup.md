# Session Record — AI-045 #4: PDF OCR Wiring + Doc-Chunk Dedup Key

**Date:** 2026-08-24
**Branch:** `overnight/ai045-4-pdf-ocr-dedup`
**Backlog ref:** `BACKLOG.md` → AI-045 §8.2 (PDF OCR wiring + doc-chunk dedup gap)
**Plan:** `docs/plans/AI-045_4_pdf_ocr_dedup_plan.md`
**Status:** code complete — pending ship-it (ruff/mypy/pytest/eval all green locally)

## What was done

Two High-severity commercial-readiness gaps from the 2026-08-17 audit
(`docs/plans/RESEARCH_SAAS_AND_LAUNCH.md` §8.2) are now closed in the production
ingest path:

### 1. PDF OCR wired into the production path
Previously only the dormant LangGraph path (`src/agents/pipeline_graph.py:141`)
consulted `get_ocr_backend()`. The production path
(`scripts/rag_ingest.py --pdfs` → `src.pdf_ingest.ingest_pdf_directory`)
hardcoded PyMuPDF and silently skipped scanned pages.

- `ingest_pdf` / `ingest_pdf_directory` gained a keyword-only
  `ocr_fallback: Callable[[Path, int], str] | None = None`. When a page is
  image-only (`len(get_text()) < MIN_PAGE_CHARS`) and a fallback is supplied,
  it's called as `ocr_fallback(path, page_number)` and the text is merged in.
- **Page-scoped**, not whole-document: only the skipped pages hit OCR, so a
  mostly-text PDF doesn't trigger a full GPU re-OCR.
- `OcrBackend.parse_page(path, page_number)` added (default `""`).
  `UnlimitedOCRBackend` implements it — rasterises just that page at 300 DPI and
  runs the vision model on the single image. `PyMuPDFBackend` returns `""`.
- `scripts/rag_ingest.py::_build_ocr_fallback()` consults `get_ocr_backend()`
  and returns `backend.parse_page` only when `unlimited-ocr` is configured *and*
  available; otherwise `None`.
- **Loud failure:** with no fallback, an image-only page now logs a WARNING
  (was `info`) hinting at `OCR_BACKEND=unlimited-ocr`.

### 2. Doc-chunk dedup key (idempotent re-ingestion)
`RAGStore.add_docs` previously did an unconditional insert, so re-ingesting a
PDF duplicated every chunk.

- `DocChunk` gained `dedup_key: str = ""`.
- `src.pdf_ingest.doc_chunk_key(chunk)` = `sha256(source \x00 heading_path \x00 normalised_text)`;
  `_normalise_for_dedup` collapses whitespace + strip + lower (robust to
  cosmetic re-extraction differences). `ingest_pdf` stamps every returned chunk.
- `RAGStore.add_docs` now returns `tuple[int, int]` (inserted, skipped): it
  queries existing keys via the new `query_dedup_keys("doc")` backend method and
  skips chunks whose non-empty key already exists. Empty-key chunks always
  insert (back-compat).
- `VectorStoreBackend.query_dedup_keys` added to the protocol (default `[]`) +
  `MilvusLiteBackend` impl (one batched query over the dynamic `dedup_key`
  field).
- All 6 `add_docs` callers updated (rag_bundled, rag_ingest x2, test fakes).
- `scripts/rag_ingest.py --prune-dupes` (new): groups stored doc rows by
  `dedup_key`, keeps the lowest `id` per group, deletes the rest. Legacy
  no-key rows are left alone (cleaned by `--reindex`).

## Design decisions
- **Page-scoped OCR fallback** — cheaper than whole-document re-OCR; matches the
  "image-only pages are skipped" → "…should be OCR'd" intent.
- **Content-hash dedup** — identity is content, not position; normalisation
  keeps the key stable across cosmetic re-extraction.
- **Tuple return** — `add_docs` returns `(inserted, skipped)` so the CLI can
  report "N new, M duplicates skipped". Breaking change, but all callers are
  in-repo and the suite is exhaustive.
- **`--prune-dupes` over auto-migration** — non-destructive to the rest of the
  store; `--reindex` remains the nuclear option.

## Test results (local, 2026-08-24, fitz INSTALLED to match CI's `--all-extras`)
- New tests: OCR wiring x5 (fallback-called / no-fallback-warns / empty-warns /
  exception-skips / text-page-not-ocrd), dedup x3 (skip-existing / mixed /
  empty-key-always-inserts + key normalisation), prune x2 (prunes-keeps-lowest /
  none-returns-zero). OCR tests use **real one-page PyMuPDF PDFs** (image-only =
  a drawn rect, no text) + a plain callable OCR hook — no GPU, no fitz mocking.
- Full suite: **2793 passed, 0 failed** with the `[pdf]` extra installed (CI parity).
  (The earlier "2750 passed / 1 skipped" was a false positive — fitz was NOT
  installed locally, so the whole `test_pdf_ingest.py` module was `importorskip`
  -ed and the OCR tests never ran. See "Bug found" below.)
- smoke: **39/39**. ruff: clean (incl. `scripts/`). mypy: clean (143 files incl. cli/).
- eval static: **97.9%** (no regression vs baseline).
- coverage: 70% (CI gate ≥ 65%).

## Bug found (caught by CI, fixed before merge)
The first push's `ocr_fallback` param was added to the `ingest_pdf`/`ingest_pdf_directory`
**signatures + docstrings but the page-loop body edit silently failed to apply** —
the parameter was accepted but never used, so image-only pages were still skipped
with the old `info` log and no OCR/warning. All 5 OCR tests failed identically on CI
(`calls == []`, no warning). Root cause of the masking: fitz was absent locally so the
PDF test module skipped, hiding the dead parameter. **Fix:** re-applied the page-loop
OCR branch (fallback call + merge + WARNING paths) and rewrote the OCR tests to use
real PyMuPDF PDFs instead of mocking fitz (mocking `Page.get_text("dict")` / `__getitem__`
was brittle). Verified: real image-only PDF now routes to the fallback and merges its
output; full suite green with fitz installed.

## Findings / gotchas
- **⚠️ Install the `[pdf]` extra before validating PDF work.** fitz (PyMuPDF) is an
  optional extra; without it `tests/test_pdf_ingest.py` is `importorskip`-ed and
  PDF changes are *not* tested locally. CI runs `uv sync --frozen --all-extras`, so
  what passes locally without `[pdf]` can still fail in CI. (`uv sync --extra pdf`.)
- pre-commit's mypy hook runs on staged **test** files too (not just `src/`) —
  inner test helper functions and lambdas need full annotations because
  `disallow_untyped_defs = true`.
- `Callable` must be imported at module level (not under `TYPE_CHECKING`) when
  used in a runtime function-signature position (ruff F821 + mypy name-defined).
- `scripts/` is excluded from pyproject mypy but **not** from ruff — the
  B007 unused-loop-var fired on `prune_doc_duplicates`.
- A multi-hunk `edit` call fails atomically: if one hunk's `oldText` doesn't match,
  the whole call is rejected. Verify every hunk landed (grep for the new symbol) —
  don't assume a signature edit implies its body edit applied.

## Cross-refs
- `BACKLOG.md` AI-045 #4 (PDF OCR wiring) + §8.2 dedup sub-item.
- `docs/plans/RESEARCH_SAAS_AND_LAUNCH.md` §8.2.
- `markdown_docs/src/{pdf_ingest,rag_store,ocr_backends}.py.md` updated.

## Remaining (for ship-it / user)
- Status updates in BACKLOG.md / CHANGELOG happen at ship-it, not mid-session.
- `UnlimitedOCRBackend.parse_page` is mocked in tests; the real single-page GPU
  path is untested against the live model (opt-in + GPU-gated by design).
