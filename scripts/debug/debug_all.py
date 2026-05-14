#!/usr/bin/env python3
"""Unified debug entry point for all debug scripts.

Usage:
    python scripts/debug/debug_all.py --help
    python scripts/debug/debug_all.py pipeline --url https://saucedemo.com
    python scripts/debug/debug_all.py text-validation
    python scripts/debug/debug_all.py skeleton-inspection
    python scripts/debug/debug_all.py saucedemo-login
    python scripts/debug/debug_all.py saucedemo-inventory
    python scripts/debug/debug_all.py saucedemo-scrape
    python scripts/debug/debug_all.py scoring
"""

from __future__ import annotations

import argparse
import importlib
import os
import pathlib
import sys


def _import_and_run(module_path: str, args: list[str]) -> None:
    """Import a debug script and run its main() with the given args."""
    script_dir = pathlib.Path(__file__).parent.resolve()
    project_root = script_dir.parent.parent  # scripts/debug -> project root
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Change to project root so relative imports work
    original_cwd = os.getcwd()
    os.chdir(project_root)

    try:
        mod = importlib.import_module(f"scripts.debug.{module_path}")
        if hasattr(mod, "main"):
            if callable(mod.main):
                # Check if main accepts args
                import inspect

                sig = inspect.signature(mod.main)
                if len(sig.parameters) == 0:
                    mod.main()
                else:
                    mod.main(args)
            else:
                print(f"ERROR: {module_path}.main is not callable")
                sys.exit(1)
        elif hasattr(mod, "inspect_text_validation") and hasattr(mod, "inspect_skeleton_placeholders"):
            # debug_pipeline.py pattern
            print("Module has standalone inspection functions but no main().")
            print("Run the script directly: python scripts/debug/debug_pipeline.py --help")
        else:
            print(f"ERROR: {module_path} has no main() function")
            sys.exit(1)
    finally:
        os.chdir(original_cwd)


USAGE_EPILOG = """\
Commands:
  pipeline              Full pipeline trace (skeleton -> scrape -> resolve -> final code)
  text-validation       Inspect text_matches_description logic (offline)
  skeleton-inspection   Inspect skeleton placeholders (offline)
  saucedemo-login       Login to SauceDemo and test resolution
  saucedemo-inventory   Scrape SauceDemo inventory page
  saucedemo-scrape      Quick scrape of SauceDemo login page
  scoring               Debug scoring for specific elements

Examples:
  python scripts/debug/debug_all.py pipeline --url https://saucedemo.com
  python scripts/debug/debug_all.py text-validation
  python scripts/debug/debug_all.py saucedemo-login
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unified debug entry point for AI-Playwright-Test-Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=USAGE_EPILOG,
    )

    subparsers = parser.add_subparsers(dest="command", help="Debug command to run")

    # pipeline
    p_pipeline = subparsers.add_parser("pipeline", help="Full pipeline trace")
    p_pipeline.add_argument("--url", help="URL to scrape")
    p_pipeline.add_argument("--story", help="User story")
    p_pipeline.add_argument("--conditions", help="Acceptance conditions")

    # text-validation
    subparsers.add_parser("text-validation", help="Inspect text validation logic (offline)")

    # skeleton-inspection
    subparsers.add_parser("skeleton-inspection", help="Inspect skeleton placeholders (offline)")

    # saucedemo-login
    subparsers.add_parser("saucedemo-login", help="Login to SauceDemo and test resolution")

    # saucedemo-inventory
    subparsers.add_parser("saucedemo-inventory", help="Scrape SauceDemo inventory page")

    # saucedemo-scrape
    subparsers.add_parser("saucedemo-scrape", help="Quick scrape of SauceDemo login page")

    # scoring
    subparsers.add_parser("scoring", help="Debug scoring for specific elements")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.command:
        doc = __doc__ if __doc__ else ""
        print(doc.strip())
        print()
        parse_args.__globals__["parser"].parse_args(["--help"])  # noqa: F821
        return 0

    command_map = {
        "pipeline": "debug_pipeline",
        "text-validation": "debug_pipeline",
        "skeleton-inspection": "debug_pipeline",
        "saucedemo-login": "debug_saucedemo_login",
        "saucedemo-inventory": "debug_saucedemo_inventory",
        "saucedemo-scrape": "debug_saucedemo_scrape2",
        "scoring": "debug_scoring",
    }

    module_name = command_map.get(args.command)
    if not module_name:
        print(f"Unknown command: {args.command}")
        return 1

    # Build args to pass to the script
    extra_args: list[str] = []
    if args.command == "pipeline":
        if args.url:
            extra_args.extend(["--url", args.url])
        if args.story:
            extra_args.extend(["--story", args.story])
        if args.conditions:
            extra_args.extend(["--conditions", args.conditions])
    elif args.command == "text-validation":
        extra_args.append("--text-validation")
    elif args.command == "skeleton-inspection":
        extra_args.append("--skeleton-inspection")

    try:
        _import_and_run(module_name, extra_args)
    except Exception as e:
        print(f"ERROR running {module_name}: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
