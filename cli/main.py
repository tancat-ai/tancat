"""
AI Playwright Test Generator - CLI Entry Point

Main entry point for the AI Playwright Test Generator CLI tool.
Provides command-line interface for generating Playwright tests from user stories.
"""

import argparse
import json
import sys
from datetime import datetime

from cli.config import ReportFormat
from cli.input_parser import InputParser, ParsedInput
from src.analyzer import AnalysisResult, KeywordAnalyzer

# Default demo user story for quick testing
DEMO_USER_STORY = "As a customer, I want to browse products, add them to my cart, and checkout with a discount code."


def cmd_generate(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Handle generate command."""
    print("=" * 60)
    print("🤖 AI Playwright Test Generator")
    print("=" * 60)

    # Use demo story if --demo flag is set
    if getattr(args, "demo", False) and not args.input and not args.file and not args.generate:
        args.input = DEMO_USER_STORY

    start_time = datetime.now()

    # Process input
    print("\n📝 Processing Input...")
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
        print(f"   ✓ Parsed {len(parsed.test_cases)} test case(s)")
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
    generate_reports(parsed, analysis_result, args.output_dir)

    # Summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print("\n" + "=" * 60)
    print("✅ Complete!")
    print(f"   Duration: {duration:.2f}s")
    print(f"   Output Directory: {args.output_dir}")
    print("=" * 60)

    return 0


def cmd_test(args: argparse.Namespace) -> int:
    """Handle test command."""
    print("Running test suite...")
    return 0


def cmd_help(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Handle help command."""
    parser.print_help()
    return 0


def run_analysis(parsed: ParsedInput) -> AnalysisResult:
    """Run analysis on parsed input."""
    result = KeywordAnalyzer.analyze_parsed(parsed)

    summary = result.analysis_summary
    print(f"   Total Test Cases: {summary['total_cases']}")

    for case in result.analyzed_test_cases:
        print(f"   - {case.title}: {case.estimated_complexity}")

    return result


def run_generation(parsed: ParsedInput, output_dir: str, url: str | None = None) -> None:
    """Generate Playwright tests."""
    from cli.test_case_orchestrator import TestCaseOrchestrator

    orchestrator = TestCaseOrchestrator()
    # Generate content for all test cases
    for case in parsed.test_cases:
        orchestrator.process(case.description, url=url)

    print(f"   Generated tests for {len(parsed.test_cases)} case(s)")


def run_evidence_generation(output_dir: str) -> None:
    """Generate evidence for tests."""
    from cli.evidence_generator import EvidenceGenerator

    evidence_gen = EvidenceGenerator()
    evidence_gen.generate_evidence()


def generate_reports(parsed: ParsedInput, analysis_result: AnalysisResult, output_dir: str) -> None:
    """Generate reports."""
    from cli.report_generator import JiraReportGenerator

    report_gen = JiraReportGenerator(output_dir)

    for analyzed_case in analysis_result.analyzed_test_cases:
        report_gen.create_test_case(analyzed_case)

    for report_format in ReportFormat:
        report_path = report_gen.save_test_cases(report_format)
        print(f"   ✓ {report_format.value} → {report_path}")


def _get_available_models(provider_name: str, provider_url: str) -> list[str]:
    """Try to list available models for the given provider, return empty list on failure."""
    try:
        import httpx

        if provider_name == "ollama":
            client = httpx.Client(base_url="http://localhost:11434", timeout=5)
            response = client.get("/api/tags", timeout=5)
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]
        elif provider_name == "lm-studio":
            client = httpx.Client(base_url=f"{provider_url}/v1", timeout=5)
            response = client.get("/models", timeout=5)
            response.raise_for_status()
            return [m["id"] for m in response.json().get("data", [])]
        elif provider_name == "openai":
            # For OpenAI, return common models since we can't list without API key
            return ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]
        else:
            return []
    except Exception:
        return []


def _safe_input(prompt: str = "") -> str | None:
    """Read input with EOF handling for piped/non-interactive contexts."""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        return None


def cmd_interactive(parser: argparse.ArgumentParser) -> int:
    """Interactive CLI loop — presents a menu and prompts the user for input."""
    print()
    print("=" * 60)
    print("[CLI]  AI Playwright Test Generator — Interactive CLI")
    print("=" * 60)
    print()

    input_parser = InputParser()

    # --- Step 1: LLM Provider selection ---
    print("Available LLM providers:")
    print("  1) Ollama (local)")
    print("  2) LM Studio (local)")
    print("  3) OpenAI (cloud)")
    print()

    provider_choice = _safe_input("Select provider [1/2/3]: ")
    if provider_choice is None:
        print("\nGoodbye!")
        return 0

    provider_map = {
        "1": ("ollama", "http://localhost:11434"),
        "2": ("lm-studio", "http://localhost:1234"),
        "3": ("openai", "https://api.openai.com"),
    }
    provider_name, provider_url = provider_map.get(provider_choice.strip(), ("ollama", "http://localhost:11434"))

    # --- Step 2: Model selection ---
    print(f"\nConnecting to {provider_name} at {provider_url}...")
    models = _get_available_models(provider_name, provider_url)

    if models:
        print(f"\nAvailable models ({len(models)}):")
        for i, model in enumerate(models[:10], 1):  # Show first 10
            print(f"  {i}) {model}")
        if len(models) > 10:
            print(f"  ... and {len(models) - 10} more")
        model_choice = _safe_input(f"\nSelect model [1-{len(models)}] (default=1): ")
        if model_choice is None:
            print("\nGoodbye!")
            return 0
        model_choice = model_choice.strip()
        selected_model = (
            models[int(model_choice) - 1]
            if model_choice.isdigit() and 0 < int(model_choice) <= len(models)
            else models[0]
        )
    else:
        print(f"\n⚠  Could not auto-detect models for {provider_name}.")
        selected_model_input = _safe_input("Model name (e.g., qwen2.5:7b): ")
        selected_model = selected_model_input.strip() if selected_model_input else "qwen2.5:7b"

    # Set session provider so all LLMClient instances use this provider
    from src.llm_client import LLMClient

    LLMClient.set_session_provider(provider_name, provider_url)

    print(f"\nUsing provider: {provider_name} | model: {selected_model}")
    print()

    # --- Step 3: Input method selection ---
    while True:
        print("Select input method:")
        print("  1) Type user story directly")
        print("  2) Load from file (text or JSON)")
        print("  q) Quit")
        print()

        choice = _safe_input("Choice [1/2/q]: ")
        if choice is None:
            print("\nGoodbye!")
            return 0

        choice = choice.strip().lower()

        if choice == "q":
            print("Goodbye!")
            return 0

        raw_input = None
        input_format = "user_story"

        if choice == "1":
            raw_input = _safe_input("Enter user story: ")
            if not raw_input or not raw_input.strip():
                print("   ⚠  Empty input, try again.")
                continue
            raw_input = raw_input.strip()
        elif choice == "2":
            filepath = _safe_input("File path: ")
            if not filepath:
                print("\nGoodbye!")
                return 0
            filepath = filepath.strip()
            try:
                with open(filepath, encoding="utf-8") as f:
                    content = f.read()
                if filepath.endswith(".json"):
                    parsed = input_parser.parse_json(content)
                else:
                    parsed = input_parser.parse(content, input_format)
                print(f"   ✓ Loaded {len(parsed.test_cases)} test case(s) from {filepath}")
            except FileNotFoundError:
                print(f"   ⚠  File not found: {filepath}")
                continue
            except json.JSONDecodeError as e:
                print(f"   ⚠  Invalid JSON: {e}")
                continue
        else:
            print("   ⚠  Invalid choice, try again.")
            continue

        # --- Step 4: Optional URL for page context ---
        url_input = _safe_input("Target URL (optional, press Enter to skip): ")
        url = url_input.strip() if url_input and url_input.strip() else None

        # --- Step 5: Build args and run ---
        args = argparse.Namespace(
            input=raw_input,
            file=None,
            generate=None,
            format=input_format,
            output_dir="generated_tests",
            mode="auto",
            project_key="TEST",
            evidence=True,
            url=url,
            reports="all",
        )

        # Run the generation pipeline
        print()
        return cmd_generate(args, parser)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AI Playwright Test Generator - Generate Playwright tests from user stories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s generate --input "As a user, I want to login"
  %(prog)s generate --file user_stories.txt --mode thorough
  %(prog)s generate --generate "Create a test for checkout flow"
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate Playwright tests")
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
    gen_parser.add_argument("--demo", action="store_true", help="Run with a premade demo user story for quick testing")

    # Test command
    test_parser = subparsers.add_parser("test", help="Run test suite")
    test_parser.add_argument("--filter", "-f", type=str, help="Test filter pattern")

    # Help command
    subparsers.add_parser("help", help="Show help message")

    # Parse arguments
    args = parser.parse_args()

    # Default values for output_dir if not provided
    if not hasattr(args, "output_dir"):
        args.output_dir = "generated_tests"

    # Default command — no arguments means interactive mode
    if not args.command:
        return cmd_interactive(parser)

    # Validate arguments — only when explicit input args were provided
    if not getattr(args, "input", None) and not getattr(args, "file", None) and not getattr(args, "generate", None):
        print("❌ Error: Must provide input via --input, --file, or --generate")
        return 1

    if args.input and args.file:
        print("❌ Error: Cannot use both --input and --file")
        return 1

    # Execute command
    if args.command == "generate":
        return cmd_generate(args, parser)
    elif args.command == "test":
        return cmd_test(args)
    elif args.command == "help":
        return cmd_help(args, parser)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
