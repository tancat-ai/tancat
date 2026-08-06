"""Run generated pipeline test packages and parse their pytest results."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from src.pytest_output_parser import RunResult, TestResult, format_pytest_output_for_display, parse_pytest_output
from src.run_result_persistence import persist_run_result
from src.run_utils import build_pytest_run_command, get_failed_nodeids


def merge_rerun_results(previous: RunResult, rerun: RunResult) -> RunResult:
    """Merge a failed-only rerun into the previous full run result.

    A "Re-run Failed Only" run only exercises the previously-failed tests, so
    its result alone would drop the passing tests from the table. Merge it
    back into the previous run: non-re-run tests keep their prior result and
    re-run tests take the new outcome, preserving order.
    """
    rerun_map = {r.name: r for r in rerun.results}
    merged_results: list[TestResult] = []
    seen: set[str] = set()
    for r in previous.results:
        merged_results.append(rerun_map.get(r.name, r))
        seen.add(r.name)
    for r in rerun.results:
        if r.name not in seen:
            merged_results.append(r)
    return RunResult(
        results=merged_results,
        total=len(merged_results),
        passed=sum(1 for r in merged_results if r.status == "passed"),
        failed=sum(1 for r in merged_results if r.status == "failed"),
        skipped=sum(1 for r in merged_results if r.status == "skipped"),
        errors=sum(1 for r in merged_results if r.status == "error"),
        duration=rerun.duration,
        raw_output=rerun.raw_output,
    )


@dataclass(frozen=True)
class PipelineExecutionResult:
    """Structured result for one generated-package pytest execution."""

    command: list[str]
    run_result: RunResult
    display_output: str
    return_code: int


class PipelineRunService:
    """Execute saved generated tests via pytest and parse the output."""

    def run_saved_test(
        self,
        saved_path: str,
        *,
        rerun_failed_only: bool = False,
        previous_run: RunResult | None = None,
        cwd: str | None = None,
        persist: bool = False,
    ) -> PipelineExecutionResult:
        """Run a saved generated test file and return parsed results."""
        failed_nodeids = get_failed_nodeids(previous_run.results) if rerun_failed_only and previous_run else []
        pytest_command = build_pytest_run_command(saved_path, failed_nodeids=failed_nodeids or None)
        command = [sys.executable, "-m", *pytest_command]

        project_root = str(Path(__file__).resolve().parent.parent)
        package_dir = str(Path(saved_path).parent.absolute())

        env = os.environ.copy()
        # Add both project root and package directory to PYTHONPATH
        env["PYTHONPATH"] = os.pathsep.join([project_root, package_dir, env.get("PYTHONPATH", "")])

        # Enforce a hard timeout so the CLI never hangs forever on stuck tests.
        # Default 10 minutes: live-site suites with browser startup, evidence
        # tracking and 9+ tests routinely exceed 5 minutes. Configurable via
        # PIPELINE_TEST_TIMEOUT.
        timeout_secs = int(os.environ.get("PIPELINE_TEST_TIMEOUT", "600"))

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=cwd or project_root,
            env=env,
            check=False,
            timeout=timeout_secs,
        )

        raw_output = "\n".join(part for part in [completed.stdout, completed.stderr] if part).strip()
        run_result = parse_pytest_output(raw_output)

        # Persist run result to disk for historical comparison
        if persist:
            persist_run_result(run_result, test_package=saved_path)

        return PipelineExecutionResult(
            command=command,
            run_result=run_result,
            display_output=format_pytest_output_for_display(raw_output),
            return_code=completed.returncode,
        )
