"""
AI Playwright Test Generator - Interactive CLI Entry Point

An interactive, menu-driven CLI that guides users through the full
pipeline: requirements input, LLM config, URL setup, test generation,
execution, and report viewing.  Mirrors the Streamlit app workflow.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# Load .env BEFORE any other imports so env vars are available
try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — env must be set externally

from src.evidence_loader import (
    get_failure_diagnostics,
    load_evidence_for_package,
)
from src.llm_client import LLMClient
from src.orchestrator import TestOrchestrator
from src.pipeline_report_service import PipelineReportService
from src.pipeline_run_service import PipelineRunService
from src.pipeline_writer import PipelineArtifactWriter
from src.pytest_output_parser import RunResult
from src.spec_analyzer import SpecAnalyzer, TestCondition
from src.test_generator import TestGenerator
from src.test_plan import TestPlan, build_story_ref
from src.user_story_parser import FeatureParser

# ── Colour helpers (ANSI, falls back gracefully) ──────────────────────────


def _c(text: str, code: str) -> str:
    """Wrap *text* in an ANSI colour code when stdout is a terminal."""
    try:
        import os

        if os.isatty(1):
            return f"\033[{code}m{text}\033[0m"
    except Exception:
        pass
    return text


def cyan(text: str) -> str:
    return _c(text, "36")


def green(text: str) -> str:
    return _c(text, "32")


def red(text: str) -> str:
    return _c(text, "31")


def yellow(text: str) -> str:
    return _c(text, "33")


def bold(text: str) -> str:
    return _c(text, "1")


# ── Session state ─────────────────────────────────────────────────────────


def _env_or_default(key: str, default: str) -> str:
    """Return env var value or *default* when empty/missing."""
    return os.environ.get(key, "").strip() or default


def _session_defaults() -> dict[str, str]:
    """Compute Session defaults from .env (already loaded above) or hardcoded fallbacks."""
    provider = _env_or_default("LLM_PROVIDER", "ollama")

    if provider == "lm-studio":
        return {
            "provider": "lm-studio",
            "provider_base_url": _env_or_default("LM_STUDIO_BASE_URL", "http://localhost:1234"),
            "model_name": _env_or_default("LM_STUDIO_MODEL", "lmstudio-community/Qwen2.5-7B-Instruct-GGUF"),
        }
    # Default (ollama or openai) — fall back to ollama settings
    return {
        "provider": "ollama",
        "provider_base_url": _env_or_default("OLLAMA_BASE_URL", "http://localhost:11434"),
        "model_name": _env_or_default("OLLAMA_MODEL", "qwen3.5:35b"),
    }


class Session:
    """Holds mutable state across interactive prompts."""

    def __init__(self) -> None:
        defaults = _session_defaults()

        self.pipeline_results: str | None = None
        self.pipeline_skeleton: str = ""
        self.pipeline_saved_path: str = ""
        self.pipeline_manifest_path: str = ""
        self.pipeline_error: str = ""
        self.pipeline_unresolved: list[str] = []
        self.pipeline_scraped_pages: dict[str, list[dict]] = {}
        self.pipeline_urls: list[str] = []
        self.pipeline_criteria: str = ""
        self.pipeline_conditions: list[TestCondition] = []
        self.pipeline_run_result: RunResult | None = None
        self.pipeline_run_output: str = ""
        self.pipeline_run_command: str = ""
        self.pipeline_run_return_code: int | None = None
        self.pipeline_local_report: str = ""
        self.pipeline_jira_report: str = ""
        self.pipeline_html_report: str = ""
        self.pipeline_local_report_path: str = ""
        self.pipeline_jira_report_path: str = ""
        self.pipeline_html_report_path: str = ""
        self.test_plan: TestPlan | None = None
        self.plan_confirmed: bool = False
        self.provider: str = defaults["provider"]
        self.provider_base_url: str = defaults["provider_base_url"]
        self.model_name: str = defaults["model_name"]
        self.starting_url: str = ""
        self.additional_urls: str = ""
        self.consent_mode: str = "auto-dismiss"
        self.raw_requirements: str = ""


# ── UI helpers ─────────────────────────────────────────────────────────────


def print_header(title: str) -> None:
    width = 60
    print()
    print("=" * width)
    print(bold(f"  {title}"))
    print("=" * width)
    print()


def print_menu(options: list[str], prompt: str = "Choose an option") -> int:
    """Print a numbered menu and return the selected index (0-based)."""
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    while True:
        try:
            choice = input(f"\n{prompt} [1-{len(options)}]: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return idx
        except (ValueError, KeyboardInterrupt):
            pass
        print(yellow("  Invalid choice. Please try again."))


def read_non_empty(prompt: str) -> str:
    """Read a non-empty line from the user."""
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print(yellow("  Input cannot be empty. Please try again."))


def read_optional(prompt: str, default: str = "") -> str:
    """Read a line, returning *default* on empty input."""
    value = input(prompt).strip()
    return value if value else default


# ── LLM configuration ─────────────────────────────────────────────────────


def _get_available_models(provider_name: str, provider_url: str) -> list[str]:
    """Try to list available models for the given provider, return empty list on failure."""
    try:
        import httpx

        if provider_name == "ollama":
            response = httpx.get(f"{provider_url}/api/tags", timeout=5.0)
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]
        elif provider_name == "lm-studio":
            response = httpx.get(f"{provider_url}/v1/models", timeout=5.0)
            response.raise_for_status()
            return [m["id"] for m in response.json().get("data", [])]
        elif provider_name == "openai":
            # For OpenAI, return common models since we can't list without API key
            return ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]
    except Exception:
        pass
    return []


def configure_llm(session: Session) -> None:
    """Let the user pick LLM provider and model."""
    print_header("LLM Configuration")

    providers = [
        ("Ollama (local)", "ollama", "http://localhost:11434"),
        ("LM Studio (local)", "lm-studio", "http://localhost:1234"),
        ("OpenAI (cloud)", "openai", "https://api.openai.com"),
    ]

    idx = print_menu([p[0] for p in providers], "Select LLM provider")
    display_name, provider_key, default_url = providers[idx]

    base_url = read_optional(f"  Base URL (default: {default_url}):", default_url)

    # Try to auto-detect models
    models = _get_available_models(provider_key, base_url)
    if models:
        print(f"\n  Available models ({len(models)}):")
        for i, model in enumerate(models[:15], 1):
            print(f"    {i}. {model}")
        if len(models) > 15:
            print(f"    ... and {len(models) - 15} more")
        model_choice = read_optional(
            f"\n  Select model [1-{len(models)}] (default: 1):",
            "1",
        )
        if model_choice.strip().isdigit() and 0 < int(model_choice) <= len(models):
            selected_model = models[int(model_choice) - 1]
        else:
            selected_model = models[0]
    else:
        print(f"\n  Could not auto-detect models for {provider_key}.")
        if provider_key == "ollama":
            fallback_model = _env_or_default("OLLAMA_MODEL", "qwen3.5:35b")
        elif provider_key == "lm-studio":
            fallback_model = _env_or_default("LM_STUDIO_MODEL", "lmstudio-community/Qwen2.5-7B-Instruct-GGUF")
        else:
            fallback_model = "gpt-4o"
        selected_model = read_optional(f"  Model name (default: {fallback_model}):", fallback_model)

    session.provider = provider_key
    session.provider_base_url = base_url
    session.model_name = selected_model

    print(green(f"  ✓ Provider: {provider_key} | URL: {base_url} | Model: {selected_model}"))


def collect_user_story(session: Session) -> None:
    """Let user paste or upload a user story."""
    print_header("User Story Input")

    mode = print_menu(["Paste Text", "Upload File", "Load baseline (automationexercise.com)"], "Input method")
    if mode == 2:
        session.starting_url = "https://automationexercise.com/"
        session.additional_urls = ""
        session.raw_requirements = """## User Story
As a customer I want to browse products, add them to my cart, and proceed to checkout

## Acceptance Criteria
1. [navigate] From the home page, click on a product category link (e.g. a link that says "Dress")
2. [navigate] On the category page, click the "Add to cart" button next to a product
3. [assert] A confirmation popup appears with text "Product added to cart!" and a "Continue Shopping" button
4. [click] Click the "Continue Shopping" button to close the confirmation popup
5. [navigate] Click the "Cart" link or cart icon in the page header
6. [assert] The cart page displays a table showing the products I added, with product names, prices, and quantities
7. [navigate] From the cart page, click the "Check Out" button
8. [assert] The checkout page loads, showing a form to enter my details and an order summary

(Total: 8 criteria)
"""
        print(green("  Baseline loaded."))
        return
    if mode == 0:
        print("\n  Paste your user story and acceptance criteria below.")
        print("  (End with an empty line or Ctrl+D / Ctrl+Z on Windows)")
        print("  ---")
        lines: list[str] = []
        try:
            while True:
                line = input()
                if not line and lines:
                    break
                lines.append(line)
        except EOFError:
            pass
        session.raw_requirements = "\n".join(lines)
    else:
        filepath = read_optional("  Enter file path:", "")
        if not filepath:
            print(yellow("  No file provided. Please paste text instead."))
            collect_user_story(session)
            return
        try:
            session.raw_requirements = Path(filepath).read_text(encoding="utf-8")
            print(green(f"  Read {len(session.raw_requirements)} characters from {filepath}"))
        except FileNotFoundError:
            print(red(f"  File not found: {filepath}"))
            collect_user_story(session)
            return
        except Exception as exc:
            print(red(f"  Error reading file: {exc}"))
            collect_user_story(session)
            return


def parse_requirements(raw: str) -> tuple[str, str]:
    """Parse raw text into user story and acceptance criteria."""
    parser = FeatureParser()
    result = parser.parse(raw)
    if result.success and result.specification is not None:
        spec = result.specification
        req_model = parser.build_requirement_model(spec)
        return spec.user_story.strip(), req_model.to_numbered_text().strip()
    cleaned = raw.strip()
    return cleaned, cleaned


# ── URLs ───────────────────────────────────────────────────────────────────


def collect_urls(session: Session) -> None:
    """Let user enter target URLs."""
    print_header("Target URLs")

    baseline = print_menu(
        ["Enter manually", "Load baseline (automationexercise.com)"],
        "URL source",
    )
    if baseline == 1:
        session.starting_url = "https://automationexercise.com/"
        session.additional_urls = ""
        session.raw_requirements = """## User Story
As a customer I want to browse products, add them to my cart, and proceed to checkout

## Acceptance Criteria
1. [navigate] From the home page, click on a product category link (e.g. a link that says "Dress")
2. [navigate] On the category page, click the "Add to cart" button next to a product
3. [assert] A confirmation popup appears with text "Product added to cart!" and a "Continue Shopping" button
4. [click] Click the "Continue Shopping" button to close the confirmation popup
5. [navigate] Click the "Cart" link or cart icon in the page header
6. [assert] The cart page displays a table showing the products I added, with product names, prices, and quantities
7. [navigate] From the cart page, click the "Check Out" button
8. [assert] The checkout page loads, showing a form to enter my details and an order summary

(Total: 8 criteria)
"""
        print(green("  Baseline loaded."))
    else:
        session.starting_url = read_optional("  Starting URL (e.g. https://your-site.example/):")
        print("  Additional URLs (one per line, empty line to finish):")
        urls: list[str] = []
        try:
            while True:
                line = input()
                if not line and urls:
                    break
                if line.strip():
                    urls.append(line.strip())
        except EOFError:
            pass
        session.additional_urls = "\n".join(urls)


def parse_target_urls(base_url: str, urls_input: str) -> list[str]:
    urls = [u.strip() for u in urls_input.splitlines() if u.strip()]
    if base_url.strip() and base_url.strip() not in urls:
        urls.insert(0, base_url.strip())
    return urls


# ── Consent mode ──────────────────────────────────────────────────────────


def collect_consent_mode(session: Session) -> None:
    idx = print_menu(
        ["auto-dismiss", "leave-as-is", "test-consent-flow"],
        "Consent handling",
    )
    session.consent_mode = ["auto-dismiss", "leave-as-is", "test-consent-flow"][idx]


# ── Living test plan ──────────────────────────────────────────────────────


async def build_test_plan(session: Session) -> None:
    """Analyze requirements and build a living test plan for review."""
    print_header("Living Test Plan")

    user_story, criteria = parse_requirements(session.raw_requirements)
    if not user_story or not criteria:
        print(yellow("  Could not parse user story or criteria. Proceeding without plan."))
        return

    client = LLMClient(
        provider=session.provider,
        model=session.model_name,
        base_url=session.provider_base_url,
    )
    analyzer = SpecAnalyzer(llm_client=client)
    spec_text = f"User Story:\n{user_story}\n\nAcceptance Criteria:\n{criteria}"

    try:
        conditions = analyzer.analyze(spec_text)
        session.test_plan = TestPlan.from_conditions(
            story_ref=build_story_ref(user_story),
            sprint="Backlog",
            conditions=conditions,
        )
        session.pipeline_conditions = conditions
        print(green(f"  Plan built: {len(conditions)} condition(s) derived."))
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
        # When the user explicitly signs off, trust them — generation is unlocked.
        session.plan_confirmed = True
        print(green("  Plan signed off. Generation unlocked."))
    else:
        print(yellow("  Plan not signed off. Generation will be locked."))


# ── Sign-off helper ───────────────────────────────────────────────────────


async def _prompt_sign_off(session: Session) -> None:
    """Prompt the user to sign off the test plan (used when pipeline is run without sign-off)."""
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
        # When the user explicitly signs off, trust them — generation is unlocked.
        session.plan_confirmed = True
        print(green("  Plan signed off. Generation unlocked."))
    else:
        print(yellow("  Sign-off cancelled."))


# ── Pipeline execution ────────────────────────────────────────────────────


async def run_pipeline(session: Session) -> None:
    """Execute the full intelligent pipeline."""
    print_header("Running Intelligent Pipeline")

    user_story, criteria = parse_requirements(session.raw_requirements)
    target_urls = parse_target_urls(session.starting_url, session.additional_urls)

    if not user_story.strip():
        session.pipeline_error = "Please provide a user story."
        print(red(f"  ✗ {session.pipeline_error}"))
        return
    if not criteria.strip():
        session.pipeline_error = "Please provide acceptance criteria."
        print(red(f"  ✗ {session.pipeline_error}"))
        return
    if not session.plan_confirmed:
        # If a plan exists but wasn't signed off, auto-prompt sign-off
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

    # Indicate that the pipeline is running (Llm calls take time)
    print(cyan("  Running pipeline — this may take a few minutes…"))

    client = LLMClient(
        provider=session.provider,
        model=session.model_name,
        base_url=session.provider_base_url,
    )
    generator = TestGenerator(client=client, model_name=session.model_name)
    orchestrator = TestOrchestrator(generator)

    conditions = list(session.pipeline_conditions or [])
    if not conditions and session.test_plan:
        conditions = session.test_plan.conditions

    conditions_text = (
        "\n".join(f"{i}. [{c.id}] {c.text} -> Expected: {c.expected}" for i, c in enumerate(conditions, 1))
        if conditions
        else criteria
    )

    final_code: str | None = None
    try:
        print(cyan("  Phase 1: Generating placeholder skeleton"))
        final_code = await orchestrator.run_pipeline(
            user_story=user_story,
            conditions=conditions_text,
            target_urls=target_urls,
            consent_mode=session.consent_mode,
            reviewed_conditions=conditions,
        )
    except Exception as exc:
        session.pipeline_error = str(exc)

    # Check for errors
    if session.pipeline_error:
        print(red(f"  ✗ Pipeline failed: {session.pipeline_error}"))
        return

    last_result = orchestrator.last_result
    if last_result is None:
        session.pipeline_error = "Pipeline returned no result."
        print(red(f"  ✗ {session.pipeline_error}"))
        return

    session.pipeline_results = final_code
    session.pipeline_skeleton = last_result.skeleton_code
    session.pipeline_urls = last_result.pages_to_scrape
    session.pipeline_scraped_pages = last_result.scraped_pages
    session.pipeline_unresolved = last_result.unresolved_placeholders
    session.pipeline_criteria = conditions_text

    # Save artifacts
    primary_url = target_urls[0] if target_urls else ""
    artifact_writer = PipelineArtifactWriter()
    artifact_set = artifact_writer.write_run_artifacts(
        run_result=last_result,
        story_text=user_story,
        base_url=primary_url,
    )
    session.pipeline_saved_path = artifact_set.test_file_path
    session.pipeline_manifest_path = artifact_set.manifest_path

    print(green(f"  ✓ Tests saved to: {session.pipeline_saved_path}"))
    if session.pipeline_unresolved:
        print(yellow(f"  ⚠ {len(session.pipeline_unresolved)} unresolved placeholder(s) — converted to skips."))
    else:
        print(green("  ✓ All placeholders resolved."))


# ── Run generated tests ───────────────────────────────────────────────────


def run_generated_tests(session: Session, rerun_failed: bool = False) -> None:
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


def display_run_results(session: Session) -> None:
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


def generate_reports(session: Session) -> None:
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


def view_reports(session: Session) -> None:
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
        # Open in system default viewer
        _open_file(report_path)
        # Also print first few lines for quick reference
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
    import os
    import subprocess

    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=True)
        else:
            subprocess.run(["xdg-open", path], check=True)
    except Exception:
        pass


# ── Failure diagnostics viewer ────────────────────────────────────────────


def view_failure_diagnostics(session: Session) -> None:
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


def show_scrape_summary(session: Session) -> None:
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


def show_skeleton(session: Session) -> None:
    print_header("Generated Skeleton (pre-resolution)")
    if session.pipeline_skeleton:
        print(session.pipeline_skeleton[:4000])
        if len(session.pipeline_skeleton) > 4000:
            print("  ... (truncated)")
    else:
        print("  No skeleton available.")


# ── Main menu ─────────────────────────────────────────────────────────────


async def interactive_session() -> None:
    """Run the full interactive CLI session."""
    session = Session()

    while True:
        print_header("AI Playwright Test Generator")

        # Build dynamic menu based on session state (no embedded numbers —
        # print_menu() adds them automatically)
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

        # Route to handler by index (menu items have no embedded numbers)
        if idx == 0 and (menu_items[0] == "Configure LLM" or menu_items[0] == "Re-configure LLM"):
            configure_llm(session)
        elif menu_items[idx] == "Enter User Story":
            collect_user_story(session)
        elif menu_items[idx] in ("Enter Target URLs", "Re-enter Target URLs"):
            collect_urls(session)
        elif menu_items[idx] == "Consent Mode":
            collect_consent_mode(session)
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
    import argparse

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
