"""Tests for eval_runner.py — eval harness orchestration."""

import json
from pathlib import Path

import pytest
from eval_metrics import ResolutionResult, StoryResult
from eval_runner import (
    EvalRunner,
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
        total, passed, failed, skipped, duration, output = run_generated_tests(test_file, pytest_timeout=15.0)
        assert total >= 1
        assert passed >= 1
        assert failed == 0

    def test_file_not_found(self, tmp_path: Path) -> None:
        # Non-existent file — pytest returns errors
        test_file = tmp_path / "test_missing.py"
        total, passed, failed, skipped, duration, output = run_generated_tests(test_file, pytest_timeout=15.0)
        assert total == 0


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
