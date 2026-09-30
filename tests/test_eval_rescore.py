"""B-093: the held-out gate score is cheap, honest and repeatable.

A run keeps its evidence in one known place (`eval_evidence.py`), a re-score
recomputes the gate numbers from that evidence with no model call and no live
site, and a run whose evidence is gone is caught instead of read as a zero.

The recorded last re-score (82/113 gate 1, 3 hollow passes) has **no surviving
artifacts** - `scratch/gate1_full.log` and the emitted dirs were deleted - so
these tests prove the mechanism on a synthetic run that reproduces a known
number. The next live held-out run must reproduce
`scripts/eval/known_gate_scores.json`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_EVAL_DIR = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))

import rescore  # noqa: E402
from eval_evidence import (  # noqa: E402
    MissingEvidenceError,
    emitted_filename,
    read_run_evidence,
    verify_run_evidence,
    write_run_evidence,
)
from eval_metrics import HarnessReport, ResolutionResult, StoryResult  # noqa: E402
from golden_validator import validate_story  # noqa: E402

_GOLDEN = {
    "id": "eval-999",
    "site": "test",
    "base_url": "https://example.com",
    "conditions": ["1. Backpack in cart"],
    "golden_resolutions": [
        {
            "criterion_index": 0,
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

# The emitted code targets the WRONG element, so gate 1 is 0/1. Its own test
# passed (the JUnit XML below), and it is unverified, so gate 2 is 1.
_CODE = "def test_01_a(page):\n    evidence_tracker.assert_visible('#wrong', label='backpack')\n"

_JUNIT = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    "<testsuites><testsuite>"
    '<testcase name="test_01_a[chromium]" />'
    "</testsuite></testsuites>"
)


def _build_run(tmp_path: Path, *, mode: str = "full", with_junit: bool = True) -> tuple[Path, Path]:
    """Build a synthetic dataset + run directory and return both paths."""
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    (dataset_dir / "eval-999.json").write_text(json.dumps(_GOLDEN), encoding="utf-8")

    run_dir = tmp_path / "run"
    # The per-placeholder result the run recorded (also carries the story id).
    story = validate_story(_CODE, _GOLDEN)
    write_run_evidence(
        run_dir,
        code_map={"eval-999": _CODE},
        results=[story],
        verdict_map={"eval-999": [{"status": "unverified", "reason": "no element check"}]},
        summary="synthetic run",
        metadata={"mode": mode, "dataset": str(dataset_dir)},
    )
    if with_junit:
        junit_dir = run_dir / "junit"
        junit_dir.mkdir(parents=True, exist_ok=True)
        (junit_dir / f"{emitted_filename('eval-999').replace('.py', '.xml')}").write_text(_JUNIT, encoding="utf-8")
    return dataset_dir, run_dir


class TestEvidenceLayout:
    def test_write_then_read_roundtrips(self, tmp_path: Path) -> None:
        dataset_dir, run_dir = _build_run(tmp_path)

        evidence = read_run_evidence(run_dir)

        assert evidence.code_map == {"eval-999": _CODE}
        assert evidence.verdict_map["eval-999"][0]["status"] == "unverified"
        assert evidence.manifest["dataset"] == str(dataset_dir)

    def test_full_run_without_junit_is_incomplete(self, tmp_path: Path) -> None:
        _dataset_dir, run_dir = _build_run(tmp_path, with_junit=False)

        problems = verify_run_evidence(run_dir)

        assert any("per-test outcomes" in p for p in problems)

    def test_static_run_needs_no_junit(self, tmp_path: Path) -> None:
        _dataset_dir, run_dir = _build_run(tmp_path, mode="static", with_junit=False)

        assert verify_run_evidence(run_dir) == []


class TestRescore:
    def test_reproduces_a_known_number_from_kept_evidence(self, tmp_path: Path) -> None:
        """Gate 1 = 0/1 (wrong element) and gate 2 = 1 (unverified ASSERT, test passed)."""
        dataset_dir, run_dir = _build_run(tmp_path)

        report = rescore.rescore(run_dir, dataset_dir)

        assert report.correct_resolutions == 0
        assert report.total_placeholders == 1
        assert report.total_false_positives == 1

    def test_reproduces_the_same_numbers_twice(self, tmp_path: Path) -> None:
        """A re-score is repeatable: the same kept evidence gives the same score."""
        dataset_dir, run_dir = _build_run(tmp_path)

        first = rescore.rescore(run_dir, dataset_dir)
        second = rescore.rescore(run_dir, dataset_dir)

        assert (first.correct_resolutions, first.total_false_positives) == (
            second.correct_resolutions,
            second.total_false_positives,
        )

    def test_makes_no_model_call(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The re-score must not construct or call an LLM."""
        import src.llm_client as llm_client

        def _boom(*args: object, **kwargs: object) -> None:
            raise AssertionError("the re-score must not call a model")

        monkeypatch.setattr(llm_client.LLMClient, "__init__", _boom)
        monkeypatch.setattr(llm_client.LLMClient, "generate", _boom)
        dataset_dir, run_dir = _build_run(tmp_path)

        report = rescore.rescore(run_dir, dataset_dir)

        assert report.total_placeholders == 1


class TestEvidenceGuard:
    def test_missing_run_dir_is_caught(self, tmp_path: Path) -> None:
        problems = verify_run_evidence(tmp_path / "gone")

        assert problems and "does not exist" in problems[0]

    def test_deleted_junit_is_caught_by_read(self, tmp_path: Path) -> None:
        _dataset_dir, run_dir = _build_run(tmp_path)
        for xml in (run_dir / "junit").glob("*.xml"):
            xml.unlink()

        with pytest.raises(MissingEvidenceError) as excinfo:
            read_run_evidence(run_dir)

        assert "per-test outcomes" in str(excinfo.value)

    def test_rescore_cli_says_cannot_recompute(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """A deleted-evidence run exits 5 and says the score cannot be recomputed."""
        _dataset_dir, run_dir = _build_run(tmp_path)
        for xml in (run_dir / "junit").glob("*.xml"):
            xml.unlink()

        code = rescore.main(["--run-dir", str(run_dir)])

        assert code == 5
        assert "cannot be recomputed" in capsys.readouterr().err

    def test_rescore_cli_reports_the_gate_numbers(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        dataset_dir, run_dir = _build_run(tmp_path)

        code = rescore.main(["--run-dir", str(run_dir), "--dataset", str(dataset_dir)])

        out = capsys.readouterr().out
        assert code == 0
        assert "GATE 1 (resolution accuracy): 0/1" in out
        assert "GATE 2 (hollow passes):       1" in out

    def test_rescore_cli_fails_on_an_unexpected_number(self, tmp_path: Path) -> None:
        dataset_dir, run_dir = _build_run(tmp_path)

        code = rescore.main(["--run-dir", str(run_dir), "--dataset", str(dataset_dir), "--expect-gate2", "0"])

        assert code == 2

    def test_recorded_score_file_is_present_and_honest(self) -> None:
        """The recorded 82/113 + 3 is on disk, so the next run can be compared."""
        payload = json.loads((_EVAL_DIR / "known_gate_scores.json").read_text(encoding="utf-8"))
        assert (payload["gate1_correct"], payload["gate1_total"]) == (82, 113)
        assert payload["gate2_false_greens"] == 3
        assert "deleted" in payload["note"]


class TestHarnessEvidenceHook:
    def test_runner_accepts_an_evidence_dir(self, tmp_path: Path) -> None:
        from eval_runner import EvalRunner

        runner = EvalRunner(
            dataset_dir=tmp_path,
            code_dir=tmp_path,
            db_path=tmp_path / "db.sqlite",
            evidence_dir=tmp_path / "evidence",
        )
        assert runner.evidence_dir == tmp_path / "evidence"

    def test_harness_run_writes_and_verifies_evidence(self, tmp_path: Path) -> None:
        """A static harness run with --evidence-dir leaves a scorable directory."""
        from eval_runner import EvalRunner

        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        (dataset_dir / "eval-999.json").write_text(json.dumps(_GOLDEN), encoding="utf-8")
        captures = tmp_path / "captures"
        captures.mkdir()
        (captures / "eval_999_code.py").write_text(_CODE, encoding="utf-8")
        evidence_dir = tmp_path / "evidence"

        runner = EvalRunner(
            dataset_dir=dataset_dir,
            code_dir=captures,
            db_path=tmp_path / "db.sqlite",
            evidence_dir=evidence_dir,
        )
        # The capture filename is derived from the site; feed the code map directly
        # so the test does not depend on that convention.
        runner._load_code_map = lambda: {"eval-999": _CODE}  # type: ignore[method-assign]

        runner.run(mode="static", persist=False)

        assert verify_run_evidence(evidence_dir) == []
        assert (evidence_dir / "results.json").is_file()
        assert (evidence_dir / "emitted" / emitted_filename("eval-999")).is_file()


class TestFalseGreenRule:
    def test_rule_is_shared_with_the_run(self) -> None:
        """The re-score applies the same rule the run does (eval_metrics)."""
        story = StoryResult(
            story_id="eval-999",
            site="test",
            total_criteria=1,
            criteria_with_skeletons=1,
            resolutions=[
                ResolutionResult(
                    action="ASSERT",
                    description="backpack in cart",
                    expected_locator="#backpack",
                    tolerance_selectors=[],
                    generated_locator="#wrong",
                    matched=False,
                    criterion_index=0,
                    verification="unverified",
                )
            ],
        )
        from eval_metrics import count_false_greens

        assert count_false_greens(story, _CODE, {"test_01_a": "PASSED"}, passed=1) == 1
        assert count_false_greens(story, _CODE, {"test_01_a": "SKIPPED"}, passed=0) == 0

    def test_harness_report_roundtrip_carries_the_resolutions(self, tmp_path: Path) -> None:
        _dataset_dir, run_dir = _build_run(tmp_path)
        payload = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
        report = HarnessReport.from_dict(payload)
        assert report.stories[0].resolutions[0].expected_locator == "#backpack"
