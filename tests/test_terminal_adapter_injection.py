from cli import menu_renderer


class DummyTerminal:
    def __init__(self, git_bash: bool = False) -> None:
        self._git = git_bash

    def running_in_git_bash(self) -> bool:
        return self._git

    def flush(self) -> None:
        pass

    def read_key(self) -> str:
        return ""


def test_set_terminal_adapter_injection() -> None:
    dummy = DummyTerminal(git_bash=True)
    menu_renderer.set_terminal_adapter(dummy)  # type: ignore[arg-type]
    try:
        assert menu_renderer._running_in_git_bash() is True
    finally:
        # restore canonical terminal adapter so other tests see real environment
        from cli import terminal_adapter

        menu_renderer.set_terminal_adapter(terminal_adapter.terminal)  # type: ignore[arg-type]
