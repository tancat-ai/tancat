from cli import menu_renderer
from src.cli.testing_terminal import QueueTerminal


def test_print_menu_numeric_selection_single_digit() -> None:
    qt = QueueTerminal(inputs=["1"])
    # inject
    menu_renderer.set_terminal_adapter(qt)
    try:
        idx = menu_renderer.print_menu(["One", "Two", "Three"], prompt="Choose")
        assert idx == 0
    finally:
        from cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)


def test_print_menu_numeric_selection_multi_digit() -> None:
    # Create 15 options and select 12
    options = [f"Item {i + 1}" for i in range(15)]
    qt = QueueTerminal(inputs=["12"])
    menu_renderer.set_terminal_adapter(qt)
    try:
        idx = menu_renderer.print_menu(options)
        assert idx == 11
    finally:
        from cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)


def test_print_menu_arrow_navigation_then_enter() -> None:
    qt = QueueTerminal(inputs=["v", "\r"])  # move down, then enter
    menu_renderer.set_terminal_adapter(qt)
    try:
        idx = menu_renderer.print_menu(["A", "B", "C"])
        assert idx == 1
    finally:
        from cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)
