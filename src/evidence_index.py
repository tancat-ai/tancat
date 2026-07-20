"""Evidence index — SQLite-backed search, filter & export metadata.

Indexes ``.evidence.json`` sidecar metadata into the existing
``evidence/run_results.sqlite`` database (AI-012).  Powers the in-tool
search UI, faceted filters, and CSV/NDJSON/JUnit exports (AI-028).

Typical usage::

    from src.evidence_index import EvidenceIndex

    index = EvidenceIndex()
    count = index.build_or_refresh()
    results = index.search(query="dress", status="failed")
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.sqlite_persistence import SQLitePersistence

if TYPE_CHECKING:
    from collections.abc import Sequence


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class EvidenceSearchResult:
    """A single evidence sidecar returned by :meth:`EvidenceIndex.search`."""

    sidecar_path: str
    test_name: str
    condition_ref: str
    story_ref: str
    status: str
    page_url: str
    test_package: str
    matched_field: str  # which column contained the search query
    indexed_at: str = ""  # ISO-8601 when this row was last indexed


@dataclass
class EvidenceFilterOptions:
    """Distinct values available for faceted filter dropdowns."""

    statuses: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    condition_prefixes: list[str] = field(default_factory=list)
    story_refs: list[str] = field(default_factory=list)
    step_types: list[str] = field(default_factory=list)
    total_indexed: int = 0
    last_refreshed: str | None = None


# ---------------------------------------------------------------------------
# EvidenceIndex
# ---------------------------------------------------------------------------


class EvidenceIndex:
    """Indexes evidence sidecar metadata into SQLite for fast search/filter.

    Uses the existing ``SQLitePersistence`` singleton.  The ``evidence_index``
    table is created by ``SQLitePersistence._create_schema()`` on first
    initialisation — no separate migration step needed.
    """

    # Fields extracted from each sidecar for search indexing
    _SEARCHABLE_FIELDS = (
        "test_name",
        "condition_ref",
        "story_ref",
        "page_url",
        "step_labels",
    )

    def __init__(self, db: SQLitePersistence | None = None) -> None:
        self._db = db or SQLitePersistence()
        self._conn = self._db._conn  # internal access for direct queries
        self._base_dir: Path | None = None  # set by build_or_refresh

    # ------------------------------------------------------------------
    # Build / refresh
    # ------------------------------------------------------------------

    def build_or_refresh(
        self,
        base_dir: Path | None = None,
        force: bool = False,
    ) -> int:
        """Scan all evidence sidecars and upsert into ``evidence_index``.

        Parameters
        ----------
        base_dir:
            Root directory to scan (default: storage singleton's
            ``generated_tests_dir()``).
        force:
            If ``True``, re-read every sidecar regardless of ``file_mtime``.

        Returns
        -------
        int
            Number of sidecars indexed (new or updated).
        """
        if base_dir is None:
            from src.storage import get_storage

            base_dir = get_storage().generated_tests_dir()

        self._base_dir = base_dir  # remember for path resolution

        now = datetime.now(UTC).isoformat()
        indexed = 0

        for sidecar_path in self._find_sidecars(base_dir):
            abs_path = base_dir / sidecar_path
            try:
                file_mtime = abs_path.stat().st_mtime
            except OSError:
                continue

            if not force and not self._is_stale(sidecar_path, file_mtime):
                continue

            data = self._read_sidecar(abs_path)
            if data is None:
                continue

            self._upsert_sidecar(sidecar_path, data, file_mtime, now, base_dir)
            indexed += 1

        return indexed

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str = "",
        status: str | None = None,
        url_domain: str | None = None,
        condition_prefix: str | None = None,
        story_ref: str | None = None,
        step_type: str | None = None,
        limit: int = 100,
    ) -> list[EvidenceSearchResult]:
        """Full-text search across evidence metadata.

        Parameters
        ----------
        query:
            Free-text search.  Matched against ``test_name``, ``condition_ref``,
            ``story_ref``, ``page_url``, and ``step_labels`` via SQL ``LIKE``.
        status:
            Optional filter — ``"passed"`` or ``"failed"``.
        url_domain:
            Optional domain prefix filter (e.g. ``"automationexercise.com"``).
        condition_prefix:
            Optional prefix filter on ``condition_ref`` (e.g. ``"TC01"``).
        story_ref:
            Optional exact story reference match.
        step_type:
            Optional step type filter (``"navigate"``, ``"click"``,
            ``"fill"``, ``"assertion"``, ``"select"``).
        limit:
            Maximum results to return.
        """
        where_clauses: list[str] = []
        params: list[str] = []

        # Full-text search
        if query:
            like = f"%{query}%"
            clauses = " OR ".join(f"{f} LIKE ?" for f in self._SEARCHABLE_FIELDS)
            where_clauses.append(f"({clauses})")
            params.extend([like] * len(self._SEARCHABLE_FIELDS))

        # Faceted filters
        if status is not None:
            where_clauses.append("status = ?")
            params.append(status)

        if url_domain is not None:
            where_clauses.append("page_url LIKE ?")
            params.append(f"%{url_domain}%")

        if condition_prefix is not None:
            where_clauses.append("condition_ref LIKE ?")
            params.append(f"{condition_prefix}%")

        if story_ref is not None:
            where_clauses.append("story_ref = ?")
            params.append(story_ref)

        if step_type is not None:
            where_clauses.append("step_types LIKE ?")
            params.append(f"%{step_type}%")

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        sql = f"""
            SELECT * FROM evidence_index
            {where_sql}
            ORDER BY file_mtime DESC
            LIMIT ?
        """
        params.append(str(limit))

        rows = self._conn.execute(sql, params).fetchall()

        return [
            EvidenceSearchResult(
                sidecar_path=row["sidecar_path"],
                test_name=row["test_name"],
                condition_ref=row["condition_ref"] or "",
                story_ref=row["story_ref"] or "",
                status=row["status"],
                page_url=row["page_url"] or "",
                test_package=row["test_package"],
                indexed_at=row["indexed_at"] or "",
                matched_field=self._resolve_matched_field(query, row) if query else "",
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Filter options
    # ------------------------------------------------------------------

    def get_filter_options(self) -> EvidenceFilterOptions:
        """Return distinct values for faceted filter dropdowns."""
        statuses = [
            r[0] for r in self._conn.execute("SELECT DISTINCT status FROM evidence_index ORDER BY status").fetchall()
        ]

        domains_raw: list[str] = [
            r[0]
            for r in self._conn.execute(
                "SELECT DISTINCT page_url FROM evidence_index WHERE page_url IS NOT NULL"
            ).fetchall()
        ]
        domains = sorted({self._extract_domain(u) for u in domains_raw if u})

        condition_raw: list[str] = [
            r[0]
            for r in self._conn.execute(
                "SELECT DISTINCT condition_ref FROM evidence_index "
                "WHERE condition_ref IS NOT NULL AND condition_ref != '' "
                "ORDER BY condition_ref"
            ).fetchall()
        ]
        condition_prefixes = sorted({self._extract_prefix(c) for c in condition_raw if c})

        story_refs = [
            r[0]
            for r in self._conn.execute(
                "SELECT DISTINCT story_ref FROM evidence_index "
                "WHERE story_ref IS NOT NULL AND story_ref != '' "
                "ORDER BY story_ref"
            ).fetchall()
        ]

        step_types_raw: list[str] = [
            r[0]
            for r in self._conn.execute(
                "SELECT DISTINCT step_types FROM evidence_index WHERE step_types IS NOT NULL"
            ).fetchall()
        ]
        step_types = sorted({t for raw in step_types_raw for t in raw.split("|") if t})

        total = self._conn.execute("SELECT COUNT(*) FROM evidence_index").fetchone()[0]

        last = self._conn.execute("SELECT MAX(indexed_at) FROM evidence_index").fetchone()[0]

        return EvidenceFilterOptions(
            statuses=statuses,
            domains=domains,
            condition_prefixes=condition_prefixes,
            story_refs=story_refs,
            step_types=step_types,
            total_indexed=total,
            last_refreshed=last,
        )

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    def get_test_package_path(self, sidecar_path: str) -> Path:
        """Resolve a relative ``sidecar_path`` to an absolute :class:`Path`."""
        if self._base_dir is not None:
            return self._base_dir / sidecar_path
        from src.storage import get_storage

        return get_storage().generated_tests_dir() / sidecar_path

    def get_sidecar_detail(self, sidecar_path: str) -> dict | None:
        """Load the full sidecar JSON for a given path."""
        try:
            abs_path = self.get_test_package_path(sidecar_path)
            with open(abs_path, encoding="utf-8") as fh:
                return json.load(fh)  # type: ignore[no-any-return]
        except OSError, json.JSONDecodeError:
            return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _find_sidecars(base_dir: Path) -> list[str]:
        """Yield relative paths to every ``*.evidence.json`` under *base_dir*."""
        if not base_dir.exists():
            return []
        results: list[str] = []
        for root, _dirs, files in os.walk(base_dir):
            for fname in files:
                if fname.endswith(".evidence.json"):
                    abs_p = Path(root) / fname
                    results.append(str(abs_p.relative_to(base_dir)))
        return results

    @staticmethod
    def _read_sidecar(abs_path: Path) -> dict | None:
        """Read and return the parsed sidecar JSON, or ``None`` on failure."""
        try:
            with open(abs_path, encoding="utf-8") as fh:
                return json.load(fh)
        except OSError, json.JSONDecodeError:
            return None

    def _is_stale(self, sidecar_path: str, disk_mtime: float) -> bool:
        """Return ``True`` if the sidecar is new or has changed on disk."""
        row = self._conn.execute(
            "SELECT file_mtime FROM evidence_index WHERE sidecar_path = ?",
            (sidecar_path,),
        ).fetchone()
        if row is None:
            return True  # new file
        return disk_mtime != row["file_mtime"]

    def _upsert_sidecar(
        self,
        sidecar_path: str,
        data: dict,
        file_mtime: float,
        indexed_at: str,
        base_dir: Path,
    ) -> None:
        """Insert or update a single sidecar row."""
        test = data.get("test", {})
        page = data.get("page", {})
        steps: Sequence[dict] = data.get("steps", [])

        test_name = test.get("name", "")
        condition_ref = test.get("condition_ref", "")
        story_ref = test.get("story_ref", "")
        status = test.get("status", "unknown")
        page_url = page.get("url", "")
        step_labels = "|".join(s.get("label", "") for s in steps)
        step_types = "|".join(s.get("type", "") for s in steps)

        # Derive test_package from sidecar path (parent's parent)
        test_package = Path(sidecar_path).parts[0] if sidecar_path else ""

        self._conn.execute(
            """
            INSERT INTO evidence_index
                (sidecar_path, test_name, condition_ref, story_ref, status,
                 page_url, step_labels, step_types, test_package,
                 file_mtime, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sidecar_path) DO UPDATE SET
                test_name     = excluded.test_name,
                condition_ref = excluded.condition_ref,
                story_ref     = excluded.story_ref,
                status        = excluded.status,
                page_url      = excluded.page_url,
                step_labels   = excluded.step_labels,
                step_types    = excluded.step_types,
                test_package  = excluded.test_package,
                file_mtime    = excluded.file_mtime,
                indexed_at    = excluded.indexed_at
            """,
            (
                sidecar_path,
                test_name,
                condition_ref,
                story_ref,
                status,
                page_url,
                step_labels,
                step_types,
                test_package,
                file_mtime,
                indexed_at,
            ),
        )
        self._conn.commit()

    def _resolve_matched_field(self, query: str, row: sqlite3.Row) -> str:
        """Determine which column(s) matched the search query."""
        query_lower = query.lower()
        matched: list[str] = []
        for col in self._SEARCHABLE_FIELDS:
            val = row[col]
            if val and query_lower in str(val).lower():
                matched.append(col)
        return ", ".join(matched) if matched else ""

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract domain from a URL (e.g. ``automationexercise.com``)."""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url if "://" in url else f"https://{url}")
            return parsed.netloc or parsed.path.split("/")[0]
        except Exception:
            return url

    @staticmethod
    def _extract_prefix(condition_ref: str) -> str:
        """Extract prefix from a condition ref (e.g. ``TC01.06`` → ``TC01``)."""
        return condition_ref.split(".")[0] if "." in condition_ref else condition_ref
