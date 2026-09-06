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
from collections.abc import Sequence
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
    backend = MilvusLiteBackend(
        str(get_storage().rag_path()),
        embedder.dimension,
        embedder_identity=embedder.identity,
    )
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
    """Seed the RAG store from the bundled pack — idempotent, self-healing.

    Behaviour (B-048 marker truth: the marker means "seeded AND the store
    holds golden patterns", never "seeded once ever"):

    * Marker present **and** the store holds golden patterns (and not
      ``force``) → ``{"status": "skipped"}`` — a no-op; the steady state.
    * Marker present but the store is pattern-less (``golden == 0`` — the
      AI-059 lab-wipe signature: the marker survived an external wipe while
      the store lost its golden pack) → the bundled pack is re-added and the
      marker refreshed → ``{"status": "reseeded", ...}``. A measurement can
      never silently run against a pattern-less store again.
    * No marker, empty store → bundled patterns + docs added, marker written
      → ``{"status": "seeded", "golden": N, "docs": M}``.
    * No marker, store already populated with golden patterns (e.g. a power
      user manually ingested) → marker written without adding anything →
      ``{"status": "marked"}``.
    * ``force`` → the bundled pack is (re-)added regardless of marker,
      golden count, or store contents (an explicit power-user action, e.g.
      after a prune). Repeated forced runs duplicate entries (Milvus
      auto-ids) — harmless to scoring (a direct match returns once) but
      prefer a ``--golden`` rebuild for a clean store.

    Failures propagate to the caller (the orchestrator wraps this in a
    try/except so RAG can never block generation).

    Args:
        store: Injectable store (tests); defaults to the production store.
        marker_path: Injectable marker path (tests); defaults to evidence dir.
        force: Re-seed even when the marker exists and the store is populated.
    """
    marker = marker_path or bundled_marker_path()
    if store is None:
        store = build_default_store()

    counts = store.counts_by_type() or {}
    golden_count = int(counts.get("golden", 0) or 0)

    if marker.exists() and not force and golden_count > 0:
        logger.debug("Bundled RAG pack already seeded (marker: %s) — skipping", marker)
        return {"status": "skipped", "golden": 0, "docs": 0, "version": BUNDLED_PACK_VERSION}

    # Marker survives, golden pack gone: the B-048 wipe signature. Re-seed
    # and surface it as "reseeded" so callers/logs can flag the anomaly.
    stale_marker = marker.exists() and not force and golden_count == 0

    if store.is_empty or force or golden_count == 0:
        patterns = build_bundled_patterns()
        doc_chunks = build_bundled_docs()
        golden = store.add_patterns(patterns)
        docs, _docs_skipped = store.add_docs(doc_chunks)
        status = "reseeded" if stale_marker else "seeded"
        logger.info(
            "%s bundled RAG pack: %d golden patterns, %d doc chunks",
            "Re-seeded (stale seed marker on a pattern-less store — B-048)" if stale_marker else "Auto-seeded",
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


# ---------------------------------------------------------------------------
# Ingestion quality summary (AI-055) — the trust signal
# ---------------------------------------------------------------------------
#
# Ingestion is the trust differentiator ("your generator learns *your*
# domain, on *your* hardware, no egress").  The customer needs to know what
# happened to their docs.  These helpers build a structured summary from
# in-memory ingestion data (per-doc outcome, page OCR/skip counts, dedup
# new-vs-present, actionable re-run suggestion).  Pure / no I/O — trivially
# testable (hermetic, no GPU, no network).

from dataclasses import dataclass, field  # noqa: E402 - AI-055 section

# Format scope (AI-055 §3): v1 promises pdf + md.  Unknown formats are
# rejected loudly (loud > silent).  ``.txt`` is deliberately *not* in v1.
SUPPORTED_FORMATS: tuple[str, ...] = (".pdf", ".md")


@dataclass
class DocSummary:
    """Per-document ingestion outcome.

    ``skipped_pages`` records, for each skipped page, the ``(page_number,
    reason)`` pair where ``reason`` is ``"no_engine"`` (the OCR engine is not
    installed — the ``[ocr]`` extra is missing), ``"ocr_no_text"`` (the OCR ran
    but could not read the page), or ``"ocr_failed"`` (the OCR hook raised).
    This is what lets the summary produce a cause-differentiated warning —
    a skipped page in a bigger pack must not hide behind an overall green
    result, and a ``no_engine`` skip is an easy, user-fixable problem.
    """

    source: str
    outcome: str  # "full" | "partial" | "skipped"
    pages_total: int = 0
    pages_text: int = 0  # pages read via PyMuPDF text
    pages_ocr: int = 0  # pages extracted via the OCR fallback
    pages_skipped: int = 0  # image-only pages with no OCR text
    skipped_pages: list[tuple[int, str]] = field(default_factory=list)
    skip_reason: str = ""


@dataclass
class IngestionSummary:
    """Aggregated ingestion quality summary for a CLI run."""

    docs: list[DocSummary] = field(default_factory=list)
    chunks_new: int = 0
    chunks_present: int = 0  # dedup-skipped (already in the store)
    skipped_formats: list[str] = field(default_factory=list)
    suggestion: str = ""

    @property
    def docs_total(self) -> int:
        return len(self.docs)

    @property
    def docs_full(self) -> int:
        return sum(1 for d in self.docs if d.outcome == "full")

    @property
    def docs_partial(self) -> int:
        return sum(1 for d in self.docs if d.outcome == "partial")

    @property
    def chunks_total(self) -> int:
        return self.chunks_new + self.chunks_present

    def render(self) -> str:
        """Human-readable multi-line summary (CLI output).

        Uses plain-text markers (``[OK]`` / ``[WARN]``) rather than emoji so the
        output renders on every terminal, including Windows cp1252 consoles
        (an emoji like ``\u2705`` raises ``UnicodeEncodeError`` there).
        """
        lines: list[str] = []
        lines.append(f"Ingestion summary ({self.docs_total} docs):")
        if self.docs_full:
            lines.append(f"  [OK]   {self.docs_full} docs fully ingested -> {self.chunks_new} new chunks")

        # --- Skipped pages, cause-differentiated (the trust signal) ---
        # A page that was skipped (image-only, no OCR text) must not hide behind
        # an overall green result.  The cause is differentiated so the user knows
        # the fix: a "no_engine" skip is easy (install the [ocr] extra); an
        # "ocr_no_text" skip needs a clearer scan or a higher tier.
        skipped_docs = [d for d in self.docs if d.pages_skipped > 0]
        for d in skipped_docs:
            reason_counts: dict[str, int] = {}
            for _page, reason in d.skipped_pages:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            parts: list[str] = []
            pages_label = "page" if d.pages_skipped == 1 else "pages"
            if "no_engine" in reason_counts:
                parts.append(f"{reason_counts['no_engine']} {pages_label} (OCR engine NOT installed)")
            if "ocr_no_text" in reason_counts:
                parts.append(f"{reason_counts['ocr_no_text']} {pages_label} (OCR ran but could not read)")
            if "ocr_failed" in reason_counts:
                parts.append(f"{reason_counts['ocr_failed']} {pages_label} (OCR failed)")
            detail = ", ".join(parts) if parts else f"{d.pages_skipped} {pages_label}"
            lines.append(
                f"  [WARN] {d.source}: {detail} -> NOT digested "
                f"({d.pages_text} text, {d.pages_ocr} OCR'd of {d.pages_total})"
            )
            # Easy fix: surface the exact install command + docs when the engine
            # is the cause, so a user who *thinks* the doc was digested knows the
            # one-line fix.  This is the loud warning your use case needs.
            if "no_engine" in reason_counts:
                lines.append("         Fix (easy, you can apply this): install the CPU OCR tier with")
                lines.append("           uv sync --extra ocr")
                lines.append("         Then re-run: python scripts/rag_ingest.py --pdfs")
                lines.append("         Docs: see the [ocr] extra in pyproject.toml / FEATURE_SPEC_ingestion_local.md")
        for name in self.skipped_formats:
            lines.append(f"  [WARN] 1 doc skipped (unsupported format: {name})")
        if self.chunks_present:
            lines.append(
                f"  Store: {self.chunks_total} doc chunks "
                f"({self.chunks_new} new, {self.chunks_present} already present / deduped)"
            )
        else:
            lines.append(f"  Store: {self.chunks_total} doc chunks ({self.chunks_new} new)")
        if self.suggestion:
            lines.append(f"  Suggested: {self.suggestion}")
        return "\n".join(lines)


def doc_outcome_from_pages(pages_total: int, pages_text: int, pages_ocr: int, pages_skipped: int) -> str:
    """Derive a per-doc outcome from its page counts.

    * ``full``    — every page was read (text or OCR), none skipped.
    * ``partial`` — at least one page was skipped (no text/OCR).
    * ``skipped`` — no pages were read at all (unreadable doc).

    A doc where all pages were OCR'd (no native text) is still ``full`` —
    OCR is a successful extraction, not a degradation.
    """
    if pages_total == 0 or (pages_text + pages_ocr) == 0:
        return "skipped"
    if pages_skipped > 0:
        return "partial"
    return "full"


def doc_summaries_from_page_report(
    page_report: list[tuple[str, int, str, str]],
) -> list[DocSummary]:
    """Build per-doc summaries from the per-page report
    (``(source, page, outcome, reason)``) collected by
    :func:`src.pdf_ingest.ingest_pdf_directory`.  For a skipped page the
    ``reason`` is carried through to ``DocSummary.skipped_pages`` so the
    summary can produce a cause-differentiated warning.
    """
    by_doc: dict[str, list[tuple[int, str, str]]] = {}
    for source, page, outcome, reason in page_report:
        by_doc.setdefault(source, []).append((page, outcome, reason))

    summaries: list[DocSummary] = []
    for source, pages in by_doc.items():
        text = sum(1 for _p, o, _r in pages if o == "text")
        ocr = sum(1 for _p, o, _r in pages if o == "ocr")
        skipped = sum(1 for _p, o, _r in pages if o == "skipped")
        total = len(pages)
        outcome = doc_outcome_from_pages(total, text, ocr, skipped)
        skip_details = [(p, r) for p, o, r in pages if o == "skipped"]
        summaries.append(
            DocSummary(
                source=source,
                outcome=outcome,
                pages_total=total,
                pages_text=text,
                pages_ocr=ocr,
                pages_skipped=skipped,
                skipped_pages=skip_details,
            )
        )
    return summaries


def check_supported_formats(paths: Sequence[str | Path]) -> tuple[list[str | Path], list[str]]:
    """Split a sequence of doc paths into (supported, rejected) by format scope.

    ``supported`` = paths whose extension is in :data:`SUPPORTED_FORMATS`
    (pdf + md).  ``rejected`` = filenames of unsupported formats (reported
    loudly, loud > silent).  Case-insensitive on extension.

    Accepts a ``Sequence`` (not ``list``) so a covariant ``list[Path]`` (e.g.
    from ``Path.glob``) is accepted without a mypy invariance error.
    """
    supported: list[str | Path] = []
    rejected: list[str] = []
    for p in paths:
        ext = Path(p).suffix.lower()
        if ext in SUPPORTED_FORMATS:
            supported.append(p)
        else:
            rejected.append(Path(p).name)
    return supported, rejected


def build_summary(
    page_report: list[tuple[str, int, str, str]],
    chunks_new: int,
    chunks_present: int,
    unreadable_docs: list[str] | None = None,
    skipped_formats: list[str] | None = None,
) -> IngestionSummary:
    """Build an :class:`IngestionSummary` from in-memory ingestion data."""
    docs = doc_summaries_from_page_report(page_report)
    for name in unreadable_docs or []:
        docs.append(DocSummary(source=name, outcome="skipped", skip_reason="unreadable / no pages"))
    skipped_formats = list(skipped_formats or [])

    # The actionable suggestion is cause-driven.  A "no_engine" skip is an easy,
    # user-fixable install; an "ocr_no_text" skip needs a clearer scan / higher
    # tier.  The per-doc [WARN] lines (in render()) carry the cause; the
    # top-level suggestion names the docs and the right fix.
    has_skipped_pages = any(d.pages_skipped > 0 for d in docs)
    suggestion = ""
    if has_skipped_pages:
        any_no_engine = any(r == "no_engine" for d in docs for _p, r in d.skipped_pages)
        skipped_names = ", ".join(d.source for d in docs if d.pages_skipped > 0)[:200]
        if any_no_engine:
            suggestion = f"install the CPU OCR tier (uv sync --extra ocr) and re-run for: {skipped_names}"
        else:
            suggestion = f"re-run with a clearer scan or --ocr-tier high-accuracy for: {skipped_names}"

    return IngestionSummary(
        docs=docs,
        chunks_new=chunks_new,
        chunks_present=chunks_present,
        skipped_formats=skipped_formats,
        suggestion=suggestion,
    )
