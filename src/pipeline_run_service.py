"""Run generated pipeline test packages and parse their pytest results."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from src.pytest_output_parser import RunResult, TestResult, format_pytest_output_for_display, parse_pytest_output
from src.run_result_persistence import persist_run_result
from src.run_utils import build_pytest_run_command, get_failed_nodeids

#: Hard-ceiling floor for a generated suite, in seconds.
_TEST_TIMEOUT_FLOOR = 600

#: Seconds allowed per generated test on top of the floor. A generated test
#: re-navigates and records evidence per step, and each evidence step captures a
#: full-page screenshot plus a lossless WebP re-encode — ~5s per step, ~2.5 steps
#: per test, so ~17s per test measured on a long local page. A flat 600s ceiling
#: killed a healthy 48-test suite; scaling keeps big stories runnable while still
#: bounding a genuinely stuck run.
_TEST_TIMEOUT_PER_TEST = 25


def count_generated_tests(test_path: str | Path) -> int:
    """Count ``def test_...`` functions in a generated test file or package dir."""
    path = Path(test_path)
    files = sorted(path.glob("test_*.py")) if path.is_dir() else [path]
    total = 0
    for file in files:
        try:
            total += len(re.findall(r"^\s*def test_\w+", file.read_text(encoding="utf-8"), re.M))
        except OSError:
            continue
    return total


def resolve_test_timeout(test_path: str | Path) -> int:
    """Hard pytest timeout for a generated suite, in seconds.

    ``PIPELINE_TEST_TIMEOUT`` wins when set (unchanged back-compat). Otherwise
    the ceiling scales with the number of tests: a flat 600s was fine for the 9
    tests it was chosen for, but a 48-test story needs ~15 minutes of evidence
    capture alone and was being killed mid-run.
    """
    override = os.environ.get("PIPELINE_TEST_TIMEOUT", "").strip()
    if override:
        return int(override)
    return max(_TEST_TIMEOUT_FLOOR, _TEST_TIMEOUT_PER_TEST * count_generated_tests(test_path))


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
        # Phase 6e — free-tier run gate: a free deployment is capped at
        # AITEST_FREE_TIER_RUNS runs per 30 days; paid tiers are unlimited.
        try:
            from src.usage_meter import FreeTierLimitError, UsageMeter

            UsageMeter().assert_run_allowed()
        except FreeTierLimitError as exc:
            raise FreeTierLimitError(
                f"{exc}\nSet AITEST_ENFORCE_FREE_TIER=0 to disable the free-tier cap "
                "(self-hosted deployments), or install a paid license to lift it."
            ) from exc
        failed_nodeids = get_failed_nodeids(previous_run.results) if rerun_failed_only and previous_run else []
        pytest_command = build_pytest_run_command(saved_path, failed_nodeids=failed_nodeids or None)
        command = [sys.executable, "-m", *pytest_command]

        project_root = str(Path(__file__).resolve().parent.parent)
        # saved_path may be a test FILE (UI/CLI always pass files) or a package
        # DIRECTORY (e.g. the learning-loop E2E). A directory's own .parent is
        # the wrong evidence scope — it would land in generated_tests/evidence/
        # and chain stale sidecars into flow memory. Resolve the package dir
        # explicitly so both target shapes point at the package's own evidence/.
        saved = Path(saved_path)
        package_path = saved if saved.is_dir() else saved.parent
        package_dir = str(package_path.absolute())

        env = os.environ.copy()
        # Add both project root and package directory to PYTHONPATH
        env["PYTHONPATH"] = os.pathsep.join([project_root, package_dir, env.get("PYTHONPATH", "")])

        # Enforce a hard timeout so the CLI never hangs forever on stuck tests.
        # Scales with the suite (see ``resolve_test_timeout``); configurable via
        # PIPELINE_TEST_TIMEOUT, which overrides the scaling.
        timeout_secs = resolve_test_timeout(saved_path)

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
            # AI-042-F3: suite-level flow chaining — after a real run, chain
            # the package's fully-passing tests into GOTO transitions (terminal
            # of test N → entry of test N+1). Within-test flows are learned per
            # test by the conftest hook; this closes the suite-level shape for
            # the UI/CLI product paths (synthesize_stories does it for training
            # runs). Best-effort — never breaks the run.
            try:
                from src.flow_memory import FlowMemoryStore

                FlowMemoryStore().learn_suite_flows(Path(package_dir) / "evidence")
            except Exception:
                pass

        return PipelineExecutionResult(
            command=command,
            run_result=run_result,
            display_output=format_pytest_output_for_display(raw_output),
            return_code=completed.returncode,
        )
