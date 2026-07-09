"""Regression tests for Fix 1 — Journey Builder (Menu A) quit handling.

Ensures that pressing 'q' in the journey criteria menu returns -1
so the CLI stays in the main loop instead of raising ValueError.
See: docs/plans/CLI_JOURNEY_BUILDER_FIX.md
"""

from src.cli import menu_renderer
from src.cli.testing_terminal import QueueTerminal


def test_journey_builder_quit_returns_negative() -> None:
    """Pressing 'q' should return -1 (not raise ValueError)."""
    qt = QueueTerminal(inputs=["q"])
    menu_renderer.set_terminal_adapter(qt)  # type: ignore[arg-type]
    try:
        idx = menu_renderer.print_menu(["Criterion 1", "Criterion 2"])
        assert idx == -1
    finally:
        from src.cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)


def test_journey_builder_valid_number_selection() -> None:
    """Pressing a valid number returns the correct index."""
    qt = QueueTerminal(inputs=["1"])
    menu_renderer.set_terminal_adapter(qt)  # type: ignore[arg-type]
    try:
        idx = menu_renderer.print_menu(["Criterion 1", "Criterion 2"])
        assert idx == 0
    finally:
        from src.cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)


def test_journey_builder_multi_digit_selection() -> None:
    """Pressing a multi-digit number returns the correct index."""
    options = [f"Step {i}" for i in range(1, 21)]
    qt = QueueTerminal(inputs=["15"])
    menu_renderer.set_terminal_adapter(qt)  # type: ignore[arg-type]
    try:
        idx = menu_renderer.print_menu(options)
        assert idx == 14
    finally:
        from src.cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)


def test_journey_builder_arrow_then_enter() -> None:
    """Arrow navigation + Enter still works after fix."""
    qt = QueueTerminal(inputs=["v", "\r"])  # down, then enter
    menu_renderer.set_terminal_adapter(qt)  # type: ignore[arg-type]
    try:
        idx = menu_renderer.print_menu(["First", "Second", "Third"])
        assert idx == 1
    finally:
        from src.cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)


def test_journey_builder_quit_then_normal_selection() -> None:
    """After quitting once, next call should still accept valid input."""
    qt = QueueTerminal(inputs=["1"])
    menu_renderer.set_terminal_adapter(qt)  # type: ignore[arg-type]
    try:
        idx = menu_renderer.print_menu(["A", "B"])
        assert idx == 0
    finally:
        from src.cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)
