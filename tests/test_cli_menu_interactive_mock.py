from __future__ import annotations

import pytest

from src.cli import menu_renderer
from src.cli.testing_terminal import QueueTerminal


def test_print_menu_numeric_selection_single_digit() -> None:
    qt = QueueTerminal(inputs=["1"])
    # inject
    menu_renderer.set_terminal_adapter(qt)  # type: ignore[arg-type]
    try:
        idx = menu_renderer.print_menu(["One", "Two", "Three"], prompt="Choose")
        assert idx == 0
    finally:
        from src.cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)


def test_print_menu_numeric_selection_multi_digit() -> None:
    # Create 15 options and select 12
    options = [f"Item {i + 1}" for i in range(15)]
    qt = QueueTerminal(inputs=["12"])
    menu_renderer.set_terminal_adapter(qt)  # type: ignore[arg-type]
    try:
        idx = menu_renderer.print_menu(options)
        assert idx == 11
    finally:
        from src.cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)


def test_print_menu_arrow_navigation_then_enter() -> None:
    qt = QueueTerminal(inputs=["v", "\r"])  # move down, then enter
    menu_renderer.set_terminal_adapter(qt)  # type: ignore[arg-type]
    try:
        idx = menu_renderer.print_menu(["A", "B", "C"])
        assert idx == 1
    finally:
        from src.cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)


def test_print_menu_back_returns_sentinel_from_sub_menu() -> None:
    """Pressing 'B' in a registered sub-menu returns the back sentinel."""
    qt = QueueTerminal(inputs=["b"])
    menu_renderer.set_terminal_adapter(qt)  # type: ignore[arg-type]
    menu_renderer._menu_stack.clear()
    menu_renderer.push_menu("Journey Builder")
    try:
        idx = menu_renderer.print_menu(["Add step", "Done building"], back=menu_renderer.BACK_JOURNEY)
        assert idx == menu_renderer.BACK_JOURNEY
        assert idx < 0  # negative sentinel, never a valid index
    finally:
        menu_renderer.pop_menu()
        menu_renderer._menu_stack.clear()
        from src.cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)


def test_print_menu_main_menu_returns_sentinel_at_depth_two() -> None:
    """Pressing 'M' at depth >= 2 returns BACK_MAIN and unwinds the stack."""
    qt = QueueTerminal(inputs=["m"])
    menu_renderer.set_terminal_adapter(qt)  # type: ignore[arg-type]
    menu_renderer._menu_stack.clear()
    menu_renderer.push_menu("Journey Builder")
    menu_renderer.push_menu("Step type")  # depth 2
    try:
        idx = menu_renderer.print_menu(["navigate", "click"], back=menu_renderer.BACK_JOURNEY)
        assert idx == menu_renderer.BACK_MAIN
        # The whole stack is unwound so the session lands on the main menu.
        assert menu_renderer._menu_stack == []
    finally:
        while menu_renderer.pop_menu() is not None:
            pass
        from src.cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)


def test_print_menu_back_button_only_at_depth_one(capsys: pytest.CaptureFixture) -> None:
    """At depth 1 only [B] Back is offered — no Main Menu button."""
    qt = QueueTerminal(inputs=["1"])
    menu_renderer.set_terminal_adapter(qt)  # type: ignore[arg-type]
    menu_renderer._menu_stack.clear()
    menu_renderer.push_menu("LLM Configuration")
    try:
        idx = menu_renderer.print_menu(["Ollama", "LM Studio"], back=menu_renderer.BACK_LLM)
        assert idx == 0
        out = capsys.readouterr().out
        assert "[B] Back" in out
        assert "Main Menu" not in out
    finally:
        menu_renderer._reset_menu_stack()
        from src.cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)


def test_print_menu_navigation_buttons_absent_without_stack(capsys: pytest.CaptureFixture) -> None:
    """At the main menu (empty stack, no back sentinel) no Back/Main buttons show."""
    # Feed a valid selection so the menu returns after the first render.
    qt = QueueTerminal(inputs=["1"])
    menu_renderer.set_terminal_adapter(qt)  # type: ignore[arg-type]
    menu_renderer._menu_stack.clear()
    try:
        idx = menu_renderer.print_menu(["A", "B"])
        assert idx == 0
        out = capsys.readouterr().out
        # Navigation buttons are hidden on the main menu.
        assert "Back" not in out
        assert "Main Menu" not in out
        # Quit is always present.
        assert "[Q] Quit" in out
    finally:
        menu_renderer._menu_stack.clear()
        from src.cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)


def test_print_menu_navigation_buttons_present_in_sub_menu(capsys: pytest.CaptureFixture) -> None:
    """In a registered sub-menu (depth 2), Back and Main Menu buttons appear."""
    qt = QueueTerminal(inputs=["1"])
    menu_renderer.set_terminal_adapter(qt)  # type: ignore[arg-type]
    menu_renderer._menu_stack.clear()
    menu_renderer.push_menu("Journey Builder")
    menu_renderer.push_menu("Step type")
    try:
        idx = menu_renderer.print_menu(["navigate", "click"], back=menu_renderer.BACK_JOURNEY)
        assert idx == 0
        out = capsys.readouterr().out
        assert "[B] Back" in out
        assert "[M] Main Menu" in out
    finally:
        while menu_renderer.pop_menu() is not None:
            pass
        from src.cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)


def test_push_pop_menu_stack_roundtrip() -> None:
    """push/pop round-trip restores the stack and returns None at base."""
    menu_renderer._menu_stack.clear()
    try:
        assert menu_renderer.pop_menu() is None
        menu_renderer.push_menu("A")
        menu_renderer.push_menu("B")
        assert menu_renderer.pop_menu() == "B"
        assert menu_renderer.pop_menu() == "A"
        assert menu_renderer.pop_menu() is None
    finally:
        menu_renderer._reset_menu_stack()


# ── Collector back-out semantics (state must never be wiped by Back) ──────


def test_collect_authentication_back_returns_sentinel() -> None:
    """Pressing B in the auth screen returns BACK_AUTH, not None (no wipe)."""
    qt = QueueTerminal(inputs=["b"])
    menu_renderer.set_terminal_adapter(qt)  # type: ignore[arg-type]
    menu_renderer._menu_stack.clear()
    menu_renderer.push_menu("Authentication")
    try:
        result = menu_renderer.collect_authentication()
        assert isinstance(result, int)
        assert result == menu_renderer.BACK_AUTH
    finally:
        menu_renderer._reset_menu_stack()
        from src.cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)


def test_collect_journey_back_on_first_screen_keeps_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backing out of the journey builder's first screen returns a sentinel,
    never a list — the caller keeps the previously configured journey."""
    qt = QueueTerminal(inputs=["b"])
    menu_renderer.set_terminal_adapter(qt)  # type: ignore[arg-type]
    menu_renderer._menu_stack.clear()
    menu_renderer.push_menu("Journey Builder")
    try:
        result = menu_renderer.collect_journey_steps()
        assert isinstance(result, int)
        assert result == menu_renderer.BACK_JOURNEY
    finally:
        menu_renderer._reset_menu_stack()
        from src.cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)


def test_collect_journey_step_type_back_returns_to_builder_loop() -> None:
    """B inside the step-type picker continues the builder loop; Done then
    finishes normally with an empty step list (explicit build, nothing added)."""
    # 1=Build journey → 1=Add step → b=Back on step type → 2=Done
    inputs = ["1", "1", "b", "2"]
    qt = QueueTerminal(inputs=inputs)
    menu_renderer.set_terminal_adapter(qt)  # type: ignore[arg-type]
    menu_renderer._menu_stack.clear()
    menu_renderer.push_menu("Journey Builder")
    try:
        result = menu_renderer.collect_journey_steps()
        assert isinstance(result, list)
        assert result == []
    finally:
        menu_renderer._reset_menu_stack()
        from src.cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)


def test_auth_wrapper_preserves_profile_on_back() -> None:
    """main.py's auth wrapper keeps the existing credential profile when the
    user backs out instead of clearing it (pre-fix regression)."""
    from src.cli import main as cli_main
    from src.journey_scraper import CredentialProfile

    session = cli_main.create_session()  # type: ignore[call-arg]
    session.credential_profile = CredentialProfile(label="Std", username="u", password="p")
    monkey_back = menu_renderer.BACK_AUTH
    # Bypass interactive collection: simulate a Back result directly.
    orig = cli_main.collect_authentication
    cli_main.collect_authentication = lambda: monkey_back  # type: ignore[assignment]
    try:
        cli_main._collect_authentication_inline_inner(session)
    finally:
        cli_main.collect_authentication = orig  # type: ignore[assignment]
    assert session.credential_profile is not None
    assert session.credential_profile.label == "Std"


def test_journey_wrapper_preserves_steps_on_partial_back() -> None:
    """main.py's journey wrapper keeps the existing journey when the builder
    is backed out of mid-build instead of overwriting it with partial steps."""
    from src.cli import main as cli_main

    session = cli_main.create_session()  # type: ignore[call-arg]
    from src.journey_scraper import JourneyStep

    session.journey_steps = [JourneyStep(action="navigate", url="https://x.example/")]
    orig = cli_main.collect_journey_steps
    cli_main.collect_journey_steps = lambda: menu_renderer.BACK_JOURNEY  # type: ignore[assignment]
    try:
        cli_main._collect_journey_inline_inner(session)
    finally:
        cli_main.collect_journey_steps = orig  # type: ignore[assignment]
    assert len(session.journey_steps) == 1
    assert session.journey_steps[0].action == "navigate"
