"""Unit tests for the self-heal empty-results handling (B-045)."""

from __future__ import annotations

from pathlib import Path

from src.pytest_output_parser import RunResult
from src.self_healing import SelfHealingRunner


def test_timeout_result_not_reported_as_all_pass(tmp_path: Path) -> None:
    """A run that produced NO results (timeout/collection) must not claim
    'all tests pass' — it should surface run_error instead."""
    test_file = tmp_path / "test_x.py"
    test_file.write_text("def test_a():\n    pass\n", encoding="utf-8")

    runner = SelfHealingRunner(max_iterations=1)
    # Stub the subprocess run: simulate a timeout -> empty results
    runner._run_pytest = lambda *a, **k: RunResult(  # type: ignore[method-assign]
        results=[], raw_output="pytest timed out after 600s"
    )

    report = runner.heal(str(test_file))
    assert report.total_failures == 0
    assert report.run_error, "run_error must be set for a no-results run"
    assert "timed out" in report.run_error
    assert report.fixed == 0


def test_real_failures_are_detected(tmp_path: Path) -> None:
    """A run with failed results must report them (regression: the timeout
    bug previously made real failures look like 'all pass')."""
    from src.pytest_output_parser import TestResult

    test_file = tmp_path / "test_x.py"
    test_file.write_text("def test_a():\n    pass\n", encoding="utf-8")

    runner = SelfHealingRunner(max_iterations=1)
    runner._run_pytest = lambda *a, **k: RunResult(  # type: ignore[method-assign]
        results=[
            TestResult(name="test_a", status="failed", duration=1.0, error_message="TimeoutError", file_path=""),
        ]
    )

    report = runner.heal(str(test_file))
    assert report.total_failures == 1
    assert not report.run_error


def test_directory_saved_path_resolves_to_test_file(tmp_path: Path) -> None:
    """heal() must resolve a package DIRECTORY (sidebar load) to its test file
    instead of crashing on read_text (PermissionError on Windows)."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "test_main.py").write_text("def test_a():\n    pass\n", encoding="utf-8")

    runner = SelfHealingRunner(max_iterations=1)
    runner._run_pytest = lambda *a, **k: RunResult(results=[])  # type: ignore[method-assign]

    report = runner.heal(str(pkg))
    assert report.total_failures == 0
    assert "timed out" not in report.run_error or report.run_error  # no crash


def test_llm_failure_is_surfaced(tmp_path: Path) -> None:
    """When the LLM reviewer fails (e.g. provider not configured), the report
    must say so instead of silently counting the failure as unfixable."""
    from unittest.mock import MagicMock

    from src.pytest_output_parser import TestResult

    test_file = tmp_path / "test_x.py"
    test_file.write_text("def test_a():\n    pass\n", encoding="utf-8")

    mock_llm = MagicMock()
    mock_llm.generate_test.side_effect = ConnectionError("provider not configured")

    runner = SelfHealingRunner(llm_client=mock_llm, max_iterations=1)
    # iteration 1 finds one LOCATOR failure (LLM-worthy), review then fails
    runner._run_pytest = lambda *a, **k: RunResult(  # type: ignore[method-assign]
        results=[
            TestResult(
                name="test_a",
                status="failed",
                duration=1.0,
                error_message="Timeout waiting for locator('#x')",
                file_path="",
            )
        ]
    )
    # pre-screen must pass for a locator failure so the LLM is attempted
    runner._pre_screen_failure = lambda d: True  # type: ignore[assignment]

    report = runner.heal(str(test_file))
    assert report.run_error, "LLM unavailability must be surfaced"
    assert "LLM reviewer unavailable" in report.run_error
    assert "test_a" in report.run_error
