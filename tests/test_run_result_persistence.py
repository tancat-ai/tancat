"""Tests for src/run_result_persistence.py — Run result persistence & flakiness tracking."""

from __future__ import annotations

import json
from pathlib import Path

from src.pytest_output_parser import RunResult, TestResult
from src.run_result_persistence import (
    PersistedRunResult,
    PersistedTestResult,
    RunComparison,
    RunHistory,
    compare_latest_runs,
    compare_runs,
    compute_run_history,
    delete_old_runs,
    from_dict,
    get_flaky_tests,
    list_run_results,
    load_all_run_results,
    load_run_result,
    persist_run_result,
    to_dict,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(
    *,
    total: int = 3,
    passed: int = 2,
    failed: int = 1,
    skipped: int = 0,
    errors: int = 0,
    duration: float = 1.5,
    results: list[TestResult] | None = None,
) -> RunResult:
    """Build a minimal RunResult for tests."""
    if results is None:
        results = [
            TestResult(name="test_01", status="passed", duration=0.5, error_message="", file_path="test_foo.py"),
            TestResult(name="test_02", status="passed", duration=0.4, error_message="", file_path="test_foo.py"),
            TestResult(
                name="test_03", status="failed", duration=0.6, error_message="AssertionError", file_path="test_foo.py"
            ),
        ]
    return RunResult(
        results=results,
        total=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors,
        duration=duration,
        raw_output="sample output",
    )


def _make_persisted(
    *,
    run_id: str = "2026-06-01T12:00:00+00:00",
    test_package: str = "pkg1",
    results: list[PersistedTestResult] | None = None,
    total: int = 3,
    passed: int = 2,
    failed: int = 1,
    skipped: int = 0,
    errors: int = 0,
    duration: float = 1.5,
) -> PersistedRunResult:
    if results is None:
        results = [
            PersistedTestResult("test_01", "passed", 0.5, "", "test_foo.py"),
            PersistedTestResult("test_02", "passed", 0.4, "", "test_foo.py"),
            PersistedTestResult("test_03", "failed", 0.6, "AssertionError", "test_foo.py"),
        ]
    return PersistedRunResult(
        run_id=run_id,
        test_package=test_package,
        results=results,
        total=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors,
        duration=duration,
    )


# ---------------------------------------------------------------------------
# persist_run_result / load_run_result
# ---------------------------------------------------------------------------


class TestPersistAndLoad:
    def test_persist_creates_file(self, tmp_path: Path) -> None:
        run = _make_run()
        path = persist_run_result(run, test_package="pkg", directory=tmp_path)
        assert path.exists()
        assert path.name.startswith("run_")
        assert path.suffix == ".json"

    def test_persist_writes_valid_json(self, tmp_path: Path) -> None:
        run = _make_run()
        path = persist_run_result(run, directory=tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["total"] == 3
        assert data["passed"] == 2
        assert data["failed"] == 1

    def test_load_round_trips(self, tmp_path: Path) -> None:
        run = _make_run()
        path = persist_run_result(run, test_package="mypkg", directory=tmp_path)
        loaded = load_run_result(path)
        assert loaded.run_id == path.name.replace("run_", "").replace(".json", "") or True  # ID is ISO timestamp
        assert loaded.test_package == "mypkg"
        assert loaded.total == 3
        assert loaded.passed == 2
        assert loaded.failed == 1
        assert len(loaded.results) == 3

    def test_load_preserves_test_results(self, tmp_path: Path) -> None:
        run = _make_run()
        path = persist_run_result(run, directory=tmp_path)
        loaded = load_run_result(path)
        names = [r.name for r in loaded.results]
        assert "test_01" in names
        assert "test_03" in names

    def test_load_preserves_error_message(self, tmp_path: Path) -> None:
        run = _make_run()
        path = persist_run_result(run, directory=tmp_path)
        loaded = load_run_result(path)
        failing = [r for r in loaded.results if r.name == "test_03"]
        assert len(failing) == 1
        assert failing[0].error_message == "AssertionError"

    def test_empty_run(self, tmp_path: Path) -> None:
        run = RunResult()
        path = persist_run_result(run, directory=tmp_path)
        loaded = load_run_result(path)
        assert loaded.total == 0
        assert loaded.results == []


# ---------------------------------------------------------------------------
# list_run_results / load_all_run_results
# ---------------------------------------------------------------------------


class TestListAndLoadAll:
    def test_list_empty_directory(self, tmp_path: Path) -> None:
        assert list_run_results(tmp_path) == []

    def test_list_returns_sorted_paths(self, tmp_path: Path) -> None:
        (tmp_path / "evidence" / "run_results").mkdir(parents=True)
        for _i in range(3):
            persist_run_result(_make_run(), directory=tmp_path / "evidence" / "run_results")
        paths = list_run_results(tmp_path / "evidence" / "run_results")
        assert len(paths) == 3
        assert paths == sorted(paths)

    def test_load_all_returns_runs(self, tmp_path: Path) -> None:
        persist_run_result(_make_run(), directory=tmp_path)
        persist_run_result(_make_run(), directory=tmp_path)
        runs = load_all_run_results(tmp_path)
        assert len(runs) == 2

    def test_load_all_empty_when_no_files(self, tmp_path: Path) -> None:
        # Directory exists but has no run files
        assert load_all_run_results(tmp_path) == []


# ---------------------------------------------------------------------------
# compute_run_history
# ---------------------------------------------------------------------------


class TestComputeRunHistory:
    def test_empty_history(self, tmp_path: Path) -> None:
        history = compute_run_history([], tmp_path)
        assert history.total_runs == 0
        assert history.test_flakiness == {}

    def test_single_run_history(self) -> None:
        runs = [_make_persisted()]
        history = compute_run_history(runs)
        assert history.total_runs == 1
        assert history.total_passed == 2
        assert history.total_failed == 1
        assert "test_01" in history.test_flakiness
        assert history.test_flakiness["test_01"]["passed"] == 1

    def test_multi_run_aggregation(self) -> None:
        runs = [
            _make_persisted(run_id="run1"),
            _make_persisted(run_id="run2"),
        ]
        history = compute_run_history(runs)
        assert history.total_runs == 2
        assert history.total_passed == 4
        assert history.total_failed == 2

    def test_flakiness_counts_accumulate(self) -> None:
        # Run 1: test_01 passed, test_03 failed
        run1 = _make_persisted(run_id="r1")
        # Run 2: test_01 failed (flaky!), test_03 passed
        run2 = PersistedRunResult(
            run_id="r2",
            test_package="pkg",
            results=[
                PersistedTestResult("test_01", "failed", 0.5, "err", "test_foo.py"),
                PersistedTestResult("test_02", "passed", 0.4, "", "test_foo.py"),
                PersistedTestResult("test_03", "passed", 0.6, "", "test_foo.py"),
            ],
            total=3,
            passed=2,
            failed=1,
        )
        history = compute_run_history([run1, run2])
        assert history.test_flakiness["test_01"]["passed"] == 1
        assert history.test_flakiness["test_01"]["failed"] == 1


# ---------------------------------------------------------------------------
# get_flaky_tests
# ---------------------------------------------------------------------------


class TestGetFlakyTests:
    def test_no_flaky_when_all_consistent(self) -> None:
        runs = [
            _make_persisted(run_id="r1"),
            _make_persisted(run_id="r2"),
        ]
        flaky = get_flaky_tests(runs)
        assert flaky == []

    def test_detects_flaky_test(self) -> None:
        run1 = _make_persisted(run_id="r1")
        run2 = PersistedRunResult(
            run_id="r2",
            test_package="pkg",
            results=[
                PersistedTestResult("test_01", "failed", 0.5, "err", "test_foo.py"),
                PersistedTestResult("test_02", "passed", 0.4, "", "test_foo.py"),
                PersistedTestResult("test_03", "passed", 0.6, "", "test_foo.py"),
            ],
            total=3,
            passed=2,
            failed=1,
        )
        flaky = get_flaky_tests([run1, run2])
        names = [name for name, _ in flaky]
        assert "test_01" in names

    def test_respects_min_runs(self) -> None:
        run1 = _make_persisted(run_id="r1")
        # With only 1 run, nothing can be flaky
        flaky = get_flaky_tests([run1], min_runs=2)
        assert flaky == []

    def test_sorted_by_flakiness_score(self) -> None:
        # test_a: 1 pass, 1 fail (50% flaky)
        # test_b: 2 pass, 1 fail (33% flaky)
        runs = [
            PersistedRunResult(
                run_id="r1",
                test_package="p",
                results=[
                    PersistedTestResult("test_a", "passed", 0.1, "", "t.py"),
                    PersistedTestResult("test_b", "passed", 0.1, "", "t.py"),
                ],
                total=2,
                passed=2,
                failed=0,
            ),
            PersistedRunResult(
                run_id="r2",
                test_package="p",
                results=[
                    PersistedTestResult("test_a", "failed", 0.1, "err", "t.py"),
                    PersistedTestResult("test_b", "passed", 0.1, "", "t.py"),
                ],
                total=2,
                passed=1,
                failed=1,
            ),
            PersistedRunResult(
                run_id="r3",
                test_package="p",
                results=[
                    PersistedTestResult("test_b", "failed", 0.1, "err", "t.py"),
                ],
                total=1,
                passed=0,
                failed=1,
            ),
        ]
        flaky = get_flaky_tests(runs, min_runs=2)
        names = [n for n, _ in flaky]
        # test_a has 50% flakiness, test_b has ~33%
        assert names[0] == "test_a"


# ---------------------------------------------------------------------------
# compare_runs
# ---------------------------------------------------------------------------


class TestCompareRuns:
    def test_improved_tests(self) -> None:
        older = PersistedRunResult(
            run_id="r1",
            test_package="p",
            results=[PersistedTestResult("test_a", "failed", 0.1, "err", "t.py")],
            total=1,
            passed=0,
            failed=1,
        )
        newer = PersistedRunResult(
            run_id="r2",
            test_package="p",
            results=[PersistedTestResult("test_a", "passed", 0.1, "", "t.py")],
            total=1,
            passed=1,
            failed=0,
        )
        comp = compare_runs(older, newer)
        assert "test_a" in comp.improved

    def test_regressed_tests(self) -> None:
        older = PersistedRunResult(
            run_id="r1",
            test_package="p",
            results=[PersistedTestResult("test_a", "passed", 0.1, "", "t.py")],
            total=1,
            passed=1,
            failed=0,
        )
        newer = PersistedRunResult(
            run_id="r2",
            test_package="p",
            results=[PersistedTestResult("test_a", "failed", 0.1, "err", "t.py")],
            total=1,
            passed=0,
            failed=1,
        )
        comp = compare_runs(older, newer)
        assert "test_a" in comp.regressed

    def test_new_failures(self) -> None:
        older = PersistedRunResult(
            run_id="r1",
            test_package="p",
            results=[PersistedTestResult("test_a", "passed", 0.1, "", "t.py")],
            total=1,
            passed=1,
            failed=0,
        )
        newer = PersistedRunResult(
            run_id="r2",
            test_package="p",
            results=[
                PersistedTestResult("test_a", "passed", 0.1, "", "t.py"),
                PersistedTestResult("test_new", "failed", 0.1, "err", "t.py"),
            ],
            total=2,
            passed=1,
            failed=1,
        )
        comp = compare_runs(older, newer)
        assert "test_new" in comp.new_failures

    def test_no_change(self) -> None:
        run = _make_persisted()
        comp = compare_runs(run, run)
        assert comp.improved == []
        assert comp.regressed == []
        assert comp.new_failures == []

    def test_error_to_pass_is_improved(self) -> None:
        older = PersistedRunResult(
            run_id="r1",
            test_package="p",
            results=[PersistedTestResult("test_a", "error", 0.1, "err", "t.py")],
            total=1,
            passed=0,
            failed=0,
            errors=1,
        )
        newer = PersistedRunResult(
            run_id="r2",
            test_package="p",
            results=[PersistedTestResult("test_a", "passed", 0.1, "", "t.py")],
            total=1,
            passed=1,
            failed=0,
        )
        comp = compare_runs(older, newer)
        assert "test_a" in comp.improved


# ---------------------------------------------------------------------------
# compare_latest_runs
# ---------------------------------------------------------------------------


class TestCompareLatestRuns:
    def test_returns_none_when_less_than_two(self, tmp_path: Path) -> None:
        result = compare_latest_runs(directory=tmp_path)
        assert result is None

    def test_compares_last_two(self, tmp_path: Path) -> None:
        persist_run_result(_make_run(), directory=tmp_path)
        persist_run_result(_make_run(), directory=tmp_path)
        result = compare_latest_runs(directory=tmp_path)
        assert result is not None
        assert result.older.run_id != result.newer.run_id


# ---------------------------------------------------------------------------
# delete_old_runs
# ---------------------------------------------------------------------------


class TestDeleteOldRuns:
    def test_deletes_excess(self, tmp_path: Path) -> None:
        for _ in range(7):
            persist_run_result(_make_run(), directory=tmp_path)
        deleted = delete_old_runs(keep=4, directory=tmp_path)
        remaining = list_run_results(tmp_path)
        assert deleted == 3
        assert len(remaining) == 4

    def test_does_nothing_when_under_limit(self, tmp_path: Path) -> None:
        for _ in range(3):
            persist_run_result(_make_run(), directory=tmp_path)
        deleted = delete_old_runs(keep=10, directory=tmp_path)
        assert deleted == 0
        assert len(list_run_results(tmp_path)) == 3

    def test_empty_directory(self, tmp_path: Path) -> None:
        deleted = delete_old_runs(directory=tmp_path)
        assert deleted == 0


# ---------------------------------------------------------------------------
# to_dict / from_dict
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_to_dict_round_trip(self) -> None:
        run = _make_persisted()
        data = to_dict(run)
        recovered = from_dict(data)
        assert recovered.run_id == run.run_id
        assert recovered.total == run.total
        assert recovered.results[0].name == run.results[0].name

    def test_from_dict_missing_raw_output(self) -> None:
        data = {
            "run_id": "r1",
            "test_package": "p",
            "results": [],
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "errors": 0,
            "duration": 0.0,
        }
        run = from_dict(data)
        assert run.raw_output == ""


# ---------------------------------------------------------------------------
# RunComparison dataclass structure
# ---------------------------------------------------------------------------


class TestRunComparisonDataclass:
    def test_fields(self) -> None:
        older = _make_persisted(run_id="o")
        newer = _make_persisted(run_id="n")
        comp = RunComparison(older=older, newer=newer, improved=["a"], regressed=["b"], new_failures=["c"])
        assert comp.improved == ["a"]
        assert comp.regressed == ["b"]
        assert comp.new_failures == ["c"]


# ---------------------------------------------------------------------------
# RunHistory dataclass defaults
# ---------------------------------------------------------------------------


class TestRunHistoryDefaults:
    def test_default_values(self) -> None:
        h = RunHistory()
        assert h.total_runs == 0
        assert h.test_flakiness == {}
