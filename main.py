"""Deprecated compatibility entry point.

The supported CLI lives in ``cli/main.py`` and is launched with:

    python -m cli.main

This wrapper remains so older commands such as ``python main.py`` still route
to the current CLI instead of running the retired pre-pipeline menu flow.
"""

from __future__ import annotations

import sys

from cli.main import main as cli_main


def main() -> int:
    """Run the supported CLI entry point."""
    print("Note: root main.py is deprecated. Use `python -m cli.main` or `bash launch_cli.sh`.")
    return cli_main()


if __name__ == "__main__":
    sys.exit(main())
