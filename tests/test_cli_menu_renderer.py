"""Tests for CLI menu input behavior."""

from __future__ import annotations

import io

import pytest

from cli import menu_renderer


def test_read_key_preserves_multi_digit_git_bash_input(monkeypatch: pytest.MonkeyPatch) -> None:
    """Git Bash line input should preserve choices like 11 instead of truncating to 1."""
    monkeypatch.setenv("MSYSTEM", "MINGW64")
    monkeypatch.setattr(menu_renderer.sys, "stdin", io.StringIO("11\n"))

    assert menu_renderer._read_key() == "11"


def test_read_key_maps_blank_git_bash_line_to_enter(monkeypatch: pytest.MonkeyPatch) -> None:
    """A blank Git Bash line should behave like pressing Enter on the selected item."""
    monkeypatch.setenv("MSYSTEM", "MINGW64")
    monkeypatch.setattr(menu_renderer.sys, "stdin", io.StringIO("\n"))

    assert menu_renderer._read_key() == "\r"


def test_read_key_maps_git_bash_arrow_sequence_with_newline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Git Bash arrow escape sequences with trailing newline should still map to arrows."""
    monkeypatch.setenv("MSYSTEM", "MINGW64")
    monkeypatch.setattr(menu_renderer.sys, "stdin", io.StringIO("\x1b[B\n"))

    assert menu_renderer._read_key() == "v"


def test_print_menu_accepts_numeric_input_in_git_bash(monkeypatch: pytest.MonkeyPatch) -> None:
    """Git Bash numeric input should select the correct menu item."""
    monkeypatch.setenv("MSYSTEM", "MINGW64")
    monkeypatch.setattr(menu_renderer.sys, "stdin", io.StringIO("1\n"))

    assert menu_renderer.print_menu(["Configure LLM", "Enter User Story"], "Main menu") == 0


def test_print_menu_falls_back_to_line_input_when_raw_key_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """When raw key reading fails, print_menu should still accept a number via input()."""
    monkeypatch.setenv("MSYSTEM", "")
    monkeypatch.setattr(menu_renderer, "_running_in_git_bash", lambda: False)
    monkeypatch.setattr(menu_renderer, "_read_key", lambda: "")
    monkeypatch.setattr(menu_renderer.sys, "stdin", io.StringIO("2\n"))

    assert menu_renderer.print_menu(["Configure LLM", "Enter Target URLs"], "Main menu") == 1
