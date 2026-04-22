"""Run generated pipeline test packages and parse their pytest results."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from src.pytest_output_parser import RunResult, format_pytest_output_for_display, parse_pytest_output
from src.run_utils import build_pytest_run_command, get_failed_nodeids


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

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=cwd or project_root,
            env=env,
            check=False,
        )

        raw_output = "\n".join(part for part in [completed.stdout, completed.stderr] if part).strip()
        run_result = parse_pytest_output(raw_output)
        return PipelineExecutionResult(
            command=command,
            run_result=run_result,
            display_output=format_pytest_output_for_display(raw_output),
            return_code=completed.returncode,
        )
