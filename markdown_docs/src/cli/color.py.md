# `src/cli/color.py` — ANSI Colour Helpers

## Purpose

Wraps text in ANSI colour codes when stdout is a terminal (`os.isatty(1)`); falls back to plain text when piped or redirected.

## Internal Helper

### `_c(text: str, code: str) -> str`

Wraps text with `\033[{code}m{text}\033[0m` only when stdout is a TTY.

## Standard Colours

| Function | ANSI Code | Description |
|----------|-----------|-------------|
| `cyan(text)` | `36` | Bright cyan |
| `green(text)` | `32` | Green |
| `red(text)` | `31` | Red |
| `yellow(text)` | `33` | Yellow |
| `bold(text)` | `1` | Bold |

## Retro (CHOICE-style) Phosphor Colours

| Function | ANSI Code | Usage |
|----------|-----------|-------|
| `phosphor_green(text)` | `100` | Bright green — selected/highlighted menu items |
| `dim_green(text)` | `2;32` | Dim/half-bright green — non-selected items |
| `inverse_green(text)` | `7;32` | Inverse video — green background, black text — the `>` cursor |
| `phosphor_reset()` | — | Returns `\033[0m` reset code as standalone string |

## Design Patterns

- **Conditional formatting**: All colours are no-ops when piped — prevents ANSI codes in redirected output.
- **Retro terminal aesthetic**: Phosphor colours match the CHOICE-style retro UI in `retro_ui.py`.
