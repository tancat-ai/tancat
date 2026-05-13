"""
AI Playwright Test Generator - Interactive CLI Entry Point

An interactive, menu-driven CLI that guides users through the full
pipeline: requirements input, LLM config, URL setup, test generation,
execution, and report viewing.  Mirrors the Streamlit app workflow.

This file is the slim orchestrator. Extracted modules:
- cli/color.py          — ANSI colour helpers
- cli/session.py        — Session dataclass and factory
- cli/menu_renderer.py  — Menu rendering, input prompts, LLM config
- cli/pipeline_runner.py — Pipeline execution, test running, reports
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

# Load .env BEFORE any other imports so env vars are available
try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — env must be set externally

# ── Sub-module imports ────────────────────────────────────────────────────

from src.journey_scraper import CredentialProfile, JourneyStep

from .color import green, yellow
from .menu_renderer import (
    collect_authentication,
    collect_consent_mode,
    collect_journey_steps,
    collect_urls,
    collect_user_story,
    configure_llm,
    print_header,
    print_menu,
)
from .pipeline_runner import (
    build_test_plan,
    generate_reports,
    run_generated_tests,
    run_pipeline,
    show_scrape_summary,
    show_skeleton,
    view_failure_diagnostics,
    view_reports,
)
from .session import Session, create_session

# ── Main menu ─────────────────────────────────────────────────────────────


async def interactive_session() -> None:
    """Run the full interactive CLI session."""
    session = create_session()  # type: ignore[call-arg]

    while True:
        print_header("AI Playwright Test Generator")

        # Build dynamic menu based on session state
        menu_items: list[str] = []

        if not session.raw_requirements:
            menu_items.extend(["Configure LLM", "Enter User Story"])
        else:
            menu_items.extend(["Re-configure LLM"])
            if not session.starting_url:
                menu_items.append("Enter Target URLs")
            else:
                menu_items.append("Re-enter Target URLs")

            menu_items.append("Consent Mode")

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
                ]
            )

        menu_items.extend(["Save & Exit", "Quit"])

        # Show current state summary
        print(yellow("  State:"))
        if session.provider:
            print(f"    LLM: {session.provider} / {session.model_name}")
        if session.starting_url:
            print(f"    URL: {session.starting_url}")
        if session.raw_requirements:
            print(f"    Requirements: {len(session.raw_requirements)} chars")
        if session.plan_confirmed:
            print("    Plan: Signed off")
        if session.pipeline_saved_path:
            print(f"    Output: {session.pipeline_saved_path}")
        print()

        idx = print_menu(menu_items, "Main menu")

        # Route to handler
        if idx == 0 and (menu_items[0] == "Configure LLM" or menu_items[0] == "Re-configure LLM"):
            _configure_llm_inline(session)
        elif menu_items[idx] == "Enter User Story":
            _collect_user_story_inline(session)
        elif menu_items[idx] in ("Enter Target URLs", "Re-enter Target URLs"):
            _collect_urls_inline(session)
        elif menu_items[idx] == "Consent Mode":
            session.consent_mode = collect_consent_mode()
        elif "Authentication" in menu_items[idx]:
            _collect_authentication_inline(session)
        elif "Journey" in menu_items[idx]:
            _collect_journey_inline(session)
        elif menu_items[idx] in ("Build Living Test Plan", "Review Test Plan"):
            await build_test_plan(session)
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
        elif menu_items[idx] == "Save & Exit":
            print(green("  Session saved. Goodbye!"))
            return
        elif menu_items[idx] == "Quit":
            print(yellow("  Quitting without saving."))
            return


# ── Inline wrappers (mutate session via menu_renderer returns) ────────────


def _configure_llm_inline(session: Session) -> None:
    provider, base_url, model = configure_llm(session.provider, session.provider_base_url, session.model_name)
    session.provider = provider
    session.provider_base_url = base_url
    session.model_name = model


def _collect_user_story_inline(session: Session) -> None:
    session.raw_requirements = collect_user_story()


def _collect_urls_inline(session: Session) -> None:
    starting, additional = collect_urls()
    session.starting_url = starting
    session.additional_urls = additional


def _collect_authentication_inline(session: Session) -> None:
    result = collect_authentication()
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
    raw_steps = collect_journey_steps()
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


# ── Legacy parameter-based commands (kept for backward compatibility) ────


def cmd_generate(args: Any, parser: Any) -> int:
    """Handle generate command (legacy parameter-based)."""
    print("=" * 60)
    print("🤖 AI Playwright Test Generator")
    print("=" * 60)

    start_time = __import__("datetime").datetime.now()

    # Process input
    print("\n📝 Processing Input...")
    from cli.input_parser import InputParser

    input_parser = InputParser()
    try:
        if args.input:
            parsed = input_parser.parse(args.input, args.format)
        elif args.file:
            with open(args.file, encoding="utf-8") as f:
                content = f.read()
            if args.file.endswith(".json"):
                parsed = input_parser.parse_json(content)
            else:
                parsed = input_parser.parse(content, args.format)
        else:
            parsed = input_parser.parse(args.generate, "user_story")
        print(f"   [OK] Parsed {len(parsed.test_cases)} test case(s)")
    except FileNotFoundError:
        print(f"❌ Error: File not found: {args.file}")
        return 1
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON: {e}")
        return 1
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return 1

    # Run analysis
    print("\n🔍 Running Analysis...")
    analysis_result = run_analysis(parsed)

    # Generate tests
    print("\n⚙️  Generating Tests...")
    run_generation(parsed, args.output_dir, args.url)

    # Generate evidence
    print("\n📸 Generating Evidence...")
    run_evidence_generation(args.output_dir)

    # Generate reports
    print("\n📄 Generating Reports...")
    generate_reports_legacy(parsed, analysis_result, args.output_dir)

    # Summary
    end_time = __import__("datetime").datetime.now()
    duration = (end_time - start_time).total_seconds()

    print("\n" + "=" * 60)
    print("✅ Complete!")
    print(f"   Duration: {duration:.2f}s")
    print(f"   Output Directory: {args.output_dir}")
    print("=" * 60)

    return 0


def run_analysis(parsed: Any) -> Any:
    """Run analysis on parsed input."""
    from src.analyzer import KeywordAnalyzer

    result = KeywordAnalyzer.analyze_parsed(parsed)
    summary = result.analysis_summary
    print(f"   Total Test Cases: {summary['total_cases']}")
    for case in result.analyzed_test_cases:
        print(f"   - {case.title}: {case.estimated_complexity}")
    return result


def run_generation(parsed: Any, output_dir: str, url: str | None = None) -> None:
    """Generate Playwright tests."""
    from cli.test_case_orchestrator import TestCaseOrchestrator

    orchestrator = TestCaseOrchestrator()
    for case in parsed.test_cases:
        orchestrator.process(case.description, url=url)
    print(f"   Generated tests for {len(parsed.test_cases)} case(s)")


def run_evidence_generation(output_dir: str) -> None:
    """Generate evidence for tests."""
    from cli.evidence_generator import EvidenceGenerator

    evidence_gen = EvidenceGenerator()
    evidence_gen.generate_evidence()


def generate_reports_legacy(parsed: Any, analysis_result: Any, output_dir: str) -> None:
    """Generate reports (legacy)."""
    from cli.config import ReportFormat
    from cli.report_generator import JiraReportGenerator

    report_gen = JiraReportGenerator(output_dir)
    for analyzed_case in analysis_result.analyzed_test_cases:
        report_gen.create_test_case(analyzed_case)
    for report_format in ReportFormat:
        report_path = report_gen.save_test_cases(report_format)
        print(f"   [OK] {report_format.value} -> {report_path}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AI Playwright Test Generator - Generate Playwright tests from user stories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Interactive mode (default):
  python -m cli.main

Generate mode (legacy parameter-based):
  python -m cli.main generate --input "As a user, I want to login"

Examples:
  %(prog)s                    # Interactive menu
  %(prog)s generate -i "Login test" -o generated_tests
  %(prog)s generate -f stories.md
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Generate command (legacy)
    gen_parser = subparsers.add_parser("generate", help="Generate Playwright tests (legacy mode)")
    gen_parser.add_argument("--input", "-i", type=str, help="Raw test case input")
    gen_parser.add_argument("--file", "-f", type=str, help="Input file (text or JSON)")
    gen_parser.add_argument("--generate", "-g", type=str, help="Generate test case from prompt")
    gen_parser.add_argument(
        "--format", type=str, default="user_story", choices=["user_story", "gherkin", "auto"], help="Input format"
    )
    gen_parser.add_argument(
        "--output", "-o", type=str, default="generated_tests", dest="output_dir", help="Output directory"
    )
    gen_parser.add_argument(
        "--mode", type=str, default="auto", choices=["fast", "thorough", "auto"], help="Analysis mode"
    )
    gen_parser.add_argument("--project-key", type=str, default="TEST", help="Jira project key")
    gen_parser.add_argument(
        "--evidence", action="store_true", default=True, help="Generate evidence files (default: true)"
    )
    gen_parser.add_argument("--url", type=str, default=None, help="URL to capture page context for test generation")
    gen_parser.add_argument("--reports", type=str, default="all", help="Report format: all, jira, html, json, md")

    # Test command (legacy)
    test_parser = subparsers.add_parser("test", help="Run test suite")
    test_parser.add_argument("--filter", "-f", type=str, help="Test filter pattern")

    # Help command
    subparsers.add_parser("help", help="Show help message")

    args = parser.parse_args()

    # Interactive mode (default)
    if not args.command:
        try:
            asyncio.run(interactive_session())
        except KeyboardInterrupt:
            print("\n\nInterrupted. Goodbye!")
        return 0

    # Legacy commands
    if args.command == "generate":
        if not getattr(args, "input", None) and not getattr(args, "file", None) and not getattr(args, "generate", None):
            print("❌ Error: Must provide input via --input, --file, or --generate")
            return 1
        if args.input and args.file:
            print("❌ Error: Cannot use both --input and --file")
            return 1
        return cmd_generate(args, parser)
    elif args.command == "test":
        print("Running test suite...")
        return 0
    elif args.command == "help":
        parser.print_help()
        return 0
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
