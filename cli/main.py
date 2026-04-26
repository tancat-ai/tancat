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


def cmd_generate(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Handle generate command."""
    print("=" * 60)
    print("🤖 AI Playwright Test Generator")
    print("=" * 60)

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

    # Default command
    if not args.command:
        args.command = "generate"
        args.input = ""

    # Validate arguments
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
