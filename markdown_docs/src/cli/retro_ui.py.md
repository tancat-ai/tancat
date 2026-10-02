# `src/cli/retro_ui.py` — CHOICE-Style Retro Terminal UI

## Purpose

Renders green-on-black, box-drawing menus reminiscent of the classic CHOICE mainframe menu system. Cross-platform using ANSI escape codes — no curses dependency.

## Screen Management

| Function | Description |
|----------|-------------|
| `clear_screen()` | Clears terminal (`\033[H\033[J`) or writes `=` separator when piped |
| `move_cursor(x, y)` | Absolute cursor positioning (`\033[{y};{x}H`) |
| `hide_cursor()` | Hides terminal cursor (`\033[?25l`) |
| `show_cursor()` | Shows terminal cursor (`\033[?25h`) |

All functions detect TTY vs pipe — non-TTY output uses fallback separators for CI readability.

## Box Drawing

### `_BoxChars` dataclass

Unicode box-drawing characters: `┌`, `┐`, `└`, `┘`, `─`, `│`, `┤`, `├`, `┬`, `┴`, `┼`.

### `_color_line(line, bright=False) -> str`

Applies green ANSI colour to an entire line. Wraps the full line in one ANSI pair to avoid per-character escapes breaking border alignment.

### `_visible_len(text) -> int`

Strips ANSI escapes and returns visible character length.

### Width helpers

| Function | Description |
|----------|-------------|
| `_terminal_width()` | Actual terminal width (default 78) |
| `_effective_width()` | Usable width minus 2-column border margin (min 40) |

## Colour Helpers

| Function | ANSI Code | Usage |
|----------|-----------|-------|
| `_green(text, bright=False)` | `32` / `1;32` | Standard / bold green |
| `_dim(text)` | `2` | Half-bright |
| `_bold(text)` | `1` | Bold |
| `_inverse(text)` | `7;32` | Inverse video (green bg, black fg) |

## Public API

### `render_header(title, subtitle="") -> None`

Renders a CHOICE-style header box with title and optional subtitle:
```
┌─────────────────────────────────────────────────────────────┐
│  AI PLAYWRIGHT TEST GENERATOR                              │
│  Generate Playwright tests from user stories with AI       │
├─────────────────────────────────────────────────────────────┤
```

### `render_menu(items, selected=0, group_labels=None) -> None`

Renders numbered menu items with `>` selection indicator. Selected item in inverse video + bright green; others in standard green.

### `render_state(state_lines) -> None`

Renders dim green key-value state summary (e.g., `LLM : ollama / qwen3.5:35b`).

### `render_shortcut_bar(shortcuts) -> None`

Renders a bottom shortcut bar with `[key]label` pairs, truncated to fit terminal width.

### `render_separator() -> None`

Horizontal rule inside a box: `│─────────────────────────────────────│`

### `render_status_bar(message, shortcuts=None) -> None`

Full screen wrapper: header + message + shortcut bar.

## Text Input

### `prompt_input(prompt_text, default="") -> str`

Retro-styled input prompt. Returns `default` on empty input.

### `prompt_non_empty(prompt_text) -> str`

Like `prompt_input` but rejects empty values with a retry loop.

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `render_shortcuts` (function): `render_shortcuts(entries: list[tuple[str, str]]) -> None` - Render a bottom row of key-action "buttons" in green box-drawing. Each entry is a (key, label) pair rendered as an [key] Label button. Buttons flow horizontally and wrap to additional lines when they do not fi...
- `BOX` (constant): `BOX = _BoxChars()`


## How It Works (Internals)

Private `_`-helpers - the module's real logic (5 items). Grouped under the public function that calls them.

### `render_header(title: str, subtitle: str = '') -> None` - function

- `_visible_len(text: str) -> int` (function): Return visible character length, stripping ANSI escape sequences.
- `_green(text: str, bright: bool = False) -> str` (function): Apply green ANSI colour. *bright=True* -> ANSI 1;32 (bold green - more portable than 100) *bright=False* -> ANSI 32 (standard green) Falls back to plain text when stdout is not a tty.

### `render_shortcuts(entries: list[tuple[str, str]]) -> None` - function

- `_shortcut_button_rows(entries: list[tuple[str, str]], usable: int) -> list[str]` (function): Lay out [key] Label buttons into rows that fit *usable* columns. Buttons are packed greedily onto each row and wrapped to the next row when the next button would not fit. A row is never wider than *usable*.

### Internal utilities

- `_truncate_middle(text: str, max_len: int) -> str` (function): Truncate *text* to *max_len* visible chars, keeping the start readable. Preserves the tail when the result is shorter than *max_len* (i.e. the full text fits) so nothing is lost. Only shrinks when genuinely too wide.
- `_terminal_width() -> int` (function): Return the terminal width, defaulting to 78 if undetectable.
