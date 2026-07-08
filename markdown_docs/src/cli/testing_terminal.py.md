# `src/cli/testing_terminal.py` — Testing Terminal Adapter

## Purpose

Queue-based terminal input for automated tests. Allows headless tests to drive interactive menus without a PTY.

## Class: `QueueTerminal(TerminalAdapter)`

Extends `TerminalAdapter` with a simple string queue.

### `__init__(inputs=None, git_bash=False)`

| Parameter | Description |
|-----------|-------------|
| `inputs` | Iterable of strings — `read_key()` returns them in order |
| `git_bash` | If `True`, simulates Git Bash environment |

### `read_key() -> str`

Pops and returns the first item from the queue. Returns `""` when empty.

### `push(value: str) -> None`

Appends a single value to the queue (for mid-test injection).

### `extend(values: Iterable[str]) -> None`

Extends the queue with multiple values.

### `flush() -> None`

No-op (no actual terminal buffer to flush).

## Usage

```python
from src.cli.terminal_adapter import terminal
from src.cli.testing_terminal import QueueTerminal
from src.cli.menu_renderer import set_terminal_adapter

adapter = QueueTerminal(inputs=["\n", "1", "\r", "Q"])
set_terminal_adapter(adapter)
# Now interactive menus will consume from the queue
```
