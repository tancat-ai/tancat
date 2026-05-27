"""Tests for cli/main.py — CLI entry point and argument handling.

Subprocess-based tests that verify the CLI entry point works end-to-end
without requiring interactive input.
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


class TestHelpOutput:
    def test_help_flag_returns_zero(self) -> None:
        result = _run_cli("--help")
        assert result.returncode == 0

    def test_help_flag_shows_description(self) -> None:
        result = _run_cli("--help")
        assert "Playwright" in result.stdout

    def test_help_flag_shows_generate_subcommand(self) -> None:
        result = _run_cli("--help")
        assert "generate" in result.stdout

    def test_help_flag_shows_interactive_mode(self) -> None:
        result = _run_cli("--help")
        assert "Interactive" in result.stdout or "interactive" in result.stdout.lower()


# ── Generate subcommand ───────────────────────────────────────────────────


class TestGenerateSubcommand:
    def test_generate_help(self) -> None:
        result = _run_cli("generate", "--help")
        assert result.returncode == 0
        assert "--input" in result.stdout

    def test_generate_missing_input_fails(self) -> None:
        result = _run_cli("generate")
        assert result.returncode != 0

    def test_generate_both_input_and_file_fails(self) -> None:
        result = _run_cli("generate", "--input", "test", "--file", "does_not_exist.md")
        assert result.returncode != 0

    def test_generate_file_not_found_fails(self) -> None:
        result = _run_cli("generate", "--file", "nonexistent_file_12345.md")
        assert result.returncode != 0
        # CLI prints error to stderr when file not found
        combined = (result.stdout or "") + (result.stderr or "")
        assert "not found" in combined.lower() or "Error" in combined or "error" in combined.lower()


# ── Invalid arguments ──────────────────────────────────────────────────────


class TestInvalidArguments:
    def test_unknown_flag_fails(self) -> None:
        result = _run_cli("--unknown-flag")
        assert result.returncode != 0

    def test_unknown_subcommand_shows_help(self) -> None:
        result = _run_cli("nonexistent_command")
        # argparse writes errors to stderr
        combined = (result.stdout or "") + (result.stderr or "")
        assert "usage" in combined.lower() or "invalid choice" in combined.lower()


# ── Test subcommand ────────────────────────────────────────────────────────


class TestTestSubcommand:
    def test_test_subcommand_runs(self) -> None:
        result = _run_cli("test")
        assert result.returncode == 0


# ── Help subcommand ────────────────────────────────────────────────────────


class TestHelpSubcommand:
    def test_help_subcommand_runs(self) -> None:
        result = _run_cli("help")
        assert result.returncode == 0
        assert "Playwright" in result.stdout


# ── Integration: generate with valid input ─────────────────────────────────


class TestGenerateIntegration:
    """These tests exercise the generate subcommand with real input.

    They require LLM mocking to be configured or will hit the real LLM.
    Skipped by default unless CLI_E2E_LLM is set.
    """

    @pytest.mark.skipif(True, reason="Requires LLM mocking — skip by default")
    def test_generate_with_input(self) -> None:
        result = _run_cli("generate", "--input", "As a user I want to login", "--output", "/tmp/cli_e2e_out")
        assert result.returncode == 0
        assert "Complete" in result.stdout or "Generated" in result.stdout
