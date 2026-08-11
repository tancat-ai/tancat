"""Bundled golden pack + first-run auto-seed (B-036 Phase 2).

Ships with the product so consumers never run ``rag_ingest.py`` by hand:

* **Bundled golden patterns** — all golden keys from
  ``scripts/eval/dataset/eval-*.json`` (eval-001..006 incl. the mock
  sites, whose keys never decay).
* **Bundled doc chunks** — curated Playwright docs from
  ``docs/rag_corpus/playwright/``.

``ensure_bundled_seeded()`` seeds these into the RAG store on first run,
guarded by an idempotent marker file in ``evidence/``. Re-runs are a
no-op; a failure (offline embedder download, corrupt store) propagates
so the caller can degrade gracefully — RAG never blocks generation.

The loaders here are the canonical home for dataset/docs loading;
``scripts/rag_ingest.py`` re-exports them for its power-user CLI.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter
from pathlib import Path

from src.rag_store import (
    DocChunk,
    GoldenPattern,
    MilvusLiteBackend,
    RAGStore,
    SentenceTransformerEmbedder,
)
from src.storage import StorageBackend, get_storage

logger = logging.getLogger(__name__)

# Bumped when the shipped set changes; the marker records the version so
# future releases can detect that a re-seed is warranted.
BUNDLED_PACK_VERSION = 1

_MARKER_FILENAME = ".rag_bundled_seeded.json"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    """Repo root (``pyproject.toml`` lives there)."""
    return Path(__file__).resolve().parent.parent


def bundled_dataset_dir(repo_root: Path | None = None) -> Path:
    """Directory holding the bundled eval golden keys."""
    return (repo_root or _repo_root()) / "scripts" / "eval" / "dataset"


def bundled_docs_dir(repo_root: Path | None = None) -> Path:
    """Directory holding the bundled Playwright doc corpus."""
    return (repo_root or _repo_root()) / "docs" / "rag_corpus" / "playwright"


def bundled_marker_path(storage: StorageBackend | None = None) -> Path:
    """Path to the idempotent seed marker (lives in the evidence dir)."""
    return (storage or get_storage()).evidence_dir() / _MARKER_FILENAME


def build_default_store() -> RAGStore:
    """Build the production RAGStore (lazy embedder + lazy Milvus client).

    Construction is cheap: the ~80 MB embedder model downloads only on the
    first ``embed()`` against a non-empty store.
    """
    embedder = SentenceTransformerEmbedder()
    backend = MilvusLiteBackend(str(get_storage().rag_path()), embedder.dimension)
    return RAGStore(backend, embedder)


# ---------------------------------------------------------------------------
# Bundled golden patterns
# ---------------------------------------------------------------------------


#: Canonical ``host[:port]`` identity for mock datasets whose ``base_url``
#: predates B-047 (all three mocks pointed at :8781). Real sites and
#: lv_insurance derive their identity from ``base_url``. These MUST match the
#: ports ``scripts/synthesize_stories.py`` assigns when it serves the mock
#: sites concurrently (8781 lv_insurance / 8782 banking / 8783 ecommerce).
_MOCK_SITE_IDENTITY: dict[str, str] = {
    "banking_mock": "localhost:8782",
    "ecommerce_mock": "localhost:8783",
}


def _site_identity_hash(site_name: str, base_url: str) -> str:
    """One-way hash of a golden pattern's canonical site identity (B-047).

    Golden patterns are site-scoped so a saucedemo golden cannot award a +20
    bonus while resolving another site. Identity comes from the dataset
    ``base_url`` domain — except the mock datasets whose ``base_url`` predates
    B-047 (all three mocks on :8781); those use the canonical concurrent-serve
    ports. Lazy import: ``src.rag_learn`` imports this module, so importing it
    at module level would be circular.
    """
    from src.rag_learn import domain_from_url, site_hash

    identity = _MOCK_SITE_IDENTITY.get(site_name) or domain_from_url(base_url)
    return site_hash(identity) if identity else ""


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
        site_identity_hash = _site_identity_hash(data.get("site", ""), data.get("base_url", ""))
        for criterion in data.get("golden_resolutions", []):
            for placeholder in criterion.get("placeholders", []):
                patterns.append(
                    GoldenPattern(
                        action=placeholder.get("action", ""),
                        description=placeholder.get("description", ""),
                        expected_locator=placeholder.get("expected_locator", ""),
                        tolerance_selectors=placeholder.get("tolerance_selectors", []),
                        expected_page=placeholder.get("expected_page", ""),
                        site_hash=site_identity_hash,
                    )
                )

    logger.info("Loaded %d golden patterns from %d dataset file(s)", len(patterns), len(json_files))
    return patterns


def build_bundled_patterns(repo_root: Path | None = None) -> list[GoldenPattern]:
    """Load the bundled golden patterns (eval-001..006)."""
    return load_golden_patterns(bundled_dataset_dir(repo_root))


# ---------------------------------------------------------------------------
# Bundled docs
# ---------------------------------------------------------------------------

CHARS_PER_TOKEN = 4  # rough: GPT tokenizers are ~4 chars per token
CHUNK_TARGET_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50


def _estimate_tokens(text: str) -> int:
    """Rough token count: character length / 4."""
    return max(1, len(text) // CHARS_PER_TOKEN)


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


def build_bundled_docs(repo_root: Path | None = None) -> list[DocChunk]:
    """Load the bundled Playwright doc corpus."""
    return load_docs(bundled_docs_dir(repo_root))


# ---------------------------------------------------------------------------
# Idempotent first-run auto-seed
# ---------------------------------------------------------------------------


def _write_marker(marker_path: Path) -> None:
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(
        json.dumps({"version": BUNDLED_PACK_VERSION, "seeded_at": time.strftime("%Y-%m-%dT%H:%M:%S")}),
        encoding="utf-8",
    )
    logger.info("Bundled RAG seed marker written to %s", marker_path)


def ensure_bundled_seeded(
    store: RAGStore | None = None,
    *,
    marker_path: Path | None = None,
    force: bool = False,
) -> dict[str, object]:
    """Seed the RAG store from the bundled pack — idempotent, first-run only.

    Behaviour:

    * Marker present (and not ``force``) → ``{"status": "skipped"}`` — a
      no-op; this is the steady state for every run after the first.
    * Store empty → bundled patterns + docs are added, marker written →
      ``{"status": "seeded", "golden": N, "docs": M}``.
    * Store already populated (e.g. a power user manually ingested) →
      marker written without adding anything → ``{"status": "marked"}``.
    * ``force`` → the bundled pack is (re-)added regardless of marker or
      store contents (an explicit power-user action, e.g. after a prune).
      Repeated forced runs duplicate entries (Milvus auto-ids) — harmless
      to scoring (a direct match returns once) but prefer a ``--golden``
      rebuild for a clean store.

    Failures propagate to the caller (the orchestrator wraps this in a
    try/except so RAG can never block generation).

    Args:
        store: Injectable store (tests); defaults to the production store.
        marker_path: Injectable marker path (tests); defaults to evidence dir.
        force: Re-seed even when the marker exists or the store is populated.
    """
    marker = marker_path or bundled_marker_path()
    if marker.exists() and not force:
        logger.debug("Bundled RAG pack already seeded (marker: %s) — skipping", marker)
        return {"status": "skipped", "golden": 0, "docs": 0, "version": BUNDLED_PACK_VERSION}

    if store is None:
        store = build_default_store()

    if store.is_empty or force:
        patterns = build_bundled_patterns()
        doc_chunks = build_bundled_docs()
        golden = store.add_patterns(patterns)
        docs = store.add_docs(doc_chunks)
        status = "seeded"
        logger.info(
            "Auto-seeded bundled RAG pack: %d golden patterns, %d doc chunks",
            golden,
            docs,
        )
    else:
        golden = 0
        docs = 0
        status = "marked"
        logger.info("RAG store already populated — marking bundled pack as seeded")

    _write_marker(marker)
    return {"status": status, "golden": golden, "docs": docs, "version": BUNDLED_PACK_VERSION}


# ---------------------------------------------------------------------------
# Store diagnostics (AI-035 store management carry-over)
# ---------------------------------------------------------------------------


def store_stats(store: RAGStore | None = None) -> dict[str, int]:
    """Per-``entry_type`` counts for the store (golden/doc/learned)."""
    store = store or build_default_store()
    counts = store.counts_by_type()
    totals: Counter[str] = Counter(counts)
    totals["total"] = sum(counts.values())
    return dict(totals)


def prune_learned(store: RAGStore | None = None) -> int:
    """Remove learned patterns, keep golden patterns and doc chunks.

    Returns the number of entries deleted. With no learned patterns yet
    (B-036 Phase 3 not shipped) this is a no-op — the CLI exists now so
    consumers have the reset lever before learning lands.
    """
    store = store or build_default_store()
    deleted = store.delete_learned()
    logger.info("Pruned %d learned pattern(s) from the RAG store", deleted)
    return deleted
