"""CLI pipeline execution, test running, and report generation.

Extracted from cli/main.py for easier debugging. All function signatures
and imports are preserved exactly — this is a pure extraction, no refactoring.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from src.evidence_loader import (
    get_failure_diagnostics,
    load_evidence_for_package,
)
from src.pipeline_report_service import PipelineReportService
from src.pipeline_run_service import PipelineRunService
from src.pytest_output_parser import RunResult
from src.ui_pipeline import (
    PipelineSessionState,
    parse_requirements_text,
)
from src.ui_pipeline import (
    build_test_plan as ui_build_test_plan,
)
from src.ui_pipeline import (
    parse_target_urls as ui_parse_target_urls,
)
from src.ui_pipeline import (
    run_pipeline as ui_run_pipeline,
)

from .color import cyan, green, red, yellow
from .menu_renderer import print_header, print_menu, read_optional

# ── Requirements parsing ──────────────────────────────────────────────────


def parse_requirements(raw: str) -> tuple[str, str]:
    """Parse raw text into user story and acceptance criteria."""
    return parse_requirements_text(raw)


# ── Living test plan ──────────────────────────────────────────────────────


async def build_test_plan(session: Any) -> None:
    """Analyze requirements and build a living test plan for review."""
    print_header("Living Test Plan")

    user_story, criteria = parse_requirements(session.raw_requirements)
    if not user_story or not criteria:
        print(yellow("  Could not parse user story or criteria. Proceeding without plan."))
        return

    try:
        session.test_plan = ui_build_test_plan(
            user_story=user_story,
            criteria=criteria,
            provider=session.provider,
            provider_base_url=session.provider_base_url,
            model_name=session.model_name,
        )
        session.pipeline_conditions = session.test_plan.conditions
        print(green(f"  Plan built: {len(session.pipeline_conditions)} condition(s) derived."))
    except Exception as exc:
        print(yellow(f"  Could not build plan ({exc}). Proceeding without plan."))
        return

    # Display conditions
    print(f"\n  {'ID':<12} {'Type':<16} {'Intent':<20} {'Condition'}")
    print("  " + "-" * 70)
    for c in session.test_plan.conditions:
        print(f"  {c.id:<12} {c.type:<16} {c.intent:<20} {c.text}")

    # Sign-off
    signoff = print_menu(["Sign off and confirm", "Skip sign-off"], "Sign off the plan?")
    if signoff == 0:
        tester_name = read_optional("  Tester name:", "Anonymous")
        sign_notes = read_optional("  Sign-off notes (optional):")
        session.test_plan = session.test_plan.sign_off(
            tester_name=tester_name,
            sign_off_notes=sign_notes,
        )
        session.plan_confirmed = True
        print(green("  Plan signed off. Generation unlocked."))
    else:
        print(yellow("  Plan not signed off. Generation will be locked."))


async def _prompt_sign_off(session: Any) -> None:
    """Prompt the user to sign off the test plan."""
    print_header("Test Plan Sign-Off Required")
    if session.test_plan and session.test_plan.conditions:
        print(f"\n  Plan has {len(session.test_plan.conditions)} condition(s) — not yet signed off.")
        print()
        print(f"  {'ID':<12} {'Type':<16} {'Intent':<20} {'Condition'}")
        print("  " + "-" * 70)
        for c in session.test_plan.conditions:
            print(f"  {c.id:<12} {c.type:<16} {c.intent:<20} {c.text}")
        print()

    signoff = print_menu(["Sign off and confirm", "Cancel"], "Sign off the plan?")
    if signoff == 0:
        tester_name = read_optional("  Tester name:", "Anonymous")
        sign_notes = read_optional("  Sign-off notes (optional):")
        if session.test_plan is not None:
            session.test_plan = session.test_plan.sign_off(
                tester_name=tester_name,
                sign_off_notes=sign_notes,
            )
        session.plan_confirmed = True
        print(green("  Plan signed off. Generation unlocked."))
    else:
        print(yellow("  Sign-off cancelled."))


# ── Pipeline execution ────────────────────────────────────────────────────


async def run_pipeline(session: Any) -> None:
    """Execute the full intelligent pipeline."""
    print_header("Running Intelligent Pipeline")

    user_story, criteria = parse_requirements(session.raw_requirements)
    target_urls = ui_parse_target_urls(session.starting_url, session.additional_urls)

    if not user_story.strip():
        session.pipeline_error = "Please provide a user story."
        print(red(f"  ✗ {session.pipeline_error}"))
        return
    if not criteria.strip():
        session.pipeline_error = "Please provide acceptance criteria."
        print(red(f"  ✗ {session.pipeline_error}"))
        return
    if not session.plan_confirmed:
        if session.test_plan and session.test_plan.conditions:
            print(yellow("  Plan exists but is not signed off. Prompting for sign-off..."))
            await _prompt_sign_off(session)
            if not session.plan_confirmed:
                print(yellow("  Pipeline skipped — plan not signed off."))
                return
        else:
            session.pipeline_error = "Build, review, and sign off the Living Test Plan before generation."
            print(red(f"  ✗ {session.pipeline_error}"))
            return

    print(cyan("  Running pipeline — this may take a few minutes…"))

    conditions = list(session.pipeline_conditions or [])
    if not conditions and session.test_plan:
        conditions = session.test_plan.conditions

    try:
        ui_session = PipelineSessionState()
        await ui_run_pipeline(
            user_story=user_story,
            criteria=criteria,
            provider=session.provider,
            provider_base_url=session.provider_base_url,
            model_name=session.model_name,
            target_urls=target_urls,
            consent_mode=session.consent_mode,
            reviewed_conditions=conditions,
            session=ui_session,
            credential_profile=session.credential_profile,
            journey_steps=session.journey_steps if session.journey_steps else None,
        )
    except Exception as exc:
        session.pipeline_error = str(exc)

    if session.pipeline_error:
        print(red(f"  ✗ Pipeline failed: {session.pipeline_error}"))
        return

    session.pipeline_results = ui_session.get("pipeline_results")
    session.pipeline_skeleton = ui_session.get("pipeline_skeleton") or ""
    session.pipeline_urls = ui_session.get("pipeline_urls") or []
    session.pipeline_scraped_pages = ui_session.get("pipeline_scraped_pages") or {}
    session.pipeline_unresolved = ui_session.get("pipeline_unresolved") or []
    session.pipeline_criteria = ui_session.get("pipeline_criteria") or criteria
    session.pipeline_saved_path = ui_session.get("pipeline_saved_path") or ""
    session.pipeline_manifest_path = ui_session.get("pipeline_manifest_path") or ""

    if session.pipeline_saved_path:
        print(green(f"  ✓ Tests saved to: {session.pipeline_saved_path}"))
    else:
        print(yellow("  ⚠ Pipeline completed, but no test artifact path was produced."))

    if session.pipeline_unresolved:
        print(yellow(f"  ⚠ {len(session.pipeline_unresolved)} unresolved placeholder(s) — converted to skips."))
    else:
        print(green("  ✓ All placeholders resolved."))


# ── URL parsing ───────────────────────────────────────────────────────────


def parse_target_urls(base_url: str, urls_input: str) -> list[str]:
    urls = [u.strip() for u in urls_input.splitlines() if u.strip()]
    if base_url.strip() and base_url.strip() not in urls:
        urls.insert(0, base_url.strip())
    return urls


# ── Run generated tests ───────────────────────────────────────────────────


def run_generated_tests(session: Any, rerun_failed: bool = False) -> None:
    """Execute generated tests with pytest."""
    if not session.pipeline_saved_path:
        print(yellow("  No generated tests to run. Run the pipeline first."))
        return

    try:
        print(cyan("  Running generated tests with pytest..."))
        exec_result = PipelineRunService().run_saved_test(
            session.pipeline_saved_path,
            rerun_failed_only=rerun_failed,
            previous_run=session.pipeline_run_result if rerun_failed else None,
        )
        session.pipeline_run_result = exec_result.run_result
        session.pipeline_run_output = exec_result.display_output
        session.pipeline_run_command = " ".join(exec_result.command)
        session.pipeline_run_return_code = exec_result.return_code

        if session.pipeline_run_return_code == 0:
            print(green("  All tests passed!"))
        else:
            print(yellow(f"  Tests completed with return code {session.pipeline_run_return_code}"))
    except Exception as exc:
        session.pipeline_error = f"Failed to run generated tests: {exc}"


def display_run_results(session: Any) -> None:
    """Display pytest results and metrics."""
    run_result = session.pipeline_run_result
    if not isinstance(run_result, RunResult):
        print(yellow("  No test results to display."))
        return

    print()
    if session.pipeline_run_command:
        print(f"  Command: {session.pipeline_run_command}")
    print()

    if run_result.errors > 0:
        print(red("  Pytest hit a collection or import error."))

    print(
        f"  Total: {run_result.total}  Passed: {run_result.passed}  "
        f"Failed: {run_result.failed}  Skipped: {run_result.skipped}  Errors: {run_result.errors}"
    )

    if session.pipeline_run_output:
        print()
        print("  --- Pytest Output ---")
        print(session.pipeline_run_output)


# ── Reports ───────────────────────────────────────────────────────────────


def generate_reports(session: Any) -> None:
    """Generate local, Jira, and HTML reports."""
    if not session.pipeline_results or not session.pipeline_saved_path:
        print(yellow("  No pipeline results to generate reports for."))
        return

    try:
        bundle = PipelineReportService().build_reports(
            criteria_text=session.pipeline_criteria,
            generated_code=session.pipeline_results,
            run_result=session.pipeline_run_result
            if isinstance(session.pipeline_run_result, RunResult)
            else RunResult(),
            package_dir=str(Path(session.pipeline_saved_path).resolve().parent),
        )
        session.pipeline_local_report = bundle.local_report
        session.pipeline_jira_report = bundle.jira_report
        session.pipeline_html_report = bundle.html_report
        session.pipeline_local_report_path = bundle.local_report_path
        session.pipeline_jira_report_path = bundle.jira_report_path
        session.pipeline_html_report_path = bundle.html_report_path

        print(green(f"  Local report:  {bundle.local_report_path}"))
        print(green(f"  Jira report:   {bundle.jira_report_path}"))
        print(green(f"  HTML report:   {bundle.html_report_path}"))
    except Exception as exc:
        print(red(f"  Report generation failed: {exc}"))


def view_reports(session: Any) -> None:
    """Let user view/download reports."""
    if (
        not session.pipeline_local_report_path
        and not session.pipeline_jira_report_path
        and not session.pipeline_html_report_path
    ):
        generate_reports(session)

    options: list[str] = []
    if session.pipeline_local_report_path:
        options.append(f"Local report ({session.pipeline_local_report_path})")
    if session.pipeline_jira_report_path:
        options.append(f"Jira report ({session.pipeline_jira_report_path})")
    if session.pipeline_html_report_path:
        options.append(f"HTML report ({session.pipeline_html_report_path})")
    if not options:
        print(yellow("  No reports available."))
        return

    idx = print_menu(options, "Select report to view")
    paths = [session.pipeline_local_report_path, session.pipeline_jira_report_path, session.pipeline_html_report_path]
    report_path = paths[idx]
    try:
        print()
        print(cyan(f"  Opening report: {report_path}"))
        print(yellow("  (If the viewer doesn't open, open the file manually)"))
        print()
        _open_file(report_path)
        content = Path(report_path).read_text(encoding="utf-8")
        print("  --- Preview (first 30 lines) ---")
        for line in content.splitlines()[:30]:
            print(f"  {line}")
        if len(content.splitlines()) > 30:
            print(f"  ... ({len(content.splitlines()) - 30} more lines — see opened file for full report)")
        print("  --- End preview ---")
        print()
    except Exception as exc:
        print(red(f"  Error opening report: {exc}"))
        print(yellow(f"  File location: {report_path}"))


def _open_file(path: str) -> None:
    """Open a file using the system's default application."""
    import subprocess

    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[name-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=True)
        else:
            subprocess.run(["xdg-open", path], check=True)
    except Exception:
        pass


# ── Failure diagnostics viewer ────────────────────────────────────────────


def view_failure_diagnostics(session: Any) -> None:
    """Display per-failure diagnostic information from evidence JSON files."""
    print_header("Failure Diagnostics")

    if not session.pipeline_saved_path:
        print(yellow("  No generated tests yet. Run the pipeline first."))
        return

    package_dir = str(Path(session.pipeline_saved_path).resolve().parent)
    evidence_map = load_evidence_for_package(package_dir)

    if not evidence_map:
        print(yellow("  No evidence files found. Run the generated tests first."))
        return

    failed_count = 0
    for test_name, evidence in evidence_map.items():
        diag = get_failure_diagnostics(evidence)
        if not diag.get("failed_steps"):
            continue

        failed_count += 1
        print(red(f"\n  [{failed_count}] {test_name}"))
        print(f"      Condition: {diag.get('condition_ref', '?')}")
        print(f"      Duration:  {diag.get('test_duration_s', 0):.2f}s")
        print(f"      Page:      {diag.get('page_url', 'N/A')}")
        if diag.get("page_title"):
            print(f"      Title:     {diag['page_title']}")

        for step in diag["failed_steps"]:
            print()
            print(red(f"      Step {step.get('step_number', '?')} ({step.get('step_type', '?')}) FAILED"))
            if step.get("label"):
                print(f"         Label:   {step['label']}")
            if step.get("locator"):
                print(f"         Locator: {step['locator']}")
            error_summary = step.get("error_summary", "")
            if error_summary:
                if len(error_summary) > 300:
                    error_summary = error_summary[:297] + "..."
                print(f"         Error:   {error_summary}")

            suggestions = step.get("suggested_locators", [])
            if suggestions:
                top = suggestions[:3]
                locs = ", ".join(f"`{s.get('locator', '?')}`" for s in top)
                print(yellow(f"         Suggested alternatives: {locs}"))

            elements = step.get("available_elements", [])
            if elements:
                roles: dict[str, int] = {}
                for elem in elements[:20]:
                    role = elem.get("role", elem.get("tag", "unknown"))
                    roles[role] = roles.get(role, 0) + 1
                summary = ", ".join(f"[{r}]x{c}" for r, c in sorted(roles.items()))
                print(f"         Available elements: {summary}")

    if failed_count == 0:
        print(green("  No failures found — all tests passed!"))
    else:
        print()
        print(yellow(f"  Total failed tests: {failed_count}"))


# ── Scrape summary ────────────────────────────────────────────────────────


def show_scrape_summary(session: Any) -> None:
    print_header("Scrape Summary")
    if session.pipeline_urls:
        for url in session.pipeline_urls:
            elem_count = len(session.pipeline_scraped_pages.get(url, []))
            print(f"  - {url} ({elem_count} elements)")
    else:
        print("  No URLs were scraped.")
    if session.pipeline_unresolved:
        print()
        print(yellow(f"  {len(session.pipeline_unresolved)} unresolved placeholder(s):"))
        for ph in session.pipeline_unresolved:
            print(f"    - {ph}")


# ── Skeleton viewer ───────────────────────────────────────────────────────


def show_skeleton(session: Any) -> None:
    print_header("Generated Skeleton (pre-resolution)")
    if session.pipeline_skeleton:
        print(session.pipeline_skeleton[:4000])
        if len(session.pipeline_skeleton) > 4000:
            print("  ... (truncated)")
    else:
        print("  No skeleton available.")
