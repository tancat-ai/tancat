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
