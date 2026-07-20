"""Tests for cli/main.py — CLI entry point and argument handling.

Subprocess-based tests that verify the CLI entry point works end-to-end
without requiring interactive input.

NOTE: The CLI was refactored to be purely interactive in 2026-07.
The legacy argparse-based ``generate --input``/``--file`` subcommand
was removed. Tests that exercised that interface have been updated
or removed accordingly.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_ENTRY = "-m"


# ── Helpers ────────────────────────────────────────────────────────────────


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the CLI via subprocess and return the result.

    Uses errors='replace' to handle the CLI's UTF-8 stdout on Windows
    where the parent process may default to cp1252.
    """
    return subprocess.run(
        [sys.executable, CLI_ENTRY, "cli.main"] + list(args),
        capture_output=True,
        text=True,
        errors="replace",
        timeout=30,
        cwd=str(REPO_ROOT),
    )


# ── Help & Usage ───────────────────────────────────────────────────────────


@pytest.mark.subprocess
class TestHelpOutput:
    def test_help_flag_returns_zero(self) -> None:
        result = _run_cli("--help")
        assert result.returncode == 0

    def test_help_flag_shows_description(self) -> None:
        result = _run_cli("--help")
        assert "Playwright" in result.stdout

    def test_help_flag_shows_menu_items(self) -> None:
        """The interactive menu should list available actions."""
        result = _run_cli("--help")
        combined = (result.stdout or "").lower()
        assert "enter user story" in combined or "configure llm" in combined, (
            "help output should show interactive menu items"
        )

    def test_help_flag_shows_entry_point(self) -> None:
        """The interactive menu title should be visible."""
        result = _run_cli("--help")
        combined = (result.stdout or "").lower()
        assert "playwright" in combined, "help output should reference Playwright"


# ── Test subcommand ────────────────────────────────────────────────────────


@pytest.mark.subprocess
class TestTestSubcommand:
    def test_test_subcommand_runs(self) -> None:
        result = _run_cli("test")
        assert result.returncode == 0


# ── Help subcommand ────────────────────────────────────────────────────────


@pytest.mark.subprocess
class TestHelpSubcommand:
    def test_help_subcommand_runs(self) -> None:
        result = _run_cli("help")
        assert result.returncode == 0
        assert "Playwright" in result.stdout
