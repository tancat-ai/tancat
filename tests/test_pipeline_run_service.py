"""Tests for generated-package execution service."""

from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from src.pipeline_run_service import PipelineRunService
from src.pytest_output_parser import RunResult, TestResult


def test_run_saved_test_executes_pytest_module_and_parses_output() -> None:
    service = PipelineRunService()
    stdout = """
generated_tests/test_demo.py::test_checkout PASSED [100%]
============================== 1 passed in 1.20s ==============================
"""

    with patch("src.pipeline_run_service.subprocess.run") as mock_run:
        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")
        result = service.run_saved_test("generated_tests/test_demo.py", cwd=".")

    assert result.command[:3] == ["python", "-m", "pytest"] or result.command[1:3] == ["-m", "pytest"]
    assert result.run_result.passed == 1
    assert "test_checkout PASSED" in result.display_output
    assert result.return_code == 0


def test_run_saved_test_uses_failed_only_rerun_when_requested() -> None:
    service = PipelineRunService()
    previous_run = RunResult(
        results=[
            TestResult(
                name="test_checkout[chromium]",
                status="failed",
                duration=0.0,
                error_message="boom",
                file_path="generated_tests/test_demo.py",
            )
        ]
    )

    with patch("src.pipeline_run_service.subprocess.run") as mock_run:
        mock_run.return_value = CompletedProcess(args=[], returncode=1, stdout="", stderr="")
        result = service.run_saved_test(
            "generated_tests/test_demo.py",
            rerun_failed_only=True,
            previous_run=previous_run,
            cwd=".",
        )

    assert "generated_tests/test_demo.py::test_checkout[chromium]" in result.command


def test_run_saved_test_chains_suite_flows_when_persisting() -> None:
    """AI-042-F3: a real (persisting) run chains the package's suite flows —
    the UI/CLI product-path hook (within-test flows come from the conftest)."""
    service = PipelineRunService()
    stdout = """
generated_tests/pkg/test_01.py::test_01_login PASSED [50%]
generated_tests/pkg/test_02.py::test_02_products PASSED [100%]
============================== 2 passed in 1.20s ==============================
"""
    captured: dict[str, object] = {}

    def fake_learn(self: object, evidence_dir: object) -> dict[str, int]:  # noqa: ARG002
        captured["evidence_dir"] = evidence_dir
        return {"sidecars": 2, "inserted": 1, "exists": 0, "errors": 0}

    with (
        patch("src.pipeline_run_service.subprocess.run") as mock_run,
        patch("src.pipeline_run_service.persist_run_result") as mock_persist,
        patch("src.flow_memory.FlowMemoryStore.learn_suite_flows", fake_learn),
    ):
        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")
        service.run_saved_test("generated_tests/pkg/test_01.py", cwd=".", persist=True)

    mock_persist.assert_called_once()
    # the chain hook gets the package's evidence dir
    assert captured["evidence_dir"] == Path("generated_tests/pkg/evidence").absolute()


def test_run_saved_test_does_not_chain_on_preview_runs() -> None:
    """Non-persisting (preview) runs skip the suite-chain hook."""
    service = PipelineRunService()
    stdout = "\n============================== 1 passed in 1.00s ==============================\n"

    with (
        patch("src.pipeline_run_service.subprocess.run") as mock_run,
        patch("src.flow_memory.FlowMemoryStore.learn_suite_flows") as mock_learn,
    ):
        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")
        service.run_saved_test("generated_tests/test_demo.py", cwd=".", persist=False)

    mock_learn.assert_not_called()
