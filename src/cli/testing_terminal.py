"""Testing terminal adapter: queue-based inputs for automated tests.

Use `QueueTerminal(inputs)` where `inputs` is an iterable of strings
that `read_key()` will return in order. Useful for headless tests that
need to drive interactive menus without a PTY.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.cli.terminal_adapter import TerminalAdapter


class QueueTerminal(TerminalAdapter):
    def __init__(self, inputs: Iterable[str] | None = None, git_bash: bool = False):
        self._queue: list[str] = list(inputs or [])
        self._git = git_bash

    def running_in_git_bash(self) -> bool:
        return bool(self._git)

    def flush(self) -> None:
        # no-op for testing terminal
        return None

    def read_key(self) -> str:
        if not self._queue:
            return ""
        return self._queue.pop(0)

    def push(self, value: str) -> None:
        self._queue.append(value)

    def extend(self, values: Iterable[str]) -> None:
        self._queue.extend(values)
