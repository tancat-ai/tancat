"""ANSI colour helpers for the CLI.

Wraps text in ANSI colour codes when stdout is a terminal;
falls back to plain text when piped or redirected.
"""

from __future__ import annotations

import os


def _c(text: str, code: str) -> str:
    """Wrap *text* in an ANSI colour code when stdout is a terminal."""
    try:
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
