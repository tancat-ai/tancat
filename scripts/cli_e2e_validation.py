"""CLI-based E2E validation for the unified pipeline.

This script exercises the full CLI pipeline and validates that the
generated Python code is syntactically correct. It is designed to
reproduce quoting and other code-generation bugs via the CLI path.

Usage:
    python scripts/cli_e2e_validation.py [--url URL] [--story FILE] [--timeout N] [--output PATH]
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Ensure the project root is on sys.path so cli packages resolve.
_project_root = Path(__file__).parent.parent.resolve()
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Load .env so LLM_PROVIDER, LM_STUDIO_BASE_URL, LM_STUDIO_MODEL etc. are available.
_load_dotenv = load_dotenv(dotenv_path=_project_root / ".env")


def _load_user_story(path: str | None = None) -> str:
    """Return the user story text from file or use a default."""
    if path:
        return Path(path).read_text(encoding="utf-8")
    return (
        "## User Story\n"
        "As a customer I want to add items to cart\n\n"
        "## Acceptance Criteria\n"
        "1. add items to cart\n"
        "2. go to cart\n"
        "3. check the items have been added correctly\n"
        "4. go to check out\n"
        "5. check out\n"
        "\n"
        "(Total: 5 criteria)\n"
    )


def _run_cli_pipeline(user_story: str, url: str | None) -> dict[str, Any]:
    """Execute the CLI pipeline and return results."""
    from cli.input_parser import InputParser
    from cli.test_case_orchestrator import TestCaseOrchestrator

    parser = InputParser()
    parsed = parser.parse(user_story, None)

    orchestrator = TestCaseOrchestrator()
    result = orchestrator.process(str(parsed), url=url)

    return {
        "generated_files": result.generated_files,
        "errors": result.errors,
        "summary": result.summary,
    }


def _validate_python_syntax(filepath: str) -> tuple[bool, str | None]:
    """Validate that a generated test file is valid Python.

    Returns:
        (is_valid, error_message)
    """
    try:
        source = Path(filepath).read_text(encoding="utf-8")
        ast.parse(source)
        return True, None
    except SyntaxError as e:
        return False, f"{e.filename}:{e.lineno}: {e.msg}"
    except FileNotFoundError:
        return False, f"File not found: {filepath}"


def run_validation(
    url: str | None = None,
    story_path: str | None = None,
    timeout: int = 600,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Run the full E2E validation and return results.

    Args:
        url: Target URL to scrape. Defaults to automationexercise.com.
        story_path: Path to user story file. Uses built-in default if None.
        timeout: LLM timeout in seconds (default: 600).
        output_path: Path for JSON result file. Defaults to uat_result.json.
    """
    user_story = _load_user_story(story_path)
    target_url = url or "https://www.automationexercise.com"
    print("[E2E] Running CLI pipeline...")
    print(f"[E2E] Target URL: {target_url}")
    print(f"[E2E] LLM timeout: {timeout}s")
    print(f"[E2E] User story: {user_story[:100]}...")

    # Run the CLI pipeline
    pipeline_result = _run_cli_pipeline(user_story, target_url)

    generated_files = pipeline_result["generated_files"]
    errors = pipeline_result["errors"]

    print(f"\n[E2E] Generated {len(generated_files)} file(s)")
    for f in generated_files:
        print(f"  - {f}")

    if errors:
        print("\n[E2E] Errors:")
        for e in errors:
            print(f"  - {e}")

    # Validate Python syntax for each generated file
    syntax_results: list[dict[str, Any]] = []
    all_valid = True
    for filepath in generated_files:
        is_valid, error = _validate_python_syntax(filepath)
        syntax_results.append({"file": filepath, "valid": is_valid, "error": error})
        if not is_valid:
            all_valid = False
            print(f"\n[FAIL] Syntax error in {filepath}: {error}")
        else:
            print(f"[PASS] Syntax valid: {filepath}")

    # Write structured JSON result for Cline to poll
    result_json_path = output_path or str(_project_root / "uat_result.json")
    json_result = {
        "status": "PASS" if all_valid else "FAIL",
        "generated_files": len(generated_files),
        "files": [str(f) for f in generated_files],
        "syntax_errors": [s["error"] for s in syntax_results if s["error"]],
        "errors": errors,
        "timeout_s": timeout,
        "target_url": target_url,
    }
    Path(result_json_path).write_text(json.dumps(json_result, indent=2), encoding="utf-8")
    print(f"\n[RESULT] JSON result written to: {result_json_path}")

    return {
        "all_valid": all_valid,
        "generated_files": generated_files,
        "syntax_results": syntax_results,
        "errors": errors,
    }


def main() -> int:
    """Entry point for the E2E validation script."""
    import argparse

    parser = argparse.ArgumentParser(description="CLI E2E validation for the unified pipeline")
    parser.add_argument(
        "--url",
        type=str,
        help="Target URL to scrape (default: https://www.automationexercise.com)",
        default=None,
    )
    parser.add_argument(
        "--story",
        type=str,
        help="Path to user story file",
        default=None,
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="LLM timeout in seconds (default: 600)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Path for JSON result file (default: uat_result.json)",
        default=None,
    )
    args = parser.parse_args()

    result = run_validation(
        url=args.url,
        story_path=args.story,
        timeout=args.timeout,
        output_path=args.output,
    )

    if result["all_valid"]:
        print(f"\n[E2E] All {len(result['generated_files'])} file(s) passed syntax validation.")
        return 0
    else:
        print("\n[E2E] FAILED: Some files have syntax errors.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
