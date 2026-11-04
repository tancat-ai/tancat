"""j-0273: one store for every eval run, in a shape the owner can question.

The owner asked for a single place for every run: per-leg numbers, the model,
and every setting a leg ran at. Three homes existed - this database, the
`fixtures/heldout_runs/` directories, and a hand-written `RUNS.md`. These tests
pin the database side:

* the leg identity and the settings columns exist, and an old row keeps NULL
  rather than a made-up value (step 1);
* a model-bearing run cannot be told not to persist, and cannot persist without
  naming its leg (step 2);
* a run rebuilt from kept evidence keeps what the manifest holds and leaves the
  rest unknown instead of defaulting it (step 3);
* two legs are compared by one command that refuses when they are not the same
  sample (step 4).

No new database: the columns live on `eval_runs`, the table the harness already
writes and `eval_harness report` already reads.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))

from eval_runner import _EVAL_SCHEMA_SQL, _ensure_eval_table  # noqa: E402

# The table as it stood before j-0273: no leg identity, no settings JSON.
_LEGACY_SCHEMA = """
CREATE TABLE eval_runs (
    run_id      TEXT PRIMARY KEY,
    story_id    TEXT NOT NULL,
    site        TEXT NOT NULL,
    placeholders_total   INTEGER NOT NULL DEFAULT 0,
    placeholders_correct INTEGER NOT NULL DEFAULT 0,
    resolution_accuracy  REAL NOT NULL DEFAULT 0.0,
    test_pass_rate       REAL NOT NULL DEFAULT 0.0,
    false_positive_rate  REAL NOT NULL DEFAULT 0.0,
    skeleton_completeness REAL NOT NULL DEFAULT 0.0,
    generation_duration  REAL NOT NULL DEFAULT 0.0,
    mode         TEXT NOT NULL DEFAULT 'static',
    raw_report   TEXT,
    created_at   TEXT NOT NULL,
    pipeline     TEXT NOT NULL DEFAULT 'linear',
    generation_mode TEXT NOT NULL DEFAULT 'captured',
    rag_enabled  INTEGER NOT NULL DEFAULT 0,
    pom_mode     INTEGER NOT NULL DEFAULT 0,
    provider     TEXT NOT NULL DEFAULT '',
    model        TEXT NOT NULL DEFAULT '',
    git_commit   TEXT NOT NULL DEFAULT '',
    temperature_sent REAL,
    server_defaults  TEXT,
    thinking         TEXT,
    verified_by_element INTEGER NOT NULL DEFAULT 0,
    verified_by_page    INTEGER NOT NULL DEFAULT 0,
    unverified          INTEGER NOT NULL DEFAULT 0
)
"""


class TestSchema:
    def test_a_fresh_database_carries_the_leg_and_settings_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        conn = sqlite3.connect(str(db))
        try:
            _ensure_eval_table(conn)
            columns = {row[1]: row for row in conn.execute("PRAGMA table_info(eval_runs)")}
            for name in ("run_group", "dataset_key", "dataset_size", "rag_store", "run_settings"):
                assert name in columns, f"{name} missing from a fresh eval_runs"
        finally:
            conn.close()
        assert "verified_by_element" in _EVAL_SCHEMA_SQL

    def test_an_old_row_keeps_a_null_group_instead_of_a_default(self, tmp_path: Path) -> None:
        """The 1284 rows that predate this change must read as ungrouped, not 'default'."""
        db = tmp_path / "run_results.sqlite"
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(_LEGACY_SCHEMA)
            conn.execute(
                "INSERT INTO eval_runs (run_id, story_id, site, created_at) "
                "VALUES ('run-1', 'eval-001', 'saucedemo', '2026-10-29T15:05:00+00:00')"
            )
            conn.commit()

            _ensure_eval_table(conn)

            row = conn.execute(
                "SELECT run_group, dataset_key, dataset_size, rag_store, run_settings FROM eval_runs"
            ).fetchone()
            assert row == (None, None, None, None, None)
        finally:
            conn.close()

    def test_the_group_column_is_indexed(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        conn = sqlite3.connect(str(db))
        try:
            _ensure_eval_table(conn)
            indexes = {row[1] for row in conn.execute("PRAGMA index_list(eval_runs)")}
        finally:
            conn.close()
        assert "idx_eval_runs_group" in indexes

    def test_running_the_migration_twice_is_safe(self, tmp_path: Path) -> None:
        """A second `_ensure_eval_table` on an already-migrated table must not raise."""
        db = tmp_path / "run_results.sqlite"
        conn = sqlite3.connect(str(db))
        try:
            _ensure_eval_table(conn)
            _ensure_eval_table(conn)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(eval_runs)")}
        finally:
            conn.close()
        assert {"run_group", "run_settings"} <= columns
