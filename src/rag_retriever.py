"""RAG Retriever — bridges RAGStore into the resolution pipeline.

Provides a resolver-friendly API: takes a placeholder description + action
type, queries the vector store, and returns a list of
``RetrievedPattern`` objects.  The ``scoring_bonus_for`` method
evaluates whether a DOM element matches a retrieved golden pattern
(by selector overlap), returning the bonus amount to add.

Usage::

    from src.rag_retriever import RAGRetriever
    from src.rag_store import RAGStore, MilvusLiteBackend, SentenceTransformerEmbedder
    from src.storage import get_storage

    embedder = SentenceTransformerEmbedder()
    backend = MilvusLiteBackend(str(get_storage().rag_path()), embedder.dimension)
    store = RAGStore(backend, embedder)
    retriever = RAGRetriever(store)

    patterns = retriever.retrieve("Add to cart button", action_type="CLICK")
    for elem in candidates:
        bonus = retriever.scoring_bonus_for(elem, patterns)
        # bonus is GOLDEN_PATTERN_BONUS (20) if selector matches,
        # scaled by pattern confidence if partial match.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from src.rag_store import EmbeddingMismatchError, RetrievedPattern

if TYPE_CHECKING:
    from src.rag_store import RAGStore

logger = logging.getLogger(__name__)


class RAGRetriever:
    """Retrieval bridge between RAGStore and the resolution pipeline.

    When the store is ``None``, every method returns empty/no-op —
    this is the "RAG disabled" path and has zero overhead.

    B-036 Phase 1 (2026-08-03): the retriever is now built by default
    (always-on). Any failure inside the store or embedder — model
    download failure, offline machine, corrupt DB — degrades to an
    empty result list rather than raising, so RAG can never block
    generation. A warning is logged on the first failure only.
    """

    def __init__(self, store: RAGStore | None) -> None:
        """Initialise with an optional RAGStore.

        Args:
            store: An initialised ``RAGStore`` or ``None`` to disable RAG.
        """
        self._store = store
        self._warned_failure = False

    @property
    def enabled(self) -> bool:
        """Whether RAG is enabled (store is not ``None`` and not empty)."""
        if self._store is None:
            return False
        try:
            return not self._store.is_empty
        except EmbeddingMismatchError:
            # Logged loudly on the first retrieve() attempt — the mismatch is
            # a config/data error, not a silent degradation.
            return False

    def retrieve(
        self,
        description: str,
        *,
        action_type: str = "",
        k: int = 5,
        min_confidence: float = 0.6,
    ) -> list[RetrievedPattern]:
        """Retrieve golden patterns and doc chunks for a placeholder.

        Returns an empty list when RAG is disabled or the store is empty,
        and when the underlying store or embedder fails (graceful
        degradation — RAG never blocks generation). An embedder mismatch
        is logged at ERROR with the reindex fix — never silently.
        """
        if self._store is None:
            return []
        query = f"{action_type}: {description}" if action_type else description
        try:
            return self._store.retrieve(
                query,
                action_type=action_type,
                k=k,
                min_confidence=min_confidence,
            )
        except EmbeddingMismatchError as exc:
            logger.error(
                "RAG store embedding-model mismatch — refusing retrieval to prevent "
                "silent corruption. Re-embed with: `python scripts/rag_ingest.py "
                "--reindex` (%s)",
                exc,
            )
            return []
        except Exception:
            if not self._warned_failure:
                logger.warning(
                    "RAG retrieval failed — degrading to no patterns (resolution proceeds without RAG bonus)",
                    exc_info=True,
                )
                self._warned_failure = True
            return []

    def pattern_usage(
        self,
        patterns: list[RetrievedPattern],
        site_hash: str,
        element_selector: str,
    ) -> list[dict[str, Any]]:
        """Report per-pattern usage for a resolved winner element.

        Mirrors the bonus logic in ``scoring_bonus_for`` / ``PlaceholderScorer``
        but returns **all** patterns (not just the first match) so a lab run
        can observe, for each retrieved pattern:

        * ``eligible`` — did the site gate pass for this run's site identity?
        * ``matched`` — did the pattern selector hit the winning element?
        * ``bonus`` — points it would contribute to the winner's score.

        An empty ``element_selector`` yields eligibility-only records (``matched``
        / ``bonus`` are always ``False`` / ``0``), which is how the retrieval
        diagnostic reuses this for correlation with the usage line.
        """
        from src.placeholder_scorers import PlaceholderScorer

        site_hash = site_hash or ""
        element_selector = (element_selector or "").strip()
        records: list[dict[str, Any]] = []

        for pattern in patterns:
            if not pattern.selector:
                records.append(
                    {
                        "description": str(pattern.description),
                        "source": str(pattern.source),
                        "site_hash": str(pattern.site_hash),
                        "eligible": False,
                        "matched": False,
                        "bonus": 0,
                    }
                )
                continue

            source = str(pattern.source)
            pattern_site = str(pattern.site_hash)
            eligible = False
            bonus = 0

            if source == "golden":
                # Empty site_hash = legacy, site-agnostic → eligible everywhere.
                eligible = not (pattern_site and pattern_site != site_hash)
                if eligible and element_selector:
                    if pattern.selector == element_selector:
                        bonus = int(PlaceholderScorer.GOLDEN_PATTERN_BONUS * pattern.confidence)
                    elif element_selector in pattern.selector or pattern.selector in element_selector:
                        bonus = int(PlaceholderScorer.GOLDEN_PATTERN_BONUS * 0.5 * pattern.confidence)
            elif source == "learned" and site_hash and pattern_site == site_hash:
                eligible = True
                if element_selector:
                    if pattern.selector == element_selector:
                        bonus = int(PlaceholderScorer.SAME_SITE_LEARNED_BONUS * pattern.confidence)
                    elif element_selector in pattern.selector or pattern.selector in element_selector:
                        bonus = int(PlaceholderScorer.SAME_SITE_LEARNED_BONUS * 0.5 * pattern.confidence)

            records.append(
                {
                    "description": str(pattern.description),
                    "source": source,
                    "site_hash": pattern_site,
                    "eligible": eligible,
                    "matched": bonus > 0,
                    "bonus": bonus,
                }
            )

        return records

    def scoring_bonus_for(
        self,
        element: dict[str, str],
        patterns: list[RetrievedPattern],
        site_hash: str = "",
    ) -> float:
        """Compute a scoring bonus for an element based on pattern overlap.

        Delegates the gate+match+bonus logic to :meth:`pattern_usage` and
        returns the first positive bonus (first-match-wins). This keeps the
        reported bonus byte-for-byte consistent with the value
        ``PlaceholderScorer`` actually applies to the winning element.

        Returns ``GOLDEN_PATTERN_BONUS`` (20) for a direct golden selector
        match, scaled by pattern confidence for partial (tolerance) matches —
        site-scoped to the golden's own site when seeded with a ``site_hash``
        (B-047 residual). Same-site learned patterns (``source == "learned"``
        and matching ``site_hash``) earn ``SAME_SITE_LEARNED_BONUS`` (5)
        instead — cross-site learned patterns earn nothing (they could be
        wrong here). Returns 0 when no patterns match.

        The bonus is designed to tip the scale between similarly-scored
        candidates (e.g. two elements scoring ~25 each) without overriding
        strong structural matches (+80) or visibility penalties (-40).
        """
        if not patterns:
            return 0.0

        element_selector = str(element.get("selector", "")).strip()
        if not element_selector:
            return 0.0

        for rec in self.pattern_usage(patterns, site_hash, element_selector):
            if rec["bonus"] > 0:
                return float(rec["bonus"])

        return 0.0
