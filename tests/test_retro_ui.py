"""Tests for cli/retro_ui.py — CHOICE-inspired retro terminal UI."""

from __future__ import annotations

import io
import sys
from unittest.mock import patch

import pytest

from cli.retro_ui import (
    _bold,
    _dim,
    _effective_width,
    _green,
    _inverse,
    _terminal_width,
    clear_screen,
    hide_cursor,
    move_cursor,
    prompt_input,
    show_cursor,
)

# ── Screen management ──────────────────────────────────────────────────────


class TestClearScreen:
    def test_clear_screen_sends_ansi_codes(self) -> None:
        buf = io.StringIO()
        # Mock isatty() to return True so ANSI codes are written
        buf.isatty = lambda: True  # type: ignore[method-assign]
        with patch.object(sys, "stdout", buf):
            clear_screen()
        output = buf.getvalue()
        assert "\033[H" in output
        assert "\033[J" in output

    def test_clear_screen_flushes(self) -> None:
        io.StringIO()
        flush_called = False

        class FlushTracking(io.StringIO):
            def flush(self) -> None:
                nonlocal flush_called
                flush_called = True

        tracking = FlushTracking()
        with patch.object(sys, "stdout", tracking):
            clear_screen()
        assert flush_called, "flush() should be called after clear_screen"


class TestMoveCursor:
    def test_move_cursor_position(self) -> None:
        buf = io.StringIO()
        buf.isatty = lambda: True  # type: ignore[method-assign]
        with patch.object(sys, "stdout", buf):
            move_cursor(x=5, y=10)
        assert "\033[11;6H" in buf.getvalue()


class TestCursorVisibility:
    def test_hide_cursor(self) -> None:
        buf = io.StringIO()
        buf.isatty = lambda: True  # type: ignore[method-assign]
        with patch.object(sys, "stdout", buf):
            hide_cursor()
        assert "\033[?25l" in buf.getvalue()

    def test_show_cursor(self) -> None:
        buf = io.StringIO()
        buf.isatty = lambda: True  # type: ignore[method-assign]
        with patch.object(sys, "stdout", buf):
            show_cursor()
        assert "\033[?25h" in buf.getvalue()


# ── Terminal width ─────────────────────────────────────────────────────────


class TestTerminalWidth:
    def test_terminal_width_returns_columns(self) -> None:
        with patch("os.get_terminal_size", return_value=type("Size", (), {"columns": 120})()):
            assert _terminal_width() == 120

    def test_terminal_width_fallback(self) -> None:
        with patch("os.get_terminal_size", side_effect=OSError("no tty")):
            assert _terminal_width() == 78

    def test_effective_width_minus_two(self) -> None:
        with patch("os.get_terminal_size", return_value=type("Size", (), {"columns": 80})()):
            assert _effective_width() == 78

    def test_effective_width_minimum(self) -> None:
        # Simulate a very narrow terminal
        with patch("os.get_terminal_size", return_value=type("Size", (), {"columns": 10})()):
            assert _effective_width() >= 40


# ── Colour helpers ─────────────────────────────────────────────────────────


class TestGreen:
    def test_green_bright_uses_ansi_100(self) -> None:
        # When stdout is a tty, ANSI codes are applied
        result = _green("hello", bright=True)
        assert "hello" in result

    def test_green_standard_uses_ansi_32(self) -> None:
        result = _green("hello", bright=False)
        assert "hello" in result


class TestDim:
    def test_dim_applies_style(self) -> None:
        result = _dim("faint text")
        assert "faint text" in result


class TestBold:
    def test_bold_applies_style(self) -> None:
        result = _bold("strong text")
        assert "strong text" in result


class TestInverse:
    def test_inverse_applies_style(self) -> None:
        result = _inverse("> ")
        assert "> " in result


# ── Prompt helpers ─────────────────────────────────────────────────────────


class TestPromptInput:
    def test_prompt_input_returns_user_value(self) -> None:
        with patch("builtins.input", return_value="my answer"):
            result = prompt_input("What is your name?")
        assert result == "my answer"

    def test_prompt_input_returns_default_on_empty(self) -> None:
        with patch("builtins.input", return_value=""):
            result = prompt_input("What is your name?", default="Alice")
        assert result == "Alice"

    def test_prompt_input_strips_whitespace(self) -> None:
        with patch("builtins.input", return_value="  spaced  "):
            result = prompt_input("Name")
        assert result == "spaced"


# ── Box-drawing characters ─────────────────────────────────────────────────


class TestBoxChars:
    def test_box_characters_present(self) -> None:
        from cli.retro_ui import BOX

        assert BOX.corner_tl == "┌"  # type: ignore[attr-defined]
        assert BOX.corner_tr == "┐"  # type: ignore[attr-defined]
        assert BOX.corner_bl == "└"  # type: ignore[attr-defined]
        assert BOX.corner_br == "┘"  # type: ignore[attr-defined]
        assert BOX.h_line == "─"  # type: ignore[attr-defined]
        assert BOX.v_line == "│"  # type: ignore[attr-defined]
        assert BOX.tee_r == "├"  # type: ignore[attr-defined]
        assert BOX.tee_l == "┤"  # type: ignore[attr-defined]


class TestRenderHeader:
    def test_render_header_outputs_box(self, capsys: pytest.CaptureFixture) -> None:
        from cli.retro_ui import render_header

        render_header("Test Title", "Subtitle")
        captured = capsys.readouterr().out
        assert "┌" in captured
        assert "┐" in captured
        assert "├" in captured
        assert "Test Title" in captured
        assert "Subtitle" in captured


class TestRenderMenu:
    def test_render_menu_highlights_selected(self, capsys: pytest.CaptureFixture) -> None:
        from cli.retro_ui import render_menu

        render_menu(["Option A", "Option B", "Option C"], selected=1)
        captured = capsys.readouterr().out
        assert "Option A" in captured
        assert "Option B" in captured
        assert "Option C" in captured
        # Selected item should have > cursor
        assert "> " in captured


class TestRenderState:
    def test_render_state_outputs_lines(self, capsys: pytest.CaptureFixture) -> None:
        from cli.retro_ui import render_state

        render_state(["  LLM : ollama / qwen3.5", "  URL : http://localhost"])
        captured = capsys.readouterr().out
        assert "State:" in captured
        assert "LLM" in captured
        assert "URL" in captured

    def test_render_state_empty_does_nothing(self, capsys: pytest.CaptureFixture) -> None:
        from cli.retro_ui import render_state

        render_state([])
        captured = capsys.readouterr().out
        assert captured.strip() == ""


class TestRenderShortcutBar:
    def test_render_shortcut_bar_outputs_box(self, capsys: pytest.CaptureFixture) -> None:
        from cli.retro_ui import render_shortcut_bar

        render_shortcut_bar([("1", "Select"), ("Q", "Quit")])
        captured = capsys.readouterr().out
        assert "[1]Select" in captured
        assert "[Q]Quit" in captured
        assert "├" in captured
        assert "┤" in captured
        assert "└" in captured
        assert "┘" in captured


# ── Color module phosphor functions ────────────────────────────────────────


class TestColorPhosphor:
    def test_phosphor_green(self) -> None:
        from cli.color import phosphor_green

        result = phosphor_green("test")
        assert "test" in result

    def test_dim_green(self) -> None:
        from cli.color import dim_green

        result = dim_green("test")
        assert "test" in result

    def test_inverse_green(self) -> None:
        from cli.color import inverse_green

        result = inverse_green("> ")
        assert "> " in result

    def test_phosphor_reset(self) -> None:
        from cli.color import phosphor_reset

        result = phosphor_reset()
        assert "\033[0m" == result
