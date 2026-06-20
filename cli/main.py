"""Backwards-compatible shim — CLI entry point moved to src.cli.main."""

import sys

from src.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
