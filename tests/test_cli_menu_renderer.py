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
