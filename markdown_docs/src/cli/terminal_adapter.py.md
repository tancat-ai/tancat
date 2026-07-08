# `src/cli/terminal_adapter.py` — Terminal Abstraction

## Purpose

Centralises TTY/PTY handling for key reading and buffer flushing. Provides a single `terminal` module-level instance used by CLI code, making TTY interaction testable via `QueueTerminal`.

## Class: `TerminalAdapter`

### `running_in_git_bash() -> bool`

Detects Git Bash (MINGW64) via `MSYSTEM` or `MSYS_WINVERSION` environment variables. In Git Bash, `msvcrt` functions don't work — must use `select`-based fallback.

### `flush() -> None`

Drains residual keystrokes from `msvcrt` buffer (up to 10 pending chars via `kbhit`/`getwch`). No-ops in Git Bash.

### `read_key() -> str`

Platform-aware single keypress reader:

**Windows (native):**
- Uses `msvcrt.getwch()`
- Detects arrow keys via `\x00`/`\xe0` prefix + `H` (Up → `^`) / `P` (Down → `v`)
- Falls back to `sys.stdin.read(1)`

**Git Bash:**
- Uses `_read_key_git_bash()` — threaded `select`-based byte-level read
- Fast path: direct `sys.stdin.readline()` (works for StringIO tests and piped input)
- Slow path: background thread with `os.read()` and 0.5s select timeout, 3s total timeout

### `_read_key_git_bash() -> str`

Threaded key reader for Git Bash. Collects bytes from stdin, handles escape sequences (`\x1b[`), and returns normalised key tokens.

### `_normalize_git_bash_input(raw: str) -> str`

Normalises raw input:
- `\r`, `\n`, `\r\n` → `\r`
- `\x1b[A` → `^` (Up arrow)
- `\x1b[B` → `v` (Down arrow)
- `\x1bOA` / `\x1bOB` → `^` / `v` (alternate arrow key sequences)

## Module-Level Instance

```python
terminal = TerminalAdapter()
```

Singleton used by `menu_renderer.py`. Can be replaced via `set_terminal_adapter()` for testing.
