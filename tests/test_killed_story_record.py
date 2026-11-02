"""A story killed by the per-file clock must record what it managed to run (d-0084).

The fault: ``run_generated_tests`` returned the B-061 marker *before* writing its
log and its JUnit file, so a story killed at the per-file clock left no
``ev/pytest`` log, no ``ev/junit`` XML, and ``results.json`` said
``tests_executed=0``. In the 2026-10-31 run that hid four eval-005 tests that ran
and failed at step 9 - the record understated failures, and gate 2 read a zero
over a smaller set than it claimed.

These tests drive the runner with a stubbed ``subprocess.run``: no model, no
browser, no live site. The first two are written without the new ``timeout_out``
argument on purpose, so on the pre-fix code they fail on the *substance* - the
evidence was dropped - rather than on a signature mismatch.
"""

from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

_EVAL_DIR = Path(__file__).resolve().parent.parent / "scripts" / "eval"
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from eval_metrics import HarnessReport  # noqa: E402
from eval_runner import (  # noqa: E402
    PYTEST_TIMEOUT_MARKER,
    _parse_junit_xml,
    run_full_validation,
    run_generated_tests,
)

#: Four tests in the file; three report before the kill, one never starts.
_TEST_FILE = """\
def test_01_a(page):
    pass


def test_02_b(page):
    pass


def test_03_c(page):
    pass


def test_04_d(page):
    pass
"""

#: What pytest -v had already printed when the clock fired.
_PARTIAL = (
    "tests/test_killed.py::test_01_a PASSED [ 25%]\n"
    "tests/test_killed.py::test_02_b PASSED [ 50%]\n"
    "tests/test_killed.py::test_03_c FAILED [ 75%]\n"
)


def _stub_timeout(monkeypatch: pytest.MonkeyPatch, partial: str, *, elapsed: float = 746.0) -> None:
    """Make the pytest subprocess be killed by its clock, after *elapsed* seconds.

    Only the runner's own ``time`` name is replaced, never the global ``time``
    module: monkeypatching ``time.monotonic`` process-wide would reach into
    pytest's timers. ``raising=False`` so the pre-fix module, which never imports
    ``time``, still reaches its own code path and fails on the substance.
    """
    ticks = iter([1000.0, 1000.0 + elapsed])
    monkeypatch.setattr(
        "eval_runner.time",
        types.SimpleNamespace(monotonic=lambda: next(ticks)),
        raising=False,
    )

    def fake_run(cmd: list[str], **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0.0), output=partial, stderr="")

    monkeypatch.setattr("eval_runner.subprocess.run", fake_run)


def test_killed_after_some_tests_keeps_their_log_and_junit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The tests that ran keep their evidence - log, JUnit entries and counts.

    Written without ``timeout_out``: on the pre-fix code this fails because the
    JUnit file is never written and the counts come back as zero.
    """
    test_file = tmp_path / "test_killed.py"
    test_file.write_text(_TEST_FILE, encoding="utf-8")
    junit_dir = tmp_path / "ev" / "junit"
    log_dir = tmp_path / "ev" / "pytest"
    _stub_timeout(monkeypatch, _PARTIAL)

    total, passed, failed, skipped, _duration, raw_output, per_test = run_generated_tests(
        test_file,
        pytest_timeout=700.0,
        junit_dir=junit_dir,
        log_dir=log_dir,
    )

    # B-061's distinction is kept: the marker still says "killed", not "clean".
    assert raw_output.strip() == PYTEST_TIMEOUT_MARKER

    # The log the killed run printed reached ev/.
    log = (log_dir / "test_killed.log").read_text(encoding="utf-8")
    assert "test_03_c FAILED" in log

    # And so did a JUnit file a re-score can read.
    kept = _parse_junit_xml(junit_dir / "test_killed.xml")
    assert kept == {"test_01_a": "PASSED", "test_02_b": "PASSED", "test_03_c": "FAILED"}

    # Three ran (two passed, one failed); the fourth never started - not zero.
    assert (total, passed, failed, skipped) == (3, 2, 1, 0)
    assert per_test["test_03_c"] == "FAILED"


def test_killed_before_any_test_ran_still_reports_killed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The other half: killed with nothing to show is still "killed", never "clean"."""
    test_file = tmp_path / "test_killed.py"
    test_file.write_text(_TEST_FILE, encoding="utf-8")
    junit_dir = tmp_path / "ev" / "junit"
    log_dir = tmp_path / "ev" / "pytest"
    _stub_timeout(monkeypatch, "")

    total, passed, failed, skipped, _duration, raw_output, per_test = run_generated_tests(
        test_file,
        pytest_timeout=700.0,
        junit_dir=junit_dir,
        log_dir=log_dir,
    )

    assert raw_output.strip() == PYTEST_TIMEOUT_MARKER
    assert (total, passed, failed, skipped) == (0, 0, 0, 0)
    assert per_test == {}
    # No test reported, so no testcase may exist - an empty file is honest.
    assert _parse_junit_xml(junit_dir / "test_killed.xml") == {}
    assert (log_dir / "test_killed.log").exists()


def test_the_record_says_which_clock_fired_and_for_how_long(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A reader must be able to see 746 s against a 730 s limit, and "3 of 4"."""
    test_file = tmp_path / "test_killed.py"
    test_file.write_text(_TEST_FILE, encoding="utf-8")
    timeout_out: dict[str, Any] = {}
    _stub_timeout(monkeypatch, _PARTIAL)

    _total, _passed, _failed, _skipped, duration, _raw, _per_test = run_generated_tests(
        test_file,
        pytest_timeout=700.0,
        timeout_out=timeout_out,
    )

    assert timeout_out["clock"] == "per-file"
    assert timeout_out["limit_s"] == 730.0
    assert timeout_out["elapsed_s"] == 746.0
    assert duration == 746.0
    assert timeout_out["tests_collected"] == 4
    assert timeout_out["tests_run"] == 3


def test_the_story_record_says_killed_after_three_of_four(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """results.json carries distinct executed/failed/not-run counts and the clock."""
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    golden = {
        "id": "eval-999",
        "site": "test",
        "base_url": "https://example.com",
        "conditions": ["1. Do X"],
        "golden_resolutions": [],
    }
    (dataset / "eval-999.json").write_text(json.dumps(golden), encoding="utf-8")
    test_file = tmp_path / "test_eval_999.py"
    test_file.write_text(_TEST_FILE, encoding="utf-8")
    evidence_dir = tmp_path / "ev"
    _stub_timeout(monkeypatch, _PARTIAL)

    results = run_full_validation(
        dataset,
        {"eval-999": "evidence_tracker.fill('#input', 'val')"},
        test_files={"eval-999": test_file},
        pytest_timeout=700.0,
        evidence_dir=evidence_dir,
    )

    story = results[0]
    assert story.tests_timed_out is True
    assert (story.tests_executed, story.tests_passed, story.tests_failed) == (3, 2, 1)
    assert story.tests_not_run == 1
    assert story.tests_collected == 4
    assert story.tests_kill_clock == "per-file"
    assert story.tests_kill_limit_s == 730.0
    assert story.tests_kill_elapsed_s == 746.0

    # The evidence a re-score reads is on disk under ev/.
    assert (evidence_dir / "junit" / "test_eval_999.xml").exists()
    assert (evidence_dir / "pytest" / "test_eval_999.log").exists()

    # And the summary cannot read as "nothing ran" or as "everything ran".
    summary = HarnessReport(stories=results).to_summary()
    assert "KILLED by the per-file clock" in summary
    assert "746s" in summary and "730s" in summary
    assert "3 ran, 1 failed, 1 not run" in summary

    # The serialized record carries the same distinct fields.
    entry = HarnessReport(stories=results).to_dict()["stories"][0]
    for key in ("tests_executed", "tests_failed", "tests_not_run", "tests_timed_out"):
        assert key in entry, key
    assert entry["tests_failed"] == 1
    assert entry["tests_not_run"] == 1
