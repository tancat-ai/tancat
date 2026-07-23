"""RAG Ingestion CLI — build/rebuild the vector store.

Usage::

    python scripts/rag_ingest.py --golden --docs --pdfs
    python scripts/rag_ingest.py --golden --docs
    python scripts/rag_ingest.py --pdfs

Ingests knowledge sources into the RAG vector store:

1. **Golden patterns** from ``scripts/eval/dataset/`` — verified
   placeholder → selector mappings (4 sites, 43 placeholders).
2. **Playwright documentation** from ``docs/rag_corpus/playwright/`` —
   curated markdown files chunked by heading.
3. **PDF domain docs** from ``docs/rag_corpus/lv_docs/`` — insurance
   policy PDFs parsed with PyMuPDF and chunked by heading.

The store file is written to ``<workspace>/evidence/rag_store.db``
(via ``get_storage().rag_path()``).

Run offline — no LLM or browser needed.  SentenceTransformer downloads
the embedding model on first use (~80 MB, cached by Hugging Face).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path

from src.pdf_ingest import ingest_pdf_directory
from src.rag_store import (
    DocChunk,
    GoldenPattern,
    MilvusLiteBackend,
    RAGStore,
    SentenceTransformerEmbedder,
)
from src.storage import get_storage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token estimation (fast, offline — no dependency needed)
# ---------------------------------------------------------------------------

CHARS_PER_TOKEN = 4  # rough: GPT tokenizers are ~4 chars per token
CHUNK_TARGET_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50


def _estimate_tokens(text: str) -> int:
    """Rough token count: character length / 4."""
    return max(1, len(text) // CHARS_PER_TOKEN)


# ---------------------------------------------------------------------------
# Golden pattern loading
# ---------------------------------------------------------------------------


def load_golden_patterns(dataset_dir: Path) -> list[GoldenPattern]:
    """Parse golden eval dataset JSON files into GoldenPattern entries.

    Each dataset file contains ``golden_resolutions`` — a list of
    criterion-level objects, each with a ``placeholders`` array.
    """

    patterns: list[GoldenPattern] = []
    json_files = sorted(dataset_dir.glob("eval-*.json"))
    if not json_files:
        logger.warning("No eval-*.json files found in %s", dataset_dir)
        return patterns

    for fpath in json_files:
        data = json.loads(fpath.read_text(encoding="utf-8"))
        for criterion in data.get("golden_resolutions", []):
            for placeholder in criterion.get("placeholders", []):
                patterns.append(
                    GoldenPattern(
                        action=placeholder.get("action", ""),
                        description=placeholder.get("description", ""),
                        expected_locator=placeholder.get("expected_locator", ""),
                        tolerance_selectors=placeholder.get("tolerance_selectors", []),
                        expected_page=placeholder.get("expected_page", ""),
                    )
                )

    logger.info("Loaded %d golden patterns from %d dataset file(s)", len(patterns), len(json_files))
    return patterns


# ---------------------------------------------------------------------------
# Playwright docs chunking
# ---------------------------------------------------------------------------


def chunk_markdown_file(filepath: Path) -> list[DocChunk]:
    """Split a markdown file into chunks at ``##`` heading boundaries.

    Each chunk targets ~500 tokens with ~50 tokens of overlap between
    consecutive chunks.  The heading path (doc title + section headings)
    is stored as metadata for prompt citations.
    """

    text = filepath.read_text(encoding="utf-8")
    source = filepath.name
    chunks: list[DocChunk] = []

    # Extract document title from the first # heading
    doc_title = source
    title_match = re.match(r"^#\s+(.+)$", text, re.MULTILINE)
    if title_match:
        doc_title = title_match.group(1).strip()

    # Split on ## boundaries
    sections = re.split(r"\n(?=##\s)", text)

    # First "section" before any ## is the preamble (title + intro).
    # If it only contains a bare # Title and nothing else, skip it — it
    # adds no useful retrieval signal beyond what subsequent sections carry.
    sections = [s.strip() for s in sections if s.strip()]
    sections = [s for s in sections if not re.match(r"^# .+$", s.strip())]

    for section in sections:
        # Extract the section heading
        heading_match = re.match(r"^##\s+(.+)$", section, re.MULTILINE)
        section_heading = heading_match.group(1).strip() if heading_match else ""

        heading_path = f"{doc_title} > {section_heading}" if section_heading else doc_title

        # If the section fits within target, use as-is
        if _estimate_tokens(section) <= CHUNK_TARGET_TOKENS:
            chunks.append(
                DocChunk(
                    text=section,
                    source=source,
                    heading_path=heading_path,
                )
            )
            continue

        # Otherwise, split the section further (at paragraph boundaries)
        paragraphs = re.split(r"\n\n+", section)
        current_text = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if _estimate_tokens(current_text + para) > CHUNK_TARGET_TOKENS and current_text:
                chunks.append(
                    DocChunk(
                        text=current_text.strip(),
                        source=source,
                        heading_path=heading_path,
                    )
                )
                # Overlap: keep the last ~50 tokens worth of text
                overlap_chars = CHUNK_OVERLAP_TOKENS * CHARS_PER_TOKEN
                current_text = current_text[-overlap_chars:] + "\n\n" + para
            else:
                current_text = current_text + "\n\n" + para if current_text else para

        if current_text.strip():
            chunks.append(
                DocChunk(
                    text=current_text.strip(),
                    source=source,
                    heading_path=heading_path,
                )
            )

    return chunks


def load_docs(docs_dir: Path) -> list[DocChunk]:
    """Load and chunk all markdown files from the docs directory."""

    all_chunks: list[DocChunk] = []
    md_files = sorted(docs_dir.glob("*.md"))
    if not md_files:
        logger.warning("No .md files found in %s", docs_dir)
        return all_chunks

    for fpath in md_files:
        chunks = chunk_markdown_file(fpath)
        all_chunks.extend(chunks)
        logger.info(
            "  %s → %d chunk(s)",
            fpath.name,
            len(chunks),
        )

    logger.info("Loaded %d doc chunks from %d file(s)", len(all_chunks), len(md_files))
    return all_chunks


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

    # Delete existing store if present (Milvus Lite creates a directory)
    import shutil

    try:
        shutil.rmtree(store_path)
    except FileNotFoundError, PermissionError, OSError:
        pass

    backend = MilvusLiteBackend(store_path, embedder.dimension)
    store = RAGStore(backend, embedder)

    result: dict[str, int] = {"golden": 0, "docs": 0, "pdfs": 0}

    if patterns:
        result["golden"] = store.add_patterns(patterns)
        logger.info("Ingested %d golden patterns", result["golden"])

    if docs:
        result["docs"] = store.add_docs(docs)
        logger.info("Ingested %d doc chunks", result["docs"])

    if pdfs:
        result["pdfs"] = store.add_docs(pdfs)
        logger.info("Ingested %d pdf chunks", result["pdfs"])

    logger.info("Store rebuilt at %s (total entries: %d)", store_path, backend.count())
    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> dict[str, int]:
    """Run the ingestion CLI.

    Returns the count summary dict so tests can verify output.
    """

    parser = argparse.ArgumentParser(
        description="Rebuild the RAG vector store from golden patterns and Playwright docs.",
    )
    parser.add_argument(
        "--golden",
        action="store_true",
        help="Ingest golden patterns from scripts/eval/dataset/",
    )
    parser.add_argument(
        "--docs",
        action="store_true",
        help="Ingest Playwright docs from docs/rag_corpus/playwright/",
    )
    parser.add_argument(
        "--pdfs",
        action="store_true",
        help="Ingest PDF domain docs from docs/rag_corpus/lv_docs/",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not args.golden and not args.docs and not args.pdfs:
        parser.print_help()
        return {"golden": 0, "docs": 0, "pdfs": 0}

    # Resolve paths relative to the repo root (where pyproject.toml lives)
    repo_root = Path(__file__).resolve().parent.parent
    dataset_dir = repo_root / "scripts" / "eval" / "dataset"
    docs_dir = repo_root / "docs" / "rag_corpus" / "playwright"
    pdfs_dir = repo_root / "docs" / "rag_corpus" / "lv_docs"

    patterns: list[GoldenPattern] = []
    docs_chunks: list[DocChunk] = []
    pdf_chunks: list[DocChunk] = []

    if args.golden:
        patterns = load_golden_patterns(dataset_dir)

    if args.docs:
        docs_chunks = load_docs(docs_dir)

    if args.pdfs:
        pdf_chunks = ingest_pdf_directory(pdfs_dir)

    return rebuild_store(patterns, docs_chunks, pdf_chunks)


if __name__ == "__main__":
    main()
