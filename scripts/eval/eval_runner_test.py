"""Tests for eval_runner.py — eval harness orchestration."""

import json
from pathlib import Path
from typing import Any

import pytest
from eval_metrics import ResolutionResult, StoryResult
from eval_runner import (
    EvalRunner,
    _parse_junit_xml,
    _parse_per_test_results,
    load_eval_history,
    persist_results,
    run_full_validation,
    run_generated_tests,
    run_static_validation,
)

# ---------------------------------------------------------------------------
# run_static_validation
# ---------------------------------------------------------------------------


class TestStaticValidation:
    def test_validates_dataset(self, tmp_path: Path) -> None:
        golden = {
            "id": "eval-999",
            "site": "test",
            "base_url": "https://example.com",
            "conditions": ["1. Do X"],
            "golden_resolutions": [
                {
                    "criterion_index": 0,
                    "placeholders": [
                        {"action": "FILL", "description": "x", "expected_locator": "#input", "tolerance_selectors": []},
                    ],
                },
            ],
        }
        (tmp_path / "eval-999.json").write_text(json.dumps(golden))

        results = run_static_validation(tmp_path, {"eval-999": "evidence_tracker.fill('#input', 'val')"})
        assert len(results) == 1
        assert results[0].story_id == "eval-999"
        assert len(results[0].resolutions) == 1
        assert results[0].resolutions[0].matched is True

    def test_empty_code_map(self, tmp_path: Path) -> None:
        golden = {
            "id": "eval-999",
            "site": "test",
            "base_url": "https://example.com",
            "conditions": ["1. Do X"],
            "golden_resolutions": [],
        }
        (tmp_path / "eval-999.json").write_text(json.dumps(golden))
        results = run_static_validation(tmp_path, {})
        assert len(results) == 1
        assert results[0].criteria_with_skeletons == 0


# ---------------------------------------------------------------------------
# run_generated_tests
# ---------------------------------------------------------------------------


class TestRunGeneratedTests:
    def test_parses_pytest_output(self, tmp_path: Path) -> None:
        # Create a simple passing test
        test_file = tmp_path / "test_passing.py"
        test_file.write_text("def test_always_pass():\n    assert True\n")
        total, passed, failed, skipped, duration, output, per_test = run_generated_tests(test_file, pytest_timeout=15.0)
        assert total >= 1
        assert passed >= 1
        assert failed == 0
        # B-093 on first principles: the per-test map must come back populated
        # (JUnit XML). Under xdist, console scraping silently returned {} and
        # every false green read as zero — this asserts the real source works.
        assert per_test.get("test_always_pass") == "PASSED"

    def test_file_not_found(self, tmp_path: Path) -> None:
        # Non-existent file — pytest returns errors
        test_file = tmp_path / "test_missing.py"
        total, passed, failed, skipped, duration, output, per_test = run_generated_tests(test_file, pytest_timeout=15.0)
        assert total == 0
        assert per_test == {}


# ---------------------------------------------------------------------------
# run_full_validation
# ---------------------------------------------------------------------------


class TestFullValidation:
    def test_includes_test_results(self, tmp_path: Path) -> None:
        golden = {
            "id": "eval-999",
            "site": "test",
            "base_url": "https://example.com",
            "conditions": ["1. Do X"],
            "golden_resolutions": [
                {
                    "criterion_index": 0,
                    "placeholders": [
                        {"action": "FILL", "description": "x", "expected_locator": "#input", "tolerance_selectors": []},
                    ],
                },
            ],
        }
        (tmp_path / "eval-999.json").write_text(json.dumps(golden))

        test_file = tmp_path / "test_eval.py"
        test_file.write_text("def test_always_pass():\n    assert True\n")

        results = run_full_validation(
            tmp_path,
            {"eval-999": "evidence_tracker.fill('#input', 'val')"},
            test_files={"eval-999": test_file},
        )
        assert results[0].tests_executed >= 1
        assert results[0].tests_passed >= 1

    def test_timeout_is_marked_not_zero(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """B-061 (b): a pytest run killed by its timeout is its own state.

        It must not render as "Tests executed: 0" — that is indistinguishable
        from the missing-conftest trap.
        """
        from eval_runner import PYTEST_TIMEOUT_MARKER

        golden = {
            "id": "eval-998",
            "site": "test",
            "base_url": "https://example.com",
            "conditions": ["1. Do X"],
            "golden_resolutions": [],
        }
        (tmp_path / "eval-998.json").write_text(json.dumps(golden))
        test_file = tmp_path / "test_eval.py"
        test_file.write_text("def test_always_pass():\n    assert True\n")

        def fake_run(
            test_file: Path, pytest_timeout: float = 120.0
        ) -> tuple[int, int, int, int, float, str, dict[str, str]]:
            return (0, 0, 0, 0, 0.0, PYTEST_TIMEOUT_MARKER, {})

        monkeypatch.setattr("eval_runner.run_generated_tests", fake_run)
        results = run_full_validation(
            tmp_path,
            {"eval-998": "evidence_tracker.fill('#input', 'val')"},
            test_files={"eval-998": test_file},
        )
        assert results[0].tests_timed_out is True
        assert results[0].tests_executed == 0

        from eval_metrics import HarnessReport

        summary = HarnessReport(stories=results).to_summary()
        assert "TIMED OUT" in summary
        assert "Tests timed out" in summary

    def test_false_green_is_attributed_to_its_own_test(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Gate 2 (B-093): a false green requires the criterion's OWN test to pass.

        The old story-level rule ("any pass taints every unmatched ASSERT")
        overcounted: an unmatched ASSERT on a skipped test is an honest skip,
        not a false green.
        """
        golden = {
            "id": "eval-997",
            "site": "test",
            "base_url": "https://example.com",
            "conditions": ["1. A", "2. B", "3. C"],
            "golden_resolutions": [
                {
                    "criterion_index": 0,
                    "placeholders": [
                        {"action": "ASSERT", "description": "a", "expected_locator": "#a", "tolerance_selectors": []},
                    ],
                },
                {
                    "criterion_index": 1,
                    "placeholders": [
                        {"action": "ASSERT", "description": "b", "expected_locator": "#b", "tolerance_selectors": []},
                    ],
                },
                {
                    "criterion_index": 2,
                    "placeholders": [
                        {"action": "ASSERT", "description": "c", "expected_locator": "#c", "tolerance_selectors": []},
                    ],
                },
            ],
        }
        (tmp_path / "eval-997.json").write_text(json.dumps(golden))
        test_file = tmp_path / "test_eval.py"
        test_file.write_text("")

        code = (
            "def test_01_a(page):\n"
            "    evidence_tracker.assert_visible('#wrong', label='a')\n"
            "def test_02_b(page):\n"
            "    evidence_tracker.assert_visible('#wrong', label='b')\n"
            "def test_03_c(page):\n"
            "    evidence_tracker.assert_visible('#c', label='c')\n"
        )

        fake_output = "=== 2 passed, 1 skipped in 1.0s ===\n"
        fake_per_test = {
            "test_01_a": "PASSED",
            "test_02_b": "SKIPPED",
            "test_03_c": "PASSED",
        }

        def fake_run(
            test_file: Path, pytest_timeout: float = 120.0
        ) -> tuple[int, int, int, int, float, str, dict[str, str]]:
            return (3, 2, 0, 1, 1.0, fake_output, fake_per_test)

        monkeypatch.setattr("eval_runner.run_generated_tests", fake_run)
        results = run_full_validation(tmp_path, {"eval-997": code}, test_files={"eval-997": test_file})

        # test_01 passed with the wrong locator -> false green.
        # test_02 was SKIPPED with the wrong locator -> honest, not counted.
        # test_03 passed with the right locator -> not counted.
        assert results[0].tests_false_positive == 1

    def test_failed_regeneration_is_flagged_partial(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Gate-2 measurement integrity (B-093): a story whose regeneration
        raised must be flagged — its run is partial, not a valid gate score."""
        golden = {
            "id": "eval-996",
            "site": "test",
            "base_url": "https://example.com",
            "conditions": ["1. Do X"],
            "golden_resolutions": [],
        }
        (tmp_path / "eval-996.json").write_text(json.dumps(golden))

        class _BoomOrchestrator:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            async def run_pipeline(self, *args: Any, **kwargs: Any) -> str:
                raise TimeoutError("generation timed out")

        monkeypatch.setattr("src.orchestrator.TestOrchestrator", _BoomOrchestrator)

        from eval_runner import EvalRunner

        runner = EvalRunner(
            dataset_dir=tmp_path,
            code_dir=tmp_path,
            db_path=Path(),
            regenerate=True,
        )
        code_map, _ = runner._regenerate_code()

        assert code_map["eval-996"] == ""
        assert runner.regeneration_failures == ("eval-996",)


# ---------------------------------------------------------------------------
# _parse_per_test_results
# ---------------------------------------------------------------------------


class TestParsePerTestResults:
    def test_parses_plain_node_lines(self) -> None:
        out = (
            "test_eval_001.py::test_01_login[chromium] PASSED   [ 16%]\n"
            "test_eval_001.py::test_02_cart[chromium] FAILED    [ 33%]\n"
            "test_eval_001.py::test_03_skip[chromium] SKIPPED   [ 50%]\n"
        )
        assert _parse_per_test_results(out) == {
            "test_01_login": "PASSED",
            "test_02_cart": "FAILED",
            "test_03_skip": "SKIPPED",
        }

    def test_parses_xdist_lines_outcome_before_node_id(self) -> None:
        """pytest.ini enables -n 4, so this is the shape the harness sees.

        Under xdist the outcome prints BEFORE the node id:
        ``[gw0] [ 33%] PASSED path::test_01_alpha[1]``.
        """
        out = (
            "[gw0] [ 33%] PASSED test_eval.py::test_01_alpha[chromium] \n"
            "[gw1] [ 66%] SKIPPED test_eval.py::test_02_beta[chromium] \n"
            "[gw0] [100%] FAILED test_eval.py::test_03_gamma[chromium] \n"
        )
        assert _parse_per_test_results(out) == {
            "test_01_alpha": "PASSED",
            "test_02_beta": "SKIPPED",
            "test_03_gamma": "FAILED",
        }

    def test_ignores_summary_and_log_lines(self) -> None:
        out = "=== 1 passed in 0.5s ===\nsome log line\n"
        assert _parse_per_test_results(out) == {}


# ---------------------------------------------------------------------------
# _parse_junit_xml
# ---------------------------------------------------------------------------


class TestParseJunitXml:
    def _write(self, tmp_path: Path, body: str) -> Path:
        xml = tmp_path / "results.xml"
        xml.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            f'<testsuites><testsuite name="pytest" tests="4">{body}</testsuite></testsuites>',
            encoding="utf-8",
        )
        return xml

    def test_reads_all_three_outcomes_and_strips_param_suffix(self, tmp_path: Path) -> None:
        xml = self._write(
            tmp_path,
            '<testcase name="test_01_login[chromium]" time="0.1" />'
            '<testcase name="test_02_cart[chromium]" time="0.2"><failure message="boom">t</failure></testcase>'
            '<testcase name="test_03_skip[chromium]" time="0.0"><skipped message="unresolved" /></testcase>'
            '<testcase name="test_04_err[chromium]" time="0.0"><error message="err">t</error></testcase>',
        )
        assert _parse_junit_xml(xml) == {
            "test_01_login": "PASSED",
            "test_02_cart": "FAILED",
            "test_03_skip": "SKIPPED",
            "test_04_err": "FAILED",
        }

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert _parse_junit_xml(tmp_path / "nope.xml") == {}

    def test_malformed_xml_returns_empty(self, tmp_path: Path) -> None:
        xml = tmp_path / "bad.xml"
        xml.write_text("<not-xml", encoding="utf-8")
        assert _parse_junit_xml(xml) == {}


class TestMissingPerTestOutcomesFallBackLoudly:
    def test_unknown_outcomes_use_story_level_rule_not_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A parse failure must never certify a run as clean (B-093).

        With no per-test map, the story-level rule applies: an unmatched
        ASSERT counts as a false green when the story had any pass. That
        over-counts rather than silently reporting zero.
        """
        golden = {
            "id": "eval-995",
            "site": "test",
            "base_url": "https://example.com",
            "conditions": ["1. A"],
            "golden_resolutions": [
                {
                    "criterion_index": 0,
                    "placeholders": [
                        {"action": "ASSERT", "description": "a", "expected_locator": "#a", "tolerance_selectors": []},
                    ],
                },
            ],
        }
        (tmp_path / "eval-995.json").write_text(json.dumps(golden))
        test_file = tmp_path / "test_eval.py"
        test_file.write_text("")
        code = "def test_01_a(page):\n    evidence_tracker.assert_visible('#wrong', label='a')\n"

        def fake_run(
            test_file: Path, pytest_timeout: float = 120.0
        ) -> tuple[int, int, int, int, float, str, dict[str, str]]:
            # 1 passed in the summary, but NO per-test outcomes parsed.
            return (1, 1, 0, 0, 1.0, "=== 1 passed in 1.0s ===\n", {})

        monkeypatch.setattr("eval_runner.run_generated_tests", fake_run)
        results = run_full_validation(tmp_path, {"eval-995": code}, test_files={"eval-995": test_file})

        assert results[0].tests_false_positive == 1


# ---------------------------------------------------------------------------
# persist_results / load_eval_history
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_persist_and_load(self, tmp_path: Path) -> None:
        stories = [
            StoryResult(
                story_id="eval-999",
                site="test",
                total_criteria=2,
                criteria_with_skeletons=2,
                resolutions=[
                    ResolutionResult("FILL", "x", "#a", [], "#a", True),
                ],
                tests_executed=2,
                tests_passed=2,
            ),
        ]
        db_path = tmp_path / "test.sqlite"
        run_ids = persist_results(db_path, stories, "static")
        assert len(run_ids) == 1

        history = load_eval_history(db_path)
        assert len(history) == 1
        assert history[0]["story_id"] == "eval-999"
        assert history[0]["resolution_accuracy"] == pytest.approx(100.0)
        assert history[0]["mode"] == "static"

    def test_filter_by_story_id(self, tmp_path: Path) -> None:
        stories = [
            StoryResult(
                "eval-001", "saucedemo", 6, 6, resolutions=[ResolutionResult("FILL", "x", "#a", [], "#a", True)]
            ),
            StoryResult(
                "eval-002", "demoqa", 6, 6, resolutions=[ResolutionResult("CLICK", "y", "#b", [], "#wrong", False)]
            ),
        ]
        db_path = tmp_path / "test.sqlite"
        persist_results(db_path, stories, "static")

        history = load_eval_history(db_path, story_id="eval-001")
        assert len(history) == 1
        assert history[0]["site"] == "saucedemo"


# ---------------------------------------------------------------------------
# EvalRunner
# ---------------------------------------------------------------------------


class TestEvalRunner:
    def test_run_static(self, tmp_path: Path) -> None:
        dataset_dir = tmp_path / "dataset"
        captures_dir = tmp_path / "captures"
        db_path = tmp_path / "test.sqlite"
        dataset_dir.mkdir()
        captures_dir.mkdir()

        golden = {
            "id": "eval-001",
            "site": "saucedemo",
            "base_url": "https://www.saucedemo.com",
            "conditions": ["1. Login"],
            "golden_resolutions": [
                {
                    "criterion_index": 0,
                    "placeholders": [
                        {
                            "action": "FILL",
                            "description": "u",
                            "expected_locator": "#user-name",
                            "tolerance_selectors": [],
                        },
                    ],
                },
            ],
        }
        (dataset_dir / "eval-001_saucedemo.json").write_text(json.dumps(golden))
        (captures_dir / "saucedemo_code.py").write_text("evidence_tracker.fill('#user-name', 'std')")

        runner = EvalRunner(
            dataset_dir=dataset_dir,
            code_dir=captures_dir,
            db_path=db_path,
        )
        report = runner.run(mode="static", persist=False)
        assert report.total_placeholders == 1
        assert report.correct_resolutions == 1
        assert report.resolution_accuracy() == 100.0

    def test_load_code_map_matches_by_site(self, tmp_path: Path) -> None:
        dataset_dir = tmp_path / "dataset"
        captures_dir = tmp_path / "captures"
        dataset_dir.mkdir()
        captures_dir.mkdir()

        golden = {
            "id": "eval-003",
            "site": "demoqa",
            "base_url": "https://demoqa.com",
            "conditions": ["1. Fill form"],
            "golden_resolutions": [],
        }
        (dataset_dir / "eval-003_demoqa.json").write_text(json.dumps(golden))
        (captures_dir / "demoqa_code.py").write_text("print('test')")

        runner = EvalRunner(
            dataset_dir=dataset_dir,
            code_dir=captures_dir,
            db_path=tmp_path / "test.sqlite",
        )
        code_map = runner._load_code_map()
        assert "eval-003" in code_map


class TestPersistRegeneratedTests:
    """Full-regenerate mode must persist test files so execution phase runs them."""

    def _make_runner(self, tmp_path: Path) -> EvalRunner:
        dataset_dir = tmp_path / "dataset"
        captures_dir = tmp_path / "captures"
        dataset_dir.mkdir()
        captures_dir.mkdir()
        golden = {
            "id": "eval-003",
            "site": "demoqa",
            "base_url": "https://demoqa.com",
            "conditions": ["1. Fill form"],
            "golden_resolutions": [],
        }
        (dataset_dir / "eval-003_demoqa.json").write_text(json.dumps(golden))
        return EvalRunner(
            dataset_dir=dataset_dir,
            code_dir=captures_dir,
            db_path=tmp_path / "test.sqlite",
            test_output_dir=tmp_path / "out",
        )

    def test_writes_story_named_test_file(self, tmp_path: Path) -> None:
        runner = self._make_runner(tmp_path)
        runner._persist_regenerated_tests({"eval-003": "def test_x():\n    pass\n"})

        out_file = tmp_path / "out" / "test_eval_003.py"
        assert out_file.exists()
        assert "def test_x()" in out_file.read_text(encoding="utf-8")

    def test_skips_stories_without_code(self, tmp_path: Path) -> None:
        runner = self._make_runner(tmp_path)
        runner._persist_regenerated_tests({"eval-003": ""})
        assert not (tmp_path / "out" / "test_eval_003.py").exists()

    def test_copies_conftest_when_missing(self, tmp_path: Path) -> None:
        """B-061 (a): a custom --test-output dir must get the evidence_tracker fixture."""
        runner = self._make_runner(tmp_path)
        runner._persist_regenerated_tests({"eval-003": "def test_x():\n    pass\n"})

        conftest = tmp_path / "out" / "conftest.py"
        assert conftest.exists()
        assert "evidence_tracker" in conftest.read_text(encoding="utf-8")

    def test_does_not_overwrite_existing_conftest(self, tmp_path: Path) -> None:
        """B-061 (a): a caller-placed conftest wins over the repo copy."""
        runner = self._make_runner(tmp_path)
        out_dir = tmp_path / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "conftest.py").write_text("# custom conftest\n", encoding="utf-8")

        runner._persist_regenerated_tests({"eval-003": "def test_x():\n    pass\n"})

        assert (out_dir / "conftest.py").read_text(encoding="utf-8") == "# custom conftest\n"

    def test_load_test_files_finds_persisted_file(self, tmp_path: Path) -> None:
        runner = self._make_runner(tmp_path)
        runner._persist_regenerated_tests({"eval-003": "def test_x():\n    pass\n"})

        test_files = runner._load_test_files()
        assert test_files["eval-003"] == tmp_path / "out" / "test_eval_003.py"


class TestSameSiteStoriesDoNotCollide:
    """B-094: two stories on one site must own two files, not overwrite one."""

    def _make_runner(self, tmp_path: Path) -> EvalRunner:
        dataset_dir = tmp_path / "dataset"
        captures_dir = tmp_path / "captures"
        dataset_dir.mkdir()
        captures_dir.mkdir()
        for story_id in ("eval-007", "eval-008"):
            golden = {
                "id": story_id,
                "site": "banking_mock",
                "base_url": "http://localhost:8781/",
                "conditions": [f"1. Step for {story_id}"],
                "golden_resolutions": [],
            }
            (dataset_dir / f"{story_id}_banking_mock.json").write_text(json.dumps(golden))
        return EvalRunner(
            dataset_dir=dataset_dir,
            code_dir=captures_dir,
            db_path=tmp_path / "test.sqlite",
            test_output_dir=tmp_path / "out",
        )

    def test_same_site_stories_get_distinct_files(self, tmp_path: Path) -> None:
        runner = self._make_runner(tmp_path)
        runner._persist_regenerated_tests(
            {
                "eval-007": "def test_seven():\n    pass\n",
                "eval-008": "def test_eight():\n    pass\n",
            }
        )

        seven = tmp_path / "out" / "test_eval_007.py"
        eight = tmp_path / "out" / "test_eval_008.py"
        assert seven.exists() and eight.exists()
        assert "test_seven" in seven.read_text(encoding="utf-8")
        assert "test_eight" in eight.read_text(encoding="utf-8")

        test_files = runner._load_test_files()
        assert test_files["eval-007"] == seven
        assert test_files["eval-008"] == eight
        assert test_files["eval-007"] != test_files["eval-008"]
