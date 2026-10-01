"""Per-criterion verification basis, stored in the eval DB that already exists (B-093).

The harness already computes, per assertion, whether the criterion's own test
verified it by the **golden** locator, a distinctive **element**, a **page**
arrival, or **nothing** (``golden_validator`` -> ``ResolutionResult.verification``).
It never stored it: of 1149 ``eval_runs`` rows, none named the basis.

This module stores it per criterion placeholder, in the SAME SQLite file as
``eval_runs`` (``evidence/run_results.sqlite``). No new database and no parallel
pipeline: the ``eval_criteria`` table is created beside ``eval_runs`` and the
existing compare/history commands read it. The table carries three indexes in
that same file - on ``identity`` (the compare lookup), ``story_id`` (the rollup
filter) and ``run_id`` (loading one run, and the ON DELETE CASCADE).

The owner's questions this answers:

1. Which criteria failed, and for each one the resolved locator, the golden
   locator and the page.
2. Whether this run's failures are the same as the last run's, new, or fixed -
   each criterion has a stable ``identity`` (story + criterion + placeholder).
3. For every pass, what it verified against (golden / element / page /
   unverified).
4. How many criteria were judged by the golden locator vs by the test's own
   outcome.
5. What a fix would have to change, per miss class.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval_metrics import ResolutionResult, StoryResult

# Miss classes (the owner's question 5: what a fix would have to change).
MISS_TARGET_NEVER_CAPTURED = "target_never_captured"
MISS_PAGE_CONTEXT_MISASSIGNED = "page_context_misassigned"
MISS_WEAKENED_TO_VISIBLE = "weakened_to_visible_element"
MISS_ELEMENT_INSTEAD_OF_URL = "element_instead_of_page_arrival"
MISS_GOLDEN_WEAKER = "golden_weaker_than_generated"
MISS_WRONG_ELEMENT = "wrong_element"

#: Miss class -> what a fix would have to change.
MISS_FIX_HINT: dict[str, str] = {
    MISS_TARGET_NEVER_CAPTURED: "capture: the target page/element never entered the candidate pool",
    MISS_PAGE_CONTEXT_MISASSIGNED: "resolver: the step was resolved against the wrong page's pool",
    MISS_WEAKENED_TO_VISIBLE: "generator: it emitted a page-global element instead of the criterion's own",
    MISS_ELEMENT_INSTEAD_OF_URL: "generator: a page criterion needs a URL assertion, not an element",
    MISS_GOLDEN_WEAKER: "golden: the golden expects a container where the generated check is stronger",
    MISS_WRONG_ELEMENT: "resolver: the pool held the target and a different element was chosen",
}

CRITERIA_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS eval_criteria (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           TEXT    NOT NULL,
    story_id         TEXT    NOT NULL,
    site             TEXT    NOT NULL,
    criterion_index  INTEGER,
    criterion_id     TEXT    NOT NULL,
    identity         TEXT    NOT NULL,
    placeholder      TEXT    NOT NULL,
    action           TEXT    NOT NULL,
    page             TEXT,
    golden_locator   TEXT,
    resolved_locator TEXT,
    matched          INTEGER NOT NULL DEFAULT 0,
    verification     TEXT,
    outcome          TEXT,
    miss_class       TEXT,
    created_at       TEXT    NOT NULL,
    FOREIGN KEY (run_id) REFERENCES eval_runs(run_id) ON DELETE CASCADE
)
"""

CRITERIA_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_eval_criteria_identity ON eval_criteria(identity)",
    "CREATE INDEX IF NOT EXISTS idx_eval_criteria_story ON eval_criteria(story_id)",
    "CREATE INDEX IF NOT EXISTS idx_eval_criteria_run ON eval_criteria(run_id)",
)


def ensure_criteria_table(conn: sqlite3.Connection) -> None:
    """Create the eval_criteria table and its indexes if they do not exist."""
    conn.execute(CRITERIA_TABLE_SQL)
    for statement in CRITERIA_INDEX_SQL:
        conn.execute(statement)


def verification_split(story: StoryResult) -> dict[str, int]:
    """Return the per-story ASSERT verification split.

    Keys match the harness vocabulary: ``golden`` (the human-approved locator),
    ``element`` (``verified_by_element`` from the pipeline verdict), ``page``
    (a URL assertion on the criterion's page), ``unverified`` (nothing proved).
    """
    counts = {"golden": 0, "element": 0, "page": 0, "unverified": 0}
    for r in story.resolutions:
        if r.action != "ASSERT":
            continue
        key = r.verification or "unverified"
        if key == "subject":
            key = "element"
        counts[key] = counts.get(key, 0) + 1
    return counts


def criterion_key(story_id: str, criterion_index: int | None, description: str) -> str:
    """Return the stable identity of one criterion placeholder.

    Story + criterion + placeholder, so "the same failure as last time" is a
    query across runs and not a memory. Stable across runs because it does not
    depend on the resolved locator or the outcome.

    Limit: the placeholder is slugged to ``[a-z0-9_]`` and truncated to 48
    characters. Two placeholders that share their first 48 slug characters
    therefore collide, and editing a placeholder inside those 48 characters
    makes the criterion read as new in ``compare``. Stated here on purpose;
    the README repeats it so a reader does not have to find this docstring.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", (description or "").lower()).strip("_")[:48]
    return f"{story_id}#c{criterion_index}#{slug}"


def _is_global_container(locator: str) -> bool:
    """True when a locator targets a page-level container (never proves a claim)."""
    try:
        from src.verification_strength import is_global_container

        return is_global_container(locator)
    except Exception:  # pragma: no cover - src not importable from a bare script run
        low = (locator or "").strip().strip("'\"").strip().lower()
        return any(
            low == c or (low.startswith(c) and len(low) > len(c) and low[len(c)] in ":[ >.#")
            for c in ("body", "html", "main", "#content", "#root", "#app", "#page", ".container")
        )


def classify_miss(result: ResolutionResult) -> str | None:
    """Return the miss class for a missed criterion, or None when it matched.

    Deterministic from the resolution alone. The "page context" class needs the
    page a locator was resolved from, which the harness does not record today -
    see the report note; it is never guessed here.
    """
    if result.matched:
        return None
    generated = str(result.generated_locator or "")
    expected = str(result.expected_locator or "")
    if not generated:
        return MISS_TARGET_NEVER_CAPTURED
    if expected.startswith("expect(page).to_have_url") and not generated.startswith("expect(page).to_have_url"):
        return MISS_ELEMENT_INSTEAD_OF_URL
    if _is_global_container(generated):
        return MISS_WEAKENED_TO_VISIBLE
    if _is_global_container(expected) and not _is_global_container(generated):
        return MISS_GOLDEN_WEAKER
    return MISS_WRONG_ELEMENT


def criterion_rows(
    story: StoryResult,
    code: str,
    per_test: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Return one row per criterion placeholder (a criterion with several
    placeholders writes several rows): the owner's per-criterion record.

    ``per_test`` maps test function name -> PASSED/FAILED/SKIPPED; the outcome
    of a criterion is the outcome of its own test function (the skeleton emits
    one test per criterion, in order).
    """
    per_test = per_test or {}
    test_names = re.findall(r"^def (test_\d+_\w+)", code, re.MULTILINE)
    now = datetime.now(UTC).isoformat()
    rows: list[dict[str, Any]] = []
    for r in story.resolutions:
        idx = r.criterion_index
        owner = test_names[idx] if isinstance(idx, int) and 0 <= idx < len(test_names) else ""
        outcome = per_test.get(owner) if owner else None
        rows.append(
            {
                "story_id": story.story_id,
                "site": story.site,
                "criterion_index": idx,
                "criterion_id": f"{story.story_id}#c{idx}",
                "identity": criterion_key(story.story_id, idx, r.description),
                "placeholder": r.description,
                "action": r.action,
                "page": "",
                "golden_locator": r.expected_locator,
                "resolved_locator": r.generated_locator,
                "matched": 1 if r.matched else 0,
                "verification": r.verification or ("unverified" if r.action == "ASSERT" else ""),
                "outcome": outcome,
                "miss_class": classify_miss(r),
                "created_at": now,
            }
        )
    return rows


def persist_criteria(
    conn: sqlite3.Connection,
    run_id: str,
    story: StoryResult,
    code: str,
    per_test: dict[str, str] | None = None,
) -> int:
    """Write one story's per-criterion rows; return the number written."""
    rows = criterion_rows(story, code, per_test)
    for row in rows:
        conn.execute(
            """
            INSERT INTO eval_criteria
                (run_id, story_id, site, criterion_index, criterion_id, identity,
                 placeholder, action, page, golden_locator, resolved_locator,
                 matched, verification, outcome, miss_class, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                row["story_id"],
                row["site"],
                row["criterion_index"],
                row["criterion_id"],
                row["identity"],
                row["placeholder"],
                row["action"],
                row["page"],
                row["golden_locator"],
                row["resolved_locator"],
                row["matched"],
                row["verification"],
                row["outcome"],
                row["miss_class"],
                row["created_at"],
            ),
        )
    return len(rows)


def load_criteria(
    db_path: str | Path,
    *,
    story_id: str | None = None,
    run_id: str | None = None,
    identity: str | None = None,
) -> list[dict[str, Any]]:
    """Query the per-criterion rows (no JSON parsing of raw_report needed)."""
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        ensure_criteria_table(conn)
        clauses: list[str] = []
        params: list[Any] = []
        if story_id is not None:
            clauses.append("story_id = ?")
            params.append(story_id)
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        if identity is not None:
            clauses.append("identity = ?")
            params.append(identity)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM eval_criteria{where} ORDER BY id",  # noqa: S608 - clauses are fixed strings
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@dataclass
class CriteriaComparison:
    """Which criteria improved, regressed, are new failures, or are fixed."""

    older_run_ids: list[str]
    newer_run_ids: list[str]
    improved: list[str]
    regressed: list[str]
    new_failures: list[str]
    fixed: list[str]

    def to_text(self) -> str:
        """Render the comparison for a reader."""
        lines = ["CRITERION COMPARISON", "=" * 70]
        lines.append(f"older runs: {', '.join(self.older_run_ids) or '(none)'}")
        lines.append(f"newer runs: {', '.join(self.newer_run_ids) or '(none)'}")
        for label, items in (
            ("FIXED (failed -> passed)", self.fixed),
            ("REGRESSED (passed -> failed)", self.regressed),
            ("NEW FAILURES", self.new_failures),
            ("STILL FAILING (improved basis)", self.improved),
        ):
            lines.append(f"  {label}: {len(items)}")
            for item in items:
                lines.append(f"    {item}")
        return "\n".join(lines)


def criterion_outcome(row: dict[str, Any]) -> str:
    """The single definition of a criterion's outcome: ``passed`` or ``failed``.

    A criterion is failed when its golden locator did not match, or when its
    own test did not pass (``FAILED``, ``ERROR`` or ``SKIPPED``). Everything
    else passed. The rollup and ``compare_criteria`` both call this, so the two
    views cannot disagree about the same row.
    """
    if not row.get("matched"):
        return "failed"
    outcome = str(row.get("outcome") or "")
    if outcome in ("FAILED", "ERROR", "SKIPPED"):
        return "failed"
    return "passed"


def compare_criteria(
    db_path: str | Path,
    older_run_ids: list[str],
    newer_run_ids: list[str],
) -> CriteriaComparison:
    """Compare two runs' criteria by their stable identity.

    Reuses the eval DB's ``eval_criteria`` table (no parallel pipeline). A
    criterion that failed before and passes now is FIXED; the reverse is
    REGRESSED; a failure absent before is NEW.
    """
    older = _criteria_by_identity(db_path, older_run_ids)
    newer = _criteria_by_identity(db_path, newer_run_ids)

    fixed: list[str] = []
    regressed: list[str] = []
    new_failures: list[str] = []
    improved: list[str] = []

    for identity, new_row in sorted(newer.items()):
        old_row = older.get(identity)
        new_outcome = criterion_outcome(new_row)
        if old_row is None:
            if new_outcome == "failed":
                new_failures.append(identity)
            continue
        old_outcome = criterion_outcome(old_row)
        if old_outcome == "failed" and new_outcome == "passed":
            fixed.append(identity)
        elif old_outcome == "passed" and new_outcome == "failed":
            regressed.append(identity)
        elif old_outcome == "failed" and new_outcome == "failed":
            # Same failure, but the verification basis may have improved.
            if (old_row.get("verification") or "unverified") == "unverified" and (
                new_row.get("verification") or "unverified"
            ) != "unverified":
                improved.append(identity)

    return CriteriaComparison(
        older_run_ids=list(older_run_ids),
        newer_run_ids=list(newer_run_ids),
        improved=improved,
        regressed=regressed,
        new_failures=new_failures,
        fixed=fixed,
    )


def _criteria_by_identity(db_path: str | Path, run_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Return identity -> row for the newest row in the given runs."""
    by_identity: dict[str, dict[str, Any]] = {}
    for run_id in run_ids:
        for row in load_criteria(db_path, run_id=run_id):
            by_identity[str(row["identity"])] = row
    return by_identity


__all__ = [
    "CRITERIA_TABLE_SQL",
    "MISS_ELEMENT_INSTEAD_OF_URL",
    "MISS_FIX_HINT",
    "MISS_GOLDEN_WEAKER",
    "MISS_PAGE_CONTEXT_MISASSIGNED",
    "MISS_TARGET_NEVER_CAPTURED",
    "MISS_WEAKENED_TO_VISIBLE",
    "MISS_WRONG_ELEMENT",
    "CriteriaComparison",
    "classify_miss",
    "compare_criteria",
    "criterion_key",
    "criterion_outcome",
    "criterion_rows",
    "ensure_criteria_table",
    "load_criteria",
    "persist_criteria",
    "verification_split",
]
