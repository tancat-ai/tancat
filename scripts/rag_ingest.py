"""RAG Ingestion CLI — build/rebuild the vector store.

Usage::

    python scripts/rag_ingest.py --golden --docs --pdfs
    python scripts/rag_ingest.py --golden --docs
    python scripts/rag_ingest.py --pdfs
    python scripts/rag_ingest.py --bundled              # seed the bundled pack (idempotent)
    python scripts/rag_ingest.py --bundled --force      # re-seed even if already seeded
    python scripts/rag_ingest.py --stats                # per-type store counts
    python scripts/rag_ingest.py --prune-learned        # remove learned patterns, keep golden/docs

Ingests knowledge sources into the RAG vector store:

1. **Golden patterns** from ``scripts/eval/dataset/`` — verified
   placeholder → selector mappings (6 datasets, incl. mock sites).
2. **Playwright documentation** from ``docs/rag_corpus/playwright/`` —
   curated markdown files chunked by heading.
3. **PDF domain docs** from ``docs/rag_corpus/lv_docs/`` — insurance
   policy PDFs parsed with PyMuPDF and chunked by heading.

``--bundled`` seeds exactly the pack that ships with the product and is
also run automatically on the first generation run (see
``src/rag_bundled.py``); re-running is a no-op unless ``--force``.

The store file is written to ``<workspace>/evidence/rag_store.db``
(via ``get_storage().rag_path()``).

Run offline — no LLM or browser needed.  SentenceTransformer downloads
the embedding model on first use (~80 MB, cached by Hugging Face).
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from src.ocr_backends import OcrBackend, get_ocr_backend
from src.pdf_ingest import ingest_pdf_directory
from src.rag_bundled import (
    _write_marker,
    build_bundled_docs,
    build_bundled_patterns,
    bundled_marker_path,
    chunk_markdown_file,  # re-exported for backwards compatibility
    ensure_bundled_seeded,
    load_docs,  # re-exported for backwards compatibility
    load_golden_patterns,  # re-exported for backwards compatibility
    prune_learned,
    store_stats,
)
from src.rag_store import (
    DocChunk,
    EmbeddingMismatchError,
    GoldenPattern,
    MilvusLiteBackend,
    RAGStore,
    SentenceTransformerEmbedder,
    embedder_stamp_path,
)
from src.storage import get_storage

logger = logging.getLogger(__name__)

# Backwards-compatible aliases: the bundled pack loaders moved to
# ``src/rag_bundled.py`` (B-036 Phase 2); tests and callers importing
# them from this module keep working.
__all__ = [
    "chunk_markdown_file",
    "ensure_bundled_seeded",
    "load_docs",
    "load_golden_patterns",
    "main",
    "prune_learned",
    "rebuild_store",
    "store_stats",
]


# ---------------------------------------------------------------------------
# OCR fallback
# ---------------------------------------------------------------------------


def _build_ocr_fallback() -> Callable[[Path, int], str]:
    """Build a page-scoped OCR fallback for image-only PDF pages (AI-055).

    Consults the configured OCR backend (persisted setting > ``OCR_BACKEND``
    env > ``auto`` default) and returns its ``parse_page`` — the per-page
    image-only hook.  With AI-055 tiering, the ``auto`` (default) backend
    routes image-only pages to the **tier-1 CPU OCR** (RapidOCR) when it is
    installed, so a scanned page is handled on any machine.  When no OCR tier
    is available, ``parse_page`` returns empty and the production ingest path
    skips the page with a loud WARNING (never fails ingestion for a missing
    optional tier — graceful degradation).

    Returns the backend's ``parse_page`` bound method (always callable); the
    empty-string return when no OCR is available is handled by the ingest
    path, not by returning ``None`` here.
    """
    backend: OcrBackend = get_ocr_backend()
    return backend.parse_page


# ---------------------------------------------------------------------------
# Reconstruction
# ---------------------------------------------------------------------------


def rebuild_store(
    patterns: list[GoldenPattern],
    docs: list[DocChunk],
    pdfs: list[DocChunk] | None = None,
) -> dict[str, int]:
    """(Re)build the vector store from patterns and docs.

    Deletes any existing store file and creates a fresh one.
    Returns count summary.
    """

    embedder = SentenceTransformerEmbedder()
    store_path = str(get_storage().rag_path())

    # Delete existing store + embedder-stamp sidecar if present
    # (Milvus Lite creates a directory)
    import os
    import shutil

    for target in (store_path, embedder_stamp_path(store_path)):
        try:
            if os.path.isdir(target):
                shutil.rmtree(target)
            else:
                os.remove(target)
        except FileNotFoundError, PermissionError, OSError:
            pass

    backend = MilvusLiteBackend(
        store_path,
        embedder.dimension,
        embedder_identity=embedder.identity,
    )
    store = RAGStore(backend, embedder)

    result: dict[str, int] = {"golden": 0, "docs": 0, "pdfs": 0, "docs_skipped": 0, "pdfs_skipped": 0}

    if patterns:
        result["golden"] = store.add_patterns(patterns)
        logger.info("Ingested %d golden patterns", result["golden"])

    if docs:
        result["docs"], result["docs_skipped"] = store.add_docs(docs)
        logger.info("Ingested %d doc chunks (%d duplicates skipped)", result["docs"], result["docs_skipped"])

    if pdfs:
        result["pdfs"], result["pdfs_skipped"] = store.add_docs(pdfs)
        logger.info("Ingested %d pdf chunks (%d duplicates skipped)", result["pdfs"], result["pdfs_skipped"])

    logger.info("Store rebuilt at %s (total entries: %d)", store_path, backend.count())
    return result


def prune_doc_duplicates() -> int:
    """Remove duplicate doc chunks (same ``dedup_key``) from the live store.

    Groups stored ``entry_type == "doc"`` rows by ``dedup_key`` (skipping
    legacy rows with no key), keeps the lowest ``id`` in each group, and
    deletes the rest.  Returns the number of duplicate rows removed.  Safe to
    run repeatedly — a second run finds nothing to prune.
    """
    from src.rag_store import _COLLECTION_NAME  # noqa: PLC0415 - private name, CLI-only

    embedder = SentenceTransformerEmbedder()
    store_path = str(get_storage().rag_path())
    backend = MilvusLiteBackend(store_path, embedder.dimension, embedder_identity=embedder.identity)
    # CLI-only: reach the lazy Milvus client directly to run a bulk doc-prune
    # query/delete that the RAGStore API doesn't expose.
    client = backend._c  # noqa: SLF001

    rows = client.query(
        _COLLECTION_NAME,
        filter='entry_type == "doc"',
        output_fields=["id", "dedup_key"],
        limit=100_000,
    )

    groups: dict[str, list[int]] = {}
    for row in rows:
        key = str(row.get("dedup_key") or "")
        if not key:
            continue  # legacy row (no key) — left alone, cleaned up by --reindex
        groups.setdefault(key, []).append(int(row["id"]))

    dup_ids: list[int] = []
    for _key, ids in groups.items():
        if len(ids) > 1:
            ids.sort()
            dup_ids.extend(ids[1:])  # keep the lowest id, drop the rest

    if not dup_ids:
        return 0

    result = client.delete(_COLLECTION_NAME, ids=dup_ids)
    if isinstance(result, dict):
        return int(result.get("delete_count", len(dup_ids)))
    return len(result)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> dict[str, object]:
    """Run the ingestion CLI.

    Returns a summary dict so tests can verify output. An embedder-mismatch
    refusal is printed cleanly (no traceback) with the reindex fix.
    """
    try:
        return _run(argv)
    except EmbeddingMismatchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return {"error": str(exc)}


def _run(argv: list[str] | None = None) -> dict[str, object]:
    """Parse args and execute the requested operations (see :func:`main`)."""

    parser = argparse.ArgumentParser(
        description="Manage the RAG vector store: rebuild from sources, seed the bundled pack, or inspect.",
    )
    parser.add_argument(
        "--golden",
        action="store_true",
        help="Ingest golden patterns from scripts/eval/dataset/ (rebuilds the store)",
    )
    parser.add_argument(
        "--docs",
        action="store_true",
        help="Ingest Playwright docs from docs/rag_corpus/playwright/ (rebuilds the store)",
    )
    parser.add_argument(
        "--pdfs",
        action="store_true",
        help="Ingest PDF domain docs from docs/rag_corpus/lv_docs/ (rebuilds the store)",
    )
    parser.add_argument(
        "--bundled",
        action="store_true",
        help="Seed the bundled golden pack (eval keys + docs). Idempotent — no-op if already seeded",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="With --bundled: (re-)add the pack even if already seeded or the store is populated",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show RAG store entry counts per type (golden/doc/learned)",
    )
    parser.add_argument(
        "--prune-learned",
        action="store_true",
        help="Delete learned patterns from the store, keeping golden patterns and doc chunks",
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Re-embed the bundled golden pack + docs from scratch (deletes the store, "
        "resets learned patterns, rewrites the embedder stamp). Use after changing "
        "the embedding model (Phase 6 6b)",
    )
    parser.add_argument(
        "--prune-dupes",
        action="store_true",
        help="Remove duplicate doc chunks (same dedup key) from the live store, "
        "keeping the earliest row of each group. Non-destructive to other entries.",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not any(
        (
            args.golden,
            args.docs,
            args.pdfs,
            args.bundled,
            args.stats,
            args.prune_learned,
            args.reindex,
            args.prune_dupes,
        )
    ):
        parser.print_help()
        return {"golden": 0, "docs": 0, "pdfs": 0}

    # Resolve paths relative to the repo root (where pyproject.toml lives)
    repo_root = Path(__file__).resolve().parent.parent
    dataset_dir = repo_root / "scripts" / "eval" / "dataset"
    docs_dir = repo_root / "docs" / "rag_corpus" / "playwright"
    pdfs_dir = repo_root / "docs" / "rag_corpus" / "lv_docs"

    result: dict[str, object] = {}

    if args.prune_learned:
        pruned = prune_learned()
        result["pruned"] = pruned
        print(f"Pruned {pruned} learned pattern(s) from the RAG store")

    if args.prune_dupes:
        removed = prune_doc_duplicates()
        result["pruned_dupes"] = removed
        print(f"Pruned {removed} duplicate doc chunk(s) from the RAG store")

    if args.golden or args.docs or args.pdfs:
        patterns: list[GoldenPattern] = []
        docs_chunks: list[DocChunk] = []
        pdf_chunks: list[DocChunk] = []

        if args.golden:
            patterns = load_golden_patterns(dataset_dir)

        if args.docs:
            docs_chunks = load_docs(docs_dir)

        if args.pdfs:
            # AI-055: format scope — reject unsupported formats loudly, and
            # collect the per-page report for the ingestion quality summary.
            from src.rag_bundled import (  # noqa: PLC0415 - AI-055 section
                build_summary,
                check_supported_formats,
            )

            # The --pdfs dir is expected to hold PDFs.  Any non-PDF/MD file in
            # it is reported loudly (loud > silent) in the summary rather than
            # silently ignored.  ingest_pdf_directory itself only ingests
            # *.pdf (markdown is handled by --docs from a separate dir).
            all_files = sorted(pdfs_dir.glob("*"))
            _supported, rejected = check_supported_formats(all_files)
            pdf_report: list[tuple[str, int, str, str]] = []
            pdf_chunks = ingest_pdf_directory(
                pdfs_dir,
                ocr_fallback=_build_ocr_fallback(),
                page_report=pdf_report,
            )

            # rebuild_store reports new-vs-present (dedup) per source type
            rebuild_result = rebuild_store(patterns, docs_chunks, pdf_chunks)
            result.update(rebuild_result)

            # AI-055 ingestion quality summary (the trust signal)
            summary = build_summary(
                page_report=pdf_report,
                chunks_new=int(rebuild_result.get("pdfs", 0)),
                chunks_present=int(rebuild_result.get("pdfs_skipped", 0)),
                skipped_formats=rejected,
            )
            result["summary"] = summary
            print()
            print(summary.render())

    if args.bundled:
        result["bundled"] = ensure_bundled_seeded(force=args.force)

    if args.reindex:
        patterns = build_bundled_patterns()
        doc_chunks = build_bundled_docs()
        result["reindex"] = rebuild_store(patterns, doc_chunks)
        # The rebuilt store holds the bundled pack — mark it seeded so the
        # first-run auto-seed stays a no-op.
        _write_marker(bundled_marker_path())
        reindexed = result["reindex"]
        assert isinstance(reindexed, dict)
        print(
            f"Re-indexed RAG store: golden={reindexed.get('golden', 0)} "
            f"docs={reindexed.get('docs', 0)} pdfs={reindexed.get('pdfs', 0)}"
        )

    if args.stats:
        counts = store_stats()
        result["stats"] = counts
        print(
            "RAG store entries: "
            f"golden={counts.get('golden', 0)} "
            f"docs={counts.get('doc', 0)} "
            f"learned={counts.get('learned', 0)} "
            f"total={counts.get('total', 0)}"
        )

    return result


if __name__ == "__main__":
    main()
