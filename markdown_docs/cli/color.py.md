# cli/color.py

## Purpose

ANSI color helper functions for CLI output. Wraps text in ANSI escape codes when stdout is a TTY and falls back to plain text otherwise.

## Public functions

- `_c(text: str, code: str) -> str`
  - Internal helper that applies an ANSI color code when stdout is a terminal.

- `cyan(text: str) -> str`
- `green(text: str) -> str`
- `red(text: str) -> str`
- `yellow(text: str) -> str`
- `bold(text: str) -> str`

- `phosphor_green(text: str) -> str`
  - Bright green used for selected/highlighted menu items.

- `dim_green(text: str) -> str`
  - Dim green used for non-selected items.

- `inverse_green(text: str) -> str`
  - Inverse-video green used for the cursor indicator.

- `phosphor_reset() -> str`
  - Returns the ANSI reset code as a standalone string.

## Notes

- Uses `os.isatty(1)` to detect terminal output.
- Catches exceptions to avoid failure when stdout is redirected or not available.
