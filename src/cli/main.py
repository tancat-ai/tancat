"""
AI Playwright Test Generator - Interactive CLI Entry Point

An interactive, menu-driven CLI that guides users through the full
pipeline: requirements input, LLM config, URL setup, test generation,
execution, and report viewing.  Mirrors the Streamlit app workflow.

This file is the slim orchestrator. Extracted modules:
- src/cli/color.py          — ANSI colour helpers
- src/cli/session.py        — Session dataclass and factory
- src/cli/menu_renderer.py  — Menu rendering, input prompts, LLM config
- src/cli/pipeline_runner.py — Pipeline execution, test running, reports
"""

from __future__ import annotations

import asyncio
import io
import sys

# Force UTF-8 encoding on Windows Git Bash (MINGW64)
if sys.stdout.encoding and sys.stdout.encoding.upper() not in ("UTF-8", "UTF8", "CP65001"):
    try:
        sys.stdout = io.TextIOWrapper(open(sys.stdout.fileno(), "wb"), encoding="utf-8", write_through=True)
        sys.stderr = io.TextIOWrapper(open(sys.stderr.fileno(), "wb"), encoding="utf-8", write_through=True)
    except OSError, io.UnsupportedOperation:
        pass

from src.journey_scraper import CredentialProfile, JourneyStep
from src.llm_client import LLMClient
from src.provider_config import resolve_openai_api_key, sync_openai_api_key_to_env
from src.settings_store import save_setting, save_settings

from .color import green, yellow
from .menu_renderer import (
    _reset_menu_stack,
    collect_authentication,
    collect_consent_mode,
    collect_journey_steps,
    collect_urls,
    collect_user_story,
    configure_llm,
    list_saved_packages,
    pop_menu,
    print_header,
    print_menu,
    push_menu,
    read_optional,
    select_saved_package,
    show_package_metadata,
)
from .pipeline_runner import (
    build_test_plan,
    build_test_table_interactive,
    bundle_evidence_zip,
    export_clean_package,
    generate_bug_report,
    generate_evidence_html,
    generate_reports,
    repair_locator_cli,
    run_generated_tests,
    run_pipeline,
    self_heal_cli,
    show_scrape_summary,
    show_skeleton,
    view_failure_diagnostics,
    view_reports,
    view_saved_package_diagnostics,
)
from .retro_ui import render_state
from .session import Session, create_session

# Force UTF-8 encoding on Windows when running under Git Bash (MINGW64)
# where stdout may default to cp1252, causing UnicodeEncodeError for
# box-drawing characters (┌, ─, ┐ etc.) used in the retro UI.
# Ensure line buffering so menu output flushes when stdout is redirected.
stdout_stream = sys.stdout
if hasattr(stdout_stream, "reconfigure"):
    stdout_stream.reconfigure(encoding="utf-8", line_buffering=True)
else:
    if stdout_stream.encoding and stdout_stream.encoding.upper() not in ("UTF-8", "UTF8", "CP65001"):
        sys.stdout = open(
            stdout_stream.fileno(),
            mode="w",
            encoding="utf-8",
            buffering=1,
            closefd=False,
        )  # pyright: ignore[assignment]
    else:
        sys.stdout = open(
            stdout_stream.fileno(),
            mode="w",
            encoding=stdout_stream.encoding or "utf-8",
            buffering=1,
            closefd=False,
        )  # pyright: ignore[assignment]

try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — env must be set externally

# ── Main menu ─────────────────────────────────────────────────────────────


async def interactive_session() -> None:
    """Run the full interactive CLI session."""
    session = create_session()  # type: ignore[call-arg]
    _apply_session_llm_config(session)
    _reset_menu_stack()

    while True:
        print_header("TanCat")

        # Build dynamic menu based on session state
        menu_items: list[str] = []

        if not session.raw_requirements:
            menu_items.extend(["Configure LLM", "Check LLM", "Enter User Story"])
        else:
            menu_items.extend(["Re-configure LLM", "Check LLM"])
            if not session.starting_url:
                menu_items.append("Enter Target URLs")
            else:
                menu_items.append("Re-enter Target URLs")

            menu_items.append("Consent Mode")
            menu_items.append("POM Mode")
            menu_items.append("Jira Project Key")

            # Authentication / Journey (AI-009 Phase B)
            auth_label = "Configure Authentication"
            if session.credential_profile:
                auth_label = f"Re-configure Authentication ({session.credential_profile.label})"
            menu_items.append(auth_label)

            journey_label = "Configure Journey"
            if session.journey_steps:
                journey_label = f"Re-configure Journey ({len(session.journey_steps)} steps)"
            menu_items.append(journey_label)

            if not session.plan_confirmed:
                menu_items.append("Build Living Test Plan")
            else:
                menu_items.append("Review Test Plan")
                if session.test_table is None or not session.test_table_confirmed:
                    menu_items.append("Expand into Test Rows")
                else:
                    menu_items.append("Review Test Rows")

            menu_items.append("Run Intelligent Pipeline")

        if session.pipeline_results:
            menu_items.extend(
                [
                    "View Generated Code",
                    "View Skeleton",
                    "View Scrape Summary",
                    "Run Generated Tests",
                    "Re-run Failed Only",
                    "Generate Reports",
                    "View Reports",
                    "View Failure Diagnostics",
                    "Generate Bug Report",
                    "Repair Locator",
                    "Self-Heal Failed Tests",
                    "Export Clean Package",
                    "Bundle Evidence (Zip)",
                    "Generate Evidence HTML",
                ]
            )

        # AI-026: persisted-package commands (always available)
        if session.loaded_package_manifest:
            manifest = session.loaded_package_manifest
            test_count = len(manifest.generated_test_files)
            run_count = manifest.run_results_count or 0
            state_label = f"{test_count} tests, {run_count} runs"
            menu_items.extend(
                [
                    f"Loaded : {manifest.package_name} ({state_label})",
                    "Show Package Metadata",
                    "Re-run Saved Suite",
                    "View Saved Package Diagnostics",
                    "Clear Loaded Package",
                ]
            )
        else:
            menu_items.append("Load Existing Generated Tests")

        menu_items.extend(["Save & Exit", "Quit"])

        # Show current state summary
        state: list[str] = []
        if session.provider:
            state.append(f"  LLM : {session.provider} / {session.model_name}")
        if session.starting_url:
            state.append(f"  URL : {session.starting_url}")
        if session.raw_requirements:
            state.append(f"  Story : {len(session.raw_requirements)} chars")
            # Mode toggles (Consent Mode / POM Mode) — surfaced here so toggling
            # produces visible feedback on the redrawn screen.
            state.append(f"  Consent : {session.consent_mode}")
            state.append(f"  POM Mode : {'ON' if session.pom_mode else 'OFF'}")
            state.append(f"  Jira : {session.jira_project_key or 'TEST'}")
        if session.plan_confirmed:
            state.append("  Plan : Signed off")
        if session.pipeline_saved_path:
            state.append(f"  Out   : {session.pipeline_saved_path}")
        render_state(state)
        print()

        # Build context-sensitive shortcuts (Q/Quit is auto-added by menu_renderer)
        main_shortcuts: list[tuple[str, str]] = []
        if session.raw_requirements and session.starting_url:
            main_shortcuts.append(("R", "Run Pipeline"))
        if session.pipeline_results:
            main_shortcuts.append(("V", "View Reports"))

        idx = print_menu(menu_items, "Main menu", shortcuts=main_shortcuts)

        # print_menu returns -1 when user presses Q (Quit shortcut)
        if idx < 0:
            print(yellow("  Quitting without saving."))
            return

        # Route to handler
        if idx == 0 and (menu_items[0] == "Configure LLM" or menu_items[0] == "Re-configure LLM"):
            _configure_llm_inline(session)
        elif menu_items[idx] == "Check LLM":
            _check_llm_inline(session)
        elif menu_items[idx] == "Enter User Story":
            _collect_user_story_inline(session)
        elif menu_items[idx] in ("Enter Target URLs", "Re-enter Target URLs"):
            _collect_urls_inline(session)
        elif menu_items[idx] == "Consent Mode":
            _collect_consent_inline(session)
        elif menu_items[idx] == "POM Mode":
            session.pom_mode = not session.pom_mode
            save_setting("pom_mode", session.pom_mode)  # B-036 Phase 4: persist
            if session.pom_mode:
                print(green("  POM Mode: ON — generated tests will include Page Object Model artifacts"))
            else:
                print(yellow("  POM Mode: OFF — generated tests will use inline locators only"))
            print("  Press Enter to continue...")
            input()
        elif menu_items[idx] == "Jira Project Key":
            new_key = (
                read_optional(
                    f"  Jira project key (current: {session.jira_project_key or 'TEST'})",
                    default=session.jira_project_key or "TEST",
                )
                .strip()
                .upper()
                or "TEST"
            )
            session.jira_project_key = new_key
            save_setting("jira_project_key", new_key)  # B-036 Phase 4: persist
            print(green(f"  ✓ Jira project key set to '{new_key}'"))
            print("  Press Enter to continue...")
            input()
        elif "Authentication" in menu_items[idx]:
            _collect_authentication_inline(session)
        elif "Journey" in menu_items[idx]:
            _collect_journey_inline(session)
        elif menu_items[idx] in ("Build Living Test Plan", "Review Test Plan"):
            await build_test_plan(session)
        elif menu_items[idx] in ("Expand into Test Rows", "Review Test Rows"):
            build_test_table_interactive(session)
        elif menu_items[idx] == "Run Intelligent Pipeline":
            await run_pipeline(session)
        elif menu_items[idx] == "View Generated Code":
            print_header("Generated Code")
            print(session.pipeline_results or "")
        elif menu_items[idx] == "View Skeleton":
            show_skeleton(session)
        elif menu_items[idx] == "View Scrape Summary":
            show_scrape_summary(session)
        elif menu_items[idx] == "Run Generated Tests":
            run_generated_tests(session, rerun_failed=False)
        elif menu_items[idx] == "Re-run Failed Only":
            run_generated_tests(session, rerun_failed=True)
        elif menu_items[idx] == "Generate Reports":
            generate_reports(session)
        elif menu_items[idx] == "View Reports":
            view_reports(session)
        elif menu_items[idx] == "View Failure Diagnostics":
            view_failure_diagnostics(session)
        elif menu_items[idx] == "Generate Bug Report":
            generate_bug_report(session)
        elif menu_items[idx] == "Repair Locator":
            repair_locator_cli(session)
        elif menu_items[idx] == "Self-Heal Failed Tests":
            self_heal_cli(session)
        elif menu_items[idx] == "Export Clean Package":
            export_clean_package(session)
        elif menu_items[idx] == "Bundle Evidence (Zip)":
            bundle_evidence_zip(session)
        elif menu_items[idx] == "Generate Evidence HTML":
            generate_evidence_html(session)
        # AI-026: persisted-package commands
        elif menu_items[idx] == "Load Existing Generated Tests":
            _load_saved_packages_inline(session)
        elif menu_items[idx] == "Show Package Metadata":
            _show_package_metadata_inline(session)
        elif menu_items[idx] == "Re-run Saved Suite":
            _rerun_saved_suite(session)
        elif menu_items[idx] == "View Saved Package Diagnostics":
            _view_saved_package_diagnostics_inline(session)
        elif menu_items[idx] == "Clear Loaded Package":
            _clear_loaded_package(session)
        elif menu_items[idx] == "Save & Exit":
            print(green("  Session saved. Goodbye!"))
            return
        elif menu_items[idx] == "Quit":
            print(yellow("  Quitting without saving."))
            return


# ── Inline wrappers (mutate session via menu_renderer returns) ────────────


def _apply_session_llm_config(session: Session) -> None:
    """Propagate session LLM settings to LLMClient fallbacks and cloud auth."""
    api_key = resolve_openai_api_key(provider=session.provider)
    sync_openai_api_key_to_env(session.provider, api_key)
    LLMClient.set_session_provider(session.provider, session.provider_base_url, session.model_name)


def _configure_llm_inline(session: Session) -> None:
    push_menu("LLM Configuration")
    try:
        _configure_llm_inline_inner(session)
    finally:
        pop_menu()


def _check_llm_inline(session: Session) -> None:
    """Phase 6d — BYO-LLM health check (CLI). Runs the same probe as the UI.

    Uses the session's configured provider/base_url/model (what the user will
    actually generate with) and prints a ✓/✗ report + actionable errors.
    """
    if not session.provider:
        print(yellow("  No LLM provider configured yet — choose 'Configure LLM' first."))
        print("  Press Enter to continue...")
        input()
        return

    from src.llm_health import build_client, check_llm, render_report

    print("  Checking LLM endpoint…\n")
    client = build_client(
        session.provider, base_url=session.provider_base_url or None, model=session.model_name or None
    )
    result = check_llm(client, requested_model=session.model_name or None)
    print(render_report(result))
    print()
    if result.ok:
        print(green("  ✓ LLM is ready — proceed to enter a user story."))
    else:
        print(yellow("  Fix the issues above, then run 'Check LLM' again."))
    print("  Press Enter to continue...")
    input()


def _configure_llm_inline_inner(session: Session) -> None:
    provider, base_url, model = configure_llm(session.provider, session.provider_base_url, session.model_name)
    session.provider = provider
    session.provider_base_url = base_url
    session.model_name = model
    # B-036 Phase 4: persist LLM config so it survives CLI restarts.
    save_settings(
        {
            "provider": provider,
            "provider_base_url": base_url,
            "model_name": model,
        }
    )
    _apply_session_llm_config(session)


def _collect_user_story_inline(session: Session) -> None:
    session.raw_requirements = collect_user_story()


def _collect_urls_inline(session: Session) -> None:
    starting, additional = collect_urls()
    session.starting_url = starting
    session.additional_urls = additional


def _collect_consent_inline(session: Session) -> None:
    push_menu("Consent Mode")
    try:
        mode = collect_consent_mode()
        if isinstance(mode, str) and mode:
            session.consent_mode = mode
            save_setting("consent_mode", mode)  # B-036 Phase 4: persist
            print(green(f"  ✓ Consent mode set to '{mode}'"))
            print("  Press Enter to continue...")
            input()
        # Empty/negative result = backed out or quit — keep current mode.
    finally:
        pop_menu()


def _collect_authentication_inline(session: Session) -> None:
    push_menu("Authentication")
    try:
        _collect_authentication_inline_inner(session)
    finally:
        pop_menu()


def _collect_authentication_inline_inner(session: Session) -> None:
    result = collect_authentication()
    if isinstance(result, int):
        # Back / Main Menu / Quit — keep any previously configured profile.
        return
    if result is None:
        session.credential_profile = None
    else:
        session.credential_profile = CredentialProfile(
            label=result["label"],
            username=result["username"],
            password=result["password"],
        )
        print(green(f"  ✓ Authentication configured: '{result['label']}'"))


def _collect_journey_inline(session: Session) -> None:
    push_menu("Journey Builder")
    try:
        _collect_journey_inline_inner(session)
    finally:
        pop_menu()


def _collect_journey_inline_inner(session: Session) -> None:
    raw_steps = collect_journey_steps()
    if isinstance(raw_steps, int):
        # Back / Main Menu / Quit — keep the previously configured journey.
        return
    converted: list[JourneyStep] = []
    for s in raw_steps:
        converted.append(
            JourneyStep(
                action=s["action"],
                url=s.get("url"),
                selector=s.get("selector"),
                text=s.get("text"),
                description=s.get("description", ""),
                timeout_ms=int(s.get("timeout_ms", "30000")),
            )
        )
    session.journey_steps = converted
    if session.journey_steps:
        print(green(f"  ✓ Journey configured with {len(session.journey_steps)} step(s)."))


# ── AI-026: persisted-package inline handlers ────────────────────────────


def _load_saved_packages_inline(session: Session) -> None:
    """Load an existing saved package from disk."""
    from pathlib import Path

    from src.pipeline_artifact_manager import load_package_manifest
    from src.run_result_persistence import load_all_run_results

    push_menu("Saved Packages")
    try:
        packages = list_saved_packages()
        if not packages:
            print(yellow("  No saved test packages found in generated_tests/"))
            print("  Press Enter to continue...")
            input()
            return

        idx = select_saved_package(packages)
        if idx < 0:
            return

        package = packages[idx]
        package_dir = Path(package["path"])
        manifest = load_package_manifest(package_dir, reconstruct=True)
        session.loaded_package_manifest = manifest
        session.pipeline_saved_path = package_dir

        # Load run history
        run_results = load_all_run_results(package_dir)
        session.loaded_package_run_results = run_results

        print(green(f"  ✓ Loaded package: {manifest.package_name}"))
        if manifest.source_story:
            story = manifest.source_story[:80]
            print(f"  Story : {story}...") if len(manifest.source_story) > 80 else print(f"  Story : {story}")
        print(f"  Tests : {len(manifest.generated_test_files)}")
        print(f"  Runs  : {len(run_results) if run_results else 0}")
        print()
        print("  Press Enter to continue...")
        input()
    finally:
        pop_menu()


def _show_package_metadata_inline(session: Session) -> None:
    """Show metadata for the currently loaded package."""
    if not session.loaded_package_manifest:
        print(yellow("  No package loaded. Use 'Load Existing Generated Tests' first."))
        print("  Press Enter to continue...")
        input()
        return

    package = {"path": str(session.pipeline_saved_path or "")}
    package["name"] = session.loaded_package_manifest.package_name
    package["created_at"] = session.loaded_package_manifest.created_at or ""
    package["test_count"] = str(len(session.loaded_package_manifest.generated_test_files))
    if session.loaded_package_run_results:
        package["run_count"] = str(len(session.loaded_package_run_results))
    show_package_metadata(package)


def _rerun_saved_suite(session: Session) -> None:
    """Re-run tests from the loaded saved package."""
    from .pipeline_runner import run_saved_test_from_package

    if not session.loaded_package_manifest or not session.pipeline_saved_path:
        print(yellow("  No package loaded. Use 'Load Existing Generated Tests' first."))
        print("  Press Enter to continue...")
        input()
        return

    run_saved_test_from_package(session.pipeline_saved_path, session)


def _view_saved_package_diagnostics_inline(session: Session) -> None:
    """View failure diagnostics for the loaded saved package (AI-026 Step 6)."""
    if not session.loaded_package_manifest or not session.pipeline_saved_path:
        print(yellow("  No package loaded. Use 'Load Existing Generated Tests' first."))
        print("  Press Enter to continue...")
        input()
        return

    view_saved_package_diagnostics(session.pipeline_saved_path)
    print()
    print("  Press Enter to continue...")
    input()


def _clear_loaded_package(session: Session) -> None:
    """Clear the currently loaded package."""
    session.loaded_package_manifest = None
    session.loaded_package_run_results = None
    session.pipeline_saved_path = ""
    print(green("  ✓ Cleared loaded package."))
    print("  Press Enter to continue...")
    input()


def main() -> int:
    """Main entry point — runs the interactive CLI session."""
    try:
        asyncio.run(interactive_session())
    except KeyboardInterrupt:
        print("\n\nInterrupted. Goodbye!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
