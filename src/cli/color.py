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


# ── Retro (CHOICE-style) phosphor colours ──────────────────────────────────


def phosphor_green(text: str) -> str:
    """Bright green — ANSI 100. Used for selected/highlighted menu items."""
    return _c(text, "100")


def dim_green(text: str) -> str:
    """Dim/half-bright green — ANSI 2 + 32 combo. Used for non-selected items."""
    return _c(text, "2;32")


def inverse_green(text: str) -> str:
    """Inverse video — green background, black text. Used for the '>' cursor."""
    return _c(text, "7;32")


def phosphor_reset() -> str:
    """ANSI reset code as a standalone string. Useful for mid-line colour changes."""
    return "\033[0m"
