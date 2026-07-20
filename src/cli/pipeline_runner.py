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
from src.export_service import export_clean_suite
from src.failure_classifier import FailureCategory, classify_failure
from src.pipeline_artifact_manager import find_existing_packages
from src.pipeline_models import ExportMode
from src.pipeline_report_service import PipelineReportService
from src.pipeline_run_service import PipelineRunService
from src.pytest_output_parser import RunResult
from src.run_result_persistence import load_all_run_results
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
from .run_results_display import render_run_history_summary, render_run_results

# ── Export ────────────────────────────────────────────────────────────────


def export_clean_package(session: Any) -> None:
    """Export a clean test suite without EvidenceTracker dependency."""
    from .menu_renderer import print_menu

    print_header("Export Clean Package")

    if not session.pipeline_saved_path:
        print(yellow("  No generated test package found. Run the pipeline first."))
        print("  Press Enter to continue...")
        input()
        return

    source_path = Path(session.pipeline_saved_path)
    if not source_path.exists():
        print(yellow(f"  Package directory not found: {source_path}"))
        print("  Press Enter to continue...")
        input()
        return

    # Choose export mode
    mode_choice = print_menu(
        [
            "Flat (inline locators)",
            "POM (page-object modules)",
        ],
        "Select export mode:",
    )

    export_mode = ExportMode.FLAT if mode_choice == 0 else ExportMode.POM
    mode_label = "Flat" if export_mode == ExportMode.FLAT else "POM"

    print(f"\n  Exporting ({mode_label})...\n")

    try:
        result = export_clean_suite(
            source_package_dir=source_path,
            export_mode=export_mode,
            output_base_dir="exported_tests",
            story_slug=session.story_slug or "",
        )
        print(green(result.summary()))
        print()
    except FileNotFoundError as exc:
        print(red(f"  Export failed: {exc}"))
    except Exception as exc:
        print(red(f"  Export failed: {exc}"))

    print("  Press Enter to continue...")
    input()


# ── Requirements parsing ──────────────────────────────────────────────────


def parse_requirements(raw: str) -> tuple[str, str]:
    """Parse raw text into user story and acceptance criteria."""
    return parse_requirements_text(raw)


# ── Living test plan ──────────────────────────────────────────────────────


async def build_test_plan(session: Any) -> None:
    """Analyze requirements and build a living test plan for review.

    After building the plan, enters an interactive editing loop where the
    user can edit individual conditions (type, intent, text, expected, etc.)
    before signing off.
    """
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

    # Interactive editing loop
    while True:
        _display_conditions_table(session.test_plan)
        print()

        action = print_menu(
            ["Edit a condition", "Sign off and confirm", "Skip sign-off"],
            "Review actions",
            shortcuts=[("E", "Edit"), ("S", "Sign off"), ("K", "Skip")],
        )

        if action == 0:
            # Edit mode
            _edit_condition_interactive(session)
            continue
        elif action == 1:
            # Sign off
            tester_name = read_optional("  Tester name:", "Anonymous")
            sign_notes = read_optional("  Sign-off notes (optional):")
            session.test_plan = session.test_plan.sign_off(
                tester_name=tester_name,
                sign_off_notes=sign_notes,
            )
            session.plan_confirmed = True
            print(green("  Plan signed off. Generation unlocked."))
            return
        else:
            print(yellow("  Plan not signed off. Generation will be locked."))
            return


def _display_conditions_table(plan: Any) -> None:
    """Print a formatted table of all conditions in the plan."""
    if not plan or not plan.conditions:
        print(yellow("  No conditions in plan."))
        return

    print(f"\n  {'ID':<12} {'Type':<16} {'Intent':<20} {'Text'}")
    print("  " + "-" * 80)
    for c in plan.conditions:
        flagged = " ⚑" if c.flagged else ""
        text = c.text[:50] + "..." if len(c.text) > 50 else c.text
        print(f"  {c.id:<12} {c.type:<16} {c.intent:<20} {text}{flagged}")


_CONDITION_FIELDS: list[tuple[str, str, list[str]]] = [
    ("type", "Condition type", ["happy_path", "boundary", "negative", "exploratory", "regression", "ambiguity"]),
    (
        "intent",
        "Intent",
        ["element_presence", "element_behavior", "state_assertion", "journey_step", "journey_outcome"],
    ),
    ("text", "Condition text", []),
    ("expected", "Expected result", []),
    ("source", "Source reference", []),
    ("flagged", "Flagged for review", ["true", "false"]),
    ("src", "Source kind", ["ai", "manual", "automation"]),
]


def _edit_condition_interactive(session: Any) -> None:
    """Let the user pick a condition by ID and edit its fields."""
    plan = session.test_plan
    if not plan or not plan.conditions:
        return

    # Build a lookup by ID
    condition_ids = [c.id for c in plan.conditions]
    id_index = print_menu(condition_ids, "Select condition to edit")
    if id_index < 0:
        return

    condition_id = condition_ids[id_index]
    condition = next(c for c in plan.conditions if c.id == condition_id)

    while True:
        print_header(f"Editing: {condition_id}")
        print("  Current values:")
        for field_name, field_label, _ in _CONDITION_FIELDS:
            val = getattr(condition, field_name, "")
            print(f"    {field_label}: {val}")
        print()

        field_labels = [f"{label} ({getattr(condition, name, '')})" for name, label, _ in _CONDITION_FIELDS]
        field_labels.append("Done editing")

        field_idx = print_menu(field_labels, "Which field to edit?")
        if field_idx < 0 or field_idx == len(_CONDITION_FIELDS):
            break  # Done or cancelled

        name, label, options = _CONDITION_FIELDS[field_idx]
        current = str(getattr(condition, name, ""))

        if options:
            # Dropdown-style: show options with current highlighted
            opt_idx = print_menu(options, f"Select {label}")
            if opt_idx >= 0:
                new_val: Any = options[opt_idx]
                if name == "flagged":
                    new_val = new_val == "true"
                setattr(condition, name, new_val)
                print(green(f"  ✓ {label} updated to: {new_val}"))
        else:
            # Free-text field
            new_val = read_optional(f"  New {label} (Enter to keep current):", current)
            if new_val != current:
                setattr(condition, name, new_val)
                print(green(f"  ✓ {label} updated."))

        # Apply to plan
        session.test_plan = plan.replace_condition(condition_id, condition)

        if name == "text":
            # Re-derive intent when text changes
            from src.spec_analyzer import infer_condition_intent

            new_intent = infer_condition_intent(condition.text)
            if new_intent != condition.intent:
                condition.intent = new_intent
                session.test_plan = plan.replace_condition(condition_id, condition)
                print(green(f"  ✓ Intent re-derived: {new_intent}"))

        print("  Press Enter to continue...")
        input()


async def _prompt_sign_off(session: Any) -> None:
    """Prompt the user to sign off the test plan, with optional editing."""
    print_header("Test Plan Sign-Off Required")

    while True:
        if session.test_plan and session.test_plan.conditions:
            _display_conditions_table(session.test_plan)
            print()

        action = print_menu(
            ["Sign off and confirm", "Edit a condition", "Cancel"],
            "Plan requires sign-off before generation",
            shortcuts=[("S", "Sign off"), ("E", "Edit"), ("C", "Cancel")],
        )

        if action == 0:
            tester_name = read_optional("  Tester name:", "Anonymous")
            sign_notes = read_optional("  Sign-off notes (optional):")
            if session.test_plan is not None:
                session.test_plan = session.test_plan.sign_off(
                    tester_name=tester_name,
                    sign_off_notes=sign_notes,
                )
            session.plan_confirmed = True
            print(green("  Plan signed off. Generation unlocked."))
            return
        elif action == 1:
            _edit_condition_interactive(session)
            continue
        else:
            print(yellow("  Sign-off cancelled."))
            return


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
            pom_mode=session.pom_mode,
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

    # Surface scraper warnings and errors
    scraper_warnings = ui_session.get("pipeline_scraper_warnings") or []
    scraper_errors = ui_session.get("pipeline_scraper_errors") or []
    for w in scraper_warnings:
        print(yellow(f"  ⚠ Scraper: {w}"))
    for e in scraper_errors:
        print(red(f"  ✗ Scraper: {e}"))

    journey_count = ui_session.get("pipeline_journey_captured_count")
    if journey_count:
        print(green(f"  ✓ Captured context from {journey_count} pages"))


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
    """Display pytest results using structured run results view.

    After displaying the current run results, appends the run history
    summary showing recent trends, flaky tests, and run comparison.
    """
    run_result = session.pipeline_run_result
    if not isinstance(run_result, RunResult):
        print(yellow("  No test results to display."))
        return

    print()
    if session.pipeline_run_command:
        print(f"  Command: {session.pipeline_run_command}")
    print()

    render_run_results(run_result, show_raw=False)

    # Run history summary (AI-011 Phase 4)
    render_run_history_summary()


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


# ── Bug report ────────────────────────────────────────────────────────────


def generate_bug_report(session: Any) -> None:
    """Generate a bug report from the last test run's failures."""
    from src.cli.evidence_generator import BugEvidenceGenerator

    run_result = session.pipeline_run_result
    if not isinstance(run_result, RunResult) or not run_result.results:
        print(yellow("  No test results to generate a bug report for. Run tests first."))
        return

    failed = [r for r in run_result.results if r.status in ("failed", "error")]
    if not failed:
        print(green("  No failures — nothing to report."))
        return

    print(cyan(f"  Generating bug report for {len(failed)} failure(s)..."))

    generator = BugEvidenceGenerator()
    generator.process_run_result(run_result)

    output_dir = Path("generated_tests")
    output_dir.mkdir(exist_ok=True)
    output_path = str(output_dir / "bug_report.txt")

    report_path = generator.generate_bug_report(output_path)
    session.pipeline_bug_report = Path(report_path).read_text(encoding="utf-8")
    session.pipeline_bug_report_path = report_path

    print(green(f"  Bug report saved to: {report_path}"))
    print(session.pipeline_bug_report)


# ── Locator repair (CLI) ─────────────────────────────────────────────────


def repair_locator_cli(session: Any) -> None:
    """Interactive locator repair from the CLI.

    Lists failed tests classified as locator failures and lets the user
    pick one to repair via headed Playwright codegen.
    """
    from src.locator_repair import LocatorPatch, apply_patch_to_file, run_codegen_session

    run_result = session.pipeline_run_result
    if not isinstance(run_result, RunResult) or not run_result.results:
        print(yellow("  No test results available. Run tests first."))
        return

    # Find locator-classified failures
    locator_failures: list[tuple[Any, Any]] = []
    for result in run_result.results:
        if result.status in ("failed", "error") and result.error_message:
            detail = classify_failure(result.error_message)
            if detail.category in (
                FailureCategory.LOCATOR_TIMEOUT,
                FailureCategory.STRICT_VIOLATION,
            ):
                locator_failures.append((result, detail))

    if not locator_failures:
        print(green("  No locator failures found — nothing to repair."))
        print(yellow("  Tip: run 'Generate Bug Report' for a full breakdown."))
        return

    print(cyan(f"  Found {len(locator_failures)} locator failure(s):"))
    print()

    for idx, (result, detail) in enumerate(locator_failures, 1):
        loc_str = detail.raw_locator or "(unknown)"
        url_str = detail.failure_url or "(no URL)"
        print(f"    [{idx}] {result.name}")
        print(f"        Locator: {loc_str}")
        print(f"        URL:     {url_str}")
        print(f"        File:    {result.file_path}")
        print()

    print("    [Q] Cancel")
    choice = input("  Which failure to repair? ").strip().lower()

    if choice == "q":
        print(yellow("  Cancelled."))
        return

    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(locator_failures):
            print(yellow("  Invalid selection."))
            return
    except ValueError:
        print(yellow("  Invalid input."))
        return

    result, detail = locator_failures[idx]

    # Determine the URL to open
    failure_url = detail.failure_url
    if not failure_url:
        failure_url = session.starting_url
    if not failure_url:
        print(red("  No URL available — cannot open browser."))
        return

    print()
    print(cyan(f"  Opening browser at {failure_url}"))
    print(yellow("  Click the element you want to use as the locator."))
    print(yellow("  Press Ctrl+C to cancel."))
    print()

    replacement = run_codegen_session(failure_url, timeout_seconds=120)
    if not replacement:
        print(yellow("  No locator captured — session timed out or was cancelled."))
        return

    # Apply the patch
    test_file = result.file_path
    patch = LocatorPatch(
        original_locator=detail.raw_locator or "",
        repaired_locator=replacement,
        line_number=detail.line_number or 1,
        test_file=test_file,
    )

    try:
        apply_patch_to_file(patch)
        print(green(f"  Patched `{replacement}` into {test_file}"))
        print(yellow("  Run 'Run Generated Tests' to verify the fix."))
    except Exception as exc:
        print(red(f"  Patch failed: {exc}"))


# ── Skeleton viewer ───────────────────────────────────────────────────────


def show_skeleton(session: Any) -> None:
    """Display the generated skeleton (pre-resolution)."""
    print_header("Generated Skeleton (pre-resolution)")
    if session.pipeline_skeleton:
        print(session.pipeline_skeleton[:4000])
        if len(session.pipeline_skeleton) > 4000:
            print("  ... (truncated)")
    else:
        print("  No skeleton available.")


# ── Scrape summary ────────────────────────────────────────────────────────


def show_scrape_summary(session: Any) -> None:
    """Display summary of scraped URLs and their elements."""
    print_header("Scrape Summary")
    if session.pipeline_urls:
        for url in session.pipeline_urls:
            elem_count = len(session.pipeline_scraped_pages.get(url, []))
            print(f"  - {url} ({elem_count} elements)")
    else:
        print("  No URLs were scraped.")


# ── AI-026: view failure diagnostics for loaded packages ───────────────────


def view_saved_package_diagnostics(package_dir: str | Path) -> None:
    """View failure diagnostics for a loaded saved package (AI-026 Step 6).

    Loads evidence JSON from the package's evidence/ directory and displays
    failure diagnostics along with report paths from the package manifest.
    This extends view_failure_diagnostics() to work with persisted packages
    rather than only the current session.
    """
    from src.evidence_loader import (
        get_failure_diagnostics,
        load_evidence_for_package,
    )
    from src.pipeline_artifact_manager import load_package_manifest

    print_header("Failure Diagnostics (Saved Package)")

    pkg_path = Path(package_dir)
    manifest = load_package_manifest(pkg_path, reconstruct=True)

    # Show report paths from manifest
    if manifest.reports:
        print(cyan("  Reports:"))
        for report in manifest.reports:
            fmt = report.get("format", "unknown")
            path = report.get("path", "")
            generated = report.get("generated_at", "")
            print(f"    [{fmt}] {path}")
            if generated:
                print(f"           Generated: {generated}")
    else:
        print(yellow("  No reports recorded for this package."))

    # Show evidence paths from manifest
    if manifest.evidence_paths:
        print(cyan("  Evidence paths:"))
        for ev_path in manifest.evidence_paths:
            print(f"    {ev_path}")
    else:
        print(yellow("  No evidence paths recorded in manifest."))

    print()

    # Load evidence JSON files
    evidence_map = load_evidence_for_package(str(pkg_path))
    if not evidence_map:
        print(yellow("  No evidence files found in package evidence/ directory."))
        return

    print(green(f"  Found {len(evidence_map)} evidence file(s)"))
    print()

    # Display diagnostics per test
    failed_count = 0
    for test_name, evidence in evidence_map.items():
        diag = get_failure_diagnostics(evidence)
        if not diag["failed_steps"]:
            continue

        failed_count += 1
        print(red(f"  Test: {test_name}"))
        print(f"    Status: {diag['test_status']}")
        print(f"    URL: {diag['page_url']}")
        if diag.get("page_title"):
            print(f"    Title: {diag['page_title']}")

        for step in diag["failed_steps"]:
            print(f"    Step {step.get('step_number', '?')}: {step.get('step_type', '?')}")
            print(f"      Label: {step.get('label', 'N/A')}")
            print(f"      Locator: {step.get('locator', 'N/A')}")
            print(f"      Error: {step.get('error_summary', 'N/A')[:200]}")
            if step.get("failure_note"):
                print(f"      Note: {step['failure_note']}")
            if step.get("suggested_locators"):
                print("      Suggested alternatives:")
                for loc in step["suggested_locators"][:5]:
                    print(f"        - {loc}")
            if step.get("available_elements"):
                roles: dict[str, int] = {}
                for elem in step["available_elements"]:
                    role = elem.get("role", "unknown")
                    roles[role] = roles.get(role, 0) + 1
                summary = ", ".join(f"[{r}]x{c}" for r, c in sorted(roles.items()))
                print(f"      Available elements: {summary}")

        print()

    if failed_count == 0:
        print(green("  No failures found in evidence — all tests passed!"))
    else:
        print(yellow(f"  Total failed tests with diagnostics: {failed_count}"))


# ── AI-026: re-run saved package ──────────────────────────────────────────


def run_saved_test_from_package(
    package_dir: str | Path,
    session: Any,
    rerun_failed: bool = False,
) -> None:
    """Run tests from a loaded saved package (AI-026).

    Sets up session state with the loaded package path, then runs the tests
    and displays structured results.
    """
    print_header(f"Running: {Path(package_dir).name}")

    # Set pipeline_saved_path to the package directory so downstream tools work
    session.pipeline_saved_path = package_dir

    try:
        print(cyan("  Running tests with pytest..."))
        exec_result = PipelineRunService().run_saved_test(
            str(package_dir),
            rerun_failed_only=rerun_failed,
            previous_run=session.pipeline_run_result if rerun_failed else None,
        )
        session.pipeline_run_result = exec_result.run_result
        session.pipeline_run_output = exec_result.display_output
        session.pipeline_run_command = " ".join(exec_result.command)
        session.pipeline_run_return_code = exec_result.return_code

        # Display structured results
        print()
        if session.pipeline_run_command:
            print(f"  Command: {session.pipeline_run_command}")
        print()

        if isinstance(session.pipeline_run_result, RunResult):
            render_run_results(session.pipeline_run_result, show_raw=False)

            # Run history summary (AI-011 Phase 4)
            render_run_history_summary()

        if session.pipeline_run_return_code == 0:
            print()
            print(green("  All tests passed!"))
        else:
            print()
            print(yellow(f"  Tests completed with return code {session.pipeline_run_return_code}"))

        # Update manifest's last_run_at
        from src.pipeline_artifact_manager import (
            load_package_manifest as _load_manifest,
        )
        from src.pipeline_artifact_manager import (
            save_package_manifest as _save_manifest,
        )
        from src.pipeline_artifact_manager import update_last_run_at

        manifest_path = Path(package_dir) / "package_manifest.json"
        if manifest_path.exists():
            manifest = _load_manifest(Path(package_dir))
            update_last_run_at(manifest)
            _save_manifest(Path(package_dir), manifest)

    except Exception as exc:
        session.pipeline_error = f"Failed to run saved package: {exc}"
        print(red(f"  ✗ {session.pipeline_error}"))


# ── Evidence HTML reports ────────────────────────────────────────────────


def generate_evidence_html(session: Any) -> None:
    """Generate static Gantt & heatmap HTML reports from evidence data."""
    from pathlib import Path

    from src.gantt_utils import build_gantt_chart, load_gantt_entries
    from src.heatmap_utils import build_confidence_heatmap, build_story_confidence

    print_header("Generate Evidence HTML Reports")

    if not session.pipeline_saved_path:
        print(yellow("  No generated test package found. Run the pipeline first."))
        print("  Press Enter to continue...")
        input()
        return

    pkg_dir = Path(str(session.pipeline_saved_path))
    evidence_dir = pkg_dir / "evidence"
    if not evidence_dir.exists():
        print(yellow("  No evidence directory found. Run generated tests first to produce evidence."))
        print("  Press Enter to continue...")
        input()
        return

    generated: list[str] = []

    # 1. Gantt chart
    try:
        entries = load_gantt_entries(evidence_dir)
        if entries:
            fig = build_gantt_chart(entries, grouping_mode="condition_type")
            gantt_path = str(evidence_dir / "gantt.html")
            fig.write_html(gantt_path, full_html=True, include_plotlyjs="cdn")
            generated.append(f"Gantt chart: {gantt_path}")
        else:
            print(yellow("  No Gantt entries — skipping Gantt chart."))
    except Exception as exc:
        print(yellow(f"  Gantt chart generation failed: {exc}"))

    # 2. Confidence heatmap
    try:
        stories = build_story_confidence(evidence_dir)
        if stories:
            fig = build_confidence_heatmap(stories)
            heatmap_path = str(evidence_dir / "heatmap.html")
            fig.write_html(heatmap_path, full_html=True, include_plotlyjs="cdn")
            generated.append(f"Confidence heatmap: {heatmap_path}")
        else:
            print(yellow("  No confidence data — skipping heatmap."))
    except Exception as exc:
        print(yellow(f"  Heatmap generation failed: {exc}"))

    if generated:
        print(green("  ✓ Generated evidence reports:"))
        for line in generated:
            print(f"    {line}")
    else:
        print(yellow("  No evidence reports could be generated."))

    print("  Press Enter to continue...")
    input()


# ── Evidence bundle ─────────────────────────────────────────────────────


def bundle_evidence_zip(session: Any) -> None:
    """Create a zip archive of all evidence files for the current session."""
    from pathlib import Path

    from src.cli.evidence_generator import EvidenceGenerator

    print_header("Bundle Evidence (Zip)")

    if not session.pipeline_saved_path:
        print(yellow("  No generated test package found. Run the pipeline first."))
        print("  Press Enter to continue...")
        input()
        return

    pkg_dir = Path(session.pipeline_saved_path)
    evidence_dir = pkg_dir / "evidence"
    if not evidence_dir.exists():
        print(yellow("  No evidence directory found. Run generated tests first to produce evidence."))
        print("  Press Enter to continue...")
        input()
        return

    output_path = str(pkg_dir / f"{pkg_dir.name}_evidence.zip")

    try:
        gen = EvidenceGenerator()
        zip_path = gen.create_evidence_zip(output_path)
        print(green(f"  ✓ Evidence bundle created: {zip_path}"))
    except Exception as exc:
        print(red(f"  Failed to create evidence zip: {exc}"))

    print("  Press Enter to continue...")
    input()


# ── AI-026: load existing packages ────────────────────────────────────────


def load_existing_packages(session: Any) -> None:
    """Discover and load an existing generated test package (AI-026)."""

    print_header("Load Existing Generated Tests")

    packages_dir = Path("generated_tests")
    if not packages_dir.exists():
        print(yellow("  No generated_tests/ directory found."))
        return

    packages = find_existing_packages(packages_dir)  # type: ignore[misc]
    if not packages:
        print(yellow("  No existing packages found in generated_tests/."))
        return

    print(f"\n  {'#':<4} {'Package':<45} {'Created':<12} {'Tests':<6} {'Runs':<6}")
    print("  " + "-" * 80)
    for i, pkg in enumerate(packages):
        test_count = len(pkg.generated_test_files)
        run_count = pkg.run_results_count
        created_str = pkg.created_at[:16] if pkg.created_at else "unknown"
        print(f"  {i + 1:<4} {pkg.package_name:<45} {created_str:<12} {test_count:<6} {run_count:<6}")
    print()

    # Prompt user to select
    try:
        choice_input = input(f"  Select package (1-{len(packages)}), or Enter to cancel: ").strip()
    except EOFError, KeyboardInterrupt:
        print()
        return

    if not choice_input:
        print(yellow("  Cancelled."))
        return

    try:
        choice_index = int(choice_input) - 1
        if choice_index < 0 or choice_index >= len(packages):
            print(yellow("  Invalid selection."))
            return
    except ValueError:
        print(yellow("  Invalid input."))
        return

    selected = packages[choice_index]
    package_dir = packages_dir / selected.package_name

    # Load run history
    run_results = []
    try:
        run_results = load_all_run_results(package_dir)
    except Exception:
        pass  # No run results yet, which is fine

    # Populate session
    session.loaded_package_manifest = selected
    session.loaded_package_path = str(package_dir)
    session.loaded_package_run_results = run_results
    session.pipeline_saved_path = str(package_dir)

    test_count = len(selected.generated_test_files)
    run_count = len(run_results)
    print(green(f"\n  ✓ Loaded: {selected.package_name} ({test_count} tests, {run_count} runs)"))
    if selected.source_story:
        print(f"  Story : {selected.source_story[:80]}{'...' if len(selected.source_story) > 80 else ''}")
    if selected.starting_url:
        print(f"  URL   : {selected.starting_url}")
    print()
