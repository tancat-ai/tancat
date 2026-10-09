#!/usr/bin/env python3
"""Deprecated shim — the headless driver moved to the product CLI.

The headless generation driver now lives in ``src/cli/headless.py`` and is
reached through ``tancat run`` (the GitHub Action and the GitLab template call
that). This file stays so an existing ``python scripts/ci_generate.py ...``
invocation keeps working; it delegates to the product module.

Prefer::

    tancat run --story story.md --url https://staging.example.com [--json]
"""

from __future__ import annotations

import sys

from src.cli.headless import (
    EXIT_CONFIG_ERROR,
    EXIT_GENERATION_ERROR,
    EXIT_OK,
    build_parser,
    main,
)

__all__ = ["EXIT_CONFIG_ERROR", "EXIT_GENERATION_ERROR", "EXIT_OK", "build_parser", "main"]

if __name__ == "__main__":
    sys.exit(main())
