"""B-093: the verification basis is persisted, queryable and comparable.

The harness computed per-assertion whether a criterion was verified by the
golden locator, a distinctive element, a page arrival, or nothing - and never
stored it. These tests pin the smaller job: the run that produced a gate number
writes one `eval_runs` row carrying the verification split, one `eval_criteria`
row per criterion, the row can be rebuilt from the run's kept evidence, and the
existing compare command names a criterion that improved and one that regressed.

No new database: the table is created beside `eval_runs` in the same SQLite file.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))

from eval_criteria import (  # noqa: E402
    MISS_ELEMENT_INSTEAD_OF_URL,
    MISS_WRONG_ELEMENT,
    compare_criteria,
    criterion_key,
    load_criteria,
    verification_split,
)
from eval_evidence import emitted_filename, write_run_evidence  # noqa: E402
from eval_metrics import ResolutionResult, StoryResult  # noqa: E402
from eval_runner import (  # noqa: E402
    load_eval_history,
    persist_results,
    rebuild_run_from_evidence,
)
from golden_validator import validate_story  # noqa: E402

_GOLDEN = {
    "id": "eval-999",
    "site": "test",
    "base_url": "https://example.com",
    "conditions": ["1. Backpack in cart", "2. Cart page loaded"],
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
        {
            "criterion_index": 1,
            "criterion_kind": "page",
            "placeholders": [
                {
                    "action": "ASSERT",
                    "description": "cart page loaded",
                    "expected_locator": 'expect(page).to_have_url("https://example.com/cart.html")',
                    "tolerance_selectors": [],
                    "expected_page": "https://example.com/cart.html",
                },
            ],
        },
    ],
}

# Older run: c0 misses (wrong element), c1 passes (the golden URL assertion).
_CODE_OLDER = (
    "def test_01_a(page):\n"
    "    evidence_tracker.assert_visible('#wrong', label='backpack in cart')\n"
    "def test_02_b(page):\n"
    '    expect(page).to_have_url("https://example.com/cart.html")\n'
)
# Newer run: c0 passes, c1 misses (an element instead of the URL).
_CODE_NEWER = (
    "def test_01_a(page):\n"
    "    evidence_tracker.assert_visible('#backpack', label='backpack in cart')\n"
    "def test_02_b(page):\n"
    "    evidence_tracker.assert_visible('#cart', label='cart page loaded')\n"
)


def _persist(db: Path, code: str) -> list[str]:
    story = validate_story(code, _GOLDEN)
    return persist_results(
        db,
        [story],
        mode="full",
        code_map={"eval-999": code},
        outcomes={"eval-999": {"test_01_a": "PASSED", "test_02_b": "PASSED"}},
    )


class TestVerificationSplit:
    def test_split_counts_each_basis(self) -> None:
        """A hand-built story exercises all four buckets (pure, no I/O)."""
        story = StoryResult(
            story_id="eval-999",
            site="test",
            total_criteria=4,
            criteria_with_skeletons=4,
            resolutions=[
                ResolutionResult("ASSERT", "a", "#a", [], "#a", True, 0, "golden"),
                ResolutionResult("ASSERT", "b", "#b", [], "#x", False, 1, "subject"),
                ResolutionResult("ASSERT", "c", "#c", [], "#y", False, 2, "page"),
                ResolutionResult("ASSERT", "d", "#d", [], "#z", False, 3, "unverified"),
            ],
        )
        split = verification_split(story)
        assert split == {"golden": 1, "element": 1, "page": 1, "unverified": 1}

    def test_criterion_key_is_stable_and_names_the_three_parts(self) -> None:
        assert criterion_key("eval-999", 0, "backpack in cart") == "eval-999#c0#backpack_in_cart"


class TestPersistedRun:
    def test_one_eval_runs_row_carries_the_verification_split(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        story = validate_story(_CODE_OLDER, _GOLDEN)
        split = verification_split(story)
        persist_results(db, [story], mode="full", code_map={"eval-999": _CODE_OLDER})

        row = load_eval_history(db)[0]
        assert row["story_id"] == "eval-999"
        assert row["verified_by_element"] == split["golden"] + split["element"]
        assert row["verified_by_page"] == split["page"]
        assert row["unverified"] == split["unverified"]

    def test_one_criterion_row_per_placeholder(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        _persist(db, _CODE_OLDER)

        rows = load_criteria(db)
        assert len(rows) == 2
        assert {r["identity"] for r in rows} == {
            "eval-999#c0#backpack_in_cart",
            "eval-999#c1#cart_page_loaded",
        }
        c0 = next(r for r in rows if r["criterion_index"] == 0)
        assert c0["golden_locator"] == "#backpack"
        assert c0["resolved_locator"] == "#wrong"
        assert c0["matched"] == 0
        assert c0["miss_class"] == MISS_WRONG_ELEMENT

    def test_a_page_criterion_asserted_by_an_element_is_classified(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        _persist(db, _CODE_NEWER)

        c1 = next(r for r in load_criteria(db) if r["criterion_index"] == 1)
        assert c1["miss_class"] == MISS_ELEMENT_INSTEAD_OF_URL

    def test_verification_basis_is_queryable_without_raw_report(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        _persist(db, _CODE_OLDER)

        conn = sqlite3.connect(str(db))
        try:
            # A plain SQL query, no json parsing of raw_report.
            rows = conn.execute(
                "SELECT identity, verification FROM eval_criteria WHERE verification = ?",
                ("golden",),
            ).fetchall()
        finally:
            conn.close()
        assert rows == [("eval-999#c1#cart_page_loaded", "golden")]

    def test_the_split_columns_are_not_json(self, tmp_path: Path) -> None:
        """The columns exist in the schema, so a reader never parses raw_report."""
        db = tmp_path / "run_results.sqlite"
        _persist(db, _CODE_OLDER)
        conn = sqlite3.connect(str(db))
        try:
            columns = [r[1] for r in conn.execute("PRAGMA table_info(eval_runs)")]
        finally:
            conn.close()
        assert {"verified_by_element", "verified_by_page", "unverified"} <= set(columns)


class TestRebuildFromEvidence:
    def _evidence(self, tmp_path: Path, code: str) -> Path:
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        (dataset_dir / "eval-999.json").write_text(json.dumps(_GOLDEN), encoding="utf-8")
        run_dir = tmp_path / "run"
        story = validate_story(code, _GOLDEN)
        write_run_evidence(
            run_dir,
            code_map={"eval-999": code},
            results=[story],
            verdict_map={},
            summary="synthetic",
            metadata={"mode": "full", "dataset": str(dataset_dir)},
        )
        junit_dir = run_dir / "junit"
        junit_dir.mkdir(parents=True, exist_ok=True)
        (junit_dir / emitted_filename("eval-999").replace(".py", ".xml")).write_text(
            '<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite>'
            '<testcase name="test_01_a[chromium]" /><testcase name="test_02_b[chromium]" />'
            "</testsuite></testsuites>",
            encoding="utf-8",
        )
        return run_dir

    def test_the_row_is_rebuilt_from_the_run_evidence(self, tmp_path: Path) -> None:
        run_dir = self._evidence(tmp_path, _CODE_OLDER)
        db = tmp_path / "run_results.sqlite"

        run_ids = rebuild_run_from_evidence(run_dir, db)

        assert len(run_ids) == 1
        row = load_eval_history(db)[0]
        story = validate_story(_CODE_OLDER, _GOLDEN)
        split = verification_split(story)
        assert row["verified_by_element"] == split["golden"] + split["element"]
        assert row["unverified"] == split["unverified"]
        assert len(load_criteria(db)) == 2


class TestCompareCriteria:
    def test_names_a_criterion_that_improved_and_one_that_regressed(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        older = _persist(db, _CODE_OLDER)[0]
        newer = _persist(db, _CODE_NEWER)[0]

        comparison = compare_criteria(db, [older], [newer])

        assert comparison.fixed == ["eval-999#c0#backpack_in_cart"]  # failed -> passed
        assert comparison.regressed == ["eval-999#c1#cart_page_loaded"]  # passed -> failed
        assert comparison.new_failures == []

    def test_the_compare_renders_the_names(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        older = _persist(db, _CODE_OLDER)[0]
        newer = _persist(db, _CODE_NEWER)[0]

        rendered = compare_criteria(db, [older], [newer]).to_text()

        assert "eval-999#c0#backpack_in_cart" in rendered
        assert "eval-999#c1#cart_page_loaded" in rendered
        assert "FIXED" in rendered and "REGRESSED" in rendered

    def test_a_new_failure_is_named(self, tmp_path: Path) -> None:
        db = tmp_path / "run_results.sqlite"
        # Only the newer run exists, so every failure in it is new.
        newer = _persist(db, _CODE_NEWER)[0]

        comparison = compare_criteria(db, [], [newer])

        assert "eval-999#c1#cart_page_loaded" in comparison.new_failures
