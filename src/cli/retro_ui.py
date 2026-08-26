"""CHOICE-inspired retro terminal UI.

Renders green-on-black, box-drawing menus with a selection indicator
reminiscent of the classic CHOICE mainframe menu system.

Cross-platform: uses ANSI escape codes (Win10+, macOS, Linux) and
standard input() for all user interaction. No curses dependency.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from .color import _c

# ── Screen management ──────────────────────────────────────────────────────


def clear_screen() -> None:
    """Clear the terminal and move cursor to 0,0.

    Uses ANSI escape sequences which work on modern Windows (Win10+),
    macOS, and Linux terminals. When stdout is not a TTY (e.g. subprocess
    pipe, CI logging), writes a separator line instead so captured output
    remains readable.
    """
    if sys.stdout.isatty():
        # \033[H = move cursor to home position (0,0)
        # \033[J = clear from cursor to end of screen
        sys.stdout.write("\033[H\033[J")
    else:
        sys.stdout.write("\n" + "=" * 78 + "\n")
    sys.stdout.flush()


def move_cursor(x: int = 0, y: int = 0) -> None:
    """Move cursor to absolute position (column x, row y)."""
    if sys.stdout.isatty():
        sys.stdout.write(f"\033[{y + 1};{x + 1}H")
        sys.stdout.flush()


def hide_cursor() -> None:
    """Hide the terminal cursor for a cleaner retro look."""
    if sys.stdout.isatty():
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()


def show_cursor() -> None:
    """Show the terminal cursor."""
    if sys.stdout.isatty():
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


# ── Box-drawing characters ─────────────────────────────────────────────────


@dataclass
class _BoxChars:
    """Typed namespace for box-drawing characters."""

    corner_tl: str = "┌"
    corner_tr: str = "┐"
    corner_bl: str = "└"
    corner_br: str = "┘"
    h_line: str = "─"
    v_line: str = "│"
    tee_l: str = "┤"
    tee_r: str = "├"
    tee_u: str = "┬"
    tee_d: str = "┴"
    cross: str = "┼"


# Unicode box-drawing set (double-line style — closest to CHOICE aesthetic)
BOX = _BoxChars()


def _box_char(attr: str) -> str:
    """Return a plain box-drawing character for the given attribute name.

    Color is applied at the LINE level (see _color_line) to avoid
    ANSI escape sequences interfering with string length calculations
    and border alignment.
    """
    return getattr(BOX, attr)  # type: ignore[attr-defined]


def _color_line(line: str, bright: bool = False) -> str:
    """Apply green color to an entire line.

    Wrapping the full line in a single ANSI pair avoids per-character
    escape sequences that break border alignment when terminals calculate
    string lengths for padding/truncation.
    """
    return _green(line, bright=bright)


def _visible_len(text: str) -> int:
    """Return visible character length, stripping ANSI escape sequences."""
    import re

    return len(re.sub(r"\033\[\d+(;\d+)*m", "", text))


def _inner_width() -> int:
    """Usable width inside a 1-column box border (terminal width - 2)."""
    return max(20, _terminal_width() - 2)


def _truncate_middle(text: str, max_len: int) -> str:
    """Truncate *text* to *max_len* visible chars, keeping the start readable.

    Preserves the tail when the result is shorter than *max_len* (i.e. the
    full text fits) so nothing is lost.  Only shrinks when genuinely too wide.
    """
    if _visible_len(text) <= max_len:
        return text
    if max_len <= 4:
        return text[:max_len]
    keep = max_len - 3
    return text[:keep] + "..."


# ── Screen layout ──────────────────────────────────────────────────────────


def _terminal_width() -> int:
    """Return the terminal width, defaulting to 78 if undetectable."""
    try:
        return os.get_terminal_size().columns
    except AttributeError, OSError:
        return 78


def _effective_width() -> int:
    """Return usable width (leave 2-column margin for box borders)."""
    return max(40, _terminal_width() - 2)


# ── Rendering helpers ──────────────────────────────────────────────────────


def _green(text: str, bright: bool = False) -> str:
    """Apply green ANSI colour.

    *bright=True* → ANSI 1;32 (bold green — more portable than 100)
    *bright=False* → ANSI  32 (standard green)
    Falls back to plain text when stdout is not a tty.
    """
    # _c() appends 'm' after the code, so pass code without trailing 'm'
    # Use 1;32 (bold green) instead of 100 — VS Code terminal maps 100 to white
    code = "1;32" if bright else "32"
    return _c(text, code)


def _dim(text: str) -> str:
    """Apply dim (half-bright) ANSI style."""
    return _c(text, "2")


def _bold(text: str) -> str:
    """Apply bold ANSI style."""
    return _c(text, "1")


def _inverse(text: str) -> str:
    """Apply inverse video (green background, black foreground)."""
    return _c(text, "7;32")


# ── Public API ─────────────────────────────────────────────────────────────


def render_header(title: str, subtitle: str = "") -> None:
    """Render a CHOICE-style header box.

    Example::

        ┌─────────────────────────────────────────────────────────────┐
        │  AI PLAYWRIGHT TEST GENERATOR                              │
        │  Generate Playwright tests from user stories with AI       │
        ├─────────────────────────────────────────────────────────────┤

    """
    width = _effective_width()
    inner = width - 2  # space between left and right borders

    def _pad(text: str) -> str:
        """Left-align text, padded to inner width minus 2-space margin."""
        green_text = _green(text, bright=True)
        return green_text.ljust(inner - 2)

    top = _color_line(BOX.corner_tl + BOX.h_line * inner + BOX.corner_tr)
    sep = _color_line(BOX.tee_r + BOX.h_line * inner + BOX.tee_l)

    print(top)
    # Title/subtitle lines: plain box chars + bright green text content
    title_line = BOX.v_line + "  " + _pad(title) + " " * max(1, inner - 4 - _visible_len(_pad(title))) + BOX.v_line
    print(_color_line(title_line))
    if subtitle:
        sub_line = (
            BOX.v_line + "  " + _pad(subtitle) + " " * max(1, inner - 4 - _visible_len(_pad(subtitle))) + BOX.v_line
        )
        print(_color_line(sub_line))
    else:
        blank_line = BOX.v_line + " " + BOX.h_line * (inner - 2) + BOX.v_line
        print(_color_line(blank_line))
    print(sep)


def render_menu(
    items: Sequence[str],
    selected: int = 0,
    group_labels: list[str] | None = None,
) -> None:
    """Render a menu with CHOICE-style selection indicator.

    The *selected* item is prefixed with ``> `` and rendered in bright
    green. All other items are rendered in dim green.

    Args:
        items: Menu item labels.
        selected: Zero-based index of the highlighted item.
        group_labels: Optional section headers (blank lines separate groups).

    Example output::

        > Configure LLM
          Enter User Story
          Re-enter Target URLs
    """
    for i, item in enumerate(items):
        numbered_item = f"[{i + 1}] {item}"
        if i == selected:
            # Bright green with inverse-video cursor
            print("   " + _inverse("> ") + _green(numbered_item, bright=True), flush=True)
        else:
            # Standard/dim green
            print("   " + _green("  " + numbered_item, bright=False), flush=True)


def render_state(state_lines: list[str]) -> None:
    """Render a state summary block in dim green.

    Each line is rendered as a key-value pair in dim green.

    Example output::

        State:
          LLM : ollama / qwen3.5:35b
          URL : https://automationexercise.com
    """
    if not state_lines:
        return
    print("   " + _dim(_green("State:", bright=False)))
    for line in state_lines:
        print("   " + _dim(_green(line, bright=False)))


def render_shortcut_bar(shortcuts: list[tuple[str, str]]) -> None:
    """Deprecated thin bar.  Prefer :func:`render_shortcuts` for the
    action-buttons layout.  Kept for backwards compatibility and tests.
    """
    render_shortcuts(shortcuts)


def render_shortcuts(entries: list[tuple[str, str]]) -> None:
    """Render a bottom row of key-action "buttons" in green box-drawing.

    Each entry is a ``(key, label)`` pair rendered as an ``[key] Label``
    button.  Buttons flow horizontally and wrap to additional lines when they
    do not fit on one line — nothing is ever dropped, so every action stays
    visible and usable even when there are many of them.

    Args:
        entries: List of (key, label) pairs, e.g.
            ``[("M", "Main Menu"), ("B", "Back"), ("Q", "Quit")]``

    Example output (fits one line)::

        ├─────────────────────────────────────────────────────────────┤
        │  [M] Main Menu   [B] Back   [Q] Quit                       │
        └─────────────────────────────────────────────────────────────┘

    Wraps to a second line when the buttons do not fit on one line.
    """
    inner = _inner_width()
    usable = inner - 2  # one space of padding on each side inside the border
    top = _color_line(BOX.tee_r + BOX.h_line * inner + BOX.tee_l)
    bottom = _color_line(BOX.corner_bl + BOX.h_line * inner + BOX.corner_br)
    rows = _shortcut_button_rows(entries, usable)

    print(top, flush=True)
    for row in rows:
        print(_color_line(BOX.v_line + row.ljust(inner) + BOX.v_line), flush=True)
    print(bottom, flush=True)


def _shortcut_button_rows(entries: list[tuple[str, str]], usable: int) -> list[str]:
    """Lay out ``[key] Label`` buttons into rows that fit *usable* columns.

    Buttons are packed greedily onto each row and wrapped to the next row
    when the next button would not fit.  A row is never wider than *usable*.
    """
    buttons: list[str] = []
    for key, label in entries:
        if not key:
            continue
        buttons.append(f"[{key}] {label}" if label else f"[{key}]")

    rows: list[str] = []
    row_parts: list[str] = []
    current_len = 0
    for btn in buttons:
        btn_len = _visible_len(btn)
        add = btn_len if current_len == 0 else 2 + btn_len
        if current_len and current_len + add > usable:
            rows.append(" " + _truncate_middle("  ".join(row_parts), usable))
            row_parts = []
            current_len = 0
            add = btn_len
        row_parts.append(btn)
        current_len += add
    if row_parts or not rows:
        rows.append(" " + _truncate_middle("  ".join(row_parts), usable))
    return rows


def render_separator() -> None:
    """Render a horizontal rule inside a box."""
    width = _effective_width()
    inner = width - 2
    print(_color_line(BOX.v_line + BOX.h_line * inner + BOX.v_line))


def render_status_bar(
    message: str,
    shortcuts: list[tuple[str, str]] | None = None,
) -> None:
    """Render a full screen with header, message, and shortcut bar.

    Convenience wrapper for simple single-screen displays.
    """
    render_header("AI PLAYWRIGHT TEST GENERATOR", "")
    print()
    print("   " + _green(message, bright=True))
    print()
    if shortcuts:
        render_shortcut_bar(shortcuts)


# ── Simple text input (retro-styled) ───────────────────────────────────────


def prompt_input(prompt_text: str, default: str = "") -> str:
    """Display a retro-styled input prompt.

    Returns the user's input (or *default* on empty input).
    """
    prompt = _green(prompt_text, bright=True)
    if default:
        prompt += f" (default: {default})"
    prompt += ": "
    value = input(prompt)
    return value.strip() or default


def prompt_non_empty(prompt_text: str) -> str:
    """Like :func:`prompt_input` but rejects empty values."""
    while True:
        value = prompt_input(prompt_text)
        if value:
            return value
        print("   " + _dim("  Input cannot be empty. Please try again."))
