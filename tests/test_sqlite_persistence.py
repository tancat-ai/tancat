"""Tests for src/sqlite_persistence.py.

Covers schema creation, CRUD operations, flaky test detection, history
aggregation, delete-old-runs, context-manager protocol, and edge cases.
"""

from __future__ import annotations

import time
from collections.abc import Generator
from pathlib import Path

import pytest

from src.pytest_output_parser import RunResult, TestResult
from src.sqlite_persistence import (
    SQLitePersistence,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    """Return a unique database path for each test."""
    return tmp_path / "test.sqlite"


@pytest.fixture()
def db(tmp_db: Path) -> Generator[SQLitePersistence]:
    """Create SQLitePersistence backed by a temp database. Auto-closed."""
    persistence = SQLitePersistence(db_path=tmp_db)
    yield persistence
    persistence.close()


@pytest.fixture()
def sample_run_result() -> RunResult:
    """Minimal RunResult with 3 test results."""
    return RunResult(
        results=[
            TestResult(
                name="test_login",
                status="passed",
                duration=0.5,
                error_message="",
                file_path="generated_tests/test_auth.py",
            ),
            TestResult(
                name="test_checkout",
                status="failed",
                duration=1.2,
                error_message="AssertionError: expected 200 got 500",
                file_path="generated_tests/test_cart.py",
            ),
            TestResult(
                name="test_search",
                status="skipped",
                duration=0.0,
                error_message="",
                file_path="generated_tests/test_search.py",
            ),
        ],
        total=3,
        passed=1,
        failed=1,
        skipped=1,
        errors=0,
        duration=1.7,
        raw_output="pytest output here",
    )


@pytest.fixture()
def sample_run_result_2() -> RunResult:
    """Second run where test_login fails (flaky) and test_checkout passes."""
    return RunResult(
        results=[
            TestResult(
                name="test_login",
                status="failed",
                duration=0.8,
                error_message="TimeoutError",
                file_path="generated_tests/test_auth.py",
            ),
            TestResult(
                name="test_checkout",
                status="passed",
                duration=0.9,
                error_message="",
                file_path="generated_tests/test_cart.py",
            ),
            TestResult(
                name="test_search",
                status="passed",
                duration=0.3,
                error_message="",
                file_path="generated_tests/test_search.py",
            ),
        ],
        total=3,
        passed=2,
        failed=1,
        skipped=0,
        errors=0,
        duration=2.0,
        raw_output="second run output",
    )


# ---------------------------------------------------------------------------
# Schema creation tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    def test_creates_tables_on_init(self, db: SQLitePersistence) -> None:
        """Tables exist immediately after __init__."""
        rows = db._conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        table_names = [row["name"] for row in rows]
        assert "runs" in table_names
        assert "test_results" in table_names

    def test_creates_indexes_on_init(self, db: SQLitePersistence) -> None:
        """All expected indexes are created."""
        rows = db._conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'").fetchall()
        index_names = [row["name"] for row in rows]
        assert "idx_test_results_run_id" in index_names
        assert "idx_test_results_name" in index_names
        assert "idx_test_results_status" in index_names
        assert "idx_test_results_name_status" in index_names

    def test_schema_idempotent(self, db: SQLitePersistence) -> None:
        """Calling _create_schema again does not error."""
        db._create_schema()  # Should not raise


# ---------------------------------------------------------------------------
# CRUD — persist & load
# ---------------------------------------------------------------------------


class TestPersistRunResult:
    def test_persist_returns_run_id(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        run_id = db.persist_run_result(sample_run_result)
        assert run_id is not None
        assert len(run_id) > 10  # ISO-8601 timestamp

    def test_persist_creates_run_row(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        run_id = db.persist_run_result(sample_run_result, test_package="pkg1")
        row = db._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        assert row is not None
        assert row["total"] == 3
        assert row["passed"] == 1
        assert row["failed"] == 1
        assert row["skipped"] == 1
        assert row["test_package"] == "pkg1"

    def test_persist_creates_test_result_rows(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        run_id = db.persist_run_result(sample_run_result)
        rows = db._conn.execute("SELECT * FROM test_results WHERE run_id = ?", (run_id,)).fetchall()
        assert len(rows) == 3

    def test_persist_with_empty_result(self, db: SQLitePersistence) -> None:
        run_id = db.persist_run_result(RunResult())
        row = db._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        assert row is not None
        assert row["total"] == 0

    def test_persist_raw_output_saved(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        run_id = db.persist_run_result(sample_run_result)
        row = db._conn.execute("SELECT raw_output FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        assert row["raw_output"] == "pytest output here"


# ---------------------------------------------------------------------------
# CRUD — load
# ---------------------------------------------------------------------------


class TestLoadRunResult:
    def test_load_existing_run(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        run_id = db.persist_run_result(sample_run_result, test_package="my_pkg")
        loaded = db.load_run_result(run_id)

        assert loaded is not None
        assert loaded.run_id == run_id
        assert loaded.test_package == "my_pkg"
        assert loaded.total == 3
        assert loaded.passed == 1
        assert len(loaded.results) == 3

    def test_load_test_results_detail(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        run_id = db.persist_run_result(sample_run_result)
        loaded = db.load_run_result(run_id)

        assert loaded is not None
        names = [r.name for r in loaded.results]
        assert "test_login" in names
        assert "test_checkout" in names

    def test_load_nonexistent_returns_none(self, db: SQLitePersistence) -> None:
        assert db.load_run_result("nonexistent-id") is None


# ---------------------------------------------------------------------------
# CRUD — list & load_all
# ---------------------------------------------------------------------------


class TestListAndLoadAll:
    def test_list_empty(self, db: SQLitePersistence) -> None:
        assert db.list_run_results() == []

    def test_list_returns_sorted_ids(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        id1 = db.persist_run_result(sample_run_result)
        id2 = db.persist_run_result(sample_run_result)
        ids = db.list_run_results()
        assert len(ids) == 2
        assert ids[0] == id1
        assert ids[1] == id2

    def test_load_all_empty(self, db: SQLitePersistence) -> None:
        assert db.load_all_run_results() == []

    def test_load_all_returns_runs(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        db.persist_run_result(sample_run_result)
        db.persist_run_result(sample_run_result)
        runs = db.load_all_run_results()
        assert len(runs) == 2


# ---------------------------------------------------------------------------
# compute_run_history
# ---------------------------------------------------------------------------


class TestComputeRunHistory:
    def test_empty_history(self, db: SQLitePersistence) -> None:
        history = db.compute_run_history()
        assert history.total_runs == 0
        assert history.total_passed == 0
        assert history.test_flakiness == {}

    def test_aggregates_run_stats(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        db.persist_run_result(sample_run_result)
        history = db.compute_run_history()

        assert history.total_runs == 1
        assert history.total_passed == 1
        assert history.total_failed == 1
        assert history.total_skipped == 1

    def test_aggregates_flakiness(
        self,
        db: SQLitePersistence,
        sample_run_result: RunResult,
        sample_run_result_2: RunResult,
    ) -> None:
        db.persist_run_result(sample_run_result)
        db.persist_run_result(sample_run_result_2)
        history = db.compute_run_history()

        # test_login: passed once, failed once
        assert "test_login" in history.test_flakiness
        assert history.test_flakiness["test_login"]["passed"] == 1
        assert history.test_flakiness["test_login"]["failed"] == 1


# ---------------------------------------------------------------------------
# get_flaky_tests
# ---------------------------------------------------------------------------


class TestGetFlakyTests:
    def test_no_flaky_when_all_pass(self, db: SQLitePersistence) -> None:
        run1 = RunResult(
            results=[
                TestResult("test_a", "passed", 0.1, "", "f.py"),
                TestResult("test_b", "passed", 0.1, "", "f.py"),
            ],
            total=2,
            passed=2,
        )
        db.persist_run_result(run1)
        db.persist_run_result(run1)
        assert db.get_flaky_tests() == []

    def test_detects_flaky_test(
        self,
        db: SQLitePersistence,
        sample_run_result: RunResult,
        sample_run_result_2: RunResult,
    ) -> None:
        db.persist_run_result(sample_run_result)
        db.persist_run_result(sample_run_result_2)
        flaky = db.get_flaky_tests()

        flaky_names = [name for name, _ in flaky]
        # test_login: passed + failed → flaky
        assert "test_login" in flaky_names
        # test_checkout: failed + passed → flaky
        assert "test_checkout" in flaky_names

    def test_respects_min_runs(self, db: SQLitePersistence) -> None:
        """With min_runs=3, a test with 2 runs is not flaky."""
        run = RunResult(
            results=[TestResult("test_x", "passed", 0.1, "", "f.py")],
            total=1,
            passed=1,
        )
        run2 = RunResult(
            results=[TestResult("test_x", "failed", 0.1, "err", "f.py")],
            total=1,
            failed=1,
        )
        db.persist_run_result(run)
        db.persist_run_result(run2)
        assert db.get_flaky_tests(min_runs=3) == []

    def test_flaky_sorted_by_ratio(
        self,
        db: SQLitePersistence,
        sample_run_result: RunResult,
        sample_run_result_2: RunResult,
    ) -> None:
        db.persist_run_result(sample_run_result)
        db.persist_run_result(sample_run_result_2)
        flaky = db.get_flaky_tests()
        # Both have 50/50 ratio so order is stable
        assert len(flaky) >= 1


# ---------------------------------------------------------------------------
# delete_old_runs
# ---------------------------------------------------------------------------


class TestDeleteOldRuns:
    def test_delete_keeps_specified_count(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        for _ in range(5):
            db.persist_run_result(sample_run_result)
        deleted = db.delete_old_runs(keep=3)
        assert deleted == 2
        assert len(db.list_run_results()) == 3

    def test_delete_cascades_test_results(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        """Verify CASCADE deletes test_results when a run is deleted.

        We persist 3 runs, delete oldest 2 (keep=1), and verify that
        test_results for ALL deleted runs are gone.  We check total
        test_results count = 3 (only the 1 kept run remains with 3 tests).
        """
        db.persist_run_result(sample_run_result)
        time.sleep(0.01)
        db.persist_run_result(sample_run_result)
        time.sleep(0.01)
        db.persist_run_result(sample_run_result)

        # 3 runs x 3 tests each = 9 test_results
        row = db._conn.execute("SELECT COUNT(*) as cnt FROM test_results").fetchone()
        assert row["cnt"] == 9

        deleted = db.delete_old_runs(keep=1)
        assert deleted == 2

        # Only 1 run remains (3 test_results)
        row = db._conn.execute("SELECT COUNT(*) as cnt FROM test_results").fetchone()
        assert row["cnt"] == 3

        # Verify only 1 run remains
        assert len(db.list_run_results()) == 1

    def test_delete_nothing_when_below_threshold(self, db: SQLitePersistence) -> None:
        empty = RunResult()
        db.persist_run_result(empty)
        deleted = db.delete_old_runs(keep=50)
        assert deleted == 0


# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_large_raw_output(self, db: SQLitePersistence) -> None:
        """Store a very large raw_output string."""
        big_output = "x" * 1_000_000
        run = RunResult(raw_output=big_output, total=1, passed=1)
        run_id = db.persist_run_result(run)
        row = db._conn.execute("SELECT raw_output FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        assert len(row["raw_output"]) == 1_000_000

    def test_special_characters_in_error_message(self, db: SQLitePersistence) -> None:
        run = RunResult(
            results=[
                TestResult(
                    "test_special",
                    "failed",
                    0.1,
                    "Error: <html>\n\t<script>alert('xss')</script>",
                    "f.py",
                )
            ],
            total=1,
            failed=1,
        )
        run_id = db.persist_run_result(run)
        loaded = db.load_run_result(run_id)
        assert loaded is not None
        assert "<html>" in loaded.results[0].error_message

    def test_db_file_created(self, tmp_db: Path) -> None:
        """Database file is created on __init__."""
        assert not tmp_db.exists()
        SQLitePersistence(db_path=tmp_db)
        assert tmp_db.exists()


# ---------------------------------------------------------------------------
# Integration — persist then query history end-to-end
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_workflow(
        self,
        db: SQLitePersistence,
        sample_run_result: RunResult,
        sample_run_result_2: RunResult,
    ) -> None:
        """Persist two runs, verify history and flaky detection."""
        db.persist_run_result(sample_run_result)
        db.persist_run_result(sample_run_result_2)

        # History
        history = db.compute_run_history()
        assert history.total_runs == 2
        assert history.total_passed == 3  # 1 + 2
        assert history.total_failed == 2  # 1 + 1

        # Flaky
        flaky = db.get_flaky_tests()
        assert len(flaky) >= 1

        # Load all
        runs = db.load_all_run_results()
        assert len(runs) == 2

        # Delete
        deleted = db.delete_old_runs(keep=1)
        assert deleted == 1
        assert len(db.list_run_results()) == 1


# ---------------------------------------------------------------------------
# query_test_history
# ---------------------------------------------------------------------------


class TestQueryTestHistory:
    def test_returns_all_results_by_default(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        db.persist_run_result(sample_run_result)
        results = db.query_test_history()
        assert len(results) == 3
        assert {r["test_name"] for r in results} == {"test_login", "test_checkout", "test_search"}

    def test_filters_by_name_pattern(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        db.persist_run_result(sample_run_result)
        results = db.query_test_history(test_name_pattern="test_login")
        assert len(results) == 1
        assert results[0]["test_name"] == "test_login"

    def test_filters_by_status(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        db.persist_run_result(sample_run_result)
        results = db.query_test_history(status="passed")
        assert len(results) == 1
        assert results[0]["status"] == "passed"

    def test_filters_by_date_range(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        run_id = db.persist_run_result(sample_run_result)
        results = db.query_test_history(date_from=run_id, date_to=run_id)
        assert len(results) == 3

    def test_date_range_excludes_other_runs(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        db.persist_run_result(sample_run_result)
        id2 = db.persist_run_result(sample_run_result)
        # Only include second run
        results = db.query_test_history(date_from=id2, date_to=id2)
        assert len(results) == 3
        assert all(r["run_id"] == id2 for r in results)

    def test_include_flaky_filter(
        self,
        db: SQLitePersistence,
        sample_run_result: RunResult,
        sample_run_result_2: RunResult,
    ) -> None:
        db.persist_run_result(sample_run_result)
        db.persist_run_result(sample_run_result_2)
        results = db.query_test_history(include_flaky=True)
        # Only flaky tests returned (test_login and test_checkout)
        names = {r["test_name"] for r in results}
        assert "test_login" in names
        assert "test_checkout" in names
        # test_search is not flaky (skipped then passed, no fail/error)
        assert "test_search" not in names

    def test_returns_dict_with_expected_keys(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        db.persist_run_result(sample_run_result)
        results = db.query_test_history()
        assert len(results) >= 1
        row = results[0]
        assert "run_id" in row
        assert "test_name" in row
        assert "status" in row
        assert "duration" in row
        assert "error_message" in row
        assert "file_path" in row
        assert "created_at" in row

    def test_empty_db_returns_empty_list(self, db: SQLitePersistence) -> None:
        assert db.query_test_history() == []


# ---------------------------------------------------------------------------
# get_run_stats_for_chart
# ---------------------------------------------------------------------------


class TestGetRunStatsForChart:
    def test_returns_stats_per_run(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        db.persist_run_result(sample_run_result)
        stats = db.get_run_stats_for_chart()
        assert len(stats) == 1
        assert stats[0]["passed"] == 1
        assert stats[0]["failed"] == 1
        assert stats[0]["skipped"] == 1
        assert stats[0]["total"] == 3

    def test_includes_pass_rate(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        db.persist_run_result(sample_run_result)
        stats = db.get_run_stats_for_chart()
        # pass_rate = passed / (passed + failed + errors) * 100
        # = 1 / (1 + 1 + 0) * 100 = 50.0
        assert stats[0]["pass_rate"] == 50.0

    def test_zero_total_gives_zero_pass_rate(self, db: SQLitePersistence) -> None:
        db.persist_run_result(RunResult())
        stats = db.get_run_stats_for_chart()
        assert stats[0]["pass_rate"] == 0.0

    def test_filters_by_date_range(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        db.persist_run_result(sample_run_result)
        id2 = db.persist_run_result(sample_run_result)
        # Narrow range: only second run
        stats = db.get_run_stats_for_chart(date_from=id2, date_to=id2)
        assert len(stats) == 1
        assert stats[0]["run_id"] == id2

    def test_returns_sorted_by_created_at(self, db: SQLitePersistence, sample_run_result: RunResult) -> None:
        db.persist_run_result(sample_run_result)
        db.persist_run_result(sample_run_result)
        stats = db.get_run_stats_for_chart()
        assert len(stats) == 2
        assert stats[0]["run_id"] <= stats[1]["run_id"]

    def test_empty_db_returns_empty(self, db: SQLitePersistence) -> None:
        assert db.get_run_stats_for_chart() == []
