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

import json
import sqlite3
import sys
from pathlib import Path

import pytest

_EVAL_DIR = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))

import eval_harness  # noqa: E402
from eval_metrics import ResolutionResult, StoryResult  # noqa: E402
from eval_runner import (  # noqa: E402
    _EVAL_SCHEMA_SQL,
    NOT_COMPARABLE_EXIT,
    EvalRunner,
    _ensure_eval_table,
    _resolve_dataset_dir,
    compare_run_groups,
    dataset_key,
    dataset_key_from_story_ids,
    describe_model,
    load_eval_history,
    persist_policy_error,
    persist_results,
    rebuild_run_from_evidence,
    render_runs,
)

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


def _story(story_id: str = "eval-001", total: int = 2) -> StoryResult:
    """A minimal story: the persistence columns do not depend on the code."""
    return StoryResult(
        story_id=story_id,
        site="saucedemo",
        total_criteria=1,
        criteria_with_skeletons=1,
        resolutions=[ResolutionResult("CLICK", f"r{i}", "#a", [], "#a", True, 0, "golden") for i in range(total)],
    )


class TestWriterRule:
    """A model-bearing run must land in the store, and must name its leg."""

    def test_full_mode_cannot_be_told_not_to_persist(self) -> None:
        error = persist_policy_error("full", no_persist=True, run_group="leg1")
        assert error is not None
        assert "--no-persist" in error and "full" in error

    def test_resolver_mode_cannot_be_told_not_to_persist(self) -> None:
        error = persist_policy_error("resolver", no_persist=True, run_group="leg1")
        assert error is not None
        assert "--no-persist" in error and "resolver" in error

    def test_a_persisting_model_run_must_name_its_leg(self) -> None:
        error = persist_policy_error("full", no_persist=False, run_group=None)
        assert error is not None
        assert "--run-group" in error
        # Empty or whitespace is not a name.
        assert persist_policy_error("full", no_persist=False, run_group="   ") is not None

    def test_a_named_model_run_is_allowed(self) -> None:
        assert persist_policy_error("full", no_persist=False, run_group="2026-11-04-leg1") is None
        assert persist_policy_error("resolver", no_persist=False, run_group="leg2") is None

    def test_static_keeps_the_flag(self) -> None:
        """gate_full.py gate 3 is `--mode static --no-persist`; that must still work."""
        assert persist_policy_error("static", no_persist=True, run_group=None) is None
        assert persist_policy_error("static", no_persist=False, run_group=None) is None

    def test_the_cli_refuses_before_it_starts_a_run(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = eval_harness.main(["run", "--mode", "full", "--no-persist"])
        assert rc == 2
        assert "--no-persist is not allowed" in capsys.readouterr().err

    def test_the_cli_refuses_a_full_run_with_no_group(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = eval_harness.main(["run", "--mode", "full"])
        assert rc == 2
        assert "--run-group" in capsys.readouterr().err


class TestLegIdentityInTheStore:
    def test_a_persisted_row_carries_its_leg_and_settings(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        persist_results(
            db,
            [_story()],
            mode="full",
            run_group="2026-11-04-leg1",
            dataset_key="9:abc123abc123",
            dataset_size=114,
            rag_store="bundled:113 golden + 35 docs",
            run_settings='{"pytest_timeout": 730.0}',
        )
        row = load_eval_history(db)[0]
        assert row["run_group"] == "2026-11-04-leg1"
        assert row["dataset_key"] == "9:abc123abc123"
        assert row["dataset_size"] == 114
        assert row["rag_store"] == "bundled:113 golden + 35 docs"
        assert json.loads(row["run_settings"]) == {"pytest_timeout": 730.0}

    def test_an_undeclared_leg_writes_null_not_a_default(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        persist_results(db, [_story()], mode="static")
        row = load_eval_history(db)[0]
        assert row["run_group"] is None
        assert row["dataset_key"] is None and row["dataset_size"] is None
        assert row["rag_store"] is None and row["run_settings"] is None

    def test_the_dataset_key_follows_the_story_files(self, tmp_path: Path) -> None:
        one = tmp_path / "one"
        one.mkdir()
        (one / "eval-001.json").write_text("{}", encoding="utf-8")
        two = tmp_path / "two"
        two.mkdir()
        (two / "eval-001.json").write_text("{}", encoding="utf-8")
        (two / "eval-002.json").write_text("{}", encoding="utf-8")

        key_one = dataset_key(one)
        assert key_one is not None and key_one.startswith("1:")
        assert dataset_key(two) != key_one  # a different sample is a different key
        assert dataset_key(two) == dataset_key(two)  # and it is stable
        assert dataset_key(tmp_path / "missing") is None


from eval_evidence import write_run_evidence  # noqa: E402
from golden_validator import validate_story  # noqa: E402

_GOLDEN = {
    "id": "eval-999",
    "site": "test",
    "base_url": "https://example.com",
    "conditions": ["1. Backpack in cart"],
    "golden_resolutions": [
        {
            "criterion_index": 0,
            "criterion_kind": "element",
            "placeholders": [
                {
                    "action": "ASSERT",
                    "description": "backpack in cart",
                    "expected_locator": "#backpack",
                    "tolerance_selectors": [],
                },
            ],
        },
    ],
}
_CODE = "def test_01_a(page):\n    evidence_tracker.assert_visible('#backpack', label='backpack in cart')\n"


def _evidence(tmp_path: Path, **metadata: object) -> Path:
    """One run directory holding one story, as `--evidence-dir` leaves it."""
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    (dataset_dir / "eval-999.json").write_text(json.dumps(_GOLDEN), encoding="utf-8")
    run_dir = tmp_path / "run"
    story = validate_story(_CODE, _GOLDEN)
    write_run_evidence(
        run_dir,
        code_map={"eval-999": _CODE},
        results=[story],
        verdict_map={},
        summary="synthetic",
        metadata={"mode": "full", "pipeline": "linear", "dataset": str(dataset_dir), **metadata},
    )
    # A full-mode run must carry its per-test outcomes, or it cannot be re-scored.
    junit_dir = run_dir / "junit"
    junit_dir.mkdir(parents=True, exist_ok=True)
    (junit_dir / "test_eval_999.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite>'
        '<testcase name="test_01_a[chromium]" /></testsuite></testsuites>',
        encoding="utf-8",
    )
    return run_dir


class TestRebuildKeepsWhatIsKnowable:
    """A rebuilt row carries the run's own facts and nothing invented."""

    def test_the_run_keeps_its_own_date_and_size(self, tmp_path: Path) -> None:
        # d-0136: the declared count must equal the dataset the rebuild scores
        # against; the fixture dataset holds one placeholder.
        run_dir = _evidence(
            tmp_path,
            created_at="2026-10-31T19:49:14.074731+00:00",
            gate1_placeholders_total=1,
            git_commit="f538d4bb4d7626e1ed5ddff04df17eb1b0bc8dbd",
        )
        db = tmp_path / "run_results.sqlite"

        rebuild_run_from_evidence(run_dir, db, run_group="2026-10-31-leg1")

        row = load_eval_history(db)[0]
        assert row["created_at"] == "2026-10-31T19:49:14.074731+00:00"  # not "now"
        assert row["dataset_size"] == 1
        assert row["git_commit"] == "f538d4bb4d7626e1ed5ddff04df17eb1b0bc8dbd"
        assert row["run_group"] == "2026-10-31-leg1"

    def test_an_undeclared_model_is_recorded_as_unknown_not_as_empty(self, tmp_path: Path) -> None:
        run_dir = _evidence(tmp_path)
        db = tmp_path / "run_results.sqlite"

        rebuild_run_from_evidence(run_dir, db)

        row = load_eval_history(db)[0]
        # The column predates this change and is NOT NULL DEFAULT '', so the row
        # cannot hold NULL there; what it CAN do is say the value is unknown.
        assert row["model"] == ""
        assert row["provider"] == ""
        settings = json.loads(row["run_settings"])
        assert {"model", "provider", "rag_enabled", "temperature_sent", "thinking"} <= set(settings["unknown"])
        assert row["rag_store"] is None
        # And a reader is told, never shown an empty string as if it were a model.
        assert describe_model(row["provider"], row["model"]) == "unknown"

    def test_a_declared_model_and_leg_settings_are_stored(self, tmp_path: Path) -> None:
        run_dir = _evidence(tmp_path)
        db = tmp_path / "run_results.sqlite"

        rebuild_run_from_evidence(
            run_dir,
            db,
            run_group="2026-11-04-leg1",
            rag_enabled=True,
            rag_store="bundled:113 golden + 35 docs",
            provider="openai-local",
            model="Qwen3.8-27B-UD-Q4_K_XL_v2.gguf",
            temperature_sent=0.0,
            thinking="off",
        )

        row = load_eval_history(db)[0]
        assert row["rag_enabled"] == 1
        assert row["rag_store"] == "bundled:113 golden + 35 docs"
        assert row["temperature_sent"] == 0.0
        assert row["thinking"] == "off"
        assert "Qwen3.8-27B" in describe_model(row["provider"], row["model"])
        unknown = json.loads(row["run_settings"])["unknown"]
        assert "model" not in unknown and "rag_enabled" not in unknown

    def test_a_rebuilt_run_keys_the_same_dataset_as_a_live_run(self, tmp_path: Path) -> None:
        """One key for one sample, whether the row came from a run or a rebuild."""
        run_dir = _evidence(tmp_path)
        db = tmp_path / "run_results.sqlite"

        rebuild_run_from_evidence(run_dir, db)

        assert load_eval_history(db)[0]["dataset_key"] == dataset_key(tmp_path / "dataset")


class TestComparabilityGuards:
    """d-0136/d-0137/d-0138: the store must refuse what it cannot fairly compare."""

    def test_an_edited_expected_locator_changes_the_key(self, tmp_path: Path) -> None:
        """d-0137: same story ids, different golden content = a different sample."""
        before = tmp_path / "before"
        before.mkdir()
        (before / "eval-999.json").write_text(json.dumps(_GOLDEN), encoding="utf-8")

        edited_golden = json.loads(json.dumps(_GOLDEN))
        edited_golden["golden_resolutions"][0]["placeholders"][0]["expected_locator"] = "#backpack-v2"
        after = tmp_path / "after"
        after.mkdir()
        (after / "eval-999.json").write_text(json.dumps(edited_golden), encoding="utf-8")

        assert dataset_key(before) != dataset_key(after)
        assert dataset_key(before) == dataset_key(before)  # and it is stable

    def test_the_key_covers_the_tolerance_selectors(self, tmp_path: Path) -> None:
        before = tmp_path / "before"
        before.mkdir()
        (before / "eval-999.json").write_text(json.dumps(_GOLDEN), encoding="utf-8")

        changed = json.loads(json.dumps(_GOLDEN))
        changed["golden_resolutions"][0]["placeholders"][0]["tolerance_selectors"] = [".cart-badge"]
        after = tmp_path / "after"
        after.mkdir()
        (after / "eval-999.json").write_text(json.dumps(changed), encoding="utf-8")

        assert dataset_key(before) != dataset_key(after)

    def test_an_ids_only_key_never_matches_a_golden_key(self, tmp_path: Path) -> None:
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        (dataset_dir / "eval-999.json").write_text(json.dumps(_GOLDEN), encoding="utf-8")

        ids_only = dataset_key_from_story_ids(["eval-999"])
        assert ids_only is not None and ids_only.startswith("ids:")
        assert ids_only != dataset_key(dataset_dir)

    def test_a_declared_size_that_disagrees_with_the_scored_dataset_is_refused(self, tmp_path: Path) -> None:
        """d-0136: 113 declared, 1 scored - refuse and name both."""
        run_dir = _evidence(tmp_path, gate1_placeholders_total=113)
        db = tmp_path / "run_results.sqlite"

        with pytest.raises(ValueError) as excinfo:
            rebuild_run_from_evidence(run_dir, db, run_group="2026-10-31-leg1")

        message = str(excinfo.value)
        assert "113" in message and "1" in message
        assert "--dataset" in message
        assert load_eval_history(db) == []

    def test_the_cli_rebuild_refuses_with_exit_two(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        run_dir = _evidence(tmp_path, gate1_placeholders_total=113)
        db = tmp_path / "run_results.sqlite"

        rc = eval_harness.main(["rebuild", "--evidence-dir", str(run_dir), "--db", str(db), "--dataset-size", "113"])

        assert rc == 2
        err = capsys.readouterr().err
        assert "113" in err and "1" in err
        assert "ERROR:" in err

    def test_a_matching_declared_size_still_stores(self, tmp_path: Path) -> None:
        run_dir = _evidence(tmp_path, gate1_placeholders_total=1)
        db = tmp_path / "run_results.sqlite"

        rebuild_run_from_evidence(run_dir, db, run_group="leg-ok")

        assert load_eval_history(db)[0]["dataset_size"] == 1

    def test_a_direct_runner_call_refuses_the_same_way(self, tmp_path: Path) -> None:
        """d-0138: ci_summary's direct call reaches the rule, not only the CLI."""
        runner = EvalRunner(
            dataset_dir=tmp_path / "dataset", code_dir=tmp_path / "captures", db_path=tmp_path / "db.sqlite"
        )

        with pytest.raises(ValueError, match="--no-persist"):
            runner.run(mode="full", persist=False)

        with pytest.raises(ValueError, match="--run-group"):
            runner.run(mode="full", persist=True)


class TestRebuildDatasetResolution:
    def test_a_relative_recorded_dataset_is_not_read_against_the_cwd(self) -> None:
        r"""`..\..\scripts\eval\dataset` is what the t1261 manifests record."""
        default = _EVAL_DIR / "dataset"
        assert _resolve_dataset_dir(r"..\..\scripts\eval\dataset", None) == default

    def test_an_explicit_dataset_wins(self, tmp_path: Path) -> None:
        assert _resolve_dataset_dir(str(tmp_path), tmp_path) == tmp_path

    def test_a_missing_explicit_dataset_is_a_refusal(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="dataset directory not found"):
            _resolve_dataset_dir(None, tmp_path / "nope")


class TestCiSummaryReadsTheStore:
    """Review F1 (d-0138 follow-up): a summary must not re-run a leg to report it.

    The CI workflow used to call ``ci_summary --mode full``, which dispatched a
    second run with persist=False; once the persist rule moved into
    EvalRunner.run that path exited 2 and the PR comment was never posted.
    """

    def _store_with_leg(self, tmp_path: Path) -> Path:
        db = tmp_path / "store.sqlite"
        _leg(db, "ci-abc123", "eval-001", correct=1, total=2)
        _leg(db, "ci-abc123", "eval-002", correct=2, total=2)
        return db

    def test_a_full_mode_summary_path_does_not_exit_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import ci_summary
        from eval_runner import EvalRunner

        db = self._store_with_leg(tmp_path)
        output = tmp_path / "summary.md"

        def must_not_run(*args: object, **kwargs: object) -> None:
            raise AssertionError("the summary dispatched a run instead of reading the store")

        monkeypatch.setattr(EvalRunner, "run", must_not_run)

        rc = ci_summary.main(["--run-group", "ci-abc123", "--db", str(db), "--output", str(output)])

        assert rc == 0
        captured = capsys.readouterr()
        assert "--no-persist" not in captured.out + captured.err
        text = output.read_text(encoding="utf-8")
        assert "# Evaluation Harness Results" in text
        assert "| Stories | 2 |" in text
        assert "| Resolution accuracy | 75.0% |" in text

    def test_a_missing_leg_says_so_and_names_the_ones_present(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import ci_summary

        db = self._store_with_leg(tmp_path)
        output = tmp_path / "summary.md"

        rc = ci_summary.main(["--run-group", "ci-nope", "--db", str(db), "--output", str(output)])

        assert rc == 3
        assert "no stored leg named 'ci-nope'" in capsys.readouterr().err
        text = output.read_text(encoding="utf-8")
        assert "No summary" in text and "ci-abc123" in text


class TestDescribeModel:
    def test_empty_is_rendered_as_unknown(self) -> None:
        assert describe_model("", "") == "unknown"
        assert describe_model(None, None) == "unknown"

    def test_an_endpoint_without_a_model_says_which_part_is_missing(self) -> None:
        assert describe_model("openai-local", "") == "unknown model (openai-local)"

    def test_a_named_model_keeps_its_endpoint(self) -> None:
        assert describe_model("openai-local", "qwen.gguf") == "qwen.gguf (openai-local)"


def _leg(
    db: Path,
    group: str | None,
    story_id: str,
    *,
    correct: int = 1,
    total: int = 2,
    false_greens: int = 0,
    dataset_key_value: str | None = "9:abc123abc123",
    dataset_size: int | None = 114,
    model: str | None = None,
    rag_store: str | None = "bundled:113 golden + 35 docs",
) -> None:
    """Persist one story of one leg, with only the fields the test cares about."""
    story = _story(story_id, total)
    story.tests_false_positive = false_greens
    # `correct` of `total` placeholders match; the rest are misses, so the row's
    # own total is the dataset size, not the numerator.
    story.resolutions = [
        ResolutionResult("CLICK", f"r{i}", "#a", [], "#a" if i < correct else "#b", i < correct, 0, "golden")
        for i in range(total)
    ]
    persist_results(
        db,
        [story],
        mode="full",
        run_group=group,
        dataset_key=dataset_key_value,
        dataset_size=dataset_size,
        rag_store=rag_store,
        model=model or "",
        provider="openai-local" if model else "",
        run_settings='{"declared": {}}',
        created_at="2026-11-04T00:14:41.782683+00:00",
    )


class TestRunsListing:
    def test_every_leg_is_listed_with_the_settings_it_ran_at(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        _leg(db, "2026-11-04-leg1", "eval-001", correct=18, total=20, model="qwen.gguf")

        rendered = render_runs(db)

        assert "2026-11-04-leg1" in rendered
        assert "qwen.gguf (openai-local)" in rendered
        assert "bundled:113 golden + 35 docs" in rendered
        assert "size 114" in rendered
        assert "gate1 18/20 = 90.0%" in rendered
        assert "eval-001 18/20" in rendered  # per-story numbers, not just the leg total

    def test_an_old_row_is_listed_as_ungrouped_and_never_compared(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        _leg(db, None, "eval-001")

        rendered = render_runs(db)

        assert "ungrouped" in rendered
        assert "cannot be compared" in rendered

    def test_an_unrecorded_model_reads_as_unknown_not_empty(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        _leg(db, "2026-11-04-leg2", "eval-001", model=None)

        rendered = render_runs(db)

        assert "model unknown" in rendered
        assert "model (" not in rendered  # never a bare endpoint pretending to be a model

    def test_an_empty_store_says_so(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        assert "No runs in the store yet" in render_runs(db)


class TestDiffRuns:
    def test_two_legs_on_different_dataset_sizes_are_refused(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        _leg(db, "2026-10-31-leg1", "eval-001", dataset_size=113)
        _leg(db, "2026-11-04-leg1", "eval-001", dataset_size=114)

        result = compare_run_groups(db, "2026-10-31-leg1", "2026-11-04-leg1")

        assert result["comparable"] is False
        assert "113" in result["why"] and "114" in result["why"]
        assert result["exit"] == NOT_COMPARABLE_EXIT == 6
        assert "NOT COMPARABLE" in result["text"]

    def test_two_legs_on_different_story_sets_are_refused(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        _leg(db, "leg-a", "eval-001", dataset_key_value="8:aaaa")
        _leg(db, "leg-b", "eval-001", dataset_key_value="9:bbbb")

        result = compare_run_groups(db, "leg-a", "leg-b")

        assert result["comparable"] is False
        assert "8:aaaa" in result["why"] and "9:bbbb" in result["why"]

    def test_an_unrecorded_size_is_not_treated_as_a_match(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        _leg(db, "leg-a", "eval-001", dataset_size=None)
        _leg(db, "leg-b", "eval-001", dataset_size=114)

        result = compare_run_groups(db, "leg-a", "leg-b")

        assert result["comparable"] is False
        assert "not recorded" in result["why"]

    def test_the_same_sample_is_compared_per_story(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        _leg(db, "leg1", "eval-001", correct=18, total=20, false_greens=4)
        _leg(db, "leg1", "eval-002", correct=7, total=8, false_greens=0)
        _leg(db, "leg3", "eval-001", correct=19, total=20, false_greens=3)
        _leg(db, "leg3", "eval-002", correct=5, total=8, false_greens=1)

        result = compare_run_groups(db, "leg1", "leg3")

        assert result["comparable"] is True
        assert result["exit"] == 0
        assert "COMPARABLE" in result["text"]
        assert "eval-001" in result["text"] and "+1" in result["text"]
        assert "delta -1 placeholder(s)" in result["text"]  # totals, not just rows

    def test_a_leg_that_is_not_in_the_store_is_named(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        _leg(db, "leg1", "eval-001")

        result = compare_run_groups(db, "leg1", "leg9")

        assert result["comparable"] is False
        assert "no such leg: leg9" in result["why"]
        assert "leg1" in result["text"]  # says what IS there

    def test_the_refusal_states_the_reason_once(self, tmp_path: Path) -> None:
        """d-0138(4): "NOT COMPARABLE: not comparable: ..." said it twice."""
        db = tmp_path / "run_results.sqlite"
        _leg(db, "2026-10-31-leg1", "eval-001", dataset_size=113)
        _leg(db, "2026-11-04-leg1", "eval-001", dataset_size=114)

        text = compare_run_groups(db, "2026-10-31-leg1", "2026-11-04-leg1")["text"]

        assert text.count("NOT COMPARABLE") == 1
        assert text.count("not comparable") == 0  # the label already says it
        assert "NOT COMPARABLE: not comparable" not in text

    def test_the_cli_exits_six_when_it_refuses(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        _leg(db, "leg1", "eval-001", dataset_size=113)
        _leg(db, "leg2", "eval-001", dataset_size=114)

        assert eval_harness.main(["diff-runs", "leg1", "leg2", "--db", str(db)]) == 6

    def test_the_cli_exits_zero_and_prints_the_table_when_it_compares(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "run_results.sqlite"
        _leg(db, "leg1", "eval-001", correct=1, total=2)
        _leg(db, "leg2", "eval-001", correct=2, total=2)

        assert eval_harness.main(["diff-runs", "leg1", "leg2", "--db", str(db)]) == 0
        out = capsys.readouterr().out
        assert "COMPARABLE" in out and "TOTAL" in out

    def test_the_runs_cli_prints_the_store(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db = tmp_path / "run_results.sqlite"
        _leg(db, "leg1", "eval-001", model="qwen.gguf")

        assert eval_harness.main(["runs", "--db", str(db)]) == 0
        assert "leg1" in capsys.readouterr().out

    def test_a_history_sized_group_is_summarised_not_printed_cell_by_cell(self, tmp_path: Path) -> None:
        """The rows that predate run_group are 1284 wide; one line of cells is unreadable."""
        db = tmp_path / "run_results.sqlite"
        for _ in range(25):
            _leg(db, None, "eval-001")

        rendered = render_runs(db)

        assert "25 rows over 1 story ids" in rendered
        assert "per story:" not in rendered
        assert len(rendered.splitlines()[4]) < 300
